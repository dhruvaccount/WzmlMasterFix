import asyncio
import logging
import os
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

    async def initialize(self) -> bool:
        logger.info("Uphoster uploader initialized")
        return True

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        file_path = context.source
        service = config.get("service", "gofile")

        if not os.path.exists(file_path):
            return PluginResult(success=False, error="File not found")

        try:
            if service == "gofile":
                return await self._upload_gofile(file_path)
            elif service == "catbox":
                return await self._upload_catbox(file_path)
            elif service == "pixeldrain":
                return await self._upload_pixeldrain(file_path)
            elif service == "fileio":
                return await self._upload_fileio(file_path)
            elif service == "0x0":
                return await self._upload_0x0(file_path)
            else:
                return PluginResult(success=False, error=f"Unknown service: {service}")

        except Exception as e:
            logger.error(f"Uphoster upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _upload_gofile(self, file_path: str) -> PluginResult:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("fileToUpload", open(file_path, "rb"))

                async with session.post(
                    "https://up.gofile.io/api/uploadFile", data=form
                ) as response:
                    data = await response.json()

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

            return PluginResult(success=False, error="Upload failed")

        except Exception as e:
            logger.error(f"GoFile upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _upload_catbox(self, file_path: str) -> PluginResult:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("reqtype", "fileupload")
                form.add_field("fileToUpload", open(file_path, "rb"))

                async with session.post(
                    "https://catbox.moe/api/v1/upload", data=form
                ) as response:
                    data = await response.json()

                    if data.get("success"):
                        return PluginResult(
                            success=True,
                            output_path=data.get("file", {}).get("url"),
                            metadata={"url": data.get("file", {}).get("url")},
                        )

            return PluginResult(success=False, error="Upload failed")

        except Exception as e:
            logger.error(f"Catbox upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _upload_pixeldrain(self, file_path: str) -> PluginResult:
        try:
            import aiohttp

            file_name = os.path.basename(file_path)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://pixeldrain.com/api/file/{file_name}",
                    data=open(file_path, "rb"),
                ) as response:
                    if response.status == 200:
                        url = str(response.url)
                        return PluginResult(
                            success=True,
                            output_path=url,
                            metadata={"url": url},
                        )

            return PluginResult(success=False, error="Upload failed")

        except Exception as e:
            logger.error(f"Pixeldrain upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _upload_fileio(self, file_path: str) -> PluginResult:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("file", open(file_path, "rb"))

                async with session.post("https://file.io", data=form) as response:
                    data = await response.json()

                    if data.get("success"):
                        return PluginResult(
                            success=True,
                            output_path=data.get("link"),
                            metadata={"link": data.get("link")},
                        )

            return PluginResult(success=False, error="Upload failed")

        except Exception as e:
            logger.error(f"File.io upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _upload_0x0(self, file_path: str) -> PluginResult:
        try:
            import subprocess

            cmd = ["curl", "-F", f"file=@{file_path}", "https://0x0.st"]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and result.stdout.strip():
                url = result.stdout.strip()
                return PluginResult(
                    success=True,
                    output_path=url,
                    metadata={"url": url},
                )

            return PluginResult(success=False, error="Upload failed")

        except Exception as e:
            logger.error(f"0x0 upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def link(self, url: str, service: str = "gofile") -> str:
        try:
            if service == "gofile":
                return f"https://gofile.io/d/{url}"
            elif service == "catbox":
                return f"https://catbox.moe/{url}"
            elif service == "pixeldrain":
                return f"https://pixeldrain.com/api/file/{url}"
            elif service == "fileio":
                return f"https://file.io/{url}"
            return url
        except Exception as e:
            logger.error(f"Uphoster link error: {e}")
            return url
