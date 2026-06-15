from asyncio import BoundedSemaphore, CancelledError, Lock, Queue, ensure_future, gather, sleep
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath

import aiofiles
from aiofiles.os import path as aiopath

import socket

from pyrogram import StopTransmission, raw
from pyrogram.connection.transport.tcp.tcp import TCP
from pyrogram.errors import BadRequest, FloodPremiumWait, FloodWait
from pyrogram.raw.types import DocumentAttributeFilename
from pyrogram.session import Session
from pyrogram.session.internals import DataCenter

from ... import LOGGER
from ...core.config_manager import Config
from ...core.tg_client import TgClient


_orig_tcp_connect = TCP.connect


async def _tcp_tuned_connect(self, address):
    await _orig_tcp_connect(self, address)
    sock = None
    if self.writer:
        try:
            sock = self.writer.get_extra_info("socket")
        except Exception:
            pass
    if sock:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            except OSError:
                pass
        except OSError:
            pass


TCP.connect = _tcp_tuned_connect


_orig_dc_new = DataCenter.__new__


def _dc_alt_port(cls, dc_id, test_mode, ipv6, media):
    ip, port = _orig_dc_new(cls, dc_id, test_mode, ipv6, media)
    if media and not test_mode:
        port = 5222
    return ip, port


DataCenter.__new__ = staticmethod(_dc_alt_port)


