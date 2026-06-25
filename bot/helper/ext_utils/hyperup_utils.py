from asyncio import CancelledError, sleep
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath
from re import search as research

from pyrogram import StopTransmission, raw, utils
from pyrogram.errors import FilePartMissing, FloodPremiumWait, FloodWait

from ... import LOGGER
from ..telegram_helper.tg_transfer import MB, HypertgTransfer

KB = 1024
PART_SIZE = 512 * KB


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

    async def _ensure_session_pool(self, client, dc_id, n_sessions=4, mode=1):
        key = (id(client), dc_id)
        if key not in _pool_locks:
            _pool_locks[key] = Lock()
        async with _pool_locks[key]:
            pool = _session_pool.get(key, [])
            before = len(pool)
            pool[:] = [s for s in pool if s.is_connected and not s.instant_stop]
            dropped = before - len(pool)
            while len(pool) < n_sessions:
                s = await self._mk_session(client, dc_id, mode=mode)
                pool.append(s)
            created = len(pool) - (before - dropped)
            _session_pool[key] = pool
            LOGGER.info(
                f"HypertgUL pool key={key} size={len(pool)} "
                f"dropped={dropped} created={created}"
            )
            return list(pool)

    async def _upload_file(self, client, file_path):
        import time as _time
        _t0 = _time.monotonic()
        file_size = ospath.getsize(file_path)
        file_total_parts = ceil(file_size / PART_SIZE)
        file_id = client.rnd_id()
        dc_id = await client.storage.dc_id()
        from pyrogram.errors import UserMigrate
        is_big = file_size > 10 * MB

        fp = open(file_path, "rb", buffering=PART_SIZE)
        session = await self._mk_session(client, dc_id, mode=1)

        try:
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    raise StopTransmission()
                fp.seek(part * PART_SIZE)
                chunk = fp.read(PART_SIZE)
                if not chunk:
                    break

                if is_big:
                    rpc = raw.functions.upload.SaveBigFilePart(
                        file_id=file_id, file_part=part,
                        file_total_parts=file_total_parts, bytes=chunk,
                    )
                else:
                    rpc = raw.functions.upload.SaveFilePart(
                        file_id=file_id, file_part=part, bytes=chunk,
                    )

                for attempt in range(5):
                    try:
                        await session.invoke(rpc)
                        break
                    except UserMigrate as e:
                        new_dc = getattr(e, "value", None)
                        if not isinstance(new_dc, int):
                            raise
                        LOGGER.info(
                            f"HypertgUL migrating DC {dc_id} → {new_dc} "
                            f"part={part}/{file_total_parts}"
                        )
                        dc_id = new_dc
                        await client.storage.dc_id(new_dc)
                        await session.stop()
                        session = await self._mk_session(client, dc_id, mode=1)
                    except StopTransmission:
                        raise
                    except CancelledError:
                        return
                    except (OSError, TimeoutError, ConnectionError):
                        LOGGER.warning(
                            f"HypertgUL transport error part={part} "
                            f"attempt {attempt + 1}/5"
                        )
                        if attempt == 4:
                            raise
                        try:
                            await session.stop()
                        except Exception:
                            pass
                        session = await self._mk_session(client, dc_id, mode=1)
                        await sleep(1)
                    except Exception:
                        if attempt == 4:
                            raise
                        await sleep(2**attempt)

                self._obj._processed_bytes = min(
                    (part + 1) * PART_SIZE, file_size
                )

                if part > 0 and part % max(1, file_total_parts // 10) == 0:
                    elapsed = _time.monotonic() - _t0
                    mb_done = self._obj._processed_bytes / (1024 * 1024)
                    mb_total = file_size / (1024 * 1024)
                    speed = mb_done / elapsed if elapsed > 0 else 0
                    LOGGER.info(
                        f"HypertgUL {ospath.basename(file_path)} "
                        f"part={part}/{file_total_parts} "
                        f"MB={mb_done:.0f}/{mb_total:.0f} speed={speed:.1f}MB/s"
                    )

            self._obj._processed_bytes = file_size
            LOGGER.info(
                f"HypertgUL done {ospath.basename(file_path)} "
                f"elapsed={_time.monotonic() - _t0:.1f}s"
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
            LOGGER.warning("HypertgUL upload cancelled (StopTransmission)")
            raise
        except Exception as e:
            LOGGER.error(f"HypertgUL upload fail: {type(e).__name__}: {e}")
            raise
        finally:
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
                await sleep(val + 1)
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
