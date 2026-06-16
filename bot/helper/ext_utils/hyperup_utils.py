import os
from asyncio import Queue, ensure_future, gather, sleep
from hashlib import md5
from math import ceil
from mimetypes import guess_type
from os import path as ospath
from time import time

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

    def __init__(self, obj):
        super().__init__(obj)
        self._up_start = 0
        self._up_file = ""
        self._up_size = 0

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
        t0 = time()
        file_size = ospath.getsize(file_path)
        file_total_parts = ceil(file_size / self.PART_SIZE)
        file_id = client.rnd_id()
        dc_id = await client.storage.dc_id()
        ak = await client.storage.auth_key()
        tm = await client.storage.test_mode()

        is_big = file_size > 10 * MB
        n_workers = 4 if is_big else 1
        LOGGER.info(
            f"HypertgUL upload {os.path.basename(file_path)} "
            f"({file_size / MB:.1f}MB {file_total_parts}p "
            f"workers={n_workers} dc={dc_id})"
        )

        fp = open(file_path, "rb")
        sessions = []
        workers = []
        q = Queue(16)

        try:
            s = Session(client, dc_id, ak, tm, is_media=True)
            await s.start()
            sessions.append(s)

            for _ in range(n_workers):
                workers.append(ensure_future(self._worker(s, q)))

            part = 0
            rpc_fn = raw.functions.upload.SaveBigFilePart if is_big else raw.functions.upload.SaveFilePart
            md5_sum = md5() if not is_big else None

            while True:
                chunk = fp.read(self.PART_SIZE)
                if not chunk:
                    break
                if md5_sum is not None:
                    md5_sum.update(chunk)
                rpc = rpc_fn(
                    file_id=file_id, file_part=part, bytes=chunk,
                    **({"file_total_parts": file_total_parts} if is_big else {}),
                )
                await q.put(rpc)
                self._obj._processed_bytes += len(chunk)
                part += 1

            for _ in workers:
                await q.put(None)
            await gather(*workers)

            up_elapsed = time() - t0
            up_speed = file_size / up_elapsed / MB if up_elapsed > 0 else 0
            LOGGER.info(
                f"HypertgUL file done {os.path.basename(file_path)} "
                f"({file_size / MB:.1f}MB {file_total_parts}p "
                f"{n_workers}w {up_speed:.1f}MB/s {up_elapsed:.1f}s)"
            )

            if is_big:
                return raw.types.InputFileBig(
                    id=file_id, parts=file_total_parts, name=os.path.basename(file_path),
                )
            return raw.types.InputFile(
                id=file_id, parts=file_total_parts,
                name=os.path.basename(file_path), md5_checksum=md5_sum.hexdigest(),
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
            for s in sessions:
                try:
                    if s.is_connected:
                        await s.stop()
                except Exception:
                    pass
            try:
                fp.close()
            except Exception:
                pass

    async def _worker(self, session, q):
        while True:
            rpc = await q.get()
            if rpc is None:
                break
            try:
                await session.send(rpc, wait_response=True)
            except (FloodWait, FloodPremiumWait) as e:
                val = e.value if hasattr(e, "value") else 5
                LOGGER.warning(f"HypertgUL worker flood {val}s dc={session.dc_id}")
                await sleep(val + 1)
                try:
                    await session.send(rpc, wait_response=True)
                except Exception:
                    LOGGER.warning(f"HypertgUL worker flood retry fail dc={session.dc_id}")
            except (TimeoutError, OSError) as e:
                LOGGER.warning(f"HypertgUL worker {type(e).__name__}: {e} dc={session.dc_id}")
            except Exception as e:
                LOGGER.warning(f"HypertgUL worker err: {type(e).__name__}: {e} dc={session.dc_id}")
                break

    async def _upload_small(self, client, file_path):
        file_size = ospath.getsize(file_path)
        file_total_parts = ceil(file_size / self.PART_SIZE)
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
                chunk = fp.read(self.PART_SIZE)
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
            fp.close()

    async def _upload_thumb(self, client, file_path):
        file_size = ospath.getsize(file_path)
        file_id = client.rnd_id()
        file_total_parts = ceil(file_size / self.PART_SIZE)
        fp = open(file_path, "rb")
        h = md5()

        try:
            for part in range(file_total_parts):
                if self._listener.is_cancelled:
                    raise StopTransmission()
                chunk = fp.read(self.PART_SIZE)
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
            fp.close()

    async def _reupload_part(self, client, file_path, input_file, part_num):
        offset = part_num * self.PART_SIZE
        fp = open(file_path, "rb")
        try:
            fp.seek(offset)
            chunk = fp.read(self.PART_SIZE)
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
            fp.close()

    async def upload(
        self, target_client, target_chat_id, file_path, dump_chat_id,
        media_type, attributes, thumb_path=None, caption="", reply_to_message_id=None,
    ):
        self._cancel.clear()
        self._obj._processed_bytes = 0
        self._up_start = time()
        self._up_file = os.path.basename(file_path)
        self._up_size = ospath.getsize(file_path)

        LOGGER.info(
            f"HypertgUL start {self._up_file} "
            f"({self._up_size / MB:.1f}MB) -> chat={target_chat_id}"
        )

        input_file = (
            await self._upload_file(target_client, file_path)
            if self._up_size > 10 * MB
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

        up_elapsed = time() - self._up_start
        up_speed = self._up_size / up_elapsed / MB if up_elapsed > 0 else 0
        LOGGER.info(
            f"HypertgUL done {self._up_file} "
            f"({self._up_size / MB:.1f}MB {up_speed:.1f}MB/s {up_elapsed:.1f}s)"
        )

        return await target_client.get_messages(chat_id=target_chat_id, message_ids=msg_id)

    @staticmethod
    def _mime(path):
        m, _ = guess_type(path)
        return m or "application/octet-stream"
