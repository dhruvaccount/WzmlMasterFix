import os
from asyncio import (
    FIRST_COMPLETED,
    CancelledError,
    Queue,
    create_task,
    ensure_future,
    gather,
    sleep,
    to_thread,
    wait,
)
from datetime import datetime
from mimetypes import guess_extension
from os import cpu_count
from pathlib import Path
from re import sub
from sys import argv
from time import time

from aiofiles.os import makedirs
from pyrogram import StopTransmission, raw
from pyrogram.errors import (
    FileMigrate,
    FileReferenceExpired,
    FileReferenceInvalid,
    FloodPremiumWait,
    FloodWait,
)
from pyrogram.file_id import PHOTO_TYPES, FileId, FileType
from pyrogram.session.internals import MsgId

from ... import LOGGER
from ...core.config_manager import Config
from ...core.tg_client import TgClient
from ..telegram_helper.tg_transfer import HypertgTransfer, MB

KB = 1024
_MIN_CHUNK = 64 * KB
_DEFAULT_PIPELINE = 32
_MIN_PIPELINE = 4
_MAX_PIPELINE_MULT = 4
_LOW_WORKERS = 2
_HIGH_WORKERS = max(8, (cpu_count() or 4) * 2)


def _pick_clients(wl, clients, count):
    keys = list(clients.keys())
    return sorted(keys, key=lambda i: wl.get(i, 0))[:count]


