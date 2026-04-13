import asyncio
import logging
import os
from typing import Any, Optional

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.nzb_downloader")


class NZBDownloader(DownloaderPlugin):
    name = "nzb"
    plugin_type = "downloader"

    def __init__(self):
        self._host = "localhost"
        self._port = 8080
        self._api_key = None
        self._client = None

    async def initialize(
        self, host: str = "localhost", port: int = 8080, api_key: str = None
    ) -> bool:
        try:
            from pynzb import NZBClient

            self._client = NZBClient(host, port, api_key)
            self._host = host
            self._port = port
            self._api_key = api_key

            logger.info(f"NZBGet initialized: {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"NZBGet init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")
        category = config.get("category", "Movies")
        priority = config.get("priority", 0)
        nzb_name = config.get("name")

        if not url.endswith(".nzb") and "nzb" not in url.lower():
            return PluginResult(success=False, error="Not an NZB link")

        try:
            if not nzb_name:
                nzb_name = os.path.basename(url)

            result = await self._client.add_nzb(
                url, output_path, category, priority, nzb_name
            )

            if result.get("nzbid"):
                return PluginResult(
                    success=True,
                    output_path=os.path.join(output_path, nzb_name),
                    metadata={
                        "nzbid": result["nzbid"],
                        "name": nzb_name,
                        "category": category,
                    },
                )

            return PluginResult(success=False, error="Failed to add NZB")

        except Exception as e:
            logger.error(f"NZBGet download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self, nzbid: int) -> dict:
        try:
            result = await self._client.get_nzb(nzbid)
            return result
        except Exception as e:
            logger.error(f"NZBGet status error: {e}")
            return {}

    async def pause(self, nzbid: int) -> bool:
        try:
            await self._client.pause_nzb(nzbid)
            return True
        except Exception as e:
            logger.error(f"NZBGet pause error: {e}")
            return False

    async def resume(self, nzbid: int) -> bool:
        try:
            await self._client.resume_nzb(nzbid)
            return True
        except Exception as e:
            logger.error(f"NZBGet resume error: {e}")
            return False

    async def delete(self, nzbid: int) -> bool:
        try:
            await self._client.delete_nzb(nzbid)
            return True
        except Exception as e:
            logger.error(f"NZBGet delete error: {e}")
            return False

    async def list_nzbs(self) -> list:
        try:
            return await self._client.list_nzbs()
        except Exception as e:
            logger.error(f"NZBGet list error: {e}")
            return []

    async def get_queue(self) -> list:
        try:
            return await self._client.get_queue()
        except Exception as e:
            logger.error(f"NZBGet queue error: {e}")
            return []

    async def set_speed(self, speed: int) -> bool:
        try:
            await self._client.set_speed(speed)
            return True
        except Exception as e:
            logger.error(f"NZBGet speed error: {e}")
            return False

    async def get_config(self) -> dict:
        try:
            return await self._client.get_config()
        except Exception as e:
            logger.error(f"NZBGet config error: {e}")
            return {}
