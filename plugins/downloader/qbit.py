import asyncio
import logging
import os
import time
from typing import Any, Optional

from plugins.base import DownloaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError

logger = logging.getLogger("wzml.qbit_downloader")


class QBitDownloader(DownloaderPlugin):
    name = "qbit"
    plugin_type = "downloader"
    supports_torrent = True
    supports_magnet = True

    def __init__(self):
        self._host = "localhost"
        self._port = 8080
        self._username = None
        self._password = None
        self._client = None
        self._torrent_hash = None

    async def initialize(
        self,
        host: str = "localhost",
        port: int = 8080,
        username: str = None,
        password: str = None,
    ) -> bool:
        try:
            from aioqbt import QbtAPI

            if username and password:
                self._client = await QbtAPI.login(
                    f"http://{host}:{port}/", username, password
                )
            else:
                self._client = await QbtAPI.login(f"http://{host}:{port}/")

            self._host = host
            self._port = port
            self._username = username
            self._password = password

            logger.info(f"qBittorrent initialized: {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"qBittorrent init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        save_path = config.get("path", "/tmp/downloads")
        category = config.get("category")
        tags = config.get("tags", [])
        ratio_limit = config.get("ratio_limit")
        seeding_time_limit = config.get("seeding_time_limit")
        paused = config.get("paused", False)
        root_folder = config.get("root_folder", False)

        try:
            from aioqbt import AddFormBuilder

            form = AddFormBuilder.with_client(self._client)

            if os.path.exists(url):
                with open(url, "rb") as f:
                    data = f.read()
                    form = form.include_file(data)
            else:
                form = form.include_url(url)

            form = form.savepath(save_path)

            if category:
                form = form.category(category)
            if tags:
                form = form.tags(tags)
            if ratio_limit:
                form = form.ratio_limit(ratio_limit)
            if seeding_time_limit:
                form = form.seeding_time_limit(seeding_time_limit)
            if paused:
                form = form.stopped(True)
            if root_folder:
                form = form.root_folder(True)

            await self._client.torrents.add(form.build())

            from core.task import update_task_progress, get_task

            start_time = time.time()
            last_update = start_time

            # Find the torrent hash
            await asyncio.sleep(2)  # Give qbit time to register
            torrents = await self._client.torrents.info(category=category)

            # This is a bit naive, we should ideally track by tag or savepath
            if torrents:
                # Find the most recently added
                tor_info = sorted(torrents, key=lambda x: x.added_on, reverse=True)[0]
                self._torrent_hash = tor_info.hash
            else:
                return PluginResult(success=False, error="Failed to get torrent hash")

            while True:
                # Check cancellation
                t = await get_task(context.task_id)
                if t and t.status.value == "cancelled":
                    await self._client.torrents.delete(
                        hashes=[self._torrent_hash], delete_files=True
                    )
                    return PluginResult(success=False, error="Task cancelled by user")

                torrents = await self._client.torrents.info(hashes=[self._torrent_hash])
                if not torrents:
                    return PluginResult(
                        success=False, error="Torrent removed externally"
                    )

                tor_info = torrents[0]

                if tor_info.state in ("uploading", "stalledUP", "pausedUP"):
                    # Download complete, it's seeding or done
                    break
                elif tor_info.state in ("error", "missingFiles", "unknown"):
                    return PluginResult(
                        success=False,
                        error=f"qBittorrent error state: {tor_info.state}",
                    )

                now = time.time()
                if now - last_update > 1.0:
                    speed = tor_info.dlspeed
                    downloaded = tor_info.completed
                    total = tor_info.total_size
                    eta = tor_info.eta
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

            torrents = await self._client.torrents.info(hashes=[self._torrent_hash])
            if torrents:
                tor_info = torrents[0]

                result = {
                    "hash": tor_info.hash,
                    "name": tor_info.name,
                    "size": tor_info.size,
                    "progress": tor_info.progress,
                    "state": tor_info.state,
                    "save_path": tor_info.save_path,
                    "category": tor_info.category,
                    "tags": tor_info.tags,
                    "added_on": tor_info.added_on,
                    "completed_on": tor_info.completed_on,
                }

                return PluginResult(
                    success=True,
                    output_path=os.path.join(save_path, tor_info.name),
                    metadata=result,
                )

            return PluginResult(success=False, error="Torrent not added")

        except Exception as e:
            logger.error(f"qBittorrent download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self, hash: str = None) -> dict:
        if not hash:
            hash = self._torrent_hash
        if not hash:
            return {}

        try:
            tor_info = await self._client.torrents.info(hash=hash)
            if tor_info:
                tor = tor_info[0]
                return {
                    "hash": tor.hash,
                    "name": tor.name,
                    "size": tor.size,
                    "progress": tor.progress,
                    "state": tor.state,
                    "dlspeed": tor.dlspeed,
                    "upspeed": tor.upspeed,
                    "ratio": tor.ratio,
                    "save_path": tor.save_path,
                    "category": tor.category,
                }
        except Exception as e:
            logger.error(f"qBittorrent status error: {e}")
            return {"error": str(e)}

    async def pause(self, hash: str = None) -> bool:
        if not hash:
            hash = self._torrent_hash
        if not hash:
            return False
        try:
            await self._client.torrents.pause([hash])
            return True
        except Exception as e:
            logger.error(f"qBittorrent pause error: {e}")
            return False

    async def resume(self, hash: str = None) -> bool:
        if not hash:
            hash = self._torrent_hash
        if not hash:
            return False
        try:
            await self._client.torrents.start([hash])
            return True
        except Exception as e:
            logger.error(f"qBittorrent resume error: {e}")
            return False

    async def cancel(self, hash: str = None) -> bool:
        if not hash:
            hash = self._torrent_hash
        if not hash:
            return False
        try:
            await self._client.torrents.delete([hash], True)
            return True
        except Exception as e:
            logger.error(f"qBittorrent cancel error: {e}")
            return False

    async def delete(self, hash: str, with_files: bool = True) -> bool:
        try:
            await self._client.torrents.delete([hash], with_files)
            return True
        except Exception as e:
            logger.error(f"qBittorrent delete error: {e}")
            return False

    async def get_files(self, hash: str = None) -> list:
        if not hash:
            hash = self._torrent_hash
        if not hash:
            return []

        try:
            files = await self._client.torrents.files(hash)
            return [
                {
                    "name": f.name,
                    "size": f.size,
                    "progress": f.progress,
                    "priority": f.priority,
                }
                for f in files
            ]
        except Exception as e:
            logger.error(f"qBittorrent files error: {e}")
            return []

    async def set_category(self, hash: str, category: str) -> bool:
        try:
            await self._client.torrents.set_category([hash], category)
            return True
        except Exception as e:
            logger.error(f"qBittorrent category error: {e}")
            return False

    async def set_tags(self, hash: str, tags: list) -> bool:
        try:
            await self._client.torrents.add_tags([hash], tags)
            return True
        except Exception as e:
            logger.error(f"qBittorrent tags error: {e}")
            return False

    async def get_torrent_files(self, hash: str) -> list:
        try:
            return await self._client.torrents.files(hash)
        except Exception as e:
            logger.error(f"qBittorrent torrent files error: {e}")
            return []

    async def reannounce(self, hash: str) -> bool:
        try:
            await self._client.torrents.reannounce([hash])
            return True
        except Exception as e:
            logger.error(f"qBittorrent reannounce error: {e}")
            return False

    async def set_location(self, hash: str, new_path: str) -> bool:
        try:
            await self._client.torrents.set_location([hash], new_path)
            return True
        except Exception as e:
            logger.error(f"qBittorrent set location error: {e}")
            return False

    async def set_ratio_limit(self, hash: str, ratio: float) -> bool:
        try:
            await self._client.torrents.set_share_limits([hash], ratio, -1)
            return True
        except Exception as e:
            logger.error(f"qBittorrent ratio limit error: {e}")
            return False

    async def get_global_stats(self) -> dict:
        try:
            prefs = await self._client.app.preferences()
            transfer = await self._client.transfer.info()
            return {
                "dl_speed": preferences.get("dlspeed", 0),
                "up_speed": transfer.get("up_info_functions", 0),
                "active_torrents": preferences.get("num_active", 0),
                "paused_torrents": preferences.get("num_paused", 0),
            }
        except Exception as e:
            logger.error(f"qBittorrent stats error: {e}")
            return {}

    async def list_torrents(self, category: str = None, tag: str = None) -> list:
        try:
            torrents = await self._client.torrents.info(category=category, tag=tag)
            return [
                {
                    "hash": t.hash,
                    "name": t.name,
                    "size": t.size,
                    "progress": t.progress,
                    "state": t.state,
                }
                for t in torrents
            ]
        except Exception as e:
            logger.error(f"qBittorrent list error: {e}")
            return []

    async def list_categories(self) -> list:
        try:
            return await self._client.torrents.categories()
        except Exception as e:
            logger.error(f"qBittorrent categories error: {e}")
            return []

    async def list_tags(self) -> list:
        try:
            return await self._client.torrents.tags()
        except Exception as e:
            logger.error(f"qBittorrent tags error: {e}")
            return []
