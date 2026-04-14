import asyncio
import logging
import os
from typing import Any, Optional

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.telegram_downloader")


class TelegramDownloader(DownloaderPlugin):
    name = "telegram"
    plugin_type = "downloader"

    def __init__(self):
        self._bot = None
        self._client = None

    async def initialize(self, bot_token: str = None) -> bool:
        try:
            from telegram import Bot
            from config import get_config

            cfg = get_config()
            token = bot_token or cfg.telegram.BOT_TOKEN

            if token:
                self._bot = Bot(token=token)
                logger.info("Telegram downloader initialized")
                return True
            else:
                logger.warning("No bot token provided")
                return False
        except Exception as e:
            logger.error(f"Telegram init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        file_id = context.source
        output_path = config.get("path", "/tmp/downloads")

        if not file_id.isdigit():
            return PluginResult(success=False, error="Invalid file_id")

        try:
            file = await self._bot.get_file(file_id)
            file_path = await file.download(output_path)

            result = {
                "file_id": file_id,
                "file_name": file_path,
                "file_size": file.file_size,
                "mime_type": file.mime_type,
            }

            return PluginResult(
                success=True,
                output_path=file_path,
                metadata=result,
            )

        except Exception as e:
            logger.error(f"Telegram download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_file_info(self, file_id: str) -> dict:
        try:
            file = await self._bot.get_file(file_id)
            return {
                "file_id": file.file_id,
                "file_unique_id": file.file_unique_id,
                "file_size": file.file_size,
                "mime_type": file.mime_type,
            }
        except Exception as e:
            logger.error(f"Telegram file info error: {e}")
            return {}

    async def download_from_message(self, message) -> PluginResult:
        try:
            if message.video:
                file = message.video
                file_id = file.file_id
                file_name = file.file_name
            elif message.document:
                file = message.document
                file_id = file.file_id
                file_name = file.file_name
            elif message.photo:
                file = message.photo[-1]
                file_id = file.file_id
                file_name = f"photo_{file.file_id}.jpg"
            elif message.audio:
                file = message.audio
                file_id = file.file_id
                file_name = file.file_name
            else:
                return PluginResult(success=False, error="No valid media found")

            tg_file = await self._bot.get_file(file_id)
            file_path = await tg_file.download(custom_path=file_name)

            return PluginResult(
                success=True,
                output_path=file_path,
                metadata={
                    "file_id": file_id,
                    "file_name": file_name,
                    "file_size": file.file_size,
                },
            )

        except Exception as e:
            logger.error(f"Telegram message download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_message_file(self, chat_id: int, message_id: int) -> dict:
        try:
            message = await self._bot.get_message(chat_id, message_id)
            if message:
                return {
                    "chat_id": message.chat.id,
                    "message_id": message.message_id,
                    "date": message.date,
                }
        except Exception as e:
            logger.error(f"Telegram get message error: {e}")
            return {}

    async def upload(
        self, file_path: str, chat_id: int = None, caption: str = None
    ) -> dict:
        try:
            if not os.path.exists(file_path):
                return {"error": "File not found"}

            ext = os.path.splitext(file_path)[1].lower()

            if ext in [".mp4", ".mkv", ".avi"]:
                result = await self._bot.send_video(chat_id, file_path, caption=caption)
            elif ext in [".jpg", ".jpeg", ".png", ".gif"]:
                result = await self._bot.send_photo(chat_id, file_path, caption=caption)
            elif ext in [".mp3", ".ogg", ".m4a"]:
                result = await self._bot.send_audio(chat_id, file_path, caption=caption)
            elif ext in [".pdf", ".doc", ".txt"]:
                result = await self._bot.send_document(
                    chat_id, file_path, caption=caption
                )
            else:
                result = await self._bot.send_document(
                    chat_id, file_path, caption=caption
                )

            return {
                "message_id": result.message_id,
                "chat_id": result.chat.id,
            }
        except Exception as e:
            logger.error(f"Telegram upload error: {e}")
            return {"error": str(e)}

    async def forward_message(
        self, from_chat_id: int, to_chat_id: int, message_id: int
    ) -> dict:
        try:
            result = await self._bot.forward_message(
                chat_id=to_chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
            return {
                "message_id": result.message_id,
                "chat_id": result.chat.id,
            }
        except Exception as e:
            logger.error(f"Telegram forward error: {e}")
            return {"error": str(e)}
