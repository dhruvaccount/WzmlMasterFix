import asyncio
import logging
import os
import time
import math
from typing import Any, Optional

from plugins.base import UploaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.telegram_uploader")


class TelegramUploader(UploaderPlugin):
    name = "telegram"
    plugin_type = "uploader"

    def __init__(self):
        self._bot = None

    async def initialize(self) -> bool:
        try:
            from bots.clients.telegram.helpers.message_utils import get_telegram_client

            # Use global client if already running
            global_client = get_telegram_client()
            if global_client:
                self._bot = global_client
                logger.info("Telegram uploader using global Pyrogram client")
                return True

            logger.error("No global Pyrogram client found for TelegramUploader")
            return False
        except Exception as e:
            logger.error(f"Telegram init error: {e}")
            return False

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        chat_id = config.get("chat_id") or context.metadata.get("chat_id")
        caption = config.get("caption", "") or context.metadata.get("caption", "")
        thumb = config.get("thumb")

        if not chat_id:
            return PluginResult(success=False, error="Chat ID required")

        file_path = context.source
        if not os.path.exists(file_path):
            return PluginResult(success=False, error="File not found")

        try:
            from core.task import update_task_progress, _task_store

            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()

            # Max Telegram file size limit for bots (usually 2GB, sometimes 4GB for premium/user bots)
            # Assuming standard 2GB for bot or slightly less to be safe
            LIMIT_SIZE = 2 * 1024 * 1024 * 1024 - (10 * 1024 * 1024)  # 1.99 GB

            if file_size > LIMIT_SIZE:
                logger.info(
                    f"File {file_name} is larger than Telegram limit, splitting..."
                )
                parts = await self._split_file(file_path, LIMIT_SIZE)
                if not parts:
                    return PluginResult(success=False, error="Failed to split file")
            else:
                parts = [file_path]

            uploaded_messages = []

            for i, part_path in enumerate(parts):
                part_name = os.path.basename(part_path)
                part_size = os.path.getsize(part_path)
                part_caption = caption
                if len(parts) > 1:
                    part_caption = f"{caption}\n\nPart {i + 1} of {len(parts)}"

                start_time = time.time()
                last_update = start_time

                async def progress_callback(current, total):
                    nonlocal last_update
                    # Check task cancellation
                    t = _task_store.get(context.task_id)
                    if t and t.status.value == "cancelled":
                        raise Exception("Task cancelled by user")

                    now = time.time()
                    if now - last_update > 1.0:
                        speed = current / (now - start_time) if now > start_time else 0
                        eta = (
                            int((total - current) / speed) if speed > 0 and total else 0
                        )
                        pct = (current / total) * 100 if total else 0.0

                        asyncio.create_task(
                            update_task_progress(
                                task_id=context.task_id,
                                stage=f"Uploading Part {i + 1}/{len(parts)}"
                                if len(parts) > 1
                                else "Uploading",
                                plugin=self.name,
                                progress=pct,
                                speed=speed,
                                eta=eta,
                                uploaded=current,
                                total=total,
                            )
                        )
                        last_update = now

                from bots.clients.telegram.helpers.message_utils import send_photo, send_video, send_audio, send_document

                flags = context.metadata.get("flags", {})
                force_document = "-d" in flags or "-doc" in flags or "-document" in flags
                force_media = "-m" in flags or "-med" in flags or "-media" in flags

                logger.info(f"Uploading to Telegram: {part_name}")
                if not force_document and (force_media or file_ext in [".jpg", ".jpeg", ".png", ".gif"]):
                    msg = await send_photo(
                        chat_id=chat_id,
                        photo=part_path,
                        caption=part_caption,
                        progress=progress_callback,
                    )
                elif not force_document and (force_media or file_ext in [".mp4", ".mkv", ".avi", ".mov", ".webm"]):
                    msg = await send_video(
                        chat_id=chat_id,
                        video=part_path,
                        caption=part_caption,
                        progress=progress_callback,
                        supports_streaming=True,
                    )
                elif not force_document and (force_media or file_ext in [".mp3", ".ogg", ".m4a", ".wav", ".flac"]):
                    msg = await send_audio(
                        chat_id=chat_id,
                        audio=part_path,
                        caption=part_caption,
                        progress=progress_callback,
                    )
                else:
                    msg = await send_document(
                        chat_id=chat_id,
                        document=part_path,
                        caption=part_caption,
                        progress=progress_callback,
                    )

                uploaded_messages.append(
                    {
                        "message_id": getattr(
                            msg, "id", getattr(msg, "message_id", None)
                        ),
                        "file_name": part_name,
                    }
                )

                # Cleanup split part if it's not the original file
                if part_path != file_path and os.path.exists(part_path):
                    try:
                        os.remove(part_path)
                    except:
                        pass

            # Return success with info about the first or all parts
            return PluginResult(
                success=True,
                output_path=str(uploaded_messages[0]["message_id"])
                if uploaded_messages
                else "",
                metadata={
                    "messages": uploaded_messages,
                    "chat_id": chat_id,
                    "file_name": file_name,
                    "is_split": len(parts) > 1,
                    "total_parts": len(parts),
                },
            )

        except Exception as e:
            logger.error(f"Telegram upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _split_file(self, file_path: str, chunk_size: int) -> list:
        # Splits a file into parts using chunk size
        try:
            file_name = os.path.basename(file_path)
            dir_name = os.path.dirname(file_path)
            file_size = os.path.getsize(file_path)
            num_parts = math.ceil(file_size / chunk_size)

            parts = []

            # Using asyncio to not block the event loop
            def do_split():
                with open(file_path, "rb") as f:
                    for i in range(num_parts):
                        part_path = os.path.join(dir_name, f"{file_name}.{i + 1:03d}")
                        parts.append(part_path)
                        with open(part_path, "wb") as part_f:
                            chunk = f.read(chunk_size)
                            if chunk:
                                part_f.write(chunk)
                return parts

            return await asyncio.to_thread(do_split)
        except Exception as e:
            logger.error(f"Error splitting file: {e}")
            return []

    async def get_chat(self, chat_id: int) -> Optional[dict]:
        try:
            chat = await self._bot.get_chat(chat_id)
            return {
                "id": chat.id,
                "title": chat.title,
                "username": chat.username,
                "type": str(chat.type),
            }
        except Exception as e:
            logger.error(f"Telegram get chat error: {e}")
            return None

    async def close(self):
        # We don't close the global client
        pass
