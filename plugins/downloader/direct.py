import asyncio
import logging
import os
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

from plugins.base import DownloaderPlugin, PluginContext, PluginResult
from core.helpers.bypass import bypass_link

logger = logging.getLogger("wzml.direct_downloader")


class DirectDownloader(DownloaderPlugin):
    name = "direct"
    plugin_type = "downloader"

    def __init__(self):
        self._active_processes = {}
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        # curl progress output matcher
        self._progress_regex = re.compile(
            r"^\s*(?P<percent>\d+)\s+(?P<total>[\d\.]+[A-Za-z]?)\s+\d+\s+(?P<received>[\d\.]+[A-Za-z]?)\s+\d+\s+[\d\.]+[A-Za-z]?\s+(?P<speed>[\d\.]+[A-Za-z]?)\s+[\d\.]+[A-Za-z]?\s+(?P<total_time>[\d:]+|--:--:--)\s+(?P<time_spent>[\d:]+|--:--:--)\s+(?P<eta>[\d:]+|--:--:--)"
        )

    def _parse_size(self, size_str: str) -> int:
        if not size_str or size_str == "--" or size_str == "0":
            return 0

        multiplier = 1
        unit = ""

        # Extract numeric part and unit
        match = re.match(r"([\d\.]+)([A-Za-z]*)", size_str)
        if match:
            val, unit = match.groups()
            val = float(val)
        else:
            return 0

        unit = unit.lower()
        if unit == "k":
            multiplier = 1024
        elif unit == "m":
            multiplier = 1024**2
        elif unit == "g":
            multiplier = 1024**3
        elif unit == "t":
            multiplier = 1024**4

        return int(val * multiplier)

    def _parse_time(self, time_str: str) -> int:
        if not time_str or time_str == "--:--:--":
            return 0
        parts = time_str.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return 0

    async def initialize(self) -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                "curl",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                version = stdout.decode().split("\n")[0].strip()
                logger.info(f"Direct downloader initialized (using {version})")
                return True
            else:
                logger.error("curl not found in PATH")
                return False
        except Exception as e:
            logger.error(f"Direct init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")
        filename = config.get("filename")
        headers = config.get("headers", {})
        bypass_enabled = config.get("bypass", True)

        if bypass_enabled:
            try:
                url = await bypass_link(url) or url
            except:
                pass

        try:
            parsed = urlparse(url)
            if not filename:
                path = parsed.path
                filename = os.path.basename(path) if path else f"download_{hash(url)}"

            output_file = os.path.join(output_path, filename)

            if not os.path.exists(output_path):
                os.makedirs(output_path, exist_ok=True)

            req_headers = self._headers.copy()
            req_headers.update(headers)

            cmd = [
                "curl",
                "-L",  # Follow redirects
                "--create-dirs",
                "-o",
                output_file,
            ]

            for k, v in req_headers.items():
                cmd.extend(["-H", f"{k}: {v}"])

            cmd.append(url)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._active_processes[context.task_id] = process

            from core.task import update_task_progress, _task_store

            last_update = 0

            # curl outputs progress to stderr
            while True:
                # Check cancellation
                t = _task_store.get(context.task_id)
                if t and t.status.value == "cancelled":
                    process.terminate()
                    raise Exception("Task cancelled by user")

                line = await process.stderr.readline()
                if not line:
                    break

                line_str = line.decode().strip()

                # Try parsing progress
                match = self._progress_regex.search(line_str)
                if match:
                    now = time.time()
                    if now - last_update >= 1.0:
                        data = match.groupdict()

                        pct = float(data["percent"])
                        total = self._parse_size(data["total"])
                        downloaded = self._parse_size(data["received"])
                        speed = self._parse_size(data["speed"])
                        eta = self._parse_time(data["eta"])

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

            await process.wait()
            if context.task_id in self._active_processes:
                del self._active_processes[context.task_id]

            if process.returncode != 0:
                # If error, try reading the actual error
                err_msg = f"curl exited with code {process.returncode}"
                raise Exception(err_msg)

            # Get final file size
            file_size = (
                os.path.getsize(output_file) if os.path.exists(output_file) else 0
            )

            result = {
                "url": url,
                "filename": filename,
                "size": file_size,
            }

            return PluginResult(
                success=True,
                output_path=output_file,
                metadata=result,
            )

        except Exception as e:
            if context.task_id in self._active_processes:
                try:
                    self._active_processes[context.task_id].terminate()
                except:
                    pass
                del self._active_processes[context.task_id]

            logger.error(f"Direct download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self, url: str = None) -> dict:
        try:
            cmd = ["curl", "-I", "-s", "-L", url]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            status = 0
            content_length = "0"
            content_type = ""

            for line in stdout.decode().split("\n"):
                line = line.strip().lower()
                if line.startswith("http/"):
                    parts = line.split(" ", 2)
                    if len(parts) >= 2 and parts[1].isdigit():
                        status = int(parts[1])
                elif line.startswith("content-length:"):
                    content_length = line.split(":", 1)[1].strip()
                elif line.startswith("content-type:"):
                    content_type = line.split(":", 1)[1].strip()

            return {
                "status": status,
                "content_length": content_length,
                "content_type": content_type,
            }
        except Exception as e:
            logger.error(f"Direct status error: {e}")
            return {"error": str(e)}

    async def get_content_info(self, url: str) -> dict:
        try:
            cmd = ["curl", "-I", "-s", "-L", url]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            content_length = "0"
            content_type = ""
            last_modified = ""

            for line in stdout.decode().split("\n"):
                line_lower = line.strip().lower()
                if line_lower.startswith("content-length:"):
                    content_length = line_lower.split(":", 1)[1].strip()
                elif line_lower.startswith("content-type:"):
                    content_type = line.split(":", 1)[1].strip()
                elif line_lower.startswith("last-modified:"):
                    last_modified = line.split(":", 1)[1].strip()

            return {
                "content_length": int(content_length),
                "content_type": content_type,
                "last_modified": last_modified,
                "filename": os.path.basename(urlparse(url).path),
            }
        except Exception as e:
            logger.error(f"Direct info error: {e}")
            return {}

    async def create_download_session(self, url: str, headers: dict = None) -> str:
        # Not applicable since we are using subprocess for each download
        return "session_not_needed"

    async def cancel_download(self, session_id: str) -> bool:
        # Handled by the task cancellation mechanism now
        return True
