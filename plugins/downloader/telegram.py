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
        self._client = None
        self._bot = None

    async def initialize(self) -> bool:
        try:
            from bots.clients.telegram.client import get_telegram_client
            
            tg_client = await get_telegram_client()
            if tg_client and tg_client._bot:
                self._client = tg_client
                self._bot = tg_client._bot
                logger.info("Telegram downloader initialized with global Pyrogram client")
                return True
            else:
                logger.warning("Failed to fetch global Pyrogram client")
                return False
        except Exception as e:
            logger.error(f"Telegram init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        # In Pyrogram, we can't easily download just by file_id without a message context
        # normally, but if it's a valid string file_id, download_media works.
        file_id = context.source
        output_path = config.get("path", "/tmp/downloads")

        try:
            from core.task import update_task_progress, get_task
            import time
            
            start_time = time.time()
            last_update = start_time

            async def progress(current, total):
                nonlocal last_update
                now = time.time()
                
                # Check cancellation
                t = await get_task(context.task_id)
                if t and t.status.value == "cancelled":
                    self._bot.stop_transmission()

                if now - last_update > 1.0 and total > 0:
                    speed = current / (now - start_time)
                    eta = int((total - current) / speed) if speed > 0 else 0
                    pct = (current / total) * 100
                    
                    await update_task_progress(
                        task_id=context.task_id,
                        stage="Downloading",
                        plugin=self.name,
                        progress=pct,
                        speed=speed,
                        eta=eta,
                        downloaded=current,
                        total=total,
                    )
                    last_update = now

            os.makedirs(output_path, exist_ok=True)
            
            # Since source could be a file_id string:
            file_path = await self._bot.download_media(
                message=file_id,
                file_name=output_path + "/",
                progress=progress
            )

            if not file_path:
                return PluginResult(success=False, error="Task cancelled or failed")

            result = {
                "file_id": file_id,
                "file_name": os.path.basename(file_path),
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
        # Pyrogram doesn't have a straightforward get_file without context.
        # Returning empty to gracefully degrade or if file_id is a Message object we can inspect it.
        return {}

    async def cancel(self) -> bool:
        if self._bot:
            self._bot.stop_transmission()
            return True
        return False

