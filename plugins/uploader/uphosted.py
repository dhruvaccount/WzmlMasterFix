import asyncio
import logging
import os
import re
import time
from typing import Any, Optional

from plugins.base import UploaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.uphoster_uploader")


class UphosterUploader(UploaderPlugin):
    name = "uphosted"
    plugin_type = "uploader"

    def __init__(self):
        self._services = {
            "gofile": "https://gofile.io",
            "catbox": "https://catbox.moe",
            "pixeldrain": "https://pixeldrain.com",
            "fileio": "https://file.io",
            "0x0": "https://0x0.st",
        }
        self._active_processes = {}
        # curl progress output matcher
        self._progress_regex = re.compile(
            r"^\s*(?P<percent>\d+)\s+(?P<total>[\d\.]+[A-Za-z]?)\s+\d+\s+(?P<received>[\d\.]+[A-Za-z]?)\s+\d+\s+(?P<uploaded>[\d\.]+[A-Za-z]?)\s+[\d\.]+[A-Za-z]?\s+(?P<speed>[\d\.]+[A-Za-z]?)\s+(?P<total_time>[\d:]+|--:--:--)\s+(?P<time_spent>[\d:]+|--:--:--)\s+(?P<eta>[\d:]+|--:--:--)"
        )

    def _parse_size(self, size_str: str) -> int:
        if not size_str or size_str == "--" or size_str == "0":
            return 0

        multiplier = 1
        unit = ""

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
                logger.info("Uphoster uploader initialized (using curl)")
                return True
            else:
                logger.error("curl not found in PATH")
                return False
        except Exception as e:
            logger.error(f"Uphoster init error: {e}")
            return False

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        file_path = context.source
        service = config.get("service", "0x0").lower()

        if not os.path.exists(file_path):
            return PluginResult(success=False, error="File not found")

        try:
            if service == "gofile":
                return await self._upload_gofile(context, file_path)
            elif service == "catbox":
                return await self._upload_catbox(context, file_path)
            elif service == "pixeldrain":
                return await self._upload_pixeldrain(context, file_path)
            elif service == "fileio":
                return await self._upload_fileio(context, file_path)
            elif service == "0x0":
                return await self._upload_0x0(context, file_path)
            else:
                return PluginResult(success=False, error=f"Unknown service: {service}")

        except Exception as e:
            if context.task_id in self._active_processes:
                try:
                    self._active_processes[context.task_id].terminate()
                except:
                    pass
                del self._active_processes[context.task_id]

            logger.error(f"Uphoster upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _execute_curl_upload(self, context: PluginContext, cmd: list) -> tuple:
        from core.task import update_task_progress, _task_store

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_processes[context.task_id] = process

        last_update = 0
        total_size = os.path.getsize(context.source)

        while True:
            t = _task_store.get(context.task_id)
            if t and t.status.value == "cancelled":
                process.terminate()
                raise Exception("Task cancelled by user")

            line = await process.stderr.readline()
            if not line:
                break

            line_str = line.decode().strip()
            match = self._progress_regex.search(line_str)
            if match:
                now = time.time()
                if now - last_update >= 1.0:
                    data = match.groupdict()
                    pct = float(data["percent"])
                    uploaded = self._parse_size(data["uploaded"])
                    speed = self._parse_size(data["speed"])
                    eta = self._parse_time(data["eta"])

                    asyncio.create_task(
                        update_task_progress(
                            task_id=context.task_id,
                            stage="Uploading",
                            plugin=self.name,
                            progress=pct,
                            speed=speed,
                            eta=eta,
                            uploaded=uploaded,
                            total=total_size,
                        )
                    )
                    last_update = now

        stdout, stderr = await process.communicate()
        if context.task_id in self._active_processes:
            del self._active_processes[context.task_id]

        return process.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def _upload_gofile(
        self, context: PluginContext, file_path: str
    ) -> PluginResult:
        # Gofile requires finding the best server first
        try:
            import json
            import aiohttp

            server = "store1"
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.gofile.io/getServer") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "ok":
                            server = data["data"]["server"]

            upload_url = f"https://{server}.gofile.io/uploadFile"
            cmd = ["curl", "-F", f"file=@{file_path}", upload_url]

            ret, stdout, stderr = await self._execute_curl_upload(context, cmd)
            if ret == 0 and stdout:
                try:
                    data = json.loads(stdout)
                    if data.get("status") == "ok":
                        file_data = data.get("data", {})
                        return PluginResult(
                            success=True,
                            output_path=file_data.get("downloadPage"),
                            metadata={
                                "url": file_data.get("downloadPage"),
                                "file_id": file_data.get("fileId"),
                            },
                        )
                except:
                    pass
            return PluginResult(success=False, error="Upload failed")
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _upload_catbox(
        self, context: PluginContext, file_path: str
    ) -> PluginResult:
        cmd = [
            "curl",
            "-F",
            "reqtype=fileupload",
            "-F",
            f"fileToUpload=@{file_path}",
            "https://catbox.moe/user/api.php",
        ]
        ret, stdout, stderr = await self._execute_curl_upload(context, cmd)
        if ret == 0 and stdout.startswith("http"):
            return PluginResult(
                success=True,
                output_path=stdout,
                metadata={"url": stdout},
            )
        return PluginResult(success=False, error="Upload failed")

    async def _upload_pixeldrain(
        self, context: PluginContext, file_path: str
    ) -> PluginResult:
        import json

        cmd = ["curl", "-T", file_path, "https://pixeldrain.com/api/file"]
        ret, stdout, stderr = await self._execute_curl_upload(context, cmd)
        if ret == 0 and stdout:
            try:
                data = json.loads(stdout)
                if data.get("success"):
                    url = f"https://pixeldrain.com/u/{data.get('id')}"
                    return PluginResult(
                        success=True,
                        output_path=url,
                        metadata={"url": url, "id": data.get("id")},
                    )
            except:
                pass
        return PluginResult(success=False, error="Upload failed")

    async def _upload_fileio(
        self, context: PluginContext, file_path: str
    ) -> PluginResult:
        import json

        cmd = ["curl", "-F", f"file=@{file_path}", "https://file.io"]
        ret, stdout, stderr = await self._execute_curl_upload(context, cmd)
        if ret == 0 and stdout:
            try:
                data = json.loads(stdout)
                if data.get("success"):
                    return PluginResult(
                        success=True,
                        output_path=data.get("link"),
                        metadata={"link": data.get("link")},
                    )
            except:
                pass
        return PluginResult(success=False, error="Upload failed")

    async def _upload_0x0(self, context: PluginContext, file_path: str) -> PluginResult:
        cmd = ["curl", "-F", f"file=@{file_path}", "https://0x0.st"]
        ret, stdout, stderr = await self._execute_curl_upload(context, cmd)
        if ret == 0 and stdout:
            url = stdout.strip()
            return PluginResult(
                success=True,
                output_path=url,
                metadata={"url": url},
            )
        return PluginResult(success=False, error="Upload failed")
