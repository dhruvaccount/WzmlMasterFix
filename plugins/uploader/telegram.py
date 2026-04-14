import asyncio
import logging
import os
import time
from typing import Any, Optional

try:
    import pyrogram
    from pyrogram import Client, types
except ImportError:
    raise ImportError("pyrogram required: pip install pyrotgfork")

from plugins.base import UploaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError

logger = logging.getLogger("wzml.telegram_uploader")


class TelegramUploader(UploaderPlugin):
    name = "telegram"
    plugin_type = "uploader"

    def __init__(self):
        self._bot: Optional[Client] = None

    async def initialize(self, bot_token: str = None) -> bool:
        try:
            from bots.clients.telegram.helpers.message_utils import get_telegram_client

            # Use global client if already running
            global_client = get_telegram_client()
            if global_client:
                self._bot = global_client
                me = await self._bot.get_me()
                logger.info(f"Telegram uploader using global client: @{me.username}")
                return True

            from config import get_config

            cfg = get_config()
            token = bot_token or cfg.telegram.BOT_TOKEN

            if token:
                self._bot = Client(
                    name="wzml_uploader",
                    api_id=cfg.telegram.API,
                    api_hash=cfg.telegram.HASH,
                    bot_token=token,
                )
                await self._bot.start()
                me = await self._bot.get_me()
                logger.info(
                    f"Telegram uploader initialized local client: @{me.username}"
                )
                return True
            else:
                logger.warning("No bot token provided")
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
            from core.task import update_task_progress

            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            start_time = time.time()
            last_update = start_time

            async def progress_callback(current, total):
                nonlocal last_update
                now = time.time()
                if now - last_update > 1.0:
                    speed = current / (now - start_time) if now > start_time else 0
                    eta = int((total - current) / speed) if speed > 0 and total else 0
                    pct = (current / total) * 100 if total else 0.0

                    await update_task_progress(
                        task_id=context.task_id,
                        stage="Uploading",
                        plugin=self.name,
                        progress=pct,
                        speed=speed,
                        eta=eta,
                        uploaded=current,
                        total=total,
                    )
                    last_update = now

            if file_ext in [".jpg", ".jpeg", ".png", ".gif"]:
                msg = await self._bot.send_photo(
                    chat_id=chat_id,
                    photo=file_path,
                    caption=caption,
                    progress=progress_callback,
                )
            elif file_ext in [".mp4", ".mkv", ".avi", ".mov"]:
                msg = await self._bot.send_video(
                    chat_id=chat_id,
                    video=file_path,
                    caption=caption,
                    progress=progress_callback,
                )
            elif file_ext in [".mp3", ".ogg", ".m4a", ".wav"]:
                msg = await self._bot.send_audio(
                    chat_id=chat_id,
                    audio=file_path,
                    caption=caption,
                    progress=progress_callback,
                )
            elif file_ext in [".pdf", ".doc", ".docx", ".txt"]:
                msg = await self._bot.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=caption,
                    progress=progress_callback,
                )
            else:
                msg = await self._bot.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=caption,
                    progress=progress_callback,
                )

            return PluginResult(
                success=True,
                output_path=str(msg.id),
                metadata={
                    "message_id": msg.id,
                    "chat_id": msg.chat.id,
                    "file_name": file_name,
                },
            )

        except Exception as e:
            logger.error(f"Telegram upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def upload_with_progress(
        self, file_path: str, chat_id: int, caption: str = ""
    ) -> Optional[dict]:
        try:
            msg = await self._bot.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
            )
            return {
                "message_id": msg.id,
                "chat_id": msg.chat.id,
            }
        except Exception as e:
            logger.error(f"Telegram progress upload error: {e}")
            return None

    async def send_message(
        self, chat_id: int, text: str, reply_markup: Any = None
    ) -> Optional[dict]:
        try:
            msg = await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            return {"message_id": msg.id, "chat_id": msg.chat.id}
        except Exception as e:
            logger.error(f"Telegram send message error: {e}")
            return None

    async def send_media_group(self, chat_id: int, media: list) -> Optional[list]:
        try:
            media_group = []
            for m in media:
                media_group.append(m["path"])

            messages = await self._bot.send_media_group(
                chat_id=chat_id,
                media=media_group,
            )
            return [{"message_id": m.id, "chat_id": m.chat.id} for m in messages]
        except Exception as e:
            logger.error(f"Telegram media group error: {e}")
            return None

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: Any = None
    ) -> bool:
        try:
            await self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return True
        except Exception as e:
            logger.error(f"Telegram edit error: {e}")
            return False

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        try:
            await self._bot.delete_messages(
                chat_id=chat_id,
                message_ids=[message_id],
            )
            return True
        except Exception as e:
            logger.error(f"Telegram delete error: {e}")
            return False

    async def forward_message(
        self, from_chat_id: int, to_chat_id: int, message_id: int
    ) -> Optional[dict]:
        try:
            msg = await self._bot.forward_messages(
                chat_id=to_chat_id,
                from_chat_id=from_chat_id,
                message_ids=[message_id],
            )
            return {"message_id": msg[0].id, "chat_id": msg[0].chat.id}
        except Exception as e:
            logger.error(f"Telegram forward error: {e}")
            return None

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

    async def get_me(self) -> Optional[dict]:
        try:
            me = await self._bot.get_me()
            return {
                "id": me.id,
                "username": me.username,
                "first_name": me.first_name,
            }
        except Exception as e:
            logger.error(f"Telegram get me error: {e}")
            return None

    async def close(self):
        if self._bot:
            await self._bot.stop()
            self._bot = None
