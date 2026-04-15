import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Optional

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.yt_dlp_downloader")


class YTDLPDownloader(DownloaderPlugin):
    name = "yt_dlp"
    plugin_type = "downloader"
    supports_youtube = True

    def __init__(self):
        self._format = "best"
        self._quality = "best"
        self._progress_regex = re.compile(
            r"\[download\]\s+(?P<percent>[\d\.]+)%\s+of\s+[~]?(?P<size>[\d\.]+)(?P<size_unit>[a-zA-Z]+)\s+at\s+(?P<speed>[\d\.]+)(?P<speed_unit>[a-zA-Z]+/s)\s+ETA\s+(?P<eta>[\d:]+)"
        )
        self._active_processes = {}

    async def initialize(self) -> bool:
        try:
            # Check if yt-dlp is available in PATH
            process = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                logger.info(f"yt-dlp initialized (version {stdout.decode().strip()})")
                return True
            else:
                logger.error("yt-dlp not found in PATH or failed to execute")
                return False
        except Exception as e:
            logger.error(f"yt-dlp init error: {e}")
            return False

    def _parse_size_to_bytes(self, size_str: str, unit: str) -> int:
        multiplier = 1
        unit = unit.lower()
        if unit.startswith("k"):
            multiplier = 1024
        elif unit.startswith("m"):
            multiplier = 1024**2
        elif unit.startswith("g"):
            multiplier = 1024**3
        elif unit.startswith("t"):
            multiplier = 1024**4
        return int(float(size_str) * multiplier)

    def _parse_eta_to_seconds(self, eta_str: str) -> int:
        parts = eta_str.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return 0

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")
        format_opt = config.get("format", "best")
        quality = config.get("quality", "best")
        thumbnail = config.get("thumbnail", True)
        subtitles = config.get("subtitles", True)
        playlist = config.get("playlist", True)
        playlist_items = config.get("playlist_items")
        age_limit = config.get("age_limit")
        username = config.get("username")
        password = config.get("password")
        filename_template = config.get("filename_template", "%(title)s-%(id)s.%(ext)s")

        try:
            from core.task import update_task_progress, get_tasks

            # First, dump json to get info
            info_cmd = ["yt-dlp", "--dump-json", "--no-warnings", "--ignore-errors"]
            if username and password:
                info_cmd.extend(["-u", username, "-p", password])
            info_cmd.append(url)

            info_proc = await asyncio.create_subprocess_exec(
                *info_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await info_proc.communicate()

            info = {}
            if stdout:
                for line in stdout.decode().strip().split("\n"):
                    try:
                        parsed = json.loads(line)
                        if parsed:
                            info = parsed
                            break
                    except:
                        pass

            if not info:
                raise Exception("Failed to extract video info")

            # Execute download
            cmd = [
                "yt-dlp",
                "--newline",
                "--no-warnings",
                "--ignore-errors",
                "-o",
                os.path.join(output_path, filename_template),
            ]

            if format_opt != "best":
                cmd.extend(["-f", format_opt])
            else:
                cmd.extend(["-f", "bestvideo+bestaudio/best"])

            if thumbnail:
                cmd.append("--write-thumbnail")
            if subtitles:
                cmd.append("--write-subs")
            if not playlist:
                cmd.append("--no-playlist")
            elif playlist_items:
                cmd.extend(["--playlist-items", str(playlist_items)])

            if age_limit:
                cmd.extend(["--age-limit", str(age_limit)])
            if username and password:
                cmd.extend(["-u", username, "-p", password])

            if config.get("retries"):
                cmd.extend(["--retries", str(config["retries"])])
            if config.get("fragment_retries"):
                cmd.extend(["--fragment-retries", str(config["fragment_retries"])])

            cmd.append(url)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._active_processes[context.task_id] = process

            last_update = 0

            while True:
                # Check for cancellation
                from core.task import _task_store

                t = _task_store.get(context.task_id)
                if t and t.status.value == "cancelled":
                    process.terminate()
                    raise Exception("Task cancelled by user")

                line = await process.stdout.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                match = self._progress_regex.search(line_str)

                if match:
                    now = time.time()
                    if now - last_update >= 1.0:
                        data = match.groupdict()
                        pct = float(data["percent"])
                        total = self._parse_size_to_bytes(
                            data["size"], data["size_unit"]
                        )
                        downloaded = int((pct / 100) * total)
                        speed = self._parse_size_to_bytes(
                            data["speed"], data["speed_unit"]
                        )
                        eta = self._parse_eta_to_seconds(data["eta"])

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
                raise Exception(f"yt-dlp exited with code {process.returncode}")

            # Predict final output file name
            # By default yt-dlp might use a specific template. Since we know the template, we can construct it if info is available.
            output_file = os.path.join(
                output_path, f"{info.get('title')}-{info.get('id')}.{info.get('ext')}"
            )
            # Ensure it exists, else we might just return the dir if we can't reliably guess the extension after merging
            if not os.path.exists(output_file):
                # Best effort to find the file
                base_name = f"{info.get('title')}-{info.get('id')}"
                for file in os.listdir(output_path):
                    if (
                        file.startswith(base_name)
                        and not file.endswith(".part")
                        and not file.endswith(".ytdl")
                    ):
                        output_file = os.path.join(output_path, file)
                        break

            result = {
                "url": url,
                "title": info.get("title"),
                "id": info.get("id"),
                "thumbnail": info.get("thumbnail"),
                "description": info.get("description"),
                "duration": info.get("duration"),
                "upload_date": info.get("upload_date"),
                "uploader": info.get("uploader"),
                "view_count": info.get("view_count"),
                "like_count": info.get("like_count"),
                "channel": info.get("channel"),
                "channel_id": info.get("channel_id"),
                "format": info.get("format"),
                "resolution": info.get("resolution"),
                "filesize": info.get("filesize") or info.get("filesize_approx"),
            }

            if info.get("_type") == "playlist":
                result["entries"] = [
                    {
                        "title": e.get("title"),
                        "id": e.get("id"),
                        "duration": e.get("duration"),
                    }
                    for e in info.get("entries", [])
                ]
                result["playlist_count"] = len(info.get("entries", []))

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

            logger.error(f"yt-dlp download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_info(self, url: str) -> dict:
        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--ignore-errors",
                "--flat-playlist",
                url,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if stdout:
                for line in stdout.decode().strip().split("\n"):
                    try:
                        return json.loads(line)
                    except:
                        pass
            return {}
        except Exception as e:
            logger.error(f"yt-dlp info error: {e}")
            return {}

    async def get_status(self, url: str = None) -> dict:
        return await self.get_info(url)

    async def list_playlists(self, channel_id: str = None) -> list:
        try:
            if not channel_id:
                return []

            url = f"https://www.youtube.com/channel/{channel_id}/playlists"
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--ignore-errors",
                "--flat-playlist",
                url,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            entries = []
            if stdout:
                for line in stdout.decode().strip().split("\n"):
                    try:
                        parsed = json.loads(line)
                        if (
                            parsed
                            and "_type" in parsed
                            and parsed["_type"] != "playlist"
                        ):
                            entries.append(parsed)
                    except:
                        pass
            return entries
        except Exception as e:
            logger.error(f"yt-dlp playlists error: {e}")
            return []

    async def search(self, query: str, limit: int = 10) -> list:
        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--ignore-errors",
                "--flat-playlist",
                f"ytsearch{limit}:{query}",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            entries = []
            if stdout:
                for line in stdout.decode().strip().split("\n"):
                    try:
                        parsed = json.loads(line)
                        # ytsearch returns a playlist object if not flat, but with flat-playlist it usually returns the entries one by one or a flat playlist.
                        if parsed:
                            if parsed.get("_type") == "playlist":
                                entries.extend(parsed.get("entries", []))
                            else:
                                entries.append(parsed)
                    except:
                        pass
            return entries
        except Exception as e:
            logger.error(f"yt-dlp search error: {e}")
            return []

    async def get_subs(self, url: str, languages: list = None) -> dict:
        try:
            if not languages:
                languages = ["en"]

            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--ignore-errors",
                "--skip-download",
            ]
            cmd.append("--write-subs")
            cmd.append("--sub-langs")
            cmd.append(",".join(languages))
            cmd.append(url)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if stdout:
                for line in stdout.decode().strip().split("\n"):
                    try:
                        info = json.loads(line)
                        if info:
                            return {
                                "subtitles": info.get("subtitles", {}),
                                "automatic_captions": info.get(
                                    "automatic_captions", {}
                                ),
                            }
                    except:
                        pass
            return {}
        except Exception as e:
            logger.error(f"yt-dlp subs error: {e}")
            return {}

    async def extract_audio(
        self, url: str, output_path: str, format: str = "mp3"
    ) -> PluginResult:
        try:
            cmd = [
                "yt-dlp",
                "--no-warnings",
                "--ignore-errors",
                "-f",
                "bestaudio/best",
                "-o",
                os.path.join(output_path, "%(title)s.%(ext)s"),
                "--extract-audio",
                "--audio-format",
                format,
                "--print",
                "after_move:filepath",
                url,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0:
                raise Exception("Failed to extract audio")

            output_file = stdout.decode().strip().split("\n")[-1]

            return PluginResult(
                success=True,
                output_path=output_file,
                metadata={"title": os.path.basename(output_file)},
            )
        except Exception as e:
            logger.error(f"yt-dlp audio error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_playlist_info(self, url: str) -> dict:
        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--ignore-errors",
                "--flat-playlist",
                url,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            entries = []
            title = "Playlist"
            description = ""

            if stdout:
                for line in stdout.decode().strip().split("\n"):
                    try:
                        parsed = json.loads(line)
                        if parsed:
                            if parsed.get("_type") == "playlist":
                                title = parsed.get("title", title)
                                description = parsed.get("description", description)
                                if "entries" in parsed:
                                    entries.extend(parsed["entries"])
                            else:
                                entries.append(parsed)
                    except:
                        pass

            return {
                "title": title,
                "description": description,
                "entry_count": len(entries),
                "entries": entries,
            }
        except Exception as e:
            logger.error(f"yt-dlp playlist info error: {e}")
            return {}
