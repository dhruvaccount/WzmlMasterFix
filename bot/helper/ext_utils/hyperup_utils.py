import os
from asyncio import Lock, Queue, ensure_future, gather, sleep
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath

import aiofiles
from aiofiles.os import path as aiopath
from pyrogram import StopTransmission, raw
from pyrogram.errors import BadRequest, FilePartMissing, FloodPremiumWait, FloodWait
from pyrogram.raw.types import DocumentAttributeFilename
from pyrogram.session import Session

from ... import LOGGER
from ..telegram_helper.tg_transfer import HypertgTransfer, MB

KB = 1024
GB = 1024 * MB


class HypertgUpload(HypertgTransfer):
    PART_SIZE = 512 * KB
    READ_BUFFER = 4 * MB
    PIPE = 16

    _rr = 0
    _rr_lock = Lock()
    _session_pool: dict = {}
    _pool_lock = Lock()

    @classmethod
    async def _acquire(cls, client, n, dc_id, ak, tm):
        key = (id(client), dc_id)
        sessions = []
        stale = []
        async with cls._pool_lock:
            pool = cls._session_pool.setdefault(key, [])
            while pool and len(sessions) < n:
                s = pool.pop()
                if s.is_connected:
                    sessions.append(s)
                else:
                    stale.append(s)
            needed = n - len(sessions)
        for s in stale:
            try:
                await s.stop()
            except Exception:
                pass
        if needed > 0:
            new = [Session(client, dc_id, ak, tm, is_media=True) for _ in range(needed)]
            results = await gather(*[s.start() for s in new], return_exceptions=True)
            for s, r in zip(new, results):
                if not isinstance(r, Exception):
                    sessions.append(s)
        if not sessions:
            raise RuntimeError("No sessions available for upload")
        return sessions

    @classmethod
    async def _release(cls, client, sessions, dc_id):
        if not sessions:
            return
        key = (id(client), dc_id)
        async with cls._pool_lock:
            cls._session_pool.setdefault(key, []).extend(sessions)

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
        file_size = await aiopath.getsize(file_path)
        file_total_parts = ceil(file_size / self.PART_SIZE)
        file_id = client.rnd_id()
        ak = await client.storage.auth_key()
        dc_id = await client.storage.dc_id()
        tm = await client.storage.test_mode()

        if file_size < 5 * MB:
            n_sessions, n_workers = 1, 2
        elif file_size < 100 * MB:
            n_sessions, n_workers = min(2, 8), 3
        elif file_size < 300 * MB:
            n_sessions, n_workers = min(3, 8), 4
        elif file_size < 500 * MB:
            n_sessions, n_workers = min(4, 8), 5
        elif file_size < GB:
            n_sessions, n_workers = min(6, 8), 6
        else:
            n_sessions, n_workers = 8, 8
        n_workers = min(n_workers, file_total_parts)

        fp = None
        sessions = None
        workers = []

        try:
            fp = await aiofiles.open(file_path, "rb")
            sessions = await self._acquire(client, n_sessions, dc_id, ak, tm)
            q = Queue(self.PIPE)

            async def _worker(sesh):
                while True:
                    rpc = await q.get()
                    if rpc is None:
                        break
                    for attempt in range(5):
                        try:
                            await sesh.send(rpc, wait_response=True)
                            break
                        except (FloodWait, FloodPremiumWait) as e:
                            await sleep(e.value + 1)
                        except CancelledError:
                            raise
                        except Exception:
                            if attempt == 4:
                                raise
                            await sleep(2 ** attempt)

            for s in sessions:
                for _ in range(n_workers):
                    workers.append(ensure_future(_worker(s)))

            pbs = self.READ_BUFFER // self.PART_SIZE
            part = 0
            next_buf = ensure_future(fp.read(self.READ_BUFFER))

            while part < file_total_parts:
                if self._listener.is_cancelled:
                    raise StopTransmission()
                buf = await next_buf
                if not buf:
                    break
                if part + pbs < file_total_parts:
                    next_buf = ensure_future(fp.read(self.READ_BUFFER))
                for offset in range(0, len(buf), self.PART_SIZE):
                    chunk = buf[offset:offset + self.PART_SIZE]
                    if not chunk:
                        break
                    if all(t.done() for t in workers):
                        for t in workers:
                            exc = t.exception()
                            if exc is not None:
                                raise exc
                        raise RuntimeError("All upload workers exited")
                    await q.put(raw.functions.upload.SaveBigFilePart(
                        file_id=file_id, file_part=part,
                        file_total_parts=file_total_parts, bytes=chunk,
                    ))
                    self._obj._processed_bytes += len(chunk)
                    part += 1

            for _ in workers:
                await q.put(None)
            await gather(*workers)
            return raw.types.InputFileBig(
                id=file_id, parts=file_total_parts, name=os.path.basename(file_path),
            )
        except StopTransmission:
            raise
        except Exception as e:
            LOGGER.error(f"HypertgUL upload fail: {e}")
            raise
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()
            await gather(*workers, return_exceptions=True)
            try:
                if next_buf is not None and not next_buf.done():
                    next_buf.cancel()
            except Exception:
                pass
            if sessions:
                good = [s for s in sessions if s.is_connected]
                bad = [s for s in sessions if not s.is_connected]
                await self._release(client, good, dc_id)
                for s in bad:
                    try:
                        await s.stop()
                    except Exception:
                        pass
            if fp:
                await fp.close()

    async def _upload_small(self, client, file_path):
        file_size = await aiopath.getsize(file_path)
        file_total_parts = ceil(file_size / self.PART_SIZE)
        file_id = client.rnd_id()
        ak = await client.storage.auth_key()
        dc_id = await client.storage.dc_id()
        tm = await client.storage.test_mode()
        s = Session(client, dc_id, ak, tm, is_media=False)
        fp = await aiofiles.open(file_path, "rb")
        h = md5()

        try:
            await s.start()
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    raise StopTransmission()
                chunk = await fp.read(self.PART_SIZE)
                if not chunk:
                    break
                h.update(chunk)
                await s.send(raw.functions.upload.SaveFilePart(
                    file_id=file_id, file_part=part, bytes=chunk,
                ), wait_response=True)
                self._obj._processed_bytes += len(chunk)
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=os.path.basename(file_path), md5_checksum=h.hexdigest(),
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
        fp = await aiofiles.open(file_path, "rb")
        h = md5()

        try:
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    raise StopTransmission()
                chunk = await fp.read(self.PART_SIZE)
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
            await fp.close()

    async def _reupload_part(self, client, file_path, input_file, part_num):
        offset = part_num * self.PART_SIZE
        fp = await aiofiles.open(file_path, "rb")
        try:
            await fp.seek(offset)
            chunk = await fp.read(self.PART_SIZE)
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
            await fp.close()

    async def upload(
        self, target_client, target_chat_id, file_path, dump_chat_id,
        media_type, attributes, thumb_path=None, caption="", reply_to_message_id=None,
    ):
        self._cancel.clear()
        self._obj._processed_bytes = 0

        file_size = ospath.getsize(file_path)
        input_file = (
            await self._upload_file(target_client, file_path)
            if file_size > 10 * MB
            else await self._upload_small(target_client, file_path)
        )

        thumb_file = None
        if thumb_path and ospath.exists(thumb_path) and ospath.getsize(thumb_path) > 0:
            thumb_file = await self._upload_thumb(target_client, thumb_path)

        mime_type = self._mime(file_path)
        input_media = self._build_media(input_file, mime_type, media_type, attributes, thumb_file)

        for attempt in range(3):
            try:
                r = await target_client.invoke(raw.functions.messages.UploadMedia(
                    peer=await target_client.resolve_peer(dump_chat_id),
                    media=input_media,
                ))
                break
            except FilePartMissing as e:
                part = int(str(e).split("_")[-1]) if "_" in str(e) else 0
                await self._reupload_part(target_client, file_path, input_file, part)
            except BadRequest:
                if attempt == 2 or media_type == "document":
                    raise
                doc_attrs = [a for a in (attributes or []) if isinstance(a, DocumentAttributeFilename)]
                if not doc_attrs:
                    doc_attrs = [DocumentAttributeFilename(file_name=ospath.basename(file_path))]
                input_media = raw.types.InputMediaUploadedDocument(
                    file=input_file, thumb=thumb_file,
                    mime_type=mime_type or "application/octet-stream",
                    attributes=doc_attrs, nosound_video=False, force_file=True,
                )
            except (FloodWait, FloodPremiumWait) as e:
                if attempt == 2:
                    raise
                await sleep(e.value + 1)

        if isinstance(r, raw.types.MessageMediaDocument):
            doc = r.document
        elif isinstance(r, raw.types.MessageMediaPhoto):
            doc = r.photo
        else:
            raise ValueError(f"Unexpected UploadMedia response: {type(r)}")

        text = caption or ""
        entities = None
        if caption:
            pm = target_client.parse_mode
            if pm is not None:
                try:
                    parser = target_client.parser
                    if parser is not None:
                        parsed = await parser.parse(caption, pm)
                        text = parsed["message"]
                        entities = parsed["entities"]
                except Exception:
                    pass

        if isinstance(doc, raw.types.Document):
            send_media = raw.types.InputMediaDocument(
                id=raw.types.InputDocument(id=doc.id, access_hash=doc.access_hash, file_reference=doc.file_reference),
            )
        elif isinstance(doc, raw.types.Photo):
            send_media = raw.types.InputMediaPhoto(
                id=raw.types.InputPhoto(id=doc.id, access_hash=doc.access_hash, file_reference=doc.file_reference),
            )
        else:
            raise ValueError(f"Unexpected doc type: {type(doc)}")

        peer = await target_client.resolve_peer(target_chat_id)
        rpc = raw.functions.messages.SendMedia(
            peer=peer, media=send_media, message=text,
            random_id=target_client.rnd_id(),
            reply_to=raw.types.InputReplyToMessage(reply_to_msg_id=reply_to_message_id)
            if reply_to_message_id else None,
            silent=True, entities=entities,
        )
        for attempt in range(5):
            try:
                r_updates = await target_client.invoke(rpc)
                break
            except FilePartMissing as e:
                part = int(str(e).split("_")[-1]) if "_" in str(e) else 0
                await self._reupload_part(target_client, file_path, input_file, part)
            except (FloodWait, FloodPremiumWait) as e:
                if attempt == 4:
                    raise
                await sleep(e.value + 1)
        for u in r_updates.updates:
            if isinstance(u, (raw.types.UpdateNewMessage, raw.types.UpdateNewChannelMessage, raw.types.UpdateNewScheduledMessage)):
                msg_id = u.message.id
                break
        else:
            raise ValueError("No UpdateNewMessage in SendMedia response")
        return await target_client.get_messages(chat_id=target_chat_id, message_ids=msg_id)

    @staticmethod
    def _mime(path):
        m, _ = guess_type(path)
        return m or "application/octet-stream"
