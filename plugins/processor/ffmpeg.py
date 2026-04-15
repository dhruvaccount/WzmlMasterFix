import asyncio
import logging
import os
import re
import time
import json
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.ffmpeg_processor")


class FFmpegProcessor(ProcessorPlugin):
    name = "ffmpeg"
    plugin_type = "processor"

    def __init__(self):
        self._ffmpeg_path = "ffmpeg"
        self._ffprobe_path = "ffprobe"
        self._active_processes = {}
        self._time_regex = re.compile(r"time=(?P<time>[\d:\.]+)")

    async def initialize(
        self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"
    ) -> bool:
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        try:
            # Check if ffmpeg is available
            process = await asyncio.create_subprocess_exec(
                self._ffmpeg_path,
                "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            if process.returncode == 0:
                logger.info("FFmpeg processor initialized")
                return True
            else:
                logger.error("ffmpeg binary not found in PATH")
                return False
        except Exception as e:
            logger.error(f"FFmpeg init error: {e}")
            return False

    def _parse_time(self, time_str: str) -> float:
        try:
            parts = time_str.split(":")
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            return float(time_str)
        except ValueError:
            return 0.0

    async def get_media_info(self, file_path: str) -> dict:
        try:
            cmd = [
                self._ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                return json.loads(stdout.decode())
            return {}
        except Exception as e:
            logger.error(f"FFprobe error: {e}")
            return {}

    async def _execute_ffmpeg(
        self, context: PluginContext, cmd: list, stage_name: str
    ) -> tuple:
        from core.task import update_task_progress, _task_store

        info = await self.get_media_info(context.source)
        total_duration = 0.0

        if info and "format" in info and "duration" in info["format"]:
            total_duration = float(info["format"]["duration"])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_processes[context.task_id] = process

        last_update = 0
        start_time = time.time()

        while True:
            t = _task_store.get(context.task_id)
            if t and t.status.value == "cancelled":
                process.terminate()
                raise Exception("Task cancelled by user")

            line = await process.stderr.readline()
            if not line:
                break

            line_str = line.decode().strip()
            match = self._time_regex.search(line_str)
            if match and total_duration > 0:
                current_time = self._parse_time(match.group("time"))
                now = time.time()

                if now - last_update >= 1.0:
                    pct = (
                        (current_time / total_duration) * 100 if total_duration else 0.0
                    )
                    pct = min(pct, 100.0)

                    elapsed = now - start_time
                    speed = current_time / elapsed if elapsed > 0 else 0
                    eta = (
                        int((total_duration - current_time) / speed) if speed > 0 else 0
                    )

                    asyncio.create_task(
                        update_task_progress(
                            task_id=context.task_id,
                            stage=stage_name,
                            plugin=self.name,
                            progress=pct,
                            speed=speed,  # This is roughly 'processed seconds per real second'
                            eta=eta,
                            uploaded=int(current_time),
                            total=int(total_duration),
                        )
                    )
                    last_update = now

        stdout, stderr = await process.communicate()
        if context.task_id in self._active_processes:
            del self._active_processes[context.task_id]

        return process.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        action = config.get("action", "transcode")

        if not os.path.exists(source) and action != "concat":
            return PluginResult(success=False, error="Source file not found")

        try:
            if action == "transcode":
                return await self._transcode(context, config)
            elif action == "extract_audio":
                return await self._extract_audio(context, config)
            elif action == "generate_thumb":
                return await self._generate_thumb(context, config)
            elif action == "trim":
                return await self._trim(context, config)
            elif action == "concat":
                return await self._concat(context, config)
            elif action == "convert":
                return await self._convert(context, config)
            else:
                return PluginResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            if context.task_id in self._active_processes:
                try:
                    self._active_processes[context.task_id].terminate()
                except:
                    pass
                del self._active_processes[context.task_id]

            logger.error(f"FFmpeg error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _transcode(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output = config.get("output", source.rsplit(".", 1)[0] + "_transcoded.mp4")
        vcodec = config.get("vcodec", "libx264")
        acodec = config.get("acodec", "aac")
        crf = config.get("crf", 23)
        preset = config.get("preset", "medium")

        cmd = [
            self._ffmpeg_path,
            "-i",
            source,
            "-c:v",
            vcodec,
            "-c:a",
            acodec,
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-y",
            output,
        ]

        ret, stdout, stderr = await self._execute_ffmpeg(context, cmd, "Transcoding")

        if ret == 0:
            return PluginResult(
                success=True,
                output_path=output,
                metadata={"original": source, "output": output},
            )
        else:
            return PluginResult(success=False, error=stderr)

    async def _extract_audio(
        self, context: PluginContext, config: dict
    ) -> PluginResult:
        source = context.source
        output = config.get("output", source.rsplit(".", 1)[0] + ".mp3")
        format = config.get("format", "mp3")
        bitrate = config.get("bitrate", "192k")

        cmd = [
            self._ffmpeg_path,
            "-i",
            source,
            "-vn",
            "-ab",
            bitrate,
            "-ar",
            "44100",
            "-ac",
            "2",
            "-y",
            output,
        ]

        ret, stdout, stderr = await self._execute_ffmpeg(
            context, cmd, "Extracting Audio"
        )

        if ret == 0:
            return PluginResult(
                success=True,
                output_path=output,
                metadata={"format": format},
            )
        else:
            return PluginResult(success=False, error=stderr)

    async def _generate_thumb(
        self, context: PluginContext, config: dict
    ) -> PluginResult:
        source = context.source
        output = config.get("output", "thumb.jpg")
        time_str = config.get("time", "00:00:01")

        cmd = [
            self._ffmpeg_path,
            "-i",
            source,
            "-ss",
            time_str,
            "-vframes",
            "1",
            "-y",
            output,
        ]

        ret, stdout, stderr = await self._execute_ffmpeg(
            context, cmd, "Generating Thumbnail"
        )

        if ret == 0:
            return PluginResult(
                success=True,
                output_path=output,
                metadata={"thumbnail": output},
            )
        else:
            return PluginResult(success=False, error=stderr)

    async def _trim(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output = config.get("output", source.rsplit(".", 1)[0] + "_trim.mp4")
        start = config.get("start", "00:00:00")
        duration = config.get("duration", None)

        cmd = [self._ffmpeg_path, "-i", source, "-ss", start, "-y", output]

        if duration:
            cmd.insert(4, "-t")
            cmd.insert(5, str(duration))

        ret, stdout, stderr = await self._execute_ffmpeg(context, cmd, "Trimming")

        if ret == 0:
            return PluginResult(success=True, output_path=output)
        else:
            return PluginResult(success=False, error=stderr)

    async def _concat(self, context: PluginContext, config: dict) -> PluginResult:
        output = config.get("output", "concatenated.mp4")
        file_list = config.get("files", [])

        if not file_list:
            return PluginResult(
                success=False, error="No files provided for concatenation"
            )

        list_file = "concat_list.txt"
        with open(list_file, "w") as f:
            for fl in file_list:
                # Ensure paths are safe for ffmpeg concat
                safe_fl = fl.replace("'", "'\\''")
                f.write(f"file '{safe_fl}'\n")

        cmd = [
            self._ffmpeg_path,
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c",
            "copy",
            "-y",
            output,
        ]

        ret, stdout, stderr = await self._execute_ffmpeg(context, cmd, "Concatenating")

        try:
            os.remove(list_file)
        except:
            pass

        if ret == 0:
            return PluginResult(success=True, output_path=output)
        else:
            return PluginResult(success=False, error=stderr)

    async def _convert(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output = config.get("output")

        if not output:
            ext = config.get("format", "mp4")
            output = source.rsplit(".", 1)[0] + f".{ext}"

        cmd = [self._ffmpeg_path, "-i", source, "-y", output]

        ret, stdout, stderr = await self._execute_ffmpeg(context, cmd, "Converting")

        if ret == 0:
            return PluginResult(success=True, output_path=output)
        else:
            return PluginResult(success=False, error=stderr)
