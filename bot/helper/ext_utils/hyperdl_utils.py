import os
from asyncio import (
    FIRST_COMPLETED,
    CancelledError,
    Event,
    Lock,
    Queue,
    Semaphore,
    create_task,
    ensure_future,
    gather,
    sleep,
    to_thread,
    wait,
    wait_for,
)
from datetime import datetime
from mimetypes import guess_extension
from pathlib import Path
from re import sub
from sys import argv
from time import time

from aiofiles.os import makedirs
from pyrogram import StopTransmission, raw, utils
from pyrogram.errors import (
    AuthBytesInvalid,
    FileMigrate,
    FileReferenceExpired,
    FileReferenceInvalid,
    FloodPremiumWait,
    FloodWait,
)
from pyrogram.file_id import PHOTO_TYPES, FileId, FileType, ThumbnailSource
from pyrogram.session import Auth, Session
from pyrogram.session.internals import MsgId

from ... import LOGGER
from ...core.config_manager import Config
from ...core.tg_client import TgClient

_hyper_part_sem = Semaphore(10)


def _chunk_size():
    return max(Config.HYPER_CHUNK, 64 * 1024)


def _pick_client(work_loads, client_keys):
    if not client_keys:
        return None
    return min(client_keys, key=lambda i: work_loads.get(i, 0))


