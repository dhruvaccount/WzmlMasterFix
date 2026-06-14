from asyncio import BoundedSemaphore, CancelledError, Queue, ensure_future, gather, sleep
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath

from pyrogram import StopTransmission, raw, utils
from pyrogram.errors import BadRequest, FloodPremiumWait, FloodWait
from pyrogram.raw.types import DocumentAttributeFilename
from pyrogram.session import Session

from ... import LOGGER
from ...core.config_manager import Config
from ...core.tg_client import TgClient


class HyperTGUpload:

    PART_SIZE = 512 * 1024
    BIG_FILE = 10 * 1024 * 1024
    POOL_SIZE = Config.HYPERUL_WORKERS
    PIPE = Config.HYPERUL_PIPELINE
    _rr = 0

    def __init__(self, obj):
        self._sem = BoundedSemaphore(self.POOL_SIZE)
        self._obj = obj
        self._listener = self._obj._listener

    def _pick_client(self, fallback):
        if TgClient.helper_bots:
            keys = list(TgClient.helper_bots.keys())
            if keys:
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
        _, client = self._pick_client(target_client)
        file_size = ospath.getsize(file_path)
        if file_size > self.BIG_FILE:
            input_file = await self._upload_file(client, file_path)
        else:
            input_file = await self._upload_small(client, file_path)

        thumb_file = None
        if thumb_path and ospath.exists(thumb_path):
            tsz = ospath.getsize(thumb_path)
            if tsz > 0:
                thumb_file = await self._upload_small(client, thumb_path)

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
            pm = target_client.parse_mode
            if pm is not None:
                try:
                    parser = target_client.parser
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

        peer = await target_client.resolve_peer(target_chat_id)
        rpc = raw.functions.messages.SendMedia(
            peer=peer,
            media=send_media,
            message=text,
            random_id=target_client.rnd_id(),
            reply_to=raw.types.InputReplyToMessage(reply_to_msg_id=reply_to_message_id) if reply_to_message_id else None,
            silent=True,
            entities=entities,
        )
        for attempt in range(3):
            try:
                r_updates = await target_client.invoke(rpc)
                break
            except (FloodWait, FloodPremiumWait) as e:
                if attempt == 2:
                    raise
                await sleep(getattr(e, "value", 5) + 1)
        parsed = await utils.parse_messages(target_client, r_updates)
        if isinstance(parsed, list):
            if parsed:
                return parsed[0]
            raise ValueError("parse_messages returned empty list")
        return parsed

    async def _upload_file(self, client, file_path):
        fp = open(file_path, "rb")
        fp.seek(0, 2)
        file_size = fp.tell()
        fp.seek(0)

        part_size = self.PART_SIZE
        file_total_parts = ceil(file_size / part_size)
        file_id = client.rnd_id()

        auth_key = await client.storage.auth_key()
        dc_id = await client.storage.dc_id()
        test_mode = await client.storage.test_mode()

        if file_size < 50 * 1024 * 1024:
            n_sessions = max(2, self.POOL_SIZE // 2)
            n_workers = 3
        elif file_size < 500 * 1024 * 1024:
            n_sessions = self.POOL_SIZE
            n_workers = 6
        else:
            n_sessions = self.POOL_SIZE
            n_workers = 8

        sessions = []
        for _ in range(n_sessions):
            s = Session(client, dc_id, auth_key, test_mode, is_media=True)
            await s.start()
            sessions.append(s)

        q = Queue(self.PIPE)

        async def _worker(sesh):
            while True:
                rpc = await q.get()
                if rpc is None:
                    break
                for attempt in range(3):
                    try:
                        await sesh.invoke(rpc)
                        break
                    except (FloodWait, FloodPremiumWait) as e:
                        await sleep(getattr(e, "value", 5) + 1)
                    except CancelledError:
                        raise
                    except Exception:
                        if attempt == 2:
                            raise
                        await sleep(1 * (attempt + 1))

        workers = []
        for s in sessions:
            for _ in range(n_workers):
                workers.append(ensure_future(_worker(s)))

        obj = self._obj
        listener = self._listener

        try:
            for part in range(file_total_parts):
                if listener.is_cancelled:
                    raise StopTransmission()
                chunk = fp.read(part_size)
                if not chunk:
                    break
                await q.put(raw.functions.upload.SaveBigFilePart(
                    file_id=file_id,
                    file_part=part,
                    file_total_parts=file_total_parts,
                    bytes=chunk,
                ))
                obj._processed_bytes += len(chunk)

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
            for s in sessions:
                try:
                    if s.is_connected:
                        await s.stop()
                except Exception:
                    pass
            fp.close()

    async def _upload_small(self, client, file_path):
        fp = open(file_path, "rb")
        fp.seek(0, 2)
        file_size = fp.tell()
        fp.seek(0)

        part_size = self.PART_SIZE
        file_total_parts = ceil(file_size / part_size)
        file_id = client.rnd_id()

        auth_key = await client.storage.auth_key()
        dc_id = await client.storage.dc_id()
        test_mode = await client.storage.test_mode()

        s = Session(client, dc_id, auth_key, test_mode, is_media=False)
        await s.start()

        obj = self._obj
        listener = self._listener

        try:
            for part in range(file_total_parts):
                if listener.is_cancelled:
                    raise StopTransmission()
                chunk = fp.read(part_size)
                if not chunk:
                    break
                await s.invoke(raw.functions.upload.SaveFilePart(
                    file_id=file_id,
                    file_part=part,
                    bytes=chunk,
                ))
                obj._processed_bytes += len(chunk)
            fp.seek(0)
            md5_sum = md5(fp.read()).hexdigest()
            return raw.types.InputFile(
                id=file_id,
                parts=file_total_parts,
                name=ospath.basename(file_path),
                md5_checksum=md5_sum,
            )
        finally:
            try:
                if s.is_connected:
                    await s.stop()
            except Exception:
                pass
            fp.close()

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
