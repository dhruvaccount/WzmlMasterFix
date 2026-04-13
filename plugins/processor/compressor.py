import asyncio
import logging
import os
import zipfile
import tarfile
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.compressor")


class CompressorProcessor(ProcessorPlugin):
    name = "compressor"
    plugin_type = "processor"

    def __init__(self):
        self._method = "zip"
        self._level = 6

    async def initialize(self, method: str = "zip", level: int = 6) -> bool:
        self._method = method
        self._level = level
        logger.info(f"Compressor initialized: {method}")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output_path = config.get("output_path")
        method = config.get("method", self._method)
        level = config.get("level", self._level)
        password = config.get("password")

        if not os.path.exists(source):
            return PluginResult(success=False, error="Source not found")

        try:
            if not output_path:
                if os.path.isdir(source):
                    output_path = source + f".{method}"
                else:
                    output_path = source + f".{method}"

            if method == "zip":
                result = await self._compress_zip(source, output_path, level, password)
            elif method == "tar":
                result = await self._compress_tar(source, output_path)
            elif method == "tar.gz" or method == "tgz":
                result = await self._compress_targz(source, output_path)
            else:
                return PluginResult(success=False, error=f"Unknown format: {method}")

            return PluginResult(
                success=True,
                output_path=output_path,
                metadata=result,
            )

        except Exception as e:
            logger.error(f"Compression error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _compress_zip(
        self, source: str, output: str, level: int, password: str = None
    ) -> dict:
        compression = zipfile.ZIP_DEFLATED

        with zipfile.ZipFile(output, "w", compression) as zf:
            zf.compression_level = level

            if os.path.isdir(source):
                for root, dirs, files in os.walk(source):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source)
                        zf.write(file_path, arcname)
            else:
                zf.write(source, os.path.basename(source))

        return {
            "format": "zip",
            "size": os.path.getsize(output),
        }

    async def _compress_tar(self, source: str, output: str) -> dict:
        with tarfile.open(output, "w") as tf:
            if os.path.isdir(source):
                for root, dirs, files in os.walk(source):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source)
                        tf.add(file_path, arcname=arcname)
            else:
                tf.add(source, arcname=os.path.basename(source))

        return {"format": "tar", "size": os.path.getsize(output)}

    async def _compress_targz(self, source: str, output: str) -> dict:
        import gzip

        output_tar = output.replace(".tar.gz", ".tar").replace(".tgz", ".tar")

        with tarfile.open(output_tar, "w") as tf:
            if os.path.isdir(source):
                for root, dirs, files in os.walk(source):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source)
                        tf.add(file_path, arcname=arcname)
            else:
                tf.add(source, arcname=os.path.basename(source))

        with open(output_tar, "rb") as f_in:
            with gzip.open(output, "wb", compresslevel=9) as f_out:
                f_out.writelines(f_in)

        os.remove(output_tar)

        return {"format": "tar.gz", "size": os.path.getsize(output)}
