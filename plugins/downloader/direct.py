import asyncio
import logging
import os
import hashlib
import mimetypes
import time
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen, Request
from urllib.request import urlretrieve

from plugins.base import DownloaderPlugin, PluginContext, PluginResult
from core.helpers.bypass import bypass_link

logger = logging.getLogger("wzml.direct_downloader")


class DirectDownloader(DownloaderPlugin):
    name = "direct"
    plugin_type = "downloader"

    def __init__(self):
        self._session = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def initialize(self) -> bool:
        try:
            import aiohttp

            self._session = aiohttp.ClientSession()
            logger.info("Direct downloader initialized")
            return True
        except Exception as e:
            logger.error(f"Direct init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")
        filename = config.get("filename")
        headers = config.get("headers", {})
        timeout = config.get("timeout", 300)
        chunk_size = config.get("chunk_size", 8192)
        bypass_enabled = config.get("bypass", True)

        if bypass_enabled:
            url = await bypass_link(url) or url

        try:
            parsed = urlparse(url)
            if not filename:
                path = parsed.path
                filename = os.path.basename(path) if path else f"download_{hash(url)}"
            output_file = os.path.join(output_path, filename)

            if not os.path.exists(output_path):
                os.makedirs(output_path, exist_ok=True)

            from core.task import update_task_progress
            import aiohttp

            async with aiohttp.ClientSession() as session:
                req_headers = self._headers.copy()
                req_headers.update(headers)

                async with session.get(url, headers=req_headers) as response:
                    if response.status != 200:
                        return PluginResult(
                            success=False, error=f"HTTP {response.status}"
                        )

                    content_length = response.headers.get("Content-Length")
                    total_size = int(content_length) if content_length else 0

                    with open(output_file, "wb") as f:
                        downloaded = 0
                        start_time = time.time()
                        last_update = start_time

                        from core.task import get_task

                        async for chunk in response.content.iter_chunked(chunk_size):
                            # Check cancellation
                            t = await get_task(context.task_id)
                            if t and t.status.value == "cancelled":
                                return PluginResult(
                                    success=False, error="Task cancelled by user"
                                )

                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            if now - last_update > 1.0:
                                speed = (
                                    downloaded / (now - start_time)
                                    if now > start_time
                                    else 0
                                )
                                eta = (
                                    int((total_size - downloaded) / speed)
                                    if speed > 0 and total_size
                                    else 0
                                )
                                pct = (
                                    (downloaded / total_size) * 100
                                    if total_size
                                    else 0.0
                                )

                                await update_task_progress(
                                    task_id=context.task_id,
                                    stage="Downloading",
                                    plugin=self.name,
                                    progress=pct,
                                    speed=speed,
                                    eta=eta,
                                    downloaded=downloaded,
                                    total=total_size,
                                )
                                last_update = now

                    result = {
                        "url": url,
                        "filename": filename,
                        "size": total_size,
                        "content_type": response.headers.get("Content-Type"),
                    }

                    return PluginResult(
                        success=True,
                        output_path=output_file,
                        metadata=result,
                    )

        except asyncio.TimeoutError:
            logger.error(f"Direct download timeout: {url}")
            return PluginResult(success=False, error="Download timeout")
        except Exception as e:
            logger.error(f"Direct download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self, url: str = None) -> dict:
        try:
            req = Request(url)
            req.add_header("User-Agent", self._headers["User-Agent"])
            with urlopen(req) as response:
                return {
                    "status": response.status,
                    "content_length": response.headers.get("Content-Length"),
                    "content_type": response.headers.get("Content-Type"),
                }
        except Exception as e:
            logger.error(f"Direct status error: {e}")
            return {"error": str(e)}

    async def get_content_info(self, url: str) -> dict:
        try:
            with urlopen(url) as response:
                return {
                    "content_length": int(response.headers.get("Content-Length", 0)),
                    "content_type": response.headers.get("Content-Type"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "filename": os.path.basename(response.url),
                }
        except Exception as e:
            logger.error(f"Direct info error: {e}")
            return {}

    async def create_download_session(self, url: str, headers: dict = None) -> str:
        try:
            import aiohttp

            session_id = hashlib.sha256(f"{url}{time.time()}".encode()).hexdigest()

            self._sessions[session_id] = {
                "url": url,
                "headers": headers or self._headers,
                "active": True,
            }

            return session_id
        except Exception as e:
            logger.error(f"Direct session error: {e}")
            return None

    async def cancel_download(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id]["active"] = False
            return True
        return False