class HypertgDownload(HypertgTransfer):
    def __init__(self, obj):
        super().__init__(obj)
        self.chunk_size = max(Config.HYPER_CHUNK or 256 * KB, _MIN_CHUNK)
        self.num_parts = Config.HYPER_THREADS or max(
            _LOW_WORKERS, min(_HIGH_WORKERS, self.num_clients)
        )
        self.pipeline_depth = max(Config.HYPER_PIPELINE or _DEFAULT_PIPELINE, _MIN_PIPELINE)
        self.message = None
        self.dump_chat = None
        self.directory = None
        self.file_name = ""
        self.file_size = 0
        self.download_dir = "downloads/"
        self._ref_cache = {}

    def _ref_get(self, idx):
        return self._ref_cache.get(idx)

    def _ref_put(self, idx, data):
        if len(self._ref_cache) > 100:
            self._ref_cache.pop(next(iter(self._ref_cache)))
        self._ref_cache[idx] = data

    async def _fetch_ref(self, idx, client, retries=3, force=False):
        if not force:
            cached = self._ref_get(idx)
            if cached is not None:
                return cached
        last_err = None
        for attempt in range(retries):
            try:
                msg = await client.get_messages(self.dump_chat, self.message.id)
                if msg is None:
                    raise ValueError(f"msg {self.message.id} not found in {self.dump_chat}")
                media = self._media_of(msg)
                fid_str = media.file_id if hasattr(media, "file_id") else None
                if not fid_str:
                    raise ValueError(f"no file_id in media from msg {self.message.id}")
                fid = FileId.decode(fid_str)
                self._ref_put(idx, fid)
                return fid
            except Exception as e:
                last_err = e
                LOGGER.warning(
                    f"HypertgDL _fetch_ref attempt {attempt + 1}/{retries} "
                    f"fail: {e} (client={client.me.username})"
                )
                if attempt < retries - 1:
                    await sleep(attempt + 1)
        raise ValueError(f"Failed to get file ref with {client.me.username}: {last_err}")

    @staticmethod
    def _media_of(message):
        for attr in ("audio", "document", "photo", "sticker", "animation",
                     "video", "voice", "video_note", "new_chat_photo"):
            if m := getattr(message, attr, None):
                return m
        raise ValueError("No downloadable media")

    async def _do_req(self, sess, client, location, off, csz, attempt=0):
        try:
            r = await sess.invoke(
                raw.functions.upload.GetFile(
                    precise=True, cdn_supported=False,
                    location=location, offset=off, limit=csz,
                ),
                sleep_threshold=client.sleep_threshold,
            )
            if isinstance(r, raw.types.upload.File):
                return r.bytes
            raise ValueError(f"Unexpected response type: {type(r)}")
        except FileMigrate as e:
            dc = e.value if hasattr(e, "value") else int(str(e).split()[-1])
            if attempt < 3:
                return None, dc
            raise
        except (FileReferenceExpired, FileReferenceInvalid):
            if attempt < 3:
                return None, -1
            raise
        except (ConnectionError, OSError, TimeoutError):
            if attempt < 3:
                return None, -2
            raise

    async def _pipeline_fetch(self, idx, location, start, end, fid, queue, csz):
        sess = await self._get_session(idx, fid.dc_id)
        loc = location
        first_off = start - (start % csz)
        first_trim = start - first_off
        last_byte = end - 1
        window = self.pipeline_depth
        min_win = _MIN_PIPELINE
        max_win = window * _MAX_PIPELINE_MULT
        inflight = set()
        cur = first_off
        seq = 0
        ok_count = 0
        flood_count = 0

        async def _req(off, s):
            nonlocal window, ok_count, flood_count
            my_sess = sess
            my_loc = loc
            for attempt in range(3):
                try:
                    result = await self._do_req(my_sess, self.clients[idx], my_loc, off, csz, attempt)
                    if isinstance(result, tuple):
                        _, dc_or_ref = result
                        if dc_or_ref == -1:
                            fid_new = await self._fetch_ref(idx, self.clients[idx], force=True)
                            my_loc = self._location(fid_new)
                        elif dc_or_ref == -2:
                            my_sess = await self._get_session(idx, my_sess.dc_id, force=True)
                        else:
                            my_sess = await self._get_session(idx, dc_or_ref, force=True)
                        await sleep(attempt + 1)
                        continue
                    return s, off, result
                except (FloodWait, FloodPremiumWait) as e:
                    flood_count += 1
                    val = e.value if hasattr(e, "value") else 5
                    if val > 10 or flood_count >= 3:
                        window = max(min_win, window - max(1, window // 4))
                        ok_count = 0
                        flood_count = 0
                    await sleep(val + 1)
                except CancelledError:
                    raise
            raise RuntimeError(f"Failed after 3 attempts at offset {off}")

        try:
            while cur <= last_byte or inflight:
                while len(inflight) < window and cur <= last_byte:
                    if self._cancel.is_set():
                        raise CancelledError
                    inflight.add(ensure_future(_req(cur, seq)))
                    cur += csz
                    seq += 1
                if not inflight:
                    break
                done_set, inflight = await wait(inflight, return_when=FIRST_COMPLETED)
                ok_count += len(done_set)
                if ok_count >= window:
                    window = min(window + 2, max_win)
                    ok_count = 0
                for f in done_set:
                    s, roff, chunk = f.result()
                    if not chunk:
                        continue
                    if roff == first_off and roff + csz >= end:
                        chunk = chunk[first_trim:last_byte - roff + 1]
                    elif roff == first_off:
                        chunk = chunk[first_trim:]
                    elif roff + csz > end:
                        chunk = chunk[:end - roff]
                    await queue.put((roff, chunk))
        except CancelledError:
            raise
        except Exception as e:
            if "Flood" in type(e).__name__:
                window = max(min_win, window // 2)
                ok_count = 0
            LOGGER.error(f"HypertgDL pipeline err: {e}")
            raise
        finally:
            for f in inflight:
                if not f.done():
                    f.cancel()

    async def _part(self, start, end, final_path, ci, fid, csz):
        q = Queue(maxsize=self.pipeline_depth + 1)
        err = [None]

        async def _producer():
            try:
                await self._pipeline_fetch(ci, self._location(fid), start, end, fid, q, csz)
            except CancelledError:
                pass
            except Exception as e:
                err[0] = e
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
                    await self._pwrite(fd, chunk, roff)
                    self._obj._processed_bytes += len(chunk)
            finally:
                await to_thread(os.close, fd)

        prod = ensure_future(_producer())
        try:
            await _consumer()
            if err[0] is not None:
                raise err[0]
        except CancelledError:
            prod.cancel()
            raise
        except Exception:
            prod.cancel()
            raise
        finally:
            if not prod.done():
                prod.cancel()

    @staticmethod
    async def _pwrite(fd, data, offset):
        total = len(data)
        written = 0
        while written < total:
            n = await to_thread(os.pwrite, fd, data[written:], offset + written)
            if n == 0:
                raise OSError(f"pwrite returned 0 at offset {offset + written}")
            written += n

    async def handle_download(self):
        self._cancel.clear()
        self._obj._processed_bytes = 0
        dl_start = time()
        await makedirs(self.directory, exist_ok=True)
        final = os.path.abspath(sub("\\\\", "/", os.path.join(self.directory, self.file_name)))

        n_use = min(self.num_parts, self.num_clients)
        cidx = _pick_clients(self.work_loads, self.clients, n_use)

        min_part = 1 * MB
        n_parts = min(n_use, max(1, self.file_size // min_part)) if self.file_size >= min_part else 1
        psz = self.file_size // n_parts if n_parts > 0 else self.file_size
        ranges = [(i * psz, min((i + 1) * psz, self.file_size)) for i in range(n_parts)]
        assigns = [cidx[i % n_use] for i in range(n_parts)]

        unique_clients = set(assigns)
        fid_map = {}
        try:
            for ci in unique_clients:
                fid_map[ci] = await self._fetch_ref(ci, self.clients[ci])
        except Exception as e:
            LOGGER.error(f"HypertgDL ref fail: {e}")
            return None

        first_fid = fid_map[assigns[0]]
        try:
            await self._warmup(unique_clients, first_fid.dc_id)
        except Exception as e:
            LOGGER.warning(f"HypertgDL warmup err: {e}")

        self._tasks = []
        try:
            fd = await to_thread(os.open, final, os.O_WRONLY | os.O_CREAT)
            try:
                await to_thread(os.ftruncate, fd, self.file_size)
            finally:
                await to_thread(os.close, fd)

            for i, (s, e) in enumerate(ranges):
                self._tasks.append(
                    create_task(self._part(s, e, final, assigns[i], fid_map[assigns[i]], self.chunk_size))
                )

            await gather(*self._tasks)
            dl_elapsed = time() - dl_start
            dl_speed = self.file_size / dl_elapsed / MB if dl_elapsed > 0 else 0
            wl_str = " ".join(f"c{k}:{v}" for k, v in sorted(self.work_loads.items()))
            LOGGER.info(
                f"HypertgDL done {self.file_name} "
                f"({self.file_size / MB:.1f}MB {n_parts}p {n_use}c "
                f"pipe={self.pipeline_depth} wl=[{wl_str}] {dl_speed:.1f}MB/s)"
            )
            return final
        except FloodWait:
            raise
        except (CancelledError, StopTransmission):
            return None
        except Exception as e:
            LOGGER.error(f"HypertgDL: {e}")
            return None
        finally:
            self._cancel.set()
            for t in self._tasks:
                if not t.done():
                    t.cancel()
            if self._tasks:
                await gather(*self._tasks, return_exceptions=True)
            await self._close_all()

    async def download_media(self, message, file_name="downloads/", dump_chat=None):
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
                    LOGGER.warning(f"HypertgDL copy fail: {e} (from={message.chat.id} to={dump_chat})")
                    raise RuntimeError(f"Cannot copy to dump chat: {e}") from e
            self.dump_chat = dump_chat or message.chat.id
            self.message = self.message or message
            LOGGER.info(f"HypertgDL init dump={self.dump_chat} msg_id={self.message.id}")
            media = self._media_of(self.message)
            fid_str = media if isinstance(media, str) else media.file_id
            fid_obj = FileId.decode(fid_str)
            ftype = fid_obj.file_type
            mname = media.file_name if hasattr(media, "file_name") else ""
            self.file_size = media.file_size if hasattr(media, "file_size") else 0
            mime = media.mime_type if hasattr(media, "mime_type") else "image/jpeg"
            dt = media.date if hasattr(media, "date") else None
            self.directory, self.file_name = os.path.split(file_name)
            self.file_name = self.file_name or mname or ""
            if not os.path.isabs(self.file_name):
                self.directory = Path(argv[0]).parent / (self.directory or self.download_dir)
            if not self.file_name:
                ext = self._ext(ftype, mime)
                self.file_name = (
                    f"{FileType(ftype).name.lower()}_"
                    f"{(dt or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}_"
                    f"{MsgId()}{ext}"
                )
            return await self.handle_download()
        except Exception as e:
            LOGGER.error(f"HypertgDL download_media: {e}")
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