class HyperTGUpload:

    PART_SIZE = 512 * 1024
    READ_BUFFER = 4 * 1024 * 1024
    BIG_FILE = 10 * 1024 * 1024
    POOL_SIZE = Config.HYPERUL_WORKERS
    PIPE = Config.HYPERUL_PIPELINE
    _rr = 0
    _rr_lock = Lock()
    _session_pool: dict = {}
    _session_pool_lock = Lock()

    @classmethod
    async def _acquire_sessions(cls, client, n_sessions, dc_id, auth_key, test_mode):
        key = (id(client), dc_id)
        sessions = []
        stale = []
        async with cls._session_pool_lock:
            pool = cls._session_pool.setdefault(key, [])
            while pool and len(sessions) < n_sessions:
                s = pool.pop()
                if s.is_connected:
                    sessions.append(s)
                else:
                    stale.append(s)
            needed = n_sessions - len(sessions)
        for s in stale:
            try:
                await s.stop()
            except Exception:
                pass
        if needed > 0:
            new = [Session(client, dc_id, auth_key, test_mode, is_media=True) for _ in range(needed)]
            results = await gather(*[s.start() for s in new], return_exceptions=True)
            for s, r in zip(new, results):
                if isinstance(r, Exception):
                    LOGGER.warning(f"Session start failed: {r}")
                else:
                    sessions.append(s)
        if not sessions:
            raise RuntimeError("No sessions available for upload")
        return sessions

    @classmethod
    async def _release_sessions(cls, client, sessions, dc_id=None):
        if not sessions:
            return
        if dc_id is None:
            dc_id = await sessions[0].storage.dc_id()
        key = (id(client), dc_id)
        async with cls._session_pool_lock:
            cls._session_pool.setdefault(key, []).extend(sessions)

    def __init__(self, obj):
        self._sem = BoundedSemaphore(self.POOL_SIZE)
        self._obj = obj
        self._listener = self._obj._listener

    async def _pick_client(self, fallback):
        if TgClient.helper_bots:
            keys = list(TgClient.helper_bots.keys())
            if keys:
                async with self._rr_lock:
                    i = self._rr % len(keys)
                    type(self)._rr = i + 1
                return keys[i], TgClient.helper_bots[keys[i]]
        return -1, fallback

    async def upload(self, target_client, target_chat_id, file_path, dump_chat_id,
                     media_type, attributes, thumb_path=None,
                     caption="", reply_to_message_id=None):
        async with self._sem:
            return await self._upload_one(
                target_client, target_chat_id, file_path, dump_chat_id,
                media_type, attributes, thumb_path, caption,
                reply_to_message_id,
            )

    async def _upload_one(self, target_client, target_chat_id, file_path, dump_chat_id,
                          media_type, attributes, thumb_path=None,
                          caption="", reply_to_message_id=None):
        _, client = await self._pick_client(target_client)
        file_size = ospath.getsize(file_path)
        if file_size > self.BIG_FILE:
            input_file = await self._upload_file(client, file_path)
        else:
            input_file = await self._upload_small(client, file_path)

        thumb_file = None
        if thumb_path and ospath.exists(thumb_path):
            tsz = ospath.getsize(thumb_path)
            if tsz > 0:
                thumb_file = await self._upload_thumb(client, thumb_path)

        mime_type = self._mime(file_path)
        input_media = self._build_media(input_file, mime_type, media_type, attributes, thumb_file)

        for attempt in range(3):
            try:
                r = await client.invoke(
                    raw.functions.messages.UploadMedia(
                        peer=await client.resolve_peer(dump_chat_id),
                        media=input_media,
                    )
                )
                break
            except BadRequest:
                if attempt == 2 or media_type == "document":
                    raise
                doc_attrs = [a for a in (attributes or []) if isinstance(a, DocumentAttributeFilename)]
                if not doc_attrs:
                    doc_attrs = [DocumentAttributeFilename(file_name=ospath.basename(file_path))]
                input_media = raw.types.InputMediaUploadedDocument(
                    file=input_file,
                    thumb=thumb_file,
                    mime_type=mime_type or "application/octet-stream",
                    attributes=doc_attrs,
                    nosound_video=False,
                    force_file=True,
                )
            except (FloodWait, FloodPremiumWait) as e:
                if attempt == 2:
                    raise
                await sleep(getattr(e, "value", 5) + 1)

        if isinstance(r, raw.types.MessageMediaDocument):
            doc = r.document
        elif isinstance(r, raw.types.MessageMediaPhoto):
            doc = r.photo
        else:
            raise ValueError(f"Unexpected UploadMedia response: {type(r)}")

        text = caption or ""
        entities = None
        if caption:
            pm = client.parse_mode
            if pm is not None:
                try:
                    parser = client.parser
                    if parser is not None:
                        parsed = await parser.parse(caption, pm)
                        text = parsed['message']
                        entities = parsed['entities']
                except Exception:
                    pass

        if isinstance(doc, raw.types.Document):
            send_media = raw.types.InputMediaDocument(
                id=raw.types.InputDocument(
                    id=doc.id,
                    access_hash=doc.access_hash,
                    file_reference=doc.file_reference,
                ),
            )
        elif isinstance(doc, raw.types.Photo):
            send_media = raw.types.InputMediaPhoto(
                id=raw.types.InputPhoto(
                    id=doc.id,
                    access_hash=doc.access_hash,
                    file_reference=doc.file_reference,
                ),
            )
        else:
            raise ValueError(f"Unexpected doc type: {type(doc)}")

        peer = await client.resolve_peer(target_chat_id)
        rpc = raw.functions.messages.SendMedia(
            peer=peer,
            media=send_media,
            message=text,
            random_id=client.rnd_id(),
            reply_to=raw.types.InputReplyToMessage(reply_to_msg_id=reply_to_message_id) if reply_to_message_id else None,
            silent=True,
            entities=entities,
        )
        for attempt in range(3):
            try:
                r_updates = await client.invoke(rpc)
                break
            except (FloodWait, FloodPremiumWait) as e:
                if attempt == 2:
                    raise
                await sleep(getattr(e, "value", 5) + 1)
        for u in r_updates.updates:
            if isinstance(u, (
                raw.types.UpdateNewMessage,
                raw.types.UpdateNewChannelMessage,
                raw.types.UpdateNewScheduledMessage,
            )):
                msg_id = u.message.id
                break
        else:
            raise ValueError("No UpdateNewMessage in SendMedia response")
        return await client.get_messages(chat_id=target_chat_id, message_ids=msg_id)

    async def _upload_file(self, client, file_path):
        file_size = await aiopath.getsize(file_path)
        part_size = self.PART_SIZE
        file_total_parts = ceil(file_size / part_size)
        file_id = client.rnd_id()

        auth_key = await client.storage.auth_key()
        dc_id = await client.storage.dc_id()
        test_mode = await client.storage.test_mode()

        if file_size < 5 * 1024 * 1024:
            n_sessions = 1
            n_workers = 2
        elif file_size < 100 * 1024 * 1024:
            n_sessions = min(2, self.POOL_SIZE)
            n_workers = 3
        elif file_size < 300 * 1024 * 1024:
            n_sessions = min(3, self.POOL_SIZE)
            n_workers = 4
        elif file_size < 500 * 1024 * 1024:
            n_sessions = min(4, self.POOL_SIZE)
            n_workers = 5
        elif file_size < 1024 * 1024 * 1024:
            n_sessions = min(6, self.POOL_SIZE)
            n_workers = 6
        else:
            n_sessions = self.POOL_SIZE
            n_workers = 8
        n_workers = min(n_workers, file_total_parts)

        fp = None
        sessions = None
        workers = []
        next_buf_task = None

        try:
            fp = await aiofiles.open(file_path, "rb")
            sessions = await self._acquire_sessions(client, n_sessions, dc_id, auth_key, test_mode)

            q = Queue(self.PIPE)

            async def _worker(sesh):
                while True:
                    rpc = await q.get()
                    if rpc is None:
                        break
                    for attempt in range(5):
                        try:
                            await sesh.invoke(rpc)
                            break
                        except (FloodWait, FloodPremiumWait) as e:
                            await sleep(getattr(e, "value", 5) + 1)
                        except CancelledError:
                            raise
                        except Exception:
                            if attempt == 4:
                                raise
                            await sleep(2 ** attempt)

            for s in sessions:
                for _ in range(n_workers):
                    workers.append(ensure_future(_worker(s)))

            obj = self._obj
            listener = self._listener

            parts_per_buffer = self.READ_BUFFER // self.PART_SIZE
            part = 0
            next_buf_task = ensure_future(fp.read(self.READ_BUFFER))

            while part < file_total_parts:
                if listener.is_cancelled:
                    raise StopTransmission()
                buffer = await next_buf_task
                if not buffer:
                    break
                if part + parts_per_buffer < file_total_parts:
                    next_buf_task = ensure_future(fp.read(self.READ_BUFFER))
                for offset in range(0, len(buffer), self.PART_SIZE):
                    chunk = buffer[offset:offset + self.PART_SIZE]
                    if not chunk:
                        break
                    if all(t.done() for t in workers):
                        for t in workers:
                            exc = t.exception()
                            if exc is not None:
                                raise exc
                        raise RuntimeError("All upload workers exited")
                    await q.put(raw.functions.upload.SaveBigFilePart(
                        file_id=file_id,
                        file_part=part,
                        file_total_parts=file_total_parts,
                        bytes=chunk,
                    ))
                    obj._processed_bytes += len(chunk)
                    part += 1

            for _ in workers:
                await q.put(None)
            await gather(*workers)

            return raw.types.InputFileBig(
                id=file_id,
                parts=file_total_parts,
                name=ospath.basename(file_path),
            )
        except StopTransmission:
            raise
        except Exception as e:
            LOGGER.error(f"HyperUL upload fail: {e}")
            raise
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()
            await gather(*workers, return_exceptions=True)
            try:
                if next_buf_task is not None and not next_buf_task.done():
                    next_buf_task.cancel()
            except Exception:
                pass
            if sessions:
                good = [s for s in sessions if s.is_connected]
                bad = [s for s in sessions if not s.is_connected]
                await self._release_sessions(client, good, dc_id)
                for s in bad:
                    try:
                        await s.stop()
                    except Exception:
                        pass
            if fp:
                await fp.close()

    async def _upload_small(self, client, file_path):
        file_size = await aiopath.getsize(file_path)
        part_size = self.PART_SIZE
        file_total_parts = ceil(file_size / part_size)
        file_id = client.rnd_id()

        auth_key = await client.storage.auth_key()
        dc_id = await client.storage.dc_id()
        test_mode = await client.storage.test_mode()

        s = Session(client, dc_id, auth_key, test_mode, is_media=False)
        fp = await aiofiles.open(file_path, "rb")
        md5_hash = md5()

        try:
            await s.start()

            obj = self._obj
            listener = self._listener

            for part in range(file_total_parts):
                if listener.is_cancelled:
                    raise StopTransmission()
                chunk = await fp.read(part_size)
                if not chunk:
                    break
                md5_hash.update(chunk)
                await s.invoke(raw.functions.upload.SaveFilePart(
                    file_id=file_id,
                    file_part=part,
                    bytes=chunk,
                ))
                obj._processed_bytes += len(chunk)
            return raw.types.InputFile(
                id=file_id,
                parts=file_total_parts,
                name=ospath.basename(file_path),
                md5_checksum=md5_hash.hexdigest(),
            )
        finally:
            try:
                if s.is_connected:
                    await s.stop()
            except Exception:
                pass
            await fp.close()

    async def _upload_thumb(self, client, file_path):
        file_size = await aiopath.getsize(file_path)
        file_id = client.rnd_id()
        file_total_parts = ceil(file_size / self.PART_SIZE)

        obj = self._obj
        listener = self._listener
        fp = await aiofiles.open(file_path, "rb")
        md5_hash = md5()

        try:
            for part in range(file_total_parts):
                if listener.is_cancelled:
                    raise StopTransmission()
                chunk = await fp.read(self.PART_SIZE)
                if not chunk:
                    break
                md5_hash.update(chunk)
                await client.invoke(raw.functions.upload.SaveFilePart(
                    file_id=file_id,
                    file_part=part,
                    bytes=chunk,
                ))
                obj._processed_bytes += len(chunk)
            return raw.types.InputFile(
                id=file_id,
                parts=file_total_parts,
                name=ospath.basename(file_path),
                md5_checksum=md5_hash.hexdigest(),
            )
        finally:
            await fp.close()

    def _mime(self, path):
        m, _ = guess_type(path)
        return m or "application/octet-stream"

    def _build_media(self, input_file, mime_type, media_type, attributes, thumb_file=None):
        if media_type == "photo":
            return raw.types.InputMediaUploadedPhoto(file=input_file)
        nosound = media_type == "video" and "video" in (mime_type or "")
        force = media_type == "document"
        return raw.types.InputMediaUploadedDocument(
            file=input_file,
            thumb=thumb_file,
            mime_type=mime_type or "application/octet-stream",
            attributes=attributes or [],
            nosound_video=nosound,
            force_file=force,
        )
