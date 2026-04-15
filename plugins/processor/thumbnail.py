import asyncio
import logging
import os
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.thumbnail_processor")


class ThumbnailProcessor(ProcessorPlugin):
    name = "thumbnail"
    plugin_type = "processor"

    def __init__(self):
        pass

    async def initialize(self) -> bool:
        logger.info("Thumbnail processor initialized")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output_path = config.get("output_path", "thumb.jpg")
        time = config.get("time", "00:00:01")
        width = config.get("width", 320)
        height = config.get("height", 240)
        embed = config.get("embed", False)

        try:
            result = await self._generate_thumbnail(
                source, output_path, time, width, height
            )

            return PluginResult(
                success=True,
                output_path=result.get("path"),
                metadata=result,
            )

        except Exception as e:
            logger.error(f"Thumbnail error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _generate_thumbnail(
        self, source: str, output: str, time: str, width: int, height: int
    ) -> dict:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            time,
            "-i",
            source,
            "-vframes",
            "1",
            "-vf",
            f"scale={width}:{height}",
            output,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            cmd = ["ffmpeg", "-y", "-ss", time, "-i", source, "-vframes", "1", output]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

        if process.returncode == 0:
            return {"path": output, "source": source}
        else:
            raise Exception(stderr.decode())

    async def generate_multiple(
        self, source: str, output_dir: str, count: int = 5
    ) -> list:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        durations = []
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            source,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()

        if process.returncode == 0:
            try:
                total_duration = float(stdout.decode().strip())
                step = total_duration / count

                for i in range(count):
                    time_pos = f"{(i * step):.2f}"
                    output = os.path.join(output_dir, f"thumb_{i}.jpg")
                    await self._generate_thumbnail(source, output, time_pos, 320, 240)
                    durations.append(output)
            except Exception as e:
                logger.error(f"Multiple thumbnail error: {e}")

        return durations
