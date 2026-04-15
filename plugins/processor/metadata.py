import asyncio
import logging
import os
import mimetypes
import json
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.metadata_processor")


class MetadataProcessor(ProcessorPlugin):
    name = "metadata"
    plugin_type = "processor"

    def __init__(self):
        pass

    async def initialize(self) -> bool:
        logger.info("Metadata processor initialized")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source

        if not os.path.exists(source):
            return PluginResult(success=False, error="File not found")

        try:
            metadata = await self._extract_metadata(source, config)

            return PluginResult(
                success=True,
                output_path=source,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Metadata error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _extract_metadata(self, file_path: str, config: dict) -> dict:
        metadata = {
            "filename": os.path.basename(file_path),
            "size": os.path.getsize(file_path),
            "extension": os.path.splitext(file_path)[1],
        }

        mime_type = mimetypes.guess_type(file_path)[0]
        if mime_type:
            metadata["mime_type"] = mime_type

        try:
            metadata["modified_time"] = os.path.getmtime(file_path)
            metadata["created_time"] = os.path.getctime(file_path)
        except Exception:
            pass

        ext = metadata.get("extension", "").lower()

        if ext in [".mp4", ".mkv", ".avi", ".mov", ".wmv"]:
            info = await self._get_video_metadata(file_path)
            metadata.update(info)
        elif ext in [".mp3", ".ogg", ".m4a", ".wav", ".flac"]:
            info = await self._get_audio_metadata(file_path)
            metadata.update(info)
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            info = await self._get_image_metadata(file_path)
            metadata.update(info)

        return metadata

    async def _get_video_metadata(self, file_path: str) -> dict:
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                data = json.loads(stdout.decode())
                video_stream = next(
                    (
                        s
                        for s in data.get("streams", {})
                        if s.get("codec_type") == "video"
                    ),
                    None,
                )
                audio_stream = next(
                    (
                        s
                        for s in data.get("streams", {})
                        if s.get("codec_type") == "audio"
                    ),
                    None,
                )

                info = {"type": "video"}

                if video_stream:
                    info["duration"] = float(data.get("format", {}).get("duration", 0))
                    info["width"] = video_stream.get("width")
                    info["height"] = video_stream.get("height")
                    info["codec"] = video_stream.get("codec_name")
                    info["bitrate"] = int(data.get("format", {}).get("bit_rate", 0))

                return info
        except Exception as e:
            logger.error(f"Video metadata error: {e}")

        return {"type": "video"}

    async def _get_audio_metadata(self, file_path: str) -> dict:
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                data = json.loads(stdout.decode())
                audio_stream = next(
                    (
                        s
                        for s in data.get("streams", {})
                        if s.get("codec_type") == "audio"
                    ),
                    None,
                )

                info = {"type": "audio"}

                if audio_stream:
                    info["duration"] = float(data.get("format", {}).get("duration", 0))
                    info["codec"] = audio_stream.get("codec_name")
                    info["bitrate"] = int(data.get("format", {}).get("bit_rate", 0))
                    info["sample_rate"] = audio_stream.get("sample_rate")
                    info["channels"] = audio_stream.get("channels")

                return info
        except Exception as e:
            logger.error(f"Audio metadata error: {e}")

        return {"type": "audio"}

    async def _get_image_metadata(self, file_path: str) -> dict:
        def _extract():
            from PIL import Image

            with Image.open(file_path) as img:
                return {
                    "type": "image",
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                }

        try:
            return await asyncio.to_thread(_extract)
        except Exception as e:
            logger.error(f"Image metadata error: {e}")

        return {"type": "image"}

    async def write_metadata(self, file_path: str, metadata: dict) -> bool:
        def _write():
            json_path = file_path + ".json"
            with open(json_path, "w") as f:
                json.dump(metadata, f, indent=2)
            return True

        try:
            return await asyncio.to_thread(_write)
        except Exception as e:
            logger.error(f"Write metadata error: {e}")
            return False
