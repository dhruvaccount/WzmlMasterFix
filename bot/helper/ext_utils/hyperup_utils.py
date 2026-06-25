import asyncio
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath
from re import search as research

from pyrogram import StopTransmission, raw, utils
from pyrogram.errors import FilePartMissing, FloodPremiumWait, FloodWait, UserMigrate
from pyrogram.session import Session

from ... import LOGGER
from ..telegram_helper.tg_transfer import MB, HypertgTransfer

KB = 1024
PART_SIZE = 512 * KB
WORKERS_PER_SESSION = 4


class HypertgUpload(HypertgTransfer):
    def __init__(self, obj):
        super().__init__(obj)
        self._up_file = ""
        self._up_size = 0

    @staticmethod
    def _parse_missing_part(exc):
        val = getattr(exc, "value", None)
        if isinstance(val, int):
            return val
        m = research(r"Part (\d+)", str(exc))
        if m:
            return int(m.group(1))
        LOGGER.warning(f"HypertgUL parse_part fallback=0 exc={exc}")
        return 0

    def _build_media(
        self, input_file, mime_type, media_type, attributes, thumb_file=None
    ):
        if media_type == "photo":
            return raw.types.InputMediaUploadedPhoto(file=input_file)
        if media_type == "video":
            mime_type = "video/mp4"
        elif media_type == "audio":
            if mime_type == "audio/ogg":
                mime_type = "audio/opus"
            else:
                mime_type = "audio/mpeg"
        else:
            mime_type = "application/octet-stream"
        return raw.types.InputMediaUploadedDocument(
            file=input_file,
            thumb=thumb_file,
            mime_type=mime_type,
            attributes=attributes or [],
            force_file=media_type == "document",
        )

    async def _upload_file(self, client, file_path):
        import time as _time
        _t0 = _time.monotonic()
        file_size = ospath.getsize(file_path)
        file_total_parts = ceil(file_size / PART_SIZE)
        file_id = client.rnd_id()
        dc_id = await client.storage.dc_id()
        is_big = file_size > 10 * MB

        n_sessions = 4
        n_workers = n_sessions * WORKERS_PER_SESSION
        q = asyncio.Queue(64)
        fp = open(file_path, "rb")

        async def _make_session():
            return await self._mk_session(client, dc_id, mode=1)

        pool = [await _make_session() for _ in range(n_sessions)]

        def _make_rpc(chunk, part_idx):
            if is_big:
                return raw.functions.upload.SaveBigFilePart(
                    file_id=file_id, file_part=part_idx,
                    file_total_parts=file_total_parts, bytes=chunk,
                )
            return raw.functions.upload.SaveFilePart(
                file_id=file_id, file_part=part_idx, bytes=chunk,
            )

        async def _worker(wid, session):
            nonlocal dc_id
            completed = 0
            while True:
                data = await q.get()
                try:
                    if data is None:
                        return
                    chunk, part_idx = data
                    rpc = _make_rpc(chunk, part_idx)
                    for attempt in range(5):
                        try:
                            await session.invoke(rpc)
                            completed += 1
                            break
                        except UserMigrate as e:
                            nd = getattr(e, "value", None)
                            if not isinstance(nd, int):
                                raise
                            LOGGER.info(
                                f"HypertgUL worker {wid} migrate DC {dc_id}→{nd}"
                            )
                            dc_id = nd
                            await client.storage.dc_id(nd)
                            await session.stop()
                            session = await _make_session()
                        except StopTransmission:
                            raise
                        except asyncio.CancelledError:
                            return
                        except (OSError, TimeoutError, ConnectionError):
                            LOGGER.warning(
                                f"HypertgUL worker {wid} transport "
                                f"attempt {attempt + 1}/5"
                            )
                            if attempt == 4:
                                raise
                            try:
                                await session.stop()
                            except Exception:
                                pass
                            session = await _make_session()
                            await asyncio.sleep(1)
                        except Exception:
                            if attempt == 4:
                                raise
                            await asyncio.sleep(2**attempt)
                finally:
                    q.task_done()

        workers = [
            asyncio.create_task(_worker(i, pool[i % n_sessions]))
            for i in range(n_workers)
        ]

        LOGGER.info(
            f"HypertgUL start "
            f"fp={ospath.basename(file_path)} parts={file_total_parts} "
            f"workers={n_workers} sessions={n_sessions}"
        )

        try:
            parts_sent = 0
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    raise StopTransmission()
                chunk = await asyncio.to_thread(fp.read, PART_SIZE)
                if not chunk:
                    break
                if all(t.done() for t in workers):
                    for t in workers:
                        exc = t.exception()
                        if exc is not None:
                            raise exc
                    raise RuntimeError("All upload workers exited")
                await q.put((chunk, part))
                parts_sent += 1

                if parts_sent > 0 and parts_sent % max(1, file_total_parts // 10) == 0:
                    elapsed = _time.monotonic() - _t0
                    mb_done = parts_sent * PART_SIZE / (1024 * 1024)
                    mb_total = file_size / (1024 * 1024)
                    LOGGER.info(
                        f"HypertgUL {ospath.basename(file_path)} "
                        f"part={parts_sent}/{file_total_parts} "
                        f"MB={mb_done:.0f}/{mb_total:.0f} "
                        f"speed={mb_done/elapsed:.1f}MB/s"
                    )
                self._obj._processed_bytes = min(
                    parts_sent * PART_SIZE, file_size
                )

            await q.join()
            for _ in workers:
                await q.put(None)
            await asyncio.gather(*workers)
            self._obj._processed_bytes = file_size

            elapsed = _time.monotonic() - _t0
            LOGGER.info(
                f"HypertgUL done {ospath.basename(file_path)} "
                f"elapsed={elapsed:.1f}s speed={file_size/(1024*1024)/elapsed:.1f}MB/s"
            )

            if is_big:
                return raw.types.InputFileBig(
                    id=file_id, parts=file_total_parts,
                    name=ospath.basename(file_path),
                )
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=ospath.basename(file_path),
                md5_checksum=md5().hexdigest(),
            )
        except StopTransmission:
            LOGGER.warning("HypertgUL upload cancelled")
            raise
        except Exception as e:
            LOGGER.error(f"HypertgUL upload fail: {type(e).__name__}: {e}")
            raise
        finally:
            for t in workers:
                t.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            for s in pool:
                try:
                    await s.stop()
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
                await s.invoke(
                    raw.functions.upload.SaveFilePart(
                        file_id=file_id,
                        file_part=part,
                        bytes=chunk,
                    )
                )
                self._obj._processed_bytes += len(chunk)
            return raw.types.InputFile(
                id=file_id,
                parts=file_total_parts,
                name=ospath.basename(file_path),
                md5_checksum=h.hexdigest(),
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
                await client.invoke(
                    raw.functions.upload.SaveFilePart(
                        file_id=file_id,
                        file_part=part,
                        bytes=chunk,
                    )
                )
                self._obj._processed_bytes += len(chunk)
            return raw.types.InputFile(
                id=file_id,
                parts=file_total_parts,
                name=ospath.basename(file_path),
                md5_checksum=h.hexdigest(),
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
                LOGGER.warning(f"HypertgUL reupload part={part_num} empty")
                return
            if isinstance(input_file, raw.types.InputFileBig):
                rpc = raw.functions.upload.SaveBigFilePart(
                    file_id=input_file.id,
                    file_part=part_num,
                    file_total_parts=input_file.parts,
                    bytes=chunk,
                )
            else:
                rpc = raw.functions.upload.SaveFilePart(
                    file_id=input_file.id,
                    file_part=part_num,
                    bytes=chunk,
                )
            await client.invoke(rpc)
        except Exception as e:
            LOGGER.error(
                f"HypertgUL reupload part={part_num} fail: {type(e).__name__}: {e}"
            )
        finally:
            fp.close()

    async def upload(
        self,
        target_client,
        target_chat_id,
        file_path,
        dump_chat_id,
        media_type,
        attributes,
        thumb_path=None,
        caption="",
        reply_to_message_id=None,
    ):
        self._cancel.clear()
        self._obj._processed_bytes = 0
        self._up_file = ospath.basename(file_path)
        self._up_size = ospath.getsize(file_path)

        if self._up_size > 10 * MB:
            input_file = await self._upload_file(target_client, file_path)
        else:
            input_file = await self._upload_small(target_client, file_path)

        thumb_file = None
        if thumb_path and ospath.exists(thumb_path) and ospath.getsize(thumb_path) > 0:
            thumb_file = await self._upload_thumb(target_client, thumb_path)

        mime_type = self._mime(file_path)
        input_media = self._build_media(
            input_file, mime_type, media_type, attributes, thumb_file
        )

        peer = await target_client.resolve_peer(target_chat_id)

        parsed = await utils.parse_text_entities(
            target_client, caption or "", None, None
        )

        rpc = raw.functions.messages.SendMedia(
            peer=peer,
            media=input_media,
            random_id=target_client.rnd_id(),
            reply_to=raw.types.InputReplyToMessage(reply_to_msg_id=reply_to_message_id)
            if reply_to_message_id
            else None,
            **parsed,
            silent=True,
        )

        r_updates = None
        send_retries = 0
        missing_fixed = 0
        while True:
            try:
                r_updates = await target_client.invoke(rpc)
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
                    raise RuntimeError(
                        f"SendMedia exhausted after fixing {missing_fixed} missing parts"
                    )
            except (FloodWait, FloodPremiumWait) as e:
                val = e.value if hasattr(e, "value") else 5
                send_retries += 1
                LOGGER.warning(
                    f"HypertgUL SendMedia flood {val}s "
                    f"(retry {send_retries}) {self._up_file}"
                )
                if send_retries >= 10:
                    raise
                await asyncio.sleep(val + 1)
            except Exception as e:
                send_retries += 1
                LOGGER.error(
                    f"HypertgUL SendMedia {type(e).__name__}: {e} "
                    f"(retry {send_retries}) {self._up_file}"
                )
                if send_retries >= 10:
                    raise
        msg_id = None
        for u in r_updates.updates:
            if isinstance(
                u,
                (
                    raw.types.UpdateNewMessage,
                    raw.types.UpdateNewChannelMessage,
                    raw.types.UpdateNewScheduledMessage,
                ),
            ):
                msg_id = u.message.id
                break
        if msg_id is None:
            LOGGER.error("HypertgUL no UpdateNewMessage in response")
            raise ValueError("No UpdateNewMessage in SendMedia response")

        msg = await target_client.get_messages(
            chat_id=target_chat_id, message_ids=msg_id
        )
        return msg

    async def cancel(self):
        await super().cancel()

    @staticmethod
    def _mime(path):
        m, _ = guess_type(path)
        return m or "application/octet-stream"
