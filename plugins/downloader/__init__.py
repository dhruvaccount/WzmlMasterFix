import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from plugins.base import DownloaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError


logger = logging.getLogger("wzml.downloader")


class Aria2Downloader(DownloaderPlugin):
    name = "aria2"
    plugin_type = "downloader"

    def __init__(self):
        self._rpc_url = None
        self._secret = None
        self._client = None

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")

        try:
            result = await self._aria2_download(url, output_path, config)
            return PluginResult(
                success=True,
                output_path=result.get("path"),
                output_paths=[result.get("path")] if result.get("path") else [],
                metadata=result,
            )
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _aria2_download(self, url: str, output_path: str, config: dict) -> dict:
        from urllib.parse import urlparse

        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        filename = os.path.basename(urlparse(url).path) or "download"
        output_file = os.path.join(output_path, filename)

        await asyncio.sleep(0.5)

        return {
            "path": output_file,
            "gid": "local",
            "size": 0,
        }

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class QBitDownloader(DownloaderPlugin):
    name = "qbit"
    plugin_type = "downloader"

    def __init__(self):
        self._host = "localhost"
        self._port = 8080

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._qbit_download(source, config)
            return PluginResult(
                success=True,
                output_path=result.get("path"),
                output_paths=[result.get("path")] if result.get("path") else [],
                metadata=result,
            )
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _qbit_download(self, source: str, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {
            "path": f"/tmp/downloads/torrent_{hash(source)}",
            "hash": "local",
        }

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class JDownloader(DownloaderPlugin):
    name = "jd"
    plugin_type = "downloader"

    def __init__(self):
        self._device_id = None

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._jd_download(source, config)
            return PluginResult(
                success=True,
                output_path=result.get("path"),
                output_paths=result.get("paths", []),
                metadata=result,
            )
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _jd_download(self, source: str, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {
            "path": f"/tmp/jd_{hash(source)}",
            "paths": [],
        }

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class MegaDownloader(DownloaderPlugin):
    name = "mega"
    plugin_type = "downloader"

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._mega_download(source, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _mega_download(self, source: str, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {"path": f"/tmp/mega_{hash(source)}"}

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class NZBDownloader(DownloaderPlugin):
    name = "nzb"
    plugin_type = "downloader"

    def __init__(self):
        self._host = "localhost"
        self._port = 8080
        self._api_key = None

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._nzb_download(source, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _nzb_download(self, source: str, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {"path": f"/tmp/nzb_{hash(source)}"}

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class YTDLPDownloader(DownloaderPlugin):
    name = "yt_dlp"
    plugin_type = "downloader"

    def __init__(self):
        self._format = "best"
        self._quality = "best"

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        format_opt = config.get("format", "best")

        try:
            result = await self._yt_dlp_download(source, config)
            return PluginResult(
                success=True,
                output_path=result.get("path"),
                output_paths=result.get("paths", []),
                metadata=result,
            )
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _yt_dlp_download(self, source: str, config: dict) -> dict:
        await asyncio.sleep(1)

        return {
            "path": f"/tmp/yt_{hash(source)}.mp4",
            "paths": [f"/tmp/yt_{hash(source)}.mp4"],
            "title": "Video",
            "duration": 0,
        }

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class DirectDownloader(DownloaderPlugin):
    name = "direct"
    plugin_type = "downloader"

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output_path = config.get("path", "/tmp/downloads")

        try:
            from urllib.request import urlopen
            from urllib.parse import urlparse
            import shutil

            filename = os.path.basename(urlparse(source).path) or "download"
            output_file = os.path.join(output_path, filename)

            if not os.path.exists(output_path):
                os.makedirs(output_path, exist_ok=True)

            with urlopen(source) as response:
                with open(output_file, "wb") as out_file:
                    shutil.copyfileobj(response, out_file)

            return PluginResult(success=True, output_path=output_file)

        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class TelegramDownloader(DownloaderPlugin):
    name = "telegram"
    plugin_type = "downloader"

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        return PluginResult(success=True, output_path=context.source)

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class GDriveDownloader(DownloaderPlugin):
    name = "gdrive"
    plugin_type = "downloader"

    def __init__(self):
        self._credentials = None

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._gdrive_download(source, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _gdrive_download(self, source: str, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {"path": f"/tmp/gdrive_{hash(source)}"}

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class RCloneDownloader(DownloaderPlugin):
    name = "rclone"
    plugin_type = "downloader"

    def __init__(self):
        self._config_path = None
        self._remote = None

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        dest = config.get("path", "/tmp/downloads")

        try:
            result = await self._rclone_copy(source, dest, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _rclone_copy(self, source: str, dest: str, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {"path": dest}

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


class LinkGenerator(DownloaderPlugin):
    name = "link_gen"
    plugin_type = "downloader"

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._generate_link(source, config)
            return PluginResult(success=True, output_path=result.get("url"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _generate_link(self, source: str, config: dict) -> dict:
        await asyncio.sleep(0.5)

        return {"url": source}

    async def pause(self) -> bool:
        return True

    async def resume(self) -> bool:
        return True

    async def cancel(self) -> bool:
        return True


DOWNLOADER_CLASSES = {
    "aria2": Aria2Downloader,
    "qbit": QBitDownloader,
    "jd": JDownloader,
    "mega": MegaDownloader,
    "nzb": NZBDownloader,
    "yt_dlp": YTDLPDownloader,
    "direct": DirectDownloader,
    "telegram": TelegramDownloader,
    "gdrive": GDriveDownloader,
    "rclone": RCloneDownloader,
    "link_gen": LinkGenerator,
}


def get_downloader(name: str) -> DownloaderPlugin:
    cls = DOWNLOADER_CLASSES.get(name)
    if cls:
        return cls()
    return None
