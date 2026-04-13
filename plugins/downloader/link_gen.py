import asyncio
import logging
import os
from typing import Any, Optional
from urllib.parse import urlparse

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.link_gen_downloader")


class LinkGenerator(DownloaderPlugin):
    name = "link_gen"
    plugin_type = "downloader"

    def __init__(self):
        self._shortener = None

    async def initialize(self) -> bool:
        logger.info("Link generator initialized")
        return True

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source

        try:
            file_url = await self._generate_link(url, config)

            return PluginResult(
                success=True,
                output_path=file_url,
                metadata={"original": url, "generated": file_url},
            )

        except Exception as e:
            logger.error(f"Link gen error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _generate_link(self, url: str, config: dict) -> str:
        service = config.get("service", "terabox")

        if "terabox" in service or "terabox" in url:
            return await self._terabox_link(url)
        elif "gofile" in service or "gofile.io" in url:
            return await self._gofile_link(url)
        elif "hubcloud" in service or "hubcloud.cfd" in url:
            return await self._hubcloud_link(url)
        elif "catbox" in service:
            return await self._catbox_link(url)
        elif "pixeldrain" in service:
            return await self._pixeldrain_link(url)
        else:
            return url

    async def _terabox_link(self, url: str) -> str:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://teraboxdown.com/api/v1/common/parsing?url={url}"
                ) as response:
                    data = await response.json()
                    if data.get("code") == 0:
                        return data.get("sharePoint", url)
        except Exception as e:
            logger.error(f"Terabox error: {e}")
        return url

    async def _gofile_link(self, url: str) -> str:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    if data.get("directLink"):
                        return data["directLink"]
        except Exception as e:
            logger.error(f"Gofile error: {e}")
        return url

    async def _hubcloud_link(self, url: str) -> str:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://hubcloud.cfd/bypass?url={url}"
                ) as response:
                    data = await response.json()
                    if data.get("directLink"):
                        return data["directLink"]
        except Exception as e:
            logger.error(f"Hubcloud error: {e}")
        return url

    async def _catbox_link(self, url: str) -> str:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("reqtype", "fileupload")
                form.add_field("fileToUpload", url, filename="file")
                async with session.post(
                    "https://catbox.moe/api/v1/upload", data=form
                ) as response:
                    data = await response.json()
                    if data.get("file"):
                        return data["file"]["url"]
        except Exception as e:
            logger.error(f"Catbox error: {e}")
        return url

    async def _pixeldrain_link(self, url: str) -> str:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://pixeldrain.com/api/file/{url}", follow_redirects=True
                ) as response:
                    if response.status == 200:
                        return str(response.url)
        except Exception as e:
            logger.error(f"Pixeldrain error: {e}")
        return url

    async def get_direct_link(self, share_url: str) -> str:
        return await self._generate_link(share_url, {})

    async def parse_share_link(self, url: str) -> dict:
        parsed = urlparse(url)

        if "terabox.com" in url:
            return {"service": "terabox", "type": "file"}
        elif "mega.nz" in url:
            return {"service": "mega", "type": "file"}
        elif "gofile.io" in url:
            return {"service": "gofile", "type": "folder"}
        elif "drive.google.com" in url:
            return {"service": "gdrive", "type": "file"}
        else:
            return {"service": "unknown", "type": "unknown"}


DOWNLOADER_CLASSES = {
    "aria2": "plugins.downloader.aria2.Aria2Downloader",
    "qbit": "plugins.downloader.qbit.QBitDownloader",
    "jd": "plugins.downloader.jd.JDownloaderDownloader",
    "mega": "plugins.downloader.mega.MegaDownloader",
    "nzb": "plugins.downloader.nzb.NZBDownloader",
    "yt_dlp": "plugins.downloader.yt_dlp.YTDLPDownloader",
    "direct": "plugins.downloader.direct.DirectDownloader",
    "telegram": "plugins.downloader.telegram.TelegramDownloader",
    "gdrive": "plugins.downloader.gdrive.GDriveDownloader",
    "rclone": "plugins.downloader.rclone.RCloneDownloader",
    "link_gen": "plugins.downloader.link_gen.LinkGenerator",
}


def get_downloader(name: str):
    from importlib import import_module

    if name not in DOWNLOADER_CLASSES:
        return None

    module_path = DOWNLOADER_CLASSES[name]
    module_name, class_name = module_path.rsplit(".", 1)

    try:
        module = import_module(module_name)
        return getattr(module, class_name)()
    except Exception as e:
        logger.error(f"Failed to load {name}: {e}")
        return None