class HyperTGDownload:
    _ref_cache_max = 100
    _ref_cache_ttl = 45 * 60
    _ref_cache_clean_interval = 15 * 60
    _clean_task = None

    def __init__(self):
        self.clients = TgClient.helper_bots
        self.work_loads = TgClient.helper_loads
        self.num_clients = len(self.clients)
        self.num_parts = Config.HYPER_THREADS or max(8, self.num_clients)
        self.pipeline_depth = max(Config.HYPER_PIPELINE, 16)
        self.message = None
        self.dump_chat = None
        self.directory = None
        self.file_name = ""
        self.file_size = 0
        self.download_dir = "downloads/"
        self._ref_cache = {}
        self._ref_cache_access = {}
        self._ref_fetch_locks = {}
        self._sessions = {}
        self._cancel = Event()
        self._tasks = []
        self._prog_task = None
        self._processed_bytes = 0
        if HyperTGDownload._clean_task is None or HyperTGDownload._clean_task.done():
            HyperTGDownload._clean_task = create_task(self._clean_ref_cache())

    @staticmethod
    def _media_of(message):
        for attr in (
            "audio",
            "document",
            "photo",
            "sticker",
            "animation",
            "video",
            "voice",
            "video_note",
            "new_chat_photo",
        ):
            if m := getattr(message, attr, None):
                return m
        raise ValueError("No downloadable media")

    def _ref_cache_hit(self, idx):
        self._ref_cache_access[idx] = time()

    def _ref_cache_put(self, idx, fid):
        self._ref_cache[idx] = fid
        self._ref_cache_access[idx] = time()
        if len(self._ref_cache) > self._ref_cache_max:
            oldest = min(self._ref_cache_access, key=self._ref_cache_access.get)
            self._ref_cache.pop(oldest, None)
            self._ref_cache_access.pop(oldest, None)

    async def _clean_ref_cache(self):
        while True:
            await sleep(self._ref_cache_clean_interval)
            now = time()
            expired = [
                k
                for k, v in self._ref_cache_access.items()
                if now - v > self._ref_cache_ttl
            ]
            for k in expired:
                self._ref_cache.pop(k, None)
                self._ref_cache_access.pop(k, None)
            if expired:
                LOGGER.info(f"HyperDL ref cache cleaned {len(expired)} expired entries")

    async def _fetch_ref(self, idx, client, max_retries=3, force=False):
        if not force:
            cached = self._ref_cache.get(idx)
            if cached is not None:
                self._ref_cache_hit(idx)
                return cached
        if idx not in self._ref_fetch_locks:
            self._ref_fetch_locks[idx] = Lock()
        async with self._ref_fetch_locks[idx]:
            if not force:
                cached = self._ref_cache.get(idx)
                if cached is not None:
                    self._ref_cache_hit(idx)
                    return cached
            LOGGER.info(
                f"HyperDL _fetch_ref client={client.me.username} "
                f"idx={idx} dump={self.dump_chat} msg={self.message.id} "
                f"force={force}"
            )
            last_error = None
            for attempt in range(max_retries):
                try:
                    msg = await client.get_messages(self.dump_chat, self.message.id)
                    if msg is None:
                        raise ValueError(
                            f"msg {self.message.id} not found in {self.dump_chat}"
                        )
                    media = self._media_of(msg)
                    fid_str = getattr(media, "file_id", None)
                    if not fid_str:
                        raise ValueError(
                            f"no file_id in media from msg {self.message.id}"
                        )
                    fid = FileId.decode(fid_str)
                    ref_hex = (
                        fid.file_reference.hex()[:32]
                        if fid.file_reference
                        else "EMPTY"
                    )
                    LOGGER.info(
                        f"HyperDL _fetch_ref client={client.me.username} "
                        f"idx={idx} got ref={ref_hex}... dc={fid.dc_id} "
                        f"type={fid.file_type}"
                    )
                    self._ref_cache_put(idx, fid)
                    return fid
                except Exception as e:
                    last_error = e
                    LOGGER.warning(
                        f"HyperDL _fetch_ref attempt {attempt + 1}/{max_retries} "
                        f"fail: {e} (client={client.me.username} "
                        f"chat={self.dump_chat} msg={self.message.id})"
                    )
                    if attempt < max_retries - 1:
                        await sleep(attempt * 2)
            raise ValueError(
                f"Failed to get file ref from {self.dump_chat} msg "
                f"{self.message.id} with {client.me.username}: {last_error}"
            )

    async def _mk_session(self, client, dc_id):
        tm = await client.storage.test_mode()
        if dc_id != await client.storage.dc_id():
            ak = await Auth(client, dc_id, tm).create()
            s = Session(client, dc_id, ak, tm, is_media=True)
            await s.start()
            for attempt in range(6):
                try:
                    e = await client.invoke(
                        raw.functions.auth.ExportAuthorization(dc_id=dc_id)
                    )
                    await s.invoke(
                        raw.functions.auth.ImportAuthorization(id=e.id, bytes=e.bytes)
                    )
                    return s
                except AuthBytesInvalid:
                    LOGGER.warning(
                        f"HyperDL _mk_session AuthBytesInvalid attempt {attempt + 1}/6 "
                        f"client={client.me.username} dc={dc_id}"
                    )
                    await sleep(1)
            await s.stop()
            raise AuthBytesInvalid
        ak = await client.storage.auth_key()
        s = Session(client, dc_id, ak, tm, is_media=True)
        await s.start()
        return s

    async def _get_session(self, idx, dc_id, force=False):
        s = self._sessions.get(idx)
        if s and not force:
            if s.is_connected and s.dc_id == dc_id:
                return s
            try:
                await s.stop()
            except Exception:
                pass
        LOGGER.info(
            f"HyperDL _get_session idx={idx} dc={dc_id} force={force} "
            f"client={self.clients[idx].me.username}"
        )
        s = await self._mk_session(self.clients[idx], dc_id)
        self._sessions[idx] = s
        return s

    async def _close_all(self):
        sessions = list(self._sessions.values())
        self._sessions.clear()
        await gather(*[s.stop() for s in sessions], return_exceptions=True)

    @staticmethod
    def _location(fid):
        ft = fid.file_type
        if ft == FileType.CHAT_PHOTO:
            if fid.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=fid.chat_id, access_hash=fid.chat_access_hash
                )
            elif fid.chat_access_hash == 0:
                peer = raw.types.InputPeerChat(chat_id=-fid.chat_id)
            else:
                peer = raw.types.InputPeerChannel(
                    channel_id=utils.get_channel_id(fid.chat_id),
                    access_hash=fid.chat_access_hash,
                )
            return raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=fid.volume_id,
                local_id=fid.local_id,
                big=fid.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
        if ft == FileType.PHOTO:
            return raw.types.InputPhotoFileLocation(
                id=fid.media_id,
                access_hash=fid.access_hash,
                file_reference=fid.file_reference,
                thumb_size=fid.thumbnail_size,
            )
        return raw.types.InputDocumentFileLocation(
            id=fid.media_id,
            access_hash=fid.access_hash,
            file_reference=fid.file_reference,
            thumb_size=fid.thumbnail_size,
        )

    async def _do_req(self, sess, location, off, csz, attempt=0):
        try:
            r = await wait_for(
                sess.invoke(
                    raw.functions.upload.GetFile(
                        precise=True,
                        cdn_supported=False,
                        location=location,
                        offset=off,
                        limit=csz,
                    )
                ),
                timeout=Config.HYPER_TIMEOUT,
            )
            if isinstance(r, raw.types.upload.File):
                return r.bytes
            raise ValueError(f"Unexpected response type: {type(r)}")
        except FileMigrate as e:
            dc = e.value if hasattr(e, "value") else int(str(e).split()[-1])
            LOGGER.info(
                f"HyperDL FileMigrate attempt={attempt} dc={dc} "
                f"sess_dc={sess.dc_id} off={off}"
            )
            if attempt < 3:
                return None, dc
            raise
        except (FileReferenceExpired, FileReferenceInvalid) as e:
            LOGGER.info(
                f"HyperDL {type(e).__name__} attempt={attempt} "
                f"off={off} sess_dc={sess.dc_id}"
            )
            if attempt < 3:
                return None, -1
            raise
        except (ConnectionError, OSError) as e:
            LOGGER.info(
                f"HyperDL {type(e).__name__}: {e} attempt={attempt} "
                f"off={off} sess_dc={sess.dc_id}"
            )
            if attempt < 3:
                return None, -2
            raise

    async def _pipeline_fetch(self, idx, location, start, end, fid, queue):
        csz = _chunk_size()
        sess = await self._get_session(idx, fid.dc_id)
        loc = location
        first_chunk_off = start - (start % csz)
        first_trim = start - first_chunk_off
        last_byte = end - 1
        window = self.pipeline_depth
        min_window = 2
        max_window = window * 4
        inflight = set()
        cur_off = first_chunk_off
        seq = 0
        consecutive_ok = 0
        flood_count = 0

        LOGGER.info(
            f"HyperDL pipeline idx={idx} dc={fid.dc_id} "
            f"range={start}-{end} ({(end - start) / 1048576:.1f}MB) "
            f"pipe={window} csz={csz / 1024:.0f}KB"
        )

        async def _req(off, s):
            nonlocal sess, loc, window, consecutive_ok, flood_count
            last_err = None
            for attempt in range(3):
                try:
                    result = await self._do_req(sess, loc, off, csz, attempt)
                    if isinstance(result, tuple):
                        _, dc_or_ref = result
                        last_err = dc_or_ref
                        if dc_or_ref == -1:
                            ref_hex = (
                                loc.file_reference.hex()[:16]
                                if hasattr(loc, "file_reference") and loc.file_reference
                                else "N/A"
                            )
                            LOGGER.info(
                                f"HyperDL ref refresh idx={idx} "
                                f"old_ref={ref_hex}... off={off}"
                            )
                            fid_new = await self._fetch_ref(
                                idx, self.clients[idx], force=True
                            )
                            loc = self._location(fid_new)
                            new_hex = (
                                loc.file_reference.hex()[:16]
                                if hasattr(loc, "file_reference") and loc.file_reference
                                else "N/A"
                            )
                            LOGGER.info(
                                f"HyperDL ref refreshed idx={idx} "
                                f"new_ref={new_hex}... off={off}"
                            )
                            await sleep(attempt + 1)
                        elif dc_or_ref == -2:
                            LOGGER.info(
                                f"HyperDL reconnect idx={idx} dc={sess.dc_id} off={off}"
                            )
                            sess = await self._get_session(idx, sess.dc_id, force=True)
                            await sleep(attempt + 1)
                        else:
                            LOGGER.info(
                                f"HyperDL migrate idx={idx} "
                                f"dc={sess.dc_id}->{dc_or_ref} off={off}"
                            )
                            sess = await self._get_session(idx, dc_or_ref, force=True)
                            await sleep(1)
                        continue
                    return s, off, result
                except (FloodWait, FloodPremiumWait) as e:
                    last_err = f"flood:{e.value if hasattr(e, 'value') else 5}"
                    flood_count += 1
                    wait_val = e.value if hasattr(e, "value") else 5
                    if wait_val > 10 or flood_count >= 3:
                        window = max(min_window, window - max(1, window // 4))
                        consecutive_ok = 0
                        flood_count = 0
                        LOGGER.info(
                            f"HyperDL flood shrink idx={idx} "
                            f"window={window} wait={wait_val}s off={off}"
                        )
                    await sleep(wait_val + attempt * 2)
                except CancelledError:
                    raise
            raise RuntimeError(
                f"Failed after 3 attempts at offset {off} (err={last_err})"
            )

        try:
            consecutive_fail = 0
            while cur_off <= last_byte or inflight:
                while len(inflight) < window and cur_off <= last_byte:
                    if self._cancel.is_set():
                        raise CancelledError
                    inflight.add(ensure_future(_req(cur_off, seq)))
                    cur_off += csz
                    seq += 1
                if not inflight:
                    break
                try:
                    done_set, inflight = await wait_for(
                        wait(inflight, return_when=FIRST_COMPLETED),
                        timeout=90,
                    )
                    consecutive_ok += len(done_set)
                    consecutive_fail = 0
                    if consecutive_ok >= window:
                        window = min(window + 2, max_window)
                        consecutive_ok = 0
                except TimeoutError:
                    consecutive_fail += 1
                    if consecutive_fail >= 3:
                        raise RuntimeError(
                            "Pipeline stalled: no progress for 3 consecutive rounds"
                        )
                    window = max(min_window, window // 2)
                    continue
                for f in done_set:
                    s, roff, chunk = f.result()
                    if not chunk:
                        continue
                    if roff == first_chunk_off and roff + csz >= end:
                        chunk = chunk[first_trim : last_byte - roff + 1]
                    elif roff == first_chunk_off:
                        chunk = chunk[first_trim:]
                    elif roff + csz > end:
                        chunk = chunk[: end - roff]
                    await queue.put((roff, chunk))
        except CancelledError:
            raise
        except Exception as e:
            LOGGER.error(f"HyperDL pipeline err: {type(e).__name__}: {e}")
            raise
        finally:
            for f in inflight:
                if not f.done():
                    f.cancel()

    async def _part(self, start, end, final_path, ci, fid, loc):
        q = Queue(maxsize=self.pipeline_depth + 1)
        error_holder = [None]

        async def _producer():
            try:
                await self._pipeline_fetch(ci, loc, start, end, fid, q)
            except CancelledError:
                pass
            except Exception as e:
                error_holder[0] = e
            finally:
                await q.put(None)

        async def _consumer():
            fd = await to_thread(os.open, final_path, os.O_WRONLY)
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        break
                    roff, chunk = item
                    await self._async_pwrite(fd, chunk, roff)
                    self._processed_bytes += len(chunk)
            finally:
                await to_thread(os.close, fd)

        await _hyper_part_sem.acquire()
        try:
            prod = ensure_future(_producer())
            try:
                await _consumer()
                if error_holder[0] is not None:
                    raise error_holder[0]
            except CancelledError:
                prod.cancel()
                raise
            except Exception:
                prod.cancel()
                raise
            finally:
                if not prod.done():
                    prod.cancel()
        finally:
            _hyper_part_sem.release()
            self.work_loads[ci] = max(0, self.work_loads.get(ci, 1) - 1)

    @staticmethod
    async def _async_pwrite(fd, data, offset):
        total = len(data)
        n = await to_thread(os.pwrite, fd, data, offset)
        if n == total:
            return
        if n == 0:
            raise OSError(f"pwrite returned 0 at offset {offset}")
        mv = memoryview(data)
        written = n
        while written < total:
            n = await to_thread(os.pwrite, fd, mv[written:], offset + written)
            if n == 0:
                raise OSError(f"pwrite returned 0 at offset {offset + written}")
            written += n

    async def _progress(self, cb, args):
        if not cb:
            return
        last = 0
        while not self._cancel.is_set():
            try:
                cur = self._processed_bytes
                if cur != last:
                    await cb(cur, self.file_size, *args)
                    last = cur
                await sleep(1)
            except (CancelledError, StopTransmission):
                break
            except Exception:
                await sleep(1)

    async def handle_download(self, progress, progress_args):
        self._cancel.clear()
        self._processed_bytes = 0
        dl_start = time()
        await makedirs(self.directory, exist_ok=True)
        final = os.path.abspath(
            sub("\\\\", "/", os.path.join(self.directory, self.file_name))
        )

        n_use = min(self.num_parts, self.num_clients)
        client_keys = list(self.clients.keys())

        min_part = 1 * 1024 * 1024
        n_parts = (
            min(n_use, max(1, self.file_size // min_part))
            if self.file_size >= min_part
            else 1
        )
        psz = self.file_size // n_parts if n_parts > 0 else self.file_size
        ranges = [(i * psz, min((i + 1) * psz, self.file_size)) for i in range(n_parts)]

        load_map = {}
        assigns = []
        for _ in range(n_parts):
            ci = _pick_client(self.work_loads, client_keys)
            assigns.append(ci)
            load_map[ci] = load_map.get(ci, 0) + 1
        for ci, cnt in load_map.items():
            self.work_loads[ci] = self.work_loads.get(ci, 0) + cnt

        unique_clients = set(assigns)
        fid_map = {}
        try:
            for ci in unique_clients:
                fid_map[ci] = await self._fetch_ref(ci, self.clients[ci])
        except Exception as e:
            LOGGER.error(f"HyperDL ref fail: {e}")
            for ci, cnt in load_map.items():
                self.work_loads[ci] = max(0, self.work_loads.get(ci, 1) - cnt)
            return None

        self._tasks = []
        self._prog_task = None

        try:
            await to_thread(self._create_file_sync, final, self.file_size)

            for i, (s, e) in enumerate(ranges):
                ci = assigns[i]
                fid = fid_map[ci]
                part_loc = self._location(fid)
                LOGGER.info(
                    f"HyperDL part {i}: client={ci} "
                    f"range={s}-{e} ({(e - s) / 1048576:.1f}MB) "
                    f"dc={fid.dc_id}"
                )
                self._tasks.append(
                    create_task(
                        self._part(s, e, final, ci, fid, part_loc)
                    )
                )
            if progress:
                self._prog_task = create_task(self._progress(progress, progress_args))
            await gather(*self._tasks)
            dl_elapsed = time() - dl_start
            dl_speed = self.file_size / dl_elapsed / 1048576 if dl_elapsed > 0 else 0
            wl_str = " ".join(f"c{k}:{v}" for k, v in sorted(self.work_loads.items()))
            LOGGER.info(
                f"HyperDL done {self.file_name} "
                f"({self.file_size / 1048576:.1f}MB {n_parts}p {n_use}c "
                f"pipe={self.pipeline_depth} wl=[{wl_str}] {dl_speed:.1f}MB/s)"
            )
            return final
        except FloodWait as e:
            wait_val = e.value if hasattr(e, "value") else 5
            LOGGER.warning(f"HyperDL FloodWait: sleeping {wait_val}s")
            await sleep(wait_val + 1)
            return None
        except (CancelledError, StopTransmission):
            return None
        except Exception as e:
            LOGGER.error(f"HyperDL: {type(e).__name__}: {e}")
            return None
        finally:
            self._cancel.set()
            to_cancel = []
            if self._prog_task and not self._prog_task.done():
                to_cancel.append(self._prog_task)
            to_cancel.extend(t for t in self._tasks if not t.done())
            if to_cancel:
                await gather(*to_cancel, return_exceptions=True)
            await self._close_all()

    async def download_media(
        self,
        message,
        file_name="downloads/",
        progress=None,
        progress_args=(),
        dump_chat=None,
    ):
        try:
            if dump_chat and not isinstance(dump_chat, int):
                try:
                    dump_chat = int(dump_chat)
                except (ValueError, TypeError):
                    dump_chat = None
            if dump_chat:
                try:
                    self.message = await TgClient.bot.copy_message(
                        chat_id=dump_chat,
                        from_chat_id=message.chat.id,
                        message_id=message.id,
                        disable_notification=True,
                    )
                except Exception as e:
                    LOGGER.warning(
                        f"HyperDL copy fail: {e} "
                        f"(from={message.chat.id} to={dump_chat})"
                    )
                    raise RuntimeError(f"Cannot copy to dump chat: {e}") from e
            self.dump_chat = dump_chat or message.chat.id
            self.message = self.message or message
            LOGGER.info(
                f"HyperDL init dump={self.dump_chat} "
                f"msg_id={self.message.id} msg_type={type(self.message).__name__}"
            )
            media = self._media_of(self.message)
            fid_str = media if isinstance(media, str) else media.file_id
            fid_obj = FileId.decode(fid_str)
            ftype = fid_obj.file_type
            mname = getattr(media, "file_name", "")
            self.file_size = getattr(media, "file_size", 0)
            mime = getattr(media, "mime_type", "image/jpeg")
            dt = getattr(media, "date", None)
            self.directory, self.file_name = os.path.split(file_name)
            self.file_name = self.file_name or mname or ""
            if not os.path.isabs(self.file_name):
                self.directory = Path(argv[0]).parent / (
                    self.directory or self.download_dir
                )
            if not self.file_name:
                ext = self._ext(ftype, mime)
                self.file_name = f"{FileType(ftype).name.lower()}_{(dt or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}_{MsgId()}{ext}"
            return await self.handle_download(progress, progress_args)
        except Exception as e:
            LOGGER.error(f"HyperDL download_media: {e}")
            raise

    @staticmethod
    def _ext(ft, mime):
        if ft in PHOTO_TYPES:
            return ".jpg"
        if mime:
            e = guess_extension(mime)
            if e:
                return e
        return {
            FileType.VOICE: ".ogg",
            FileType.VIDEO: ".mp4",
            FileType.ANIMATION: ".mp4",
            FileType.VIDEO_NOTE: ".mp4",
            FileType.AUDIO: ".mp3",
            FileType.STICKER: ".webp",
        }.get(ft, ".bin")

    @staticmethod
    def _create_file_sync(path, size):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT)
        try:
            os.ftruncate(fd, size)
        finally:
            os.close(fd)

    async def cancel(self):
        self._cancel.set()
        to_cancel = []
        if self._prog_task and not self._prog_task.done():
            to_cancel.append(self._prog_task)
        to_cancel.extend(t for t in self._tasks if not t.done())
        if to_cancel:
            await gather(*to_cancel, return_exceptions=True)
        await self._close_all()
