import asyncio
import logging
import os
import time
from typing import Any, Optional

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.nzb_downloader")


class NZBDownloader(DownloaderPlugin):
    name = "nzb"
    plugin_type = "downloader"

    def __init__(self):
        self._host = "http://localhost"
        self._port = 8070
        self._api_key = "admin"
        self._client = None

    async def initialize(
        self, host: str = "http://localhost", port: int = 8070, api_key: str = "admin"
    ) -> bool:
        try:
            from sabnzbdapi import SabnzbdClient
            
            self._client = SabnzbdClient(host, api_key, port)
            self._host = host
            self._port = port
            self._api_key = api_key

            logger.info(f"Sabnzbd initialized: {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"Sabnzbd init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")
        nzb_name = config.get("name")

        if not url.endswith(".nzb") and "nzb" not in url.lower():
            return PluginResult(success=False, error="Not an NZB link")

        try:
            from core.task import update_task_progress, get_task
            
            category_name = f"wzml_{context.task_id}"
            await self._client.create_category(category_name, output_path)

            nzbpath = url if os.path.exists(url) else None
            add_url = url if not nzbpath else None

            res = await self._client.add_uri(
                add_url,
                nzbpath,
                nzb_name,
                "",
                category_name,
                priority=0,
                pp=3
            )

            if not res or not res.get("status"):
                return PluginResult(success=False, error="Failed to add NZB")

            job_id = res["nzo_ids"][0]
            
            start_time = time.time()
            last_update = start_time

            while True:
                # Check cancellation
                t = await get_task(context.task_id)
                if t and t.status.value == "cancelled":
                    await self._client.delete_job(job_id, delete_files=True)
                    return PluginResult(success=False, error="Task cancelled by user")

                downloads = await self._client.get_downloads(nzo_ids=job_id)
                
                if not downloads or not downloads.get("queue", {}).get("slots"):
                    # Check history if it's completed or failed
                    history = await self._client.get_history(nzo_ids=job_id)
                    if history and history.get("history", {}).get("slots"):
                        slot = history["history"]["slots"][0]
                        if slot.get("status") == "Completed":
                            name = slot.get("name", nzb_name)
                            return PluginResult(
                                success=True,
                                output_path=os.path.join(output_path, name),
                                metadata={"job_id": job_id, "name": name, "category": category_name},
                            )
                        elif slot.get("status") == "Failed":
                            err = slot.get("fail_message", "Unknown error")
                            return PluginResult(success=False, error=err)
                    
                    # If not in queue and not in history, something is wrong, but wait
                    await asyncio.sleep(1)
                    continue

                slot = downloads["queue"]["slots"][0]
                status = slot.get("status")
                
                if status == "Paused":
                    # It might be paused waiting for user input, or we can just resume it
                    pass

                now = time.time()
                if now - last_update > 1.0:
                    speed = float(downloads["queue"].get("kbpersec", 0)) * 1024
                    downloaded = float(slot.get("mb", 0) - slot.get("mbleft", 0)) * 1024 * 1024
                    total = float(slot.get("mb", 0)) * 1024 * 1024
                    eta = int((total - downloaded) / speed) if speed > 0 else 0
                    pct = float(slot.get("percentage", 0))

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

        except Exception as e:
            logger.error(f"Sabnzbd download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self, job_id: str) -> dict:
        try:
            result = await self._client.get_downloads(nzo_ids=job_id)
            if result and result.get("queue", {}).get("slots"):
                return result["queue"]["slots"][0]
            return {}
        except Exception as e:
            logger.error(f"Sabnzbd status error: {e}")
            return {}

    async def pause(self, job_id: str) -> bool:
        try:
            await self._client.pause_job(job_id)
            return True
        except Exception as e:
            logger.error(f"Sabnzbd pause error: {e}")
            return False

    async def resume(self, job_id: str) -> bool:
        try:
            await self._client.resume_job(job_id)
            return True
        except Exception as e:
            logger.error(f"Sabnzbd resume error: {e}")
            return False

    async def cancel(self, job_id: str) -> bool:
        try:
            await self._client.delete_job(job_id, delete_files=True)
            return True
        except Exception as e:
            logger.error(f"Sabnzbd cancel error: {e}")
            return False

