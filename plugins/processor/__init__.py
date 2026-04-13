import asyncio
import logging
import os
import zipfile
import tarfile
import subprocess
from pathlib import Path
from typing import Any

from plugins.base import ProcessorPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError


logger = logging.getLogger("wzml.processor")


class Extractor(ProcessorPlugin):
    name = "extractor"
    plugin_type = "processor"

    def __init__(self):
        self._password = None

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._extract(source, config)
            return PluginResult(
                success=True,
                output_path=result.get("path"),
                output_paths=result.get("paths", []),
            )
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _extract(self, source: str, config: dict) -> dict:
        password = config.get("password")

        if not os.path.exists(source):
            return {"path": source}

        if source.endswith(".zip"):
            with zipfile.ZipFile(source, "r") as zf:
                if password:
                    zf.setpassword(password.encode())
                extract_dir = source.replace(".zip", "")
                zf.extractall(extract_dir)
                return {"path": extract_dir, "paths": []}

        elif source.endswith((".tar", ".tar.gz", ".tgz")):
            with tarfile.open(source, "r") as tf:
                extract_dir = (
                    source.replace(".tar.gz", "")
                    .replace(".tgz", "")
                    .replace(".tar", "")
                )
                tf.extractall(extract_dir)
                return {"path": extract_dir, "paths": []}

        return {"path": source}


class Compressor(ProcessorPlugin):
    name = "compressor"
    plugin_type = "processor"

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        method = config.get("method", "zip")

        try:
            result = await self._compress(source, method, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _compress(self, source: str, method: str, config: dict) -> dict:
        if method == "zip":
            output = source + ".zip"
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                if os.path.isdir(source):
                    for root, dirs, files in os.walk(source):
                        for file in files:
                            zf.write(os.path.join(root, file), file)
                else:
                    zf.write(source, os.path.basename(source))
            return {"path": output}

        elif method == "tar":
            output = source + ".tar"
            with tarfile.open(output, "w") as tf:
                if os.path.isdir(source):
                    for root, dirs, files in os.walk(source):
                        for file in files:
                            tf.add(os.path.join(root, file), arcname=file)
                else:
                    tf.add(source, os.path.basename(source))
            return {"path": output}

        return {"path": source}


class FFmpegProcessor(ProcessorPlugin):
    name = "ffmpeg"
    plugin_type = "processor"

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        action = config.get("action", "transcode")

        try:
            result = await self._ffmpeg_process(source, action, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _ffmpeg_process(self, source: str, action: str, config: dict) -> dict:
        output = source.rsplit(".", 1)[0] + "_processed.mp4"

        return {"path": output}


class MetadataExtractor(ProcessorPlugin):
    name = "metadata"
    plugin_type = "processor"

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        try:
            result = await self._extract_metadata(source, config)
            return PluginResult(success=True, output_path=source, metadata=result)
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _extract_metadata(self, source: str, config: dict) -> dict:
        import mimetypes

        mime_type = mimetypes.guess_type(source)[0]

        return {
            "filename": os.path.basename(source),
            "size": os.path.getsize(source) if os.path.exists(source) else 0,
            "mime_type": mime_type,
        }


class ThumbnailGenerator(ProcessorPlugin):
    name = "thumbnail"
    plugin_type = "processor"

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        embed = config.get("embed", False)

        try:
            result = await self._generate_thumbnail(source, embed, config)
            return PluginResult(success=True, output_path=result.get("path"))
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _generate_thumbnail(self, source: str, embed: bool, config: dict) -> dict:
        return {"path": source}


class FileSplitter(ProcessorPlugin):
    name = "splitter"
    plugin_type = "processor"

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        chunk_size = config.get("chunk_size", 10 * 1024 * 1024)

        try:
            result = await self._split_file(source, chunk_size, config)
            return PluginResult(
                success=True,
                output_paths=result.get("paths", []),
            )
        except Exception as e:
            return PluginResult(success=False, error=str(e))

    async def _split_file(self, source: str, chunk_size: int, config: dict) -> dict:
        return {"paths": []}


class FileRenamer(ProcessorPlugin):
    name = "renamer"
    plugin_type = "processor"

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        pattern = config.get("pattern", "")
        replacement = config.get("replacement", "")

        try:
            new_name = (
                pattern.replace("*", replacement)
                if pattern
                else os.path.basename(source)
            )
            new_path = os.path.join(os.path.dirname(source), new_name)
            os.rename(source, new_path)
            return PluginResult(success=True, output_path=new_path)
        except Exception as e:
            return PluginResult(success=False, error=str(e))


PROCESSOR_CLASSES = {
    "extractor": Extractor,
    "compressor": Compressor,
    "ffmpeg": FFmpegProcessor,
    "metadata": MetadataExtractor,
    "thumbnail": ThumbnailGenerator,
    "splitter": FileSplitter,
    "renamer": FileRenamer,
}


def get_processor(name: str) -> ProcessorPlugin:
    cls = PROCESSOR_CLASSES.get(name)
    if cls:
        return cls()
    return None
