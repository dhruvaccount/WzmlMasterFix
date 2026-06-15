import os
from asyncio import (
    CancelledError,
    Event,
    create_task,
    gather,
    get_event_loop,
    new_event_loop,
    sleep,
    to_thread,
)
from concurrent.futures import ThreadPoolExecutor
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

MB = 1024 * 1024


def _pick_client(work_loads, client_keys):
    if not client_keys:
        return None
    return min(client_keys, key=lambda i: work_loads.get(i, 0))


class HyperTGDownload:
    _ref_cache_max = 100

    def __init__(self):
        self.clients = TgClient.helper_bots
        self.work_loads = TgClient.helper_loads
        self.num_clients = len(self.clients)
        self.num_parts = Config.HYPER_THREADS or max(8, self.num_clients)
        self.message = None
        self.dump_chat = None
        self.directory = None
        self.file_name = ""
        self.file_size = 0
        self.download_dir = "downloads/"
        self._ref_cache = {}
        self._cancel = Event()
        self._tasks = []
        self._prog_task = None
        self._processed_bytes = 0
        pool_size = min(self.num_parts, self.num_clients)
        self._pool = ThreadPoolExecutor(
            max_workers=pool_size, thread_name_prefix="hyperdl"
        )

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

    def _ref_cache_get(self, idx):
        return self._ref_cache.get(idx)

    def _ref_cache_put(self, idx, data):
        if len(self._ref_cache) > self._ref_cache_max:
            oldest = next(iter(self._ref_cache))
            self._ref_cache.pop(oldest, None)
        self._ref_cache[idx] = data

    async def _fetch_ref(self, idx, client, force=False):
        if not force:
            cached = self._ref_cache_get(idx)
            if cached is not None:
                return cached
        for attempt in range(3):
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
                self._ref_cache_put(idx, fid)
                return fid
            except Exception as e:
                if attempt < 2:
                    LOGGER.warning(
                        f"HyperDL _fetch_ref attempt {attempt + 1} "
                        f"fail: {e} (client={client.me.username})"
                    )
                    await sleep(attempt * 2)
                else:
                    raise

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

    async def _export_auth(self, client, dc_id):
        return await client.invoke(
            raw.functions.auth.ExportAuthorization(dc_id=dc_id)
        )

    async def _mk_session_thread(self, client, dc_id, auth_export):
        tm = await client.storage.test_mode()
        if dc_id != await client.storage.dc_id():
            if auth_export is None:
                raise AuthBytesInvalid
            ak = await Auth(client, dc_id, tm).create()
            s = Session(client, dc_id, ak, tm, is_media=True)
            await s.start()
            for attempt in range(3):
                try:
                    await s.invoke(
                        raw.functions.auth.ImportAuthorization(
                            id=auth_export[0], bytes=auth_export[1]
                        )
                    )
                    return s
                except AuthBytesInvalid:
                    LOGGER.warning(
                        f"HyperDL _mk_session AuthBytesInvalid "
                        f"attempt {attempt + 1}/3 "
                        f"client={client.me.username} dc={dc_id}"
                    )
                    await sleep(1 + attempt)
            await s.stop()
            raise AuthBytesInvalid
        ak = await client.storage.auth_key()
        s = Session(client, dc_id, ak, tm, is_media=True)
        await s.start()
        return s

    async def _do_req(self, sess, client, location, off, csz, attempt=0):
        try:
            r = await sess.invoke(
                raw.functions.upload.GetFile(
                    location=location,
                    offset=off,
                    limit=csz,
                ),
                sleep_threshold=client.sleep_threshold,
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
        except TimeoutError:
            LOGGER.info(
                f"HyperDL TimeoutError attempt={attempt} "
                f"off={off} sess_dc={sess.dc_id}"
            )
            if attempt < 3:
                return None, -2
            raise

    def _thread_download(self, ci, start, end, final_path, fid, loc, auth_export):
        loop = new_event_loop()
        try:
            loop.run_until_complete(
                self._async_download(
                    ci, start, end, final_path, fid, loc, auth_export
                )
            )
        finally:
            loop.close()

    async def _async_download(
        self, ci, start, end, final_path, fid, loc, auth_export
    ):
        client = self.clients[ci]
        sess = await self._mk_session_thread(client, fid.dc_id, auth_export)

        LOGGER.info(
            f"HyperDL thread ci={ci} dc={fid.dc_id} "
            f"range={start}-{end} ({(end - start) / MB:.1f}MB)"
        )

        fd = await to_thread(os.open, final_path, os.O_WRONLY)
        try:
            csz = 1 << 20
            cur_off = start
            last_byte = end - 1
            attempt = 0

            while cur_off <= last_byte:
                if self._cancel.is_set():
                    return

                chunk_loc = self._location(fid)
                try:
                    result = await self._do_req(
                        sess, client, chunk_loc, cur_off, csz, attempt
                    )
                except (CancelledError, FloodWait, FloodPremiumWait):
                    raise
                except Exception:
                    if attempt < 2:
                        attempt += 1
                        await sleep(1 + attempt)
                        continue
                    raise

                if isinstance(result, tuple):
                    _, dc_or_ref = result
                    if dc_or_ref == -1:
                        fid = await self._fetch_ref(ci, client, force=True)
                        attempt += 1
                        if attempt <= 5:
                            await sleep(attempt + 1)
                            continue
                        raise RuntimeError("File ref refresh failed")
                    if dc_or_ref == -2:
                        try:
                            await sess.stop()
                        except Exception:
                            pass
                        sess = await self._mk_session_thread(
                            client, sess.dc_id, auth_export
                        )
                        attempt += 1
                        if attempt <= 5:
                            await sleep(attempt + 1)
                            continue
                        raise RuntimeError("Session reconnect failed")
                    try:
                        await sess.stop()
                    except Exception:
                        pass
                    sess = await self._mk_session_thread(
                        client, dc_or_ref, auth_export
                    )
                    attempt = 0
                    await sleep(1)
                    continue

                chunk = result
                if not chunk:
                    break

                remaining = last_byte - cur_off + 1
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]

                if chunk:
                    n = await to_thread(os.pwrite, fd, chunk, cur_off - start)
                    if n < len(chunk):
                        mv = memoryview(chunk)
                        written = n
                        while written < len(chunk):
                            n = await to_thread(
                                os.pwrite,
                                fd,
                                mv[written:],
                                cur_off - start + written,
                            )
                            if n == 0:
                                raise OSError(
                                    f"pwrite returned 0 at "
                                    f"offset {cur_off - start + written}"
                                )
                            written += n
                    self._processed_bytes += len(chunk)

                cur_off += csz
                attempt = 0
        finally:
            await to_thread(os.close, fd)
            try:
                await sess.stop()
            except Exception:
                pass

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

        min_part = 1 * MB
        n_parts = (
            min(n_use, max(1, self.file_size // min_part))
            if self.file_size >= min_part
            else 1
        )
        psz = self.file_size // n_parts if n_parts > 0 else self.file_size
        ranges = [
            (i * psz, min((i + 1) * psz, self.file_size)) for i in range(n_parts)
        ]

        load_map = {}
        assigns = []
        client_keys = list(self.clients.keys())
        for _ in range(n_parts):
            ci = _pick_client(self.work_loads, client_keys)
            assigns.append(ci)
            self.work_loads[ci] = self.work_loads.get(ci, 0) + 1
            load_map[ci] = load_map.get(ci, 0) + 1

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

        auth_exports = {}
        try:
            for ci in unique_clients:
                fid = fid_map[ci]
                dc_id = fid.dc_id
                if dc_id not in auth_exports:
                    client = self.clients[ci]
                    tm = await client.storage.test_mode()
                    if dc_id != await client.storage.dc_id():
                        for attempt in range(3):
                            try:
                                e = await self._export_auth(client, dc_id)
                                auth_exports[dc_id] = (e.id, e.bytes)
                                break
                            except AuthBytesInvalid:
                                LOGGER.warning(
                                    f"HyperDL ExportAuth attempt "
                                    f"{attempt + 1}/3 fail "
                                    f"client={client.me.username} dc={dc_id}"
                                )
                                await sleep(1 + attempt)
                        else:
                            auth_exports[dc_id] = None
                    else:
                        auth_exports[dc_id] = "home"
        except Exception as e:
            LOGGER.error(f"HyperDL auth export fail: {e}")
            for ci, cnt in load_map.items():
                self.work_loads[ci] = max(0, self.work_loads.get(ci, 1) - cnt)
            return None

        self._tasks = []
        self._prog_task = None

        try:
            await to_thread(self._create_file_sync, final, self.file_size)

            loop = get_event_loop()
            for i, (s, e) in enumerate(ranges):
                ci = assigns[i]
                fid = fid_map[ci]
                part_loc = self._location(fid)
                auth = auth_exports.get(fid.dc_id)
                if auth == "home":
                    auth = None
                LOGGER.info(
                    f"HyperDL part {i}: client={ci} "
                    f"range={s}-{e} ({(e - s) / MB:.1f}MB) "
                    f"dc={fid.dc_id}"
                )
                self._tasks.append(
                    loop.run_in_executor(
                        self._pool,
                        self._thread_download,
                        ci, s, e, final, fid, part_loc, auth,
                    )
                )
                if i < len(ranges) - 1:
                    await sleep(0.5)

            if progress:
                self._prog_task = create_task(
                    self._progress(progress, progress_args)
                )
            await gather(*self._tasks)
            dl_elapsed = time() - dl_start
            dl_speed = (
                self.file_size / dl_elapsed / MB if dl_elapsed > 0 else 0
            )
            wl_str = " ".join(
                f"c{k}:{v}" for k, v in sorted(self.work_loads.items())
            )
            LOGGER.info(
                f"HyperDL done {self.file_name} "
                f"({self.file_size / MB:.1f}MB {n_parts}p {n_use}c "
                f"wl=[{wl_str}] {dl_speed:.1f}MB/s)"
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
            if to_cancel:
                await gather(*to_cancel, return_exceptions=True)
            self._pool.shutdown(wait=False)

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
        if to_cancel:
            await gather(*to_cancel, return_exceptions=True)
        self._pool.shutdown(wait=False)
