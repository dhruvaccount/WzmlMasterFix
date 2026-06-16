import os
import re
from asyncio import Queue, create_task, gather, sleep
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath
from time import time

from pyrogram import StopTransmission, raw
from pyrogram.errors import FilePartMissing, FloodPremiumWait, FloodWait
from pyrogram.session import Session

from ... import LOGGER
from ..telegram_helper.tg_transfer import HypertgTransfer, MB

KB = 1024
PART_SIZE = 512 * KB


class HypertgUpload(HypertgTransfer):
    def __init__(self, obj):
        super().__init__(obj)
        self._up_start = 0
        self._up_file = ""
        self._up_size = 0
        LOGGER.info("HypertgUpload initialized")

    @staticmethod
    def _parse_missing_part(exc):
        val = getattr(exc, "value", None)
        if isinstance(val, int):
            LOGGER.debug(f"HypertgUL parse_part from value={val}")
            return val
        m = re.search(r"Part (\d+)", str(exc))
        if m:
            part = int(m.group(1))
            LOGGER.debug(f"HypertgUL parse_part from str={part}")
            return part
        LOGGER.warning(f"HypertgUL parse_part fallback=0 exc={exc}")
        return 0

    def _build_media(self, input_file, mime_type, media_type, attributes, thumb_file=None):
        LOGGER.debug(
            f"HypertgUL build_media type={media_type} mime={mime_type} "
            f"attrs={len(attributes or [])} thumb={thumb_file is not None}"
        )
        if media_type == "photo":
            return raw.types.InputMediaUploadedPhoto(file=input_file)
        return raw.types.InputMediaUploadedDocument(
            file=input_file,
            thumb=thumb_file,
            mime_type=mime_type or "application/octet-stream",
            attributes=attributes or [],
            nosound_video=media_type == "video" and "video" in (mime_type or ""),
            force_file=media_type == "document",
        )

    async def _upload_file(self, client, file_path):
        t0 = time()
        file_size = ospath.getsize(file_path)
        file_total_parts = ceil(file_size / PART_SIZE)
        file_id = client.rnd_id()
        dc_id = await client.storage.dc_id()
        ak = await client.storage.auth_key()
        tm = await client.storage.test_mode()
        is_big = file_size > 10 * MB
        num_workers = 16 if is_big else 1

        LOGGER.info(
            f"HypertgUL upload {os.path.basename(file_path)} "
            f"({file_size / MB:.1f}MB {file_total_parts}p "
            f"{num_workers}w dc={dc_id} big={is_big})"
        )

        fp = open(file_path, "rb")
        LOGGER.info(f"HypertgUL sessions {num_workers} created (not started yet) dc={dc_id}")

        q = Queue(16)

        async def worker(_, wid):
            nonlocal fp
            my_session = Session(client, dc_id, ak, tm, is_media=True)
            await my_session.start()
            LOGGER.info(f"HypertgUL w{wid} session started dc={my_session.dc_id} connected={my_session.is_connected}")
            sent = 0
            failed = 0
            consec_err = 0
            LOGGER.info(f"HypertgUL w{wid} started dc={my_session.dc_id}")
            while True:
                data = await q.get()
                if data is None:
                    LOGGER.info(
                        f"HypertgUL w{wid} done dc={my_session.dc_id} "
                        f"ok={sent} fail={failed}"
                    )
                    await my_session.stop()
                    return
                for up_retry in range(3):
                    try:
                        await my_session.invoke(data)
                        sent += 1
                        consec_err = 0
                        break
                    except (TimeoutError, OSError, ConnectionError) as e:
                        failed += 1
                        consec_err += 1
                        LOGGER.warning(
                            f"HypertgUL w{wid} {type(e).__name__}: {e} "
                            f"dc={my_session.dc_id} ok={sent} fail={failed} "
                            f"consec={consec_err} retry={up_retry}"
                        )
                        if consec_err >= 3:
                            LOGGER.warning(
                                f"HypertgUL w{wid} reconnecting after {consec_err} errors"
                            )
                            try:
                                await my_session.stop()
                            except Exception:
                                pass
                            my_session = Session(client, dc_id, ak, tm, is_media=True)
                            await my_session.start()
                            LOGGER.info(f"HypertgUL w{wid} session reconnected dc={my_session.dc_id}")
                            consec_err = 0
                        await sleep(up_retry + 1)
                    except Exception as e:
                        failed += 1
                        LOGGER.warning(
                            f"HypertgUL w{wid} {type(e).__name__}: {e} "
                            f"dc={my_session.dc_id} ok={sent} fail={failed}"
                        )
                        break

        workers = [create_task(worker(None, wid)) for wid in range(num_workers)]
        LOGGER.info(f"HypertgUL {len(workers)} workers created")

        try:
            part = 0
            rpc_fn = raw.functions.upload.SaveBigFilePart if is_big else raw.functions.upload.SaveFilePart
            LOGGER.info(f"HypertgUL queuing {file_total_parts} parts rpc={rpc_fn.__name__}")

            while True:
                chunk = fp.read(PART_SIZE)
                if not chunk:
                    break
                rpc = rpc_fn(
                    file_id=file_id, file_part=part,
                    file_total_parts=file_total_parts, bytes=chunk,
                )
                await q.put(rpc)
                self._obj._processed_bytes += len(chunk)
                part += 1
                if part % 200 == 0 or part == file_total_parts:
                    LOGGER.info(f"HypertgUL queued {part}/{file_total_parts}")

            LOGGER.info(f"HypertgUL all parts queued, signaling workers")
            for _ in workers:
                await q.put(None)
            await gather(*workers)

            up_elapsed = time() - t0
            up_speed = file_size / up_elapsed / MB if up_elapsed > 0 else 0
            LOGGER.info(
                f"HypertgUL file done {os.path.basename(file_path)} "
                f"({file_size / MB:.1f}MB {file_total_parts}p "
                f"{num_workers}w {up_speed:.1f}MB/s {up_elapsed:.1f}s)"
            )

            if is_big:
                result = raw.types.InputFileBig(
                    id=file_id, parts=file_total_parts,
                    name=os.path.basename(file_path),
                )
            else:
                result = raw.types.InputFile(
                    id=file_id, parts=file_total_parts,
                    name=os.path.basename(file_path),
                )
            LOGGER.info(f"HypertgUL InputFile id={file_id} parts={file_total_parts} big={is_big}")
            return result
        except StopTransmission:
            LOGGER.warning("HypertgUL upload cancelled (StopTransmission)")
            raise
        except Exception as e:
            LOGGER.error(f"HypertgUL upload fail: {type(e).__name__}: {e}")
            raise
        finally:
            LOGGER.info("HypertgUL upload cleanup starting")
            for _ in workers:
                await q.put(None)
            await gather(*workers, return_exceptions=True)
            try:
                fp.close()
                LOGGER.info("HypertgUL file closed")
            except Exception:
                pass

    async def _upload_small(self, client, file_path):
        file_size = ospath.getsize(file_path)
        file_total_parts = ceil(file_size / PART_SIZE)
        file_id = client.rnd_id()
        dc_id = await client.storage.dc_id()
        ak = await client.storage.auth_key()
        tm = await client.storage.test_mode()
        s = Session(client, dc_id, ak, tm, is_media=False)
        fp = open(file_path, "rb")
        h = md5()

        LOGGER.info(
            f"HypertgUL small {os.path.basename(file_path)} "
            f"({file_size / MB:.1f}MB {file_total_parts}p dc={dc_id})"
        )

        try:
            await s.start()
            LOGGER.info(f"HypertgUL small session started dc={dc_id} connected={s.is_connected}")
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    LOGGER.warning("HypertgUL small cancelled")
                    raise StopTransmission()
                chunk = fp.read(PART_SIZE)
                if not chunk:
                    break
                h.update(chunk)
                await s.invoke(raw.functions.upload.SaveFilePart(
                    file_id=file_id, file_part=part, bytes=chunk,
                ))
                self._obj._processed_bytes += len(chunk)
                if (part + 1) % 50 == 0 or part + 1 == file_total_parts:
                    LOGGER.info(f"HypertgUL small sent {part + 1}/{file_total_parts}")
            LOGGER.info(f"HypertgUL small done {os.path.basename(file_path)}")
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=os.path.basename(file_path), md5_checksum=h.hexdigest(),
            )
        finally:
            try:
                await s.stop()
                LOGGER.info("HypertgUL small session stopped")
            except Exception as e:
                LOGGER.warning(f"HypertgUL small stop err: {e}")
            fp.close()

    async def _upload_thumb(self, client, file_path):
        file_size = ospath.getsize(file_path)
        file_id = client.rnd_id()
        file_total_parts = ceil(file_size / PART_SIZE)
        fp = open(file_path, "rb")
        h = md5()

        LOGGER.info(f"HypertgUL thumb {os.path.basename(file_path)} ({file_size / KB:.1f}KB)")

        try:
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    raise StopTransmission()
                chunk = fp.read(PART_SIZE)
                if not chunk:
                    break
                h.update(chunk)
                await client.invoke(raw.functions.upload.SaveFilePart(
                    file_id=file_id, file_part=part, bytes=chunk,
                ))
                self._obj._processed_bytes += len(chunk)
            LOGGER.info(f"HypertgUL thumb done {os.path.basename(file_path)}")
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=os.path.basename(file_path), md5_checksum=h.hexdigest(),
            )
        finally:
            fp.close()

    async def _reupload_part(self, client, file_path, input_file, part_num):
        offset = part_num * PART_SIZE
        LOGGER.info(f"HypertgUL reupload part={part_num} offset={offset}")
        fp = open(file_path, "rb")
        try:
            fp.seek(offset)
            chunk = fp.read(PART_SIZE)
            if not chunk:
                LOGGER.warning(f"HypertgUL reupload part={part_num} empty")
                return
            if isinstance(input_file, raw.types.InputFileBig):
                rpc = raw.functions.upload.SaveBigFilePart(
                    file_id=input_file.id, file_part=part_num,
                    file_total_parts=input_file.parts, bytes=chunk,
                )
            else:
                rpc = raw.functions.upload.SaveFilePart(
                    file_id=input_file.id, file_part=part_num, bytes=chunk,
                )
            await client.invoke(rpc)
            LOGGER.info(f"HypertgUL reupload part={part_num} ok")
        except Exception as e:
            LOGGER.error(f"HypertgUL reupload part={part_num} fail: {type(e).__name__}: {e}")
        finally:
            fp.close()

    async def upload(
        self, target_client, target_chat_id, file_path, dump_chat_id,
        media_type, attributes, thumb_path=None, caption="", reply_to_message_id=None,
    ):
        self._cancel.clear()
        self._obj._processed_bytes = 0
        self._up_start = time()
        self._up_file = os.path.basename(file_path)
        self._up_size = ospath.getsize(file_path)

        LOGGER.info(
            f"HypertgUL start {self._up_file} "
            f"({self._up_size / MB:.1f}MB) -> chat={target_chat_id} "
            f"type={media_type}"
        )

        t_phase = time()
        if self._up_size > 10 * MB:
            LOGGER.info(f"HypertgUL phase=file_upload start (big) {self._up_file}")
            input_file = await self._upload_file(target_client, file_path)
        else:
            LOGGER.info(f"HypertgUL phase=file_upload start (small) {self._up_file}")
            input_file = await self._upload_small(target_client, file_path)
        LOGGER.info(
            f"HypertgUL phase=file_upload done {self._up_file} "
            f"({time() - t_phase:.1f}s)"
        )

        t_phase = time()
        thumb_file = None
        if thumb_path and ospath.exists(thumb_path) and ospath.getsize(thumb_path) > 0:
            LOGGER.info(f"HypertgUL phase=thumb start {thumb_path}")
            thumb_file = await self._upload_thumb(target_client, thumb_path)
        else:
            LOGGER.info(f"HypertgUL phase=thumb skip (no thumb)")
        LOGGER.info(f"HypertgUL phase=thumb done ({time() - t_phase:.1f}s)")

        mime_type = self._mime(file_path)
        input_media = self._build_media(input_file, mime_type, media_type, attributes, thumb_file)

        peer = await target_client.resolve_peer(target_chat_id)
        LOGGER.info(f"HypertgUL phase=SendMedia peer resolved chat={target_chat_id}")
        rpc = raw.functions.messages.SendMedia(
            peer=peer, media=input_media, message=caption or "",
            random_id=target_client.rnd_id(),
            reply_to=raw.types.InputReplyToMessage(reply_to_msg_id=reply_to_message_id)
            if reply_to_message_id else None,
            silent=True,
        )

        t_phase = time()
        LOGGER.info(f"HypertgUL phase=SendMedia start {self._up_file}")
        r_updates = None
        send_retries = 0
        missing_fixed = 0
        while True:
            try:
                LOGGER.info(
                    f"HypertgUL SendMedia attempt {send_retries + 1} "
                    f"{self._up_file} (fixed {missing_fixed} missing parts so far)"
                )
                r_updates = await target_client.invoke(rpc)
                LOGGER.info(f"HypertgUL SendMedia success {self._up_file}")
                break
            except FilePartMissing as e:
                part = self._parse_missing_part(e)
                missing_fixed += 1
                LOGGER.warning(
                    f"HypertgUL SendMedia missing part {part} "
                    f"(fixed {missing_fixed}) {self._up_file}"
                )
                await self._reupload_part(target_client, file_path, input_file, part)
                send_retries += 1
                if send_retries >= 100:
                    raise RuntimeError(f"SendMedia exhausted after fixing {missing_fixed} missing parts")
            except (FloodWait, FloodPremiumWait) as e:
                val = e.value if hasattr(e, "value") else 5
                send_retries += 1
                LOGGER.warning(
                    f"HypertgUL SendMedia flood {val}s "
                    f"(retry {send_retries}) {self._up_file}"
                )
                if send_retries >= 10:
                    raise
                await sleep(val + 1)
            except Exception as e:
                send_retries += 1
                LOGGER.error(
                    f"HypertgUL SendMedia {type(e).__name__}: {e} "
                    f"(retry {send_retries}) {self._up_file}"
                )
                if send_retries >= 10:
                    raise
        LOGGER.info(f"HypertgUL phase=SendMedia done ({time() - t_phase:.1f}s)")

        msg_id = None
        for u in r_updates.updates:
            if isinstance(u, (raw.types.UpdateNewMessage, raw.types.UpdateNewChannelMessage, raw.types.UpdateNewScheduledMessage)):
                msg_id = u.message.id
                LOGGER.debug(f"HypertgUL msg_id={msg_id} from {type(u).__name__}")
                break
        if msg_id is None:
            LOGGER.error(f"HypertgUL no UpdateNewMessage in response updates={r_updates.updates}")
            raise ValueError("No UpdateNewMessage in SendMedia response")

        total_elapsed = time() - self._up_start
        total_speed = self._up_size / total_elapsed / MB if total_elapsed > 0 else 0
        LOGGER.info(
            f"HypertgUL done {self._up_file} "
            f"({self._up_size / MB:.1f}MB {total_speed:.1f}MB/s {total_elapsed:.1f}s) "
            f"msg_id={msg_id}"
        )

        msg = await target_client.get_messages(chat_id=target_chat_id, message_ids=msg_id)
        LOGGER.info(f"HypertgUL msg fetched id={msg_id}")
        return msg

    @staticmethod
    def _mime(path):
        m, _ = guess_type(path)
        mime = m or "application/octet-stream"
        LOGGER.debug(f"HypertgUL mime {path} -> {mime}")
        return mime
