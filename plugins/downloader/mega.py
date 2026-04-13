import asyncio
import logging
import os
from typing import Any, Optional

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.mega_downloader")


class MegaDownloader(DownloaderPlugin):
    name = "mega"
    plugin_type = "downloader"

    def __init__(self):
        self._client = None
        self._sid = None

    async def initialize(self, email: str = None, password: str = None) -> bool:
        try:
            from mega import Mega

            self._client = Mega()
            if email and password:
                self._sid = self._client.login(email, password)
            else:
                self._sid = self._client.login()

            logger.info("Mega initialized")
            return True
        except Exception as e:
            logger.error(f"Mega init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")

        if "mega.nz" not in url.lower():
            return PluginResult(success=False, error="Not a Mega link")

        try:
            file = self._client.get_file(url)
            await file.download(output_path)

            result = {
                "name": file["name"],
                "size": file["size"],
                "link": url,
            }

            return PluginResult(
                success=True,
                output_path=os.path.join(output_path, file["name"]),
                metadata=result,
            )

        except Exception as e:
            logger.error(f"Mega download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self, url: str = None) -> dict:
        try:
            file = self._client.get_file(url)
            return {
                "name": file["name"],
                "size": file["size"],
                "progress": file.get("progress"),
            }
        except Exception as e:
            logger.error(f"Mega status error: {e}")
            return {}

    async def cancel(self) -> bool:
        return True

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True


class MegaListener:
    def __init__(self, url: str):
        self.url = url
        self._client = None

    async def download(self, path: str) -> dict:
        from mega import Mega

        client = Mega()
        file = client.get_file(self.url)
        return await file.download(path)
