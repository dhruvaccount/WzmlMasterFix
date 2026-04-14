import asyncio
import logging
import os
import time
import base64
from typing import Any, Optional
from urllib.parse import urlparse

from aioaria2 import Aria2WebsocketClient

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
        self._client: Optional[Aria2WebsocketClient] = None
        self._gid = None

    async def initialize(
        self, rpc_url: str = "http://localhost:6800/jsonrpc", secret: str = None
    ) -> bool:
        try:
            self._client = await Aria2WebsocketClient.new(rpc_url, token=secret if secret else None)
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
                self._gid = await self._client.addTorrent(encoded, [], a2c_opt)
            else:
                self._gid = await self._client.addUri([url], a2c_opt)

            from core.task import update_task_progress, get_task

            start_time = time.time()
            last_update = start_time

            while True:
                t = await get_task(context.task_id)
                if t and t.status.value == "cancelled":
                    await self._client.forceRemove(self._gid)
                    return PluginResult(success=False, error="Task cancelled by user")

                download = await self._client.tellStatus(self._gid)
                status = download.get("status")

                if status == "complete":
                    break
                elif status == "error":
                    error_msg = download.get("errorMessage", "Aria2 download error")
                    return PluginResult(success=False, error=error_msg)
                elif status == "removed":
                    return PluginResult(success=False, error="Task cancelled by user")

                now = time.time()
                if now - last_update > 1.0:
                    speed = int(download.get("downloadSpeed", 0))
                    downloaded = int(download.get("completedLength", 0))
                    total = int(download.get("totalLength", 0))
                    eta = int((total - downloaded) / speed) if speed > 0 and total else 0
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

            download = await self._client.tellStatus(self._gid)
            name = download.get("bittorrent", {}).get("info", {}).get("name")
            if not name:
                files = download.get("files", [])
                if files and files[0].get("path"):
                    name = os.path.basename(files[0]["path"])

            result = {
                "gid": self._gid,
                "name": name,
                "total_length": int(download.get("totalLength", 0)),
                "completed_length": int(download.get("completedLength", 0)),
                "download_speed": int(download.get("downloadSpeed", 0)),
                "upload_speed": int(download.get("uploadSpeed", 0)),
                "status": download.get("status"),
                "files": [f.get("path") for f in download.get("files", [])],
            }

            output_file = os.path.join(output_path, name) if name else output_path

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
            download = await self._client.tellStatus(gid)
            name = download.get("bittorrent", {}).get("info", {}).get("name")
            if not name:
                files = download.get("files", [])
                if files and files[0].get("path"):
                    name = os.path.basename(files[0]["path"])
                    
            total = int(download.get("totalLength", 0))
            completed = int(download.get("completedLength", 0))
            progress = (completed / total * 100) if total else 0.0

            return {
                "gid": gid,
                "name": name,
                "total_length": total,
                "completed_length": completed,
                "download_speed": int(download.get("downloadSpeed", 0)),
                "progress": progress,
                "status": download.get("status"),
                "error_code": download.get("errorCode"),
                "error_message": download.get("errorMessage"),
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
            await self._client.forcePause(gid)
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
            await self._client.forceRemove(gid)
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
            await self._client.removeDownloadResult(gid)
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
            download = await self._client.tellStatus(gid)
            return [
                {
                    "path": f.get("path"),
                    "completed_length": int(f.get("completedLength", 0)),
                    "total_length": int(f.get("length", 0)),
                    "selected": f.get("selected") == "true",
                }
                for f in download.get("files", [])
            ]
        except Exception as e:
            logger.error(f"Aria2 files error: {e}")
            return []

    async def select_files(self, gid: str, file_ids: list) -> bool:
        try:
            options = {"select-file": ",".join(map(str, file_ids))}
            await self._client.changeOption(gid, options)
            return True
        except Exception as e:
            logger.error(f"Aria2 select error: {e}")
            return False

    async def get_stats(self) -> dict:
        try:
            stats = await self._client.getGlobalStat()
            return {
                "download_speed": int(stats.get("downloadSpeed", 0)),
                "upload_speed": int(stats.get("uploadSpeed", 0)),
                "active": int(stats.get("numActive", 0)),
                "waiting": int(stats.get("numWaiting", 0)),
                "stopped": int(stats.get("numStopped", 0)),
            }
        except Exception as e:
            logger.error(f"Aria2 stats error: {e}")
            return {}

    async def list_downloads(self) -> list:
        try:
            active = await self._client.tellActive()
            waiting = await self._client.tellWaiting(0, 1000)
            stopped = await self._client.tellStopped(0, 1000)
            downloads = active + waiting + stopped
            return [
                {
                    "gid": d.get("gid"),
                    "name": d.get("bittorrent", {}).get("info", {}).get("name") or (os.path.basename(d["files"][0]["path"]) if d.get("files") and d["files"][0].get("path") else ""),
                    "status": d.get("status"),
                }
                for d in downloads
            ]
        except Exception as e:
            logger.error(f"Aria2 list error: {e}")
            return []
