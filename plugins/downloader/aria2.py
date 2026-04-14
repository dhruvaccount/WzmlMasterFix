import asyncio
import logging
import os
import time
from typing import Any, Optional
from urllib.parse import urlparse

from plugins.base import DownloaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError

logger = logging.getLogger("wzml.aria2_downloader")


class Aria2Downloader(DownloaderPlugin):
    name = "aria2"
    plugin_type = "downloader"
    supports_torrent = True
    supports_magnet = True

    def __init__(self):
        self._rpc_url = None
        self._secret = None
        self._client = None
        self._gid = None

    async def initialize(self, rpc_url: str, secret: str = None) -> bool:
        try:
            from aria2p import API, Secret

            if secret:
                secret = Secret(secret)
            self._client = API(rpc_url=rpc_url, secret=secret)
            self._rpc_url = rpc_url
            self._secret = secret
            logger.info(f"Aria2 initialized: {rpc_url}")
            return True
        except Exception as e:
            logger.error(f"Aria2 init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")
        filename = config.get("filename")
        header = config.get("header")
        seed_ratio = config.get("seed_ratio")
        seed_time = config.get("seed_time")

        a2c_opt = {"dir": output_path}
        if filename:
            a2c_opt["out"] = filename
        if header:
            a2c_opt["header"] = header
        if seed_ratio:
            a2c_opt["seed-ratio"] = str(seed_ratio)
        if seed_time:
            a2c_opt["seed-time"] = str(seed_time)

        try:
            if os.path.exists(url):
                with open(url, "rb") as tf:
                    torrent_data = tf.read()
                encoded = base64.b64encode(torrent_data).decode()
                self._gid = await asyncio.to_thread(
                    self._client.add_torrent, encoded, options=a2c_opt
                )
            else:
                self._gid = await asyncio.to_thread(
                    self._client.add_uri, [url], options=a2c_opt
                )

            # Since aria2p's client methods are mostly synchronous over requests, we use to_thread to avoid blocking
            if hasattr(self._gid, "gid"):
                self._gid = self._gid.gid
            elif (
                isinstance(self._gid, list)
                and len(self._gid) > 0
                and hasattr(self._gid[0], "gid")
            ):
                self._gid = self._gid[0].gid

            from core.task import update_task_progress, get_task

            start_time = time.time()
            last_update = start_time

            while True:
                # Check cancellation
                t = await get_task(context.task_id)
                if t and t.status.value == "cancelled":
                    await asyncio.to_thread(self._client.remove, [self._gid])
                    return PluginResult(success=False, error="Task cancelled by user")

                download = await asyncio.to_thread(self._client.get_download, self._gid)

                if download.status == "complete":
                    break
                elif download.status == "error":
                    return PluginResult(
                        success=False,
                        error=download.error_message or "Aria2 download error",
                    )
                elif download.status == "removed":
                    return PluginResult(success=False, error="Task cancelled by user")

                now = time.time()
                if now - last_update > 1.0:
                    speed = download.download_speed
                    downloaded = download.completed_length
                    total = download.total_length
                    eta = (
                        int((total - downloaded) / speed) if speed > 0 and total else 0
                    )
                    pct = (downloaded / total) * 100 if total else 0.0

                    await update_task_progress(
                        task_id=context.task_id,
                        stage="Downloading",
                        plugin=self.name,
                        progress=pct,
                        speed=speed,
                        eta=eta,
                        downloaded=downloaded,
                        total=total,
                    )
                    last_update = now

                await asyncio.sleep(1)

            download = await asyncio.to_thread(self._client.get_download, self._gid)

            result = {
                "gid": self._gid,
                "name": download.name,
                "total_length": download.total_length,
                "completed_length": download.completed_length,
                "download_speed": download.download_speed,
                "upload_speed": download.upload_speed,
                "progress": download.progress,
                "status": download.status,
                "files": [f.path for f in download.files],
            }

            output_file = (
                os.path.join(output_path, download.name)
                if download.name
                else output_path
            )

            return PluginResult(
                success=True,
                output_path=output_file,
                metadata=result,
            )

        except Exception as e:
            logger.error(f"Aria2 download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self, gid: str = None) -> dict:
        if not gid:
            gid = self._gid
        if not gid:
            return {}

        try:
            download = await self._client.get_download(gid)
            return {
                "gid": gid,
                "name": download.name,
                "total_length": download.total_length,
                "completed_length": download.completed_length,
                "download_speed": download.download_speed,
                "progress": download.progress,
                "status": download.status,
                "error_code": download.error_code,
                "error_message": download.error_message,
            }
        except Exception as e:
            logger.error(f"Aria2 status error: {e}")
            return {"error": str(e)}

    async def pause(self, gid: str = None) -> bool:
        if not gid:
            gid = self._gid
        if not gid:
            return False
        try:
            await self._client.pause(gid)
            return True
        except Exception as e:
            logger.error(f"Aria2 pause error: {e}")
            return False

    async def resume(self, gid: str = None) -> bool:
        if not gid:
            gid = self._gid
        if not gid:
            return False
        try:
            await self._client.unpause(gid)
            return True
        except Exception as e:
            logger.error(f"Aria2 resume error: {e}")
            return False

    async def cancel(self, gid: str = None) -> bool:
        if not gid:
            gid = self._gid
        if not gid:
            return False
        try:
            await self._client.remove([gid])
            return True
        except Exception as e:
            logger.error(f"Aria2 cancel error: {e}")
            return False

    async def purge(self, gid: str = None) -> bool:
        if not gid:
            gid = self._gid
        if not gid:
            return False
        try:
            await self._client.remove([gid], force=True)
            return True
        except Exception as e:
            logger.error(f"Aria2 purge error: {e}")
            return False

    async def get_files(self, gid: str = None) -> list:
        if not gid:
            gid = self._gid
        if not gid:
            return []

        try:
            download = await self._client.get_download(gid)
            return [
                {
                    "path": f.path,
                    "completed_length": f.completed_length,
                    "total_length": f.total_length,
                    "selected": f.is_selected,
                }
                for f in download.files
            ]
        except Exception as e:
            logger.error(f"Aria2 files error: {e}")
            return []

    async def select_files(self, gid: str, file_ids: list) -> bool:
        try:
            await self._client.set_options({"file-allocation": "none"}, gid)
            for fid in file_ids:
                await self._client.change_option(f"file.fid={fid}", "enabled", "true")
            return True
        except Exception as e:
            logger.error(f"Aria2 select error: {e}")
            return False

    async def get_stats(self) -> dict:
        try:
            stats = await self._client.get_stats()
            return {
                "download_speed": stats.download_speed,
                "upload_speed": stats.upload_speed,
                "active": stats.num_active,
                "waiting": stats.num_waiting,
                "stopped": stats.num_stopped_total,
            }
        except Exception as e:
            logger.error(f"Aria2 stats error: {e}")
            return {}

    async def list_downloads(self) -> list:
        try:
            downloads = await self._client.get_downloads()
            return [
                {
                    "gid": d.gid,
                    "name": d.name,
                    "status": d.status,
                    "progress": d.progress,
                }
                for d in downloads
            ]
        except Exception as e:
            logger.error(f"Aria2 list error: {e}")
            return []
