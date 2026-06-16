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

    @staticmethod
    def _parse_missing_part(exc):
        val = getattr(exc, "value", None)
        if isinstance(val, int):
            return val
        m = re.search(r"Part (\d+)", str(exc))
        if m:
            return int(m.group(1))
        return 0

    def _build_media(self, input_file, mime_type, media_type, attributes, thumb_file=None):
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
        pool_size = 3 if is_big else 1
        workers_count = 4 if is_big else 1

        LOGGER.info(
            f"HypertgUL upload {os.path.basename(file_path)} "
            f"({file_size / MB:.1f}MB {file_total_parts}p "
            f"{pool_size}x{workers_count}w dc={dc_id})"
        )

        fp = open(file_path, "rb")
        pool = [
            Session(client, dc_id, ak, tm, is_media=True)
            for _ in range(pool_size)
        ]

        async def worker(session, wid):
            sent = 0
            failed = 0
            while True:
                data = await q.get()
                if data is None:
                    if sent > 0 or failed > 0:
                        LOGGER.info(
                            f"HypertgUL w{wid} done dc={session.dc_id} "
                            f"ok={sent} fail={failed}"
                        )
                    return
                try:
                    await session.invoke(data)
                    sent += 1
                except Exception as e:
                    failed += 1
                    LOGGER.warning(
                        f"HypertgUL w{wid} {type(e).__name__}: {e} "
                        f"dc={session.dc_id}"
                    )

        q = Queue(16)
        workers = [
            create_task(worker(session, wid))
            for wid, session in enumerate(pool)
            for _ in range(workers_count)
        ]

        try:
            for session in pool:
                await session.start()

            part = 0
            rpc_fn = raw.functions.upload.SaveBigFilePart if is_big else raw.functions.upload.SaveFilePart

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

            for _ in workers:
                await q.put(None)
            await gather(*workers)

            up_elapsed = time() - t0
            up_speed = file_size / up_elapsed / MB if up_elapsed > 0 else 0
            LOGGER.info(
                f"HypertgUL file done {os.path.basename(file_path)} "
                f"({file_size / MB:.1f}MB {file_total_parts}p "
                f"{pool_size}x{workers_count}w {up_speed:.1f}MB/s {up_elapsed:.1f}s)"
            )

            if is_big:
                return raw.types.InputFileBig(
                    id=file_id, parts=file_total_parts,
                    name=os.path.basename(file_path),
                )
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=os.path.basename(file_path),
            )
        except StopTransmission:
            raise
        except Exception as e:
            LOGGER.error(f"HypertgUL upload fail: {e}")
            raise
        finally:
            for _ in workers:
                await q.put(None)
            await gather(*workers, return_exceptions=True)
            for session in pool:
                try:
                    await session.stop()
                except Exception:
                    pass
            try:
                fp.close()
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

        try:
            await s.start()
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    raise StopTransmission()
                chunk = fp.read(PART_SIZE)
                if not chunk:
                    break
                h.update(chunk)
                await s.invoke(raw.functions.upload.SaveFilePart(
                    file_id=file_id, file_part=part, bytes=chunk,
                ))
                self._obj._processed_bytes += len(chunk)
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=os.path.basename(file_path), md5_checksum=h.hexdigest(),
            )
        finally:
            try:
                await s.stop()
            except Exception:
                pass
            fp.close()

    async def _upload_thumb(self, client, file_path):
        file_size = ospath.getsize(file_path)
        file_id = client.rnd_id()
        file_total_parts = ceil(file_size / PART_SIZE)
        fp = open(file_path, "rb")
        h = md5()

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
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=os.path.basename(file_path), md5_checksum=h.hexdigest(),
            )
        finally:
            fp.close()

    async def _reupload_part(self, client, file_path, input_file, part_num):
        offset = part_num * PART_SIZE
        fp = open(file_path, "rb")
        try:
            fp.seek(offset)
            chunk = fp.read(PART_SIZE)
            if not chunk:
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
            f"({self._up_size / MB:.1f}MB) -> chat={target_chat_id}"
        )

        t_phase = time()
        input_file = (
            await self._upload_file(target_client, file_path)
            if self._up_size > 10 * MB
            else await self._upload_small(target_client, file_path)
        )
        LOGGER.info(
            f"HypertgUL phase=file_upload done {self._up_file} "
            f"({time() - t_phase:.1f}s)"
        )

        t_phase = time()
        thumb_file = None
        if thumb_path and ospath.exists(thumb_path) and ospath.getsize(thumb_path) > 0:
            thumb_file = await self._upload_thumb(target_client, thumb_path)
        LOGGER.info(f"HypertgUL phase=thumb done ({time() - t_phase:.1f}s)")

        mime_type = self._mime(file_path)
        input_media = self._build_media(input_file, mime_type, media_type, attributes, thumb_file)

        peer = await target_client.resolve_peer(target_chat_id)
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
        for attempt in range(5):
            try:
                LOGGER.info(
                    f"HypertgUL SendMedia attempt {attempt + 1}/5 "
                    f"{self._up_file}"
                )
                r_updates = await target_client.invoke(rpc)
                LOGGER.info(f"HypertgUL SendMedia success {self._up_file}")
                break
            except FilePartMissing as e:
                part = self._parse_missing_part(e)
                LOGGER.warning(
                    f"HypertgUL SendMedia missing part {part} "
                    f"(attempt {attempt + 1}/5) {self._up_file}"
                )
                await self._reupload_part(target_client, file_path, input_file, part)
            except (FloodWait, FloodPremiumWait) as e:
                val = e.value if hasattr(e, "value") else 5
                LOGGER.warning(
                    f"HypertgUL SendMedia flood {val}s "
                    f"(attempt {attempt + 1}/5) {self._up_file}"
                )
                if attempt == 4:
                    raise
                await sleep(val + 1)
        LOGGER.info(f"HypertgUL phase=SendMedia done ({time() - t_phase:.1f}s)")

        for u in r_updates.updates:
            if isinstance(u, (raw.types.UpdateNewMessage, raw.types.UpdateNewChannelMessage, raw.types.UpdateNewScheduledMessage)):
                msg_id = u.message.id
                break
        else:
            raise ValueError("No UpdateNewMessage in SendMedia response")

        total_elapsed = time() - self._up_start
        total_speed = self._up_size / total_elapsed / MB if total_elapsed > 0 else 0
        LOGGER.info(
            f"HypertgUL done {self._up_file} "
            f"({self._up_size / MB:.1f}MB {total_speed:.1f}MB/s {total_elapsed:.1f}s) "
            f"msg_id={msg_id}"
        )

        return await target_client.get_messages(chat_id=target_chat_id, message_ids=msg_id)

    @staticmethod
    def _mime(path):
        m, _ = guess_type(path)
        return m or "application/octet-stream"
