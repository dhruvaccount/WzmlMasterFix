import asyncio
import logging
import os
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
        self._ydl = None

    async def initialize(self) -> bool:
        try:
            import yt_dlp

            self._ydl = yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": False,
                }
            )

            logger.info("yt-dlp initialized")
            return True
        except Exception as e:
            logger.error(f"yt-dlp init error: {e}")
            return False

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
            import yt_dlp
            from core.task import update_task_progress

            loop = asyncio.get_running_loop()
            last_update = 0

            def progress_hook(d):
                nonlocal last_update
                now = time.time()

                try:
                    from core.task import get_tasks

                    # Check task status synchronously by directly accessing the store since we're in a thread
                    from core.task import _task_store

                    t = _task_store.get(context.task_id)
                    if t and t.status.value == "cancelled":
                        raise Exception("Task cancelled by user")
                except Exception as e:
                    if str(e) == "Task cancelled by user":
                        raise

                if d["status"] == "downloading":
                    if now - last_update < 1.0:
                        return
                    last_update = now

                    downloaded = d.get("downloaded_bytes", 0)
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    speed = d.get("speed", 0)
                    eta = d.get("eta", 0)

                    pct = (downloaded / total) * 100 if total else 0.0

                    asyncio.run_coroutine_threadsafe(
                        update_task_progress(
                            task_id=context.task_id,
                            stage="Downloading",
                            plugin=self.name,
                            progress=pct,
                            speed=speed or 0.0,
                            eta=eta or 0,
                            downloaded=downloaded,
                            total=total,
                        ),
                        loop,
                    )

            ydl_opts = {
                "format": format_opt
                if format_opt != "best"
                else "bestvideo+bestaudio/best",
                "outtmpl": os.path.join(output_path, filename_template),
                "thumbnail": thumbnail,
                "writesubtitles": subtitles,
                "ignoreerrors": False,
                "no_warnings": True,
                "quiet": False,
                "progress_hooks": [progress_hook],
            }

            if not playlist:
                ydl_opts["noplaylist"] = True
            if playlist_items:
                ydl_opts["playlist_items"] = playlist_items
            if age_limit:
                ydl_opts["age_limit"] = age_limit
            if username and password:
                ydl_opts["username"] = username
                ydl_opts["password"] = password
            if config.get("retries"):
                ydl_opts["retries"] = config["retries"]
            if config.get("fragment_retries"):
                ydl_opts["fragment_retries"] = config["fragment_retries"]

            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        raise Exception("Failed to extract info")
                    return info, ydl.prepare_filename(info)

            info, output_file = await asyncio.to_thread(_download)

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
            logger.error(f"yt-dlp download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_info(self, url: str) -> dict:
        try:
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            logger.error(f"yt-dlp info error: {e}")
            return {}

    async def get_status(self, url: str = None) -> dict:
        return await self.get_info(url)

    async def list_playlists(self, channel_id: str = None) -> list:
        try:
            import yt_dlp

            ydl_opts = {"ignoreerrors": True, "extract_flat": True}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if channel_id:
                    url = f"https://www.youtube.com/channel/{channel_id}/playlists"
                else:
                    return []

                info = ydl.extract_info(url, download=False)
                return info.get("entries", [])
        except Exception as e:
            logger.error(f"yt-dlp playlists error: {e}")
            return []

    async def search(self, query: str, limit: int = 10) -> list:
        try:
            import yt_dlp

            ydl_opts = {"ignoreerrors": True, "extract_flat": True}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                return info.get("entries", []) if info else []
        except Exception as e:
            logger.error(f"yt-dlp search error: {e}")
            return []

    async def get_subs(self, url: str, languages: list = None) -> dict:
        try:
            import yt_dlp

            if not languages:
                languages = ["en"]

            ydl_opts = {
                "writesubtitles": True,
                "subtitleslangs": languages,
                "skip_download": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    "subtitles": info.get("subtitles", {}),
                    "automatic_captions": info.get("automatic_captions", {}),
                }
        except Exception as e:
            logger.error(f"yt-dlp subs error: {e}")
            return {}

    async def extract_audio(
        self, url: str, output_path: str, format: str = "mp3"
    ) -> PluginResult:
        try:
            import yt_dlp

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(output_path, f"%(title)s.%(ext)s"),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": format,
                    }
                ],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                output_file = ydl.prepare_filename(info)

                return PluginResult(
                    success=True,
                    output_path=output_file,
                    metadata={"title": info.get("title")},
                )
        except Exception as e:
            logger.error(f"yt-dlp audio error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_playlist_info(self, url: str) -> dict:
        try:
            import yt_dlp

            ydl_opts = {"ignoreerrors": True, "extract_flat": False}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    "title": info.get("title"),
                    "description": info.get("description"),
                    "entry_count": len(info.get("entries", [])),
                    "entries": info.get("entries", []),
                }
        except Exception as e:
            logger.error(f"yt-dlp playlist info error: {e}")
            return {}
