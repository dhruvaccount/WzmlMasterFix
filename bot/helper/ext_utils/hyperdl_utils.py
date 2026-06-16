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
from pyrogram.crypto.aes import ctr256_decrypt
from pyrogram.errors import (
    FileMigrate,
    FileReferenceExpired,
    FileReferenceInvalid,
    FileTokenInvalid,
    FloodPremiumWait,
    FloodWait,
    RequestTokenInvalid,
)
from pyrogram.file_id import PHOTO_TYPES, FileId, FileType
from pyrogram.session import Auth, Session
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
        base_pipe = max(Config.HYPER_PIPELINE or _DEFAULT_PIPELINE, _MIN_PIPELINE)
        self.pipeline_depth = max(base_pipe // max(self.num_parts, 1), _MIN_PIPELINE)
        self.message = None
        self.dump_chat = None
        self.directory = None
        self.file_name = ""
        self.file_size = 0
        self.download_dir = "downloads/"
        self._ref_cache = {}
        self._cdn_info = {}
        self._cdn_sessions = {}
        LOGGER.info(
            f"HypertgDL init clients={self.num_clients} "
            f"chunk={self.chunk_size // KB}KB parts={self.num_parts} "
            f"pipeline={self.pipeline_depth}"
        )

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
                    precise=True, cdn_supported=True,
                    location=location, offset=off, limit=csz,
                ),
                sleep_threshold=client.sleep_threshold,
            )
            if isinstance(r, raw.types.upload.File):
                return r.bytes
            if isinstance(r, raw.types.upload.FileCdnRedirect):
                return None, {"cdn_dc": r.dc_id, "file_token": r.file_token,
                              "key": r.encryption_key, "iv": r.encryption_iv}
            raise ValueError(f"Unexpected response type: {type(r)}")
        except FileMigrate as e:
            dc = e.value if hasattr(e, "value") else int(str(e).split()[-1])
            LOGGER.warning(f"HypertgDL FileMigrate dc={dc} client={client.me.username} off={off}")
            if attempt < 3:
                return None, dc
            raise
        except (FileReferenceExpired, FileReferenceInvalid) as e:
            LOGGER.warning(f"HypertgDL {type(e).__name__} client={client.me.username} off={off}")
            if attempt < 3:
                return None, -1
            raise
        except (ConnectionError, OSError, TimeoutError) as e:
            LOGGER.warning(f"HypertgDL {type(e).__name__}: {e} client={client.me.username} off={off}")
            if attempt < 3:
                return None, -2
            raise

    async def _get_cdn_session(self, idx, cdn_dc, client):
        key = (idx, cdn_dc)
        s = self._cdn_sessions.get(key)
        if s and s.is_connected:
            return s
        tm = await client.storage.test_mode()
        ak = await Auth(client, cdn_dc, tm).create()
        s = Session(client, cdn_dc, ak, tm, is_media=True, is_cdn=True)
        await s.start()
        self._cdn_sessions[key] = s
        return s

    async def _cdnpull(self, idx, cdn_info, off, csz):
        client = self.clients[idx]
        cdn_dc = cdn_info["cdn_dc"]
        file_token = cdn_info["file_token"]
        enc_key = cdn_info["key"]
        enc_iv = cdn_info["iv"]
        sess = await self._get_cdn_session(idx, cdn_dc, client)

        for attempt in range(3):
            try:
                r = await sess.invoke(
                    raw.functions.upload.GetCdnFile(
                        file_token=file_token, offset=off, limit=csz,
                    ),
                    sleep_threshold=client.sleep_threshold,
                )
                if isinstance(r, raw.types.upload.CdnFile):
                    chunk = r.bytes
                    iv_mod = bytearray(
                        enc_iv[:-4] + (off // 16).to_bytes(4, "big")
                    )
                    return ctr256_decrypt(chunk, enc_key, iv_mod)
                if isinstance(r, raw.types.upload.CdnFileReuploadNeeded):
                    try:
                        await client.invoke(
                            raw.functions.upload.ReuploadCdnFile(
                                file_token=file_token,
                                request_token=r.request_token,
                            )
                        )
                    except Exception:
                        pass
                    await sleep(1)
                    continue
                raise ValueError(f"Unexpected CDN response: {type(r)}")
            except (FloodWait, FloodPremiumWait) as e:
                val = e.value if hasattr(e, "value") else 5
                LOGGER.warning(f"HypertgDL CDN flood {val}s dc={cdn_dc}")
                await sleep(val + 1)
            except FileTokenInvalid:
                LOGGER.warning(f"HypertgDL CDN FileTokenInvalid dc={cdn_dc} — fallback to non-CDN")
                self._cdn_info.pop(idx, None)
                return None
            except RequestTokenInvalid:
                LOGGER.warning(f"HypertgDL CDN RequestTokenInvalid dc={cdn_dc} — fallback to non-CDN")
                self._cdn_info.pop(idx, None)
                return None
            except (ConnectionError, OSError, TimeoutError) as e:
                LOGGER.warning(f"HypertgDL CDN {type(e).__name__}: {e} dc={cdn_dc}")
                if attempt < 2:
                    try:
                        await sess.stop()
                    except Exception:
                        pass
                    self._cdn_sessions.pop((idx, cdn_dc), None)
                    sess = await self._get_cdn_session(idx, cdn_dc, client)
                    await sleep(1)
        return None

    async def _pipeline_fetch(self, idx, location, start, end, fid, queue, csz):
        cname = self.clients[idx].me.username
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
        timeout_count = 0
        reconn_count = 0
        total_req = 0
        total_off = start

        LOGGER.info(
            f"HypertgDL pipe start idx={idx} client={cname} "
            f"dc={fid.dc_id} range={start}-{end} "
            f"({(end - start) / MB:.1f}MB) window={window} csz={csz}"
        )

        async def _req(off, s):
            nonlocal window, ok_count, flood_count, timeout_count, reconn_count, total_req, sess, loc
            my_sess = sess
            my_loc = loc
            bot_timeouts = 0
            for attempt in range(3):
                try:
                    cdn = self._cdn_info.get(idx)
                    if cdn:
                        chunk = await self._cdnpull(idx, cdn, off, csz)
                        if chunk is not None:
                            total_req += 1
                            return s, off, chunk
                    result = await self._do_req(my_sess, self.clients[idx], my_loc, off, csz, attempt)
                    if isinstance(result, tuple):
                        _, dc_or_ref = result
                        if isinstance(dc_or_ref, dict):
                            self._cdn_info[idx] = dc_or_ref
                            LOGGER.info(
                                f"HypertgDL CDN redirect dc={dc_or_ref['cdn_dc']} "
                                f"client={cname} off={off}"
                            )
                            chunk = await self._cdnpull(idx, dc_or_ref, off, csz)
                            if chunk is not None:
                                total_req += 1
                                return s, off, chunk
                            self._cdn_info.pop(idx, None)
                            await sleep(attempt + 1)
                            continue
                        if dc_or_ref == -1:
                            LOGGER.info(f"HypertgDL ref expired client={cname} off={off} — refreshing")
                            fid_new = await self._fetch_ref(idx, self.clients[idx], force=True)
                            my_loc = self._location(fid_new)
                            await sleep(attempt + 1)
                            continue
                        if dc_or_ref == -2:
                            bot_timeouts += 1
                            LOGGER.warning(
                                f"HypertgDL Timeout attempt {attempt + 1}/3 "
                                f"client={cname} off={off} "
                                f"(bot_timeouts={bot_timeouts}, throttling)"
                            )
                            if bot_timeouts >= 2:
                                halt = 2 ** bot_timeouts
                                LOGGER.info(f"HypertgDL backoff {halt}s client={cname} off={off}")
                                await sleep(halt)
                            continue
                        LOGGER.info(
                            f"HypertgDL FileMigrate dc={dc_or_ref} "
                            f"client={cname} off={off} — migrating"
                        )
                        reconn_count += 1
                        my_sess = await self._get_session(idx, dc_or_ref, force=True)
                        sess = my_sess
                        await sleep(attempt + 1)
                        continue
                    timeout_count = 0
                    total_req += 1
                    return s, off, result
                except (FloodWait, FloodPremiumWait) as e:
                    flood_count += 1
                    val = e.value if hasattr(e, "value") else 5
                    if val > 10 or flood_count >= 3:
                        old = window
                        window = max(min_win, window - max(1, window // 4))
                        ok_count = 0
                        flood_count = 0
                        LOGGER.warning(
                            f"HypertgDL flood window {old}->{window} "
                            f"val={val}s client={cname} off={off}"
                        )
                    await sleep(val + 1)
                except CancelledError:
                    raise
            timeout_count += 1
            if timeout_count >= 3:
                old = window
                window = max(min_win, window - max(1, window // 4))
                timeout_count = 0
                ok_count = 0
                LOGGER.warning(
                    f"HypertgDL timeout window {old}->{window} "
                    f"client={cname} off={off}"
                )
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
                    old = window
                    window = min(window + 2, max_win)
                    if window != old:
                        LOGGER.debug(f"HypertgDL window grow {old}->{window} client={cname}")
                    ok_count = 0
                for f in done_set:
                    s, roff, chunk = f.result()
                    if not chunk:
                        LOGGER.warning(f"HypertgDL empty chunk off={roff} client={cname}")
                        continue
                    if roff == first_off and roff + csz >= end:
                        chunk = chunk[first_trim:last_byte - roff + 1]
                    elif roff == first_off:
                        chunk = chunk[first_trim:]
                    elif roff + csz > end:
                        chunk = chunk[:end - roff]
                    await queue.put((roff, chunk))
            LOGGER.info(
                f"HypertgDL pipe done idx={idx} client={cname} "
                f"range={start}-{end} ({total_req}req {reconn_count}reconn "
                f"final_window={window})"
            )
        except CancelledError:
            raise
        except Exception as e:
            if "Flood" in type(e).__name__:
                window = max(min_win, window // 2)
                ok_count = 0
            LOGGER.error(f"HypertgDL pipeline fail client={cname}: {e}")
            raise
        finally:
            for f in inflight:
                if not f.done():
                    f.cancel()

    async def _part(self, start, end, final_path, ci, fid, csz):
        cname = self.clients[ci].me.username
        psize = end - start
        t0 = time()
        LOGGER.info(
            f"HypertgDL part start ci={ci} client={cname} "
            f"range={start}-{end} ({psize / MB:.1f}MB) path={os.path.basename(final_path)}"
        )
        q = Queue(maxsize=self.pipeline_depth + 1)
        err = [None]
        bytes_written = 0

        async def _producer():
            try:
                await self._pipeline_fetch(ci, self._location(fid), start, end, fid, q, csz)
            except CancelledError:
                LOGGER.info(f"HypertgDL part cancelled ci={ci} client={cname} range={start}-{end}")
            except Exception as e:
                err[0] = e
                LOGGER.error(f"HypertgDL part fail ci={ci} client={cname}: {e}")
            finally:
                await q.put(None)

        async def _consumer():
            nonlocal bytes_written
            fd = await to_thread(os.open, final_path, os.O_WRONLY)
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        break
                    roff, chunk = item
                    await self._pwrite(fd, chunk, roff)
                    self._obj._processed_bytes += len(chunk)
                    bytes_written += len(chunk)
            except Exception as e:
                LOGGER.error(f"HypertgDL consumer err ci={ci}: {e}")
                raise
            finally:
                await to_thread(os.close, fd)

        prod = ensure_future(_producer())
        try:
            await _consumer()
            if err[0] is not None:
                raise err[0]
            elapsed = time() - t0
            speed = bytes_written / elapsed / MB if elapsed > 0 else 0
            LOGGER.info(
                f"HypertgDL part done ci={ci} client={cname} "
                f"range={start}-{end} ({bytes_written / MB:.1f}MB "
                f"{speed:.1f}MB/s {elapsed:.1f}s)"
            )
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
        cnames = [self.clients[i].me.username for i in cidx]
        LOGGER.info(
            f"HypertgDL assign {self.file_name} "
            f"({self.file_size / MB:.1f}MB {n_parts}p {n_use}c "
            f"clients={cnames} dc={self.dump_chat})"
        )
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
            cdn_used = list({v["cdn_dc"] for v in self._cdn_info.values()})
            cdn_str = f" cdn={cdn_used}" if cdn_used else ""
            LOGGER.info(
                f"HypertgDL done {self.file_name} "
                f"({self.file_size / MB:.1f}MB {n_parts}p {n_use}c "
                f"pipe={self.pipeline_depth}{cdn_str} wl=[{wl_str}] {dl_speed:.1f}MB/s)"
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
            for s in self._cdn_sessions.values():
                try:
                    if s.is_connected:
                        await s.stop()
                except Exception:
                    pass
            self._cdn_sessions.clear()
            self._cdn_info.clear()
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
