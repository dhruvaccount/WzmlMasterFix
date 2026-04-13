import asyncio
import logging
import os
import subprocess
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.ffmpeg_processor")


class FFmpegProcessor(ProcessorPlugin):
    name = "ffmpeg"
    plugin_type = "processor"

    def __init__(self):
        self._ffmpeg_path = "ffmpeg"
        self._ffprobe_path = "ffprobe"

    async def initialize(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> bool:
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        logger.info("FFmpeg processor initialized")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        action = config.get("action", "transcode")
        
        try:
            if action == "transcode":
                return await self._transcode(source, config)
            elif action == "extract_audio":
                return await self._extract_audio(source, config)
            elif action == "generate_thumb":
                return await self._generate_thumb(source, config)
            elif action == "trim":
                return await self._trim(source, config)
            elif action == "concat":
                return await self._concat(source, config)
            elif action == "convert":
                return await self._convert(source, config)
            else:
                return PluginResult(success=False, error=f"Unknown action: {action}")
                
        except Exception as e:
            logger.error(f"FFmpeg error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _transcode(self, source: str, config: dict) -> PluginResult:
        output = config.get("output", source.rsplit(".", 1)[0] + "_transcoded.mp4")
        vcodec = config.get("vcodec", "libx264")
        acodec = config.get("acodec", "aac")
        crf = config.get("crf", 23)
        preset = config.get("preset", "medium")
        
        cmd = [
            self._ffmpeg_path, "-i", source,
            "-c:v", vcodec, "-c:a", acodec,
            "-crf", str(crf), "-preset", preset,
            "-y", output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return PluginResult(
                success=True,
                output_path=output,
                metadata={"original": source, "output": output},
            )
        else:
            return PluginResult(success=False, error=result.stderr)

    async def _extract_audio(self, source: str, config: dict) -> PluginResult:
        output = config.get("output", source.rsplit(".", 1)[0] + ".mp3")
        format = config.get("format", "mp3")
        bitrate = config.get("bitrate", "192k")
        
        cmd = [
            self._ffmpeg_path, "-i", source,
            "-vn", "-ab", bitrate,
            "-ar", "44100", "-ac", "2",
            "-y", output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return PluginResult(
                success=True,
                output_path=output,
                metadata={"format": format},
            )
        else:
            return PluginResult(success=False, error=result.stderr)

    async def _generate_thumb(self, source: str, config: dict) -> PluginResult:
        output = config.get("output", "thumb.jpg")
        time = config.get("time", "00:00:01")
        
        cmd = [
            self._ffmpeg_path, "-i", source,
            "-ss", time, "-vframes", "1",
            "-y", output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return PluginResult(
                success=True,
                output_path=output,
                metadata={"thumbnail": output},
            )
        else:
            return PluginResult(success=False, error=result.stderr)

    async def _trim(self, source: str, config: dict) -> PluginResult:
        output = config.get("output", source.rsplit(".", 1)[0] + "_trim.mp4")
        start = config.get("start", "00:00:00")
        duration = config.get("duration", None)
        
        cmd = [self._ffmpeg_path, "-i", source, "-ss", start, "-y", output]
        
        if duration:
            cmd.insert(4, "-t")
            cmd.insert(5, duration)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return PluginResult(success=True, output_path=output)
        else:
            return PluginResult(success=False, error=result.stderr)

    async def _concat(self, source: str, config: dict) -> PluginResult:
        output = config.get("output", "concatenated.mp4")
        file_list = config.get("files", [])
        
        list_file = "concat_list.txt"
        with open(list_file, "w") as f:
            for fl in file_list:
                f.write(f"file '{fl}'\n")
        
        cmd = [
            self._ffmpeg_path, "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", "-y", output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        os.remove(list_file)
        
        if result.returncode == 0:
            return PluginResult(success=True, output_path=output)
        else:
            return PluginResult(success=False, error=result.stderr)

    async def _convert(self, source: str, config: dict) -> PluginResult:
        output = config.get("output")
        
        if not output:
            ext = config.get("format", "mp4")
            output = source.rsplit(".", 1)[0] + f".{ext}"
        
        cmd = [self._ffmpeg_path, "-i", source, "-y", output]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return PluginResult(success=True, output_path=output)
        else:
            return PluginResult(success=False, error=result.stderr)

    async def get_media_info(self, file_path: str) -> dict:
        try:
            cmd = [self._ffprobe_path, "-v", "quiet", "-print_format", "json",
                   "-show_format", "-show_streams", file_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            return {}
        except Exception as e:
            logger.error(f"FFprobe error: {e}")
            return {}