import asyncio
import logging
import os
import zipfile
import tarfile
import subprocess
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.extractor")


class ExtractorProcessor(ProcessorPlugin):
    name = "extractor"
    plugin_type = "processor"

    def __init__(self):
        self._password = None

    async def initialize(self, password: str = None) -> bool:
        self._password = password
        logger.info("Extractor initialized")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output_path = config.get("output_path", os.path.dirname(source))
        password = config.get("password", self._password)

        if not os.path.exists(source):
            return PluginResult(success=False, error="File not found")

        try:
            extracted_files = []

            if source.endswith(".zip"):
                result = await self._extract_zip(source, output_path, password)
                extracted_files = result.get("files", [])
            elif source.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
                result = await self._extract_tar(source, output_path)
                extracted_files = result.get("files", [])
            elif source.endswith(".7z"):
                result = await self._extract_7z(source, output_path, password)
                extracted_files = result.get("files", [])
            elif source.endswith(".rar"):
                result = await self._extract_rar(source, output_path, password)
                extracted_files = result.get("files", [])
            else:
                return PluginResult(success=False, error="Unsupported archive format")

            return PluginResult(
                success=True,
                output_path=output_path,
                output_paths=extracted_files,
                metadata={"count": len(extracted_files)},
            )

        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _extract_zip(
        self, archive_path: str, output_path: str, password: str = None
    ) -> dict:
        files = []

        with zipfile.ZipFile(archive_path, "r") as zf:
            if password:
                zf.setpassword(password.encode() if password else None)

            zf.extractall(output_path)
            files = zf.namelist()

        return {"files": files, "path": output_path}

    async def _extract_tar(self, archive_path: str, output_path: str) -> dict:
        files = []

        with tarfile.open(archive_path, "r") as tf:
            tf.extractall(output_path)
            files = tf.getnames()

        return {"files": files, "path": output_path}

    async def _extract_7z(
        self, archive_path: str, output_path: str, password: str = None
    ) -> dict:
        try:
            cmd = ["7z", "x", archive_path, f"-o{output_path}", "-y"]
            if password:
                cmd.append(f"-p{password}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return {"files": [], "path": output_path}
            else:
                raise Exception(result.stderr)
        except Exception as e:
            logger.error(f"7z extraction error: {e}")
            raise

    async def _extract_rar(
        self, archive_path: str, output_path: str, password: str = None
    ) -> dict:
        try:
            cmd = ["unrar", "x", archive_path, output_path, "-y"]
            if password:
                cmd.insert(2, f"-p{password}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return {"files": [], "path": output_path}
            else:
                raise Exception(result.stderr)
        except Exception as e:
            logger.error(f"Rar extraction error: {e}")
            raise

    async def create_archive(
        self,
        source_path: str,
        output_path: str,
        format: str = "zip",
        password: str = None,
    ) -> str:
        if format == "zip":
            return await self._create_zip(source_path, output_path, password)
        elif format == "tar":
            return await self._create_tar(source_path, output_path)
        return source_path

    async def _create_zip(self, source: str, output: str, password: str = None) -> str:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.isdir(source):
                for root, dirs, files in os.walk(source):
                    for file in files:
                        zf.write(os.path.join(root, file), file)
            else:
                zf.write(source, os.path.basename(source))
        return output

    async def _create_tar(self, source: str, output: str) -> str:
        with tarfile.open(output, "w") as tf:
            if os.path.isdir(source):
                for root, dirs, files in os.walk(source):
                    for file in files:
                        tf.add(os.path.join(root, file), arcname=file)
            else:
                tf.add(source, arcname=os.path.basename(source))
        return output
