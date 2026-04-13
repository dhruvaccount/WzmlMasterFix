import asyncio
import logging
import os
import base64
import time
from typing import Any, Optional
from secrets import token_hex

from plugins.base import DownloaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError

logger = logging.getLogger("wzml.jd_downloader")


class JDownloaderDownloader(DownloaderPlugin):
    name = "jd"
    plugin_type = "downloader"

    def __init__(self):
        self._device = None
        self._device_id = None
        self._connected = False
        self._package_ids = []
        self._gid = None

    async def initialize(
        self, email: str, password: str, device_id: str = None
    ) -> bool:
        try:
            from myjd import MyJDownloader

            myjd = MyJDownloader(email, password)
            if await myjd.connect():
                self._device = await myjd.get_device(device_id)
                self._device_id = device_id or myjd.device_id
                self._connected = True
                logger.info(f"JDownloader initialized: {self._device_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"JDownloader init error: {e}")
            self._connected = False
            return False

    async def is_connected(self) -> bool:
        return self._connected

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        path = config.get("path", "/tmp/downloads")
        package_name = config.get("package_name")
        password = config.get("password")

        if not self._connected:
            return PluginResult(success=False, error="JDownloader not connected")

        try:
            self._gid = token_hex(5)

            links = [{"links": url}]
            if package_name:
                links[0]["packageName"] = package_name
            if password:
                links[0]["password"] = password

            await self._device.linkgrabber.add_links(links)

            await asyncio.sleep(1)

            await self._device.linkgrabber.collect()

            packages = await self._device.linkgrabber.query_packages([{"saveTo": True}])
            package_ids = [
                p["uuid"] for p in packages if p.get("saveTo", "").startswith(path)
            ]

            if not package_ids:
                return PluginResult(success=False, error="No packages found")

            self._package_ids = package_ids

            await self._device.linkgrabber.set_download_directory(path, package_ids)

            await self._device.linkgrabber.move_to_downloadlist(package_ids)

            await self._device.downloads.force_download(package_ids)

            result = {
                "gid": self._gid,
                "package_ids": package_ids,
                "url": url,
                "path": path,
            }

            return PluginResult(
                success=True,
                output_path=path,
                metadata=result,
            )

        except Exception as e:
            logger.error(f"JDownloader download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self) -> dict:
        if not self._connected or not self._package_ids:
            return {}

        try:
            packages = await self._device.downloads.query_packages(
                [{"packageUUIDs": self._package_ids}]
            )
            if packages:
                p = packages[0]
                return {
                    "name": p.get("name"),
                    "status": p.get("status"),
                    "bytesTotal": p.get("bytesTotal"),
                    "bytesLoaded": p.get("bytesLoaded"),
                    "speed": p.get("speed"),
                }
        except Exception as e:
            logger.error(f"JDownloader status error: {e}")
            return {"error": str(e)}

    async def pause(self) -> bool:
        if not self._connected or not self._package_ids:
            return False
        try:
            await self._device.downloads.pause(self._package_ids)
            return True
        except Exception as e:
            logger.error(f"JDownloader pause error: {e}")
            return False

    async def resume(self) -> bool:
        if not self._connected or not self._package_ids:
            return False
        try:
            await self._device.downloads.force_download(self._package_ids)
            return True
        except Exception as e:
            logger.error(f"JDownloader resume error: {e}")
            return False

    async def cancel(self) -> bool:
        if not self._connected or not self._package_ids:
            return False
        try:
            await self._device.linkgrabber.remove_links(self._package_ids)
            return True
        except Exception as e:
            logger.error(f"JDownloader cancel error: {e}")
            return False

    async def delete(self) -> bool:
        return await self.cancel()

    async def get_packages(self) -> list:
        if not self._connected:
            return []
        try:
            return await self._device.downloads.query_packages([{}])
        except Exception as e:
            logger.error(f"JDownloader packages error: {e}")
            return []

    async def get_links(self) -> list:
        if not self._connected:
            return []
        try:
            return await self._device.linkgrabber.query_links([{}])
        except Exception as e:
            logger.error(f"JDownloader links error: {e}")
            return []

    async def clear_linkgrabber(self) -> bool:
        if not self._connected:
            return False
        try:
            await self._device.linkgrabber.clear_list()
            return True
        except Exception as e:
            logger.error(f"JDownloader clear error: {e}")
            return False

    async def set_device(self, device_id: str) -> bool:
        if not self._connected:
            return False
        try:
            self._device = await self._myjd.get_device(device_id)
            self._device_id = device_id
            return True
        except Exception as e:
            logger.error(f"JDownloader set_device error: {e}")
            return False

    async def get_devices(self) -> list:
        if not self._connected:
            return []
        try:
            return await self._myjd.get_devices()
        except Exception as e:
            logger.error(f"JDownloader devices error: {e}")
            return []
