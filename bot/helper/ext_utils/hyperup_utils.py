from asyncio import (
    CancelledError,
    Lock,
    Queue,
    Semaphore,
    create_task,
    gather,
    sleep,
)
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath
from re import search as research

from pyrogram import StopTransmission, raw, utils
from pyrogram.errors import FilePartMissing, FloodPremiumWait, FloodWait
from pyrogram.session import Session

from ... import LOGGER
from ..telegram_helper.tg_transfer import MB, HypertgTransfer
from .bot_utils import sync_to_async

_ul_load_lock = Lock()
_ul_slots: Semaphore | None = None
_ul_slots_lock = Lock()

WORKERS_PER_SESSION = 4
_session_pool: dict[tuple[int, int], list[Session]] = {}
_pool_locks: dict[tuple[int, int], Lock] = {}

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
            pool[:] = [s for s in pool if s.is_connected and not s.instant_stop]
            while len(pool) < n_sessions:
                s = await self._mk_session(client, dc_id, mode=mode)
                pool.append(s)
            _session_pool[key] = pool
            return list(pool)

    async def _upload_file(self, client, file_path):
        global _ul_slots
        file_size = ospath.getsize(file_path)
        file_total_parts = ceil(file_size / PART_SIZE)
        file_id = client.rnd_id()
        dc_id = await client.storage.dc_id()
        is_big = file_size > 10 * MB

        _slot_acquired = False
        async with _ul_slots_lock:
            if _ul_slots is None:
                _ul_slots = Semaphore(max(1, self.num_clients))
        await _ul_slots.acquire()
        _slot_acquired = True

        ul_ci = None
        fp = None
        q = None
        workers = []
        pool = []

        try:
            if self.clients:
                async with _ul_load_lock:
                    ul_ci = min(
                        self.clients.keys(), key=lambda i: self.work_loads.get(i, 0)
                    )
                    self.work_loads[ul_ci] = self.work_loads.get(ul_ci, 0) + 1
                    _concurrent = sum(1 for v in self.work_loads.values() if v > 0)
                up_client = self.clients[ul_ci]
                LOGGER.info(
                    f"HypertgUL client={ul_ci} loads={dict(self.work_loads)} "
                    f"bots={len(self.clients)} concurrent={_concurrent}"
                )
            else:
                up_client = client

            n_sessions = 4
            n_workers = n_sessions * WORKERS_PER_SESSION
            pool = await self._ensure_session_pool(up_client, dc_id, n_sessions, mode=1)
            LOGGER.info(
                f"HypertgUL pool ready dc={dc_id} "
                f"sessions={len(pool)} workers={n_workers} {ospath.basename(file_path)}"
            )

            fp = open(file_path, "rb", buffering=PART_SIZE)
            q = Queue(n_workers)

            def _make_rpc(chunk, part_idx):
                if is_big:
                    return raw.functions.upload.SaveBigFilePart(
                        file_id=file_id, file_part=part_idx,
                        file_total_parts=file_total_parts, bytes=chunk,
                    )
                return raw.functions.upload.SaveFilePart(
                    file_id=file_id, file_part=part_idx, bytes=chunk,
                )

            async def _worker(session):
                _pool_key = (id(up_client), dc_id)
                while True:
                    data = await q.get()
                    try:
                        if data is None:
                            return
                        for attempt in range(5):
                            try:
                                await session.invoke(data)
                                break
                            except StopTransmission:
                                raise
                            except CancelledError:
                                return
                            except (OSError, TimeoutError, ConnectionError):
                                LOGGER.warning(
                                    f"HypertgUL transport error "
                                    f"attempt {attempt + 1}/5 — reconnecting"
                                )
                                if attempt == 4:
                                    raise
                                try:
                                    await session.stop()
                                except Exception:
                                    pass
                                session = await self._mk_session(up_client, dc_id, mode=1)
                                if _pool_key in _session_pool:
                                    _session_pool[_pool_key].append(session)
                                await sleep(1)
                            except Exception:
                                if attempt == 4:
                                    raise
                                await sleep(2**attempt)
                    finally:
                        q.task_done()

            workers = [
                create_task(_worker(pool[i % n_sessions]))
                for i in range(n_workers)
            ]

            progress_interval = max(1, file_total_parts // 10)
            parts_sent = 0

            LOGGER.info(f"HypertgUL start read {ospath.basename(file_path)}")
            while True:
                chunk = await sync_to_async(fp.read, PART_SIZE)
                if not chunk:
                    break

                if self._listener.is_cancelled:
                    raise StopTransmission()

                if all(t.done() for t in workers):
                    for t in workers:
                        exc = t.exception()
                        if exc is not None:
                            raise exc
                    raise RuntimeError("All upload workers exited prematurely")

                await q.put(_make_rpc(chunk, parts_sent))
                parts_sent += 1

                if parts_sent % progress_interval == 0:
                    self._obj._processed_bytes = min(
                        parts_sent * PART_SIZE, file_size
                    )

            for _ in range(n_workers):
                await q.put(None)
            worker_results = await gather(*workers, return_exceptions=True)
            for r in worker_results:
                if isinstance(r, BaseException) and not isinstance(r, CancelledError):
                    LOGGER.warning(f"HypertgUL worker exited with: {type(r).__name__}")
            self._obj._processed_bytes = file_size

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
            if ul_ci is not None:
                async with _ul_load_lock:
                    self.work_loads[ul_ci] = max(0, self.work_loads.get(ul_ci, 0) - 1)
            if _slot_acquired:
                _ul_slots.release()
            if q:
                for _ in range(n_workers if workers else 16):
                    try:
                        q.put_nowait(None)
                    except Exception:
                        pass
            if workers:
                await gather(*workers, return_exceptions=True)
            if fp:
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
