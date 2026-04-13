import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from plugins.base import UploaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError


logger = logging.getLogger("wzml.uploader")


class GDriveUploader(UploaderPlugin):
    name = "gdrive"
    plugin_type = "uploader"

    def __init__(self):
        self._credentials = None
        self._folder_id = "root"

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        destination = config.get("destination", "root")

        try:
            result = await self._gdrive_upload(source, destination, config)
            return PluginResult(
                success=True, output_path=result.get("url"), metadata=result
            )
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _gdrive_upload(self, source: str, destination: str, config: dict) -> dict:
        await asyncio.sleep(1)

        return {
            "url": f"https://drive.google.com/file/d/test",
            "id": "test",
            "name": os.path.basename(source),
        }


class RCloneUploader(UploaderPlugin):
    name = "rclone"
    plugin_type = "uploader"

    def __init__(self):
        self._config = None
        self._remote = None

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        dest_remote = config.get("remote", "gdrive:")

        try:
            result = await self._rclone_upload(source, dest_remote, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _rclone_upload(self, source: str, dest_remote: str, config: dict) -> dict:
        await asyncio.sleep(1)

        return {"path": f"{dest_remote}/{os.path.basename(source)}"}


class TelegramUploader(UploaderPlugin):
    name = "telegram"
    plugin_type = "uploader"

    def __init__(self):
        self._bot = None

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        chat_id = config.get("chat_id")

        try:
            result = await self._telegram_upload(source, chat_id, config)
            return PluginResult(success=True, output_path=result.get("file_id"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _telegram_upload(self, source: str, chat_id: int, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {
            "file_id": f"file_{hash(source)}",
            "message_id": hash(source),
        }


class YouTubeUploader(UploaderPlugin):
    name = "youtube"
    plugin_type = "uploader"

    def __init__(self):
        self._credentials = None

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        title = config.get("title", os.path.basename(source))
        description = config.get("description", "")

        try:
            result = await self._youtube_upload(source, title, description, config)
            return PluginResult(success=True, output_path=result.get("video_id"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _youtube_upload(
        self, source: str, title: str, description: str, config: dict
    ) -> dict:
        await asyncio.sleep(2)

        return {
            "video_id": f"yt_{hash(source)}",
            "url": f"https://youtube.com/watch?v=yt_{hash(source)}",
        }


class UphosterUploader(UploaderPlugin):
    name = "uphosted"
    plugin_type = "uploader"

    def __init__(self):
        self._service = "gofile"

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        service = config.get("service", "gofile")

        try:
            result = await self._uphosted_upload(source, service, config)
            return PluginResult(success=True, output_path=result.get("url"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _uphosted_upload(self, source: str, service: str, config: dict) -> dict:
        await asyncio.sleep(1)

        urls = {
            "gofile": f"https://gofile.io/download/test",
            "catbox": f"https://catbox.moe/file/test",
            "pixeldrain": f"https://pixeldrain.com/u/test",
        }

        return {"url": urls.get(service, "https://example.com")}


UPLOADER_CLASSES = {
    "gdrive": GDriveUploader,
    "rclone": RCloneUploader,
    "telegram": TelegramUploader,
    "youtube": YouTubeUploader,
    "uphosted": UphosterUploader,
}


def get_uploader(name: str) -> UploaderPlugin:
    cls = UPLOADER_CLASSES.get(name)
    if cls:
        return cls()
    return None
