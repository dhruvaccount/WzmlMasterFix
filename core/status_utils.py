import logging
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger("wzml.status")


class MirrorStatus(str, Enum):
    STATUS_UPLOAD = "Upload"
    STATUS_DOWNLOAD = "Download"
    STATUS_CLONE = "Clone"
    STATUS_QUEUEDL = "QueueDl"
    STATUS_QUEUEUP = "QueueUp"
    STATUS_PAUSED = "Pause"
    STATUS_ARCHIVE = "Archive"
    STATUS_EXTRACT = "Extract"
    STATUS_SPLIT = "Split"
    STATUS_CHECK = "CheckUp"
    STATUS_SEED = "Seed"
    STATUS_SAMVID = "SamVid"
    STATUS_CONVERT = "Convert"
    STATUS_FFMPEG = "FFmpeg"
    STATUS_YT = "YouTube"
    STATUS_METADATA = "Metadata"


class EngineStatus:
    STATUS_ARIA2 = "Aria2"
    STATUS_AIOHTTP = "AioHttp"
    STATUS_GDAPI = "Google-API"
    STATUS_QBIT = "qBit"
    STATUS_TGRAM = "Pyro"
    STATUS_MEGA = "MegaCMD"
    STATUS_YTDLP = "yt-dlp"
    STATUS_FFMPEG = "ffmpeg"
    STATUS_7Z = "7z"
    STATUS_RCLONE = "RClone"
    STATUS_SABNZBD = "SABnzbd+"
    STATUS_QUEUE = "QSystem"
    STATUS_JD = "JDownloader"
    STATUS_YT = "Youtube-Api"
    STATUS_METADATA = "Metadata"
    STATUS_UPHOSTER = "Uphoster"


SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def get_readable_file_size(size_in_bytes: int) -> str:
    if not size_in_bytes:
        return "0B"

    index = 0
    size = float(size_in_bytes)
    while size >= 1024 and index < len(SIZE_UNITS) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds: int) -> str:
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value = seconds // period_seconds
            seconds = seconds % period_seconds
            result += f"{period_value}{period_name}"
    return result or "0s"


def format_aria2_status(
    name: str,
    size: int,
    downloaded: int,
    speed: int,
    progress: float,
    eta: int,
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    readable_size = get_readable_file_size(size)
    readable_downloaded = get_readable_file_size(downloaded)
    readable_speed = get_readable_file_size(speed) + "/s"
    eta_str = get_readable_time(eta) if eta > 0 else "∞"

    return f"""╭───┬───╮
│ 📥 │ DOWNLOAD │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ ✦ <b>Name:</b> <code>{name}</code>
┨ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┠ 📥 {readable_downloaded}/{readable_size} ━━━━━━ @ {readable_speed}
┨ ⏱️ ETA: {eta_str}
┖ ⚡ {progress}% [{progress_bar}] {readable_downloaded} / {readable_size}"""


def format_queue_status(
    name: str,
    queue_type: str,
    size: int,
    position: int,
) -> str:
    readable_size = get_readable_file_size(size)
    status_type = "DOWNLOAD" if queue_type == "dl" else "UPLOAD"

    return f"""╭───┬───╮
│ ⚙️ │ QUEUE{status_type} │ [{position}]
╰──┴────━┴─────────────────────────────────╯
┠ 📄 <b>Name:</b> <code>{name}</code>
┨ 💾 <b>Size:</b> {readable_size}
┖ ⏳ <b>Position:</b> {position}"""


def format_torrent_status(
    name: str,
    size: int,
    downloaded: int,
    speed: int,
    progress: float,
    eta: int,
    seeders: int = 0,
    leechers: int = 0,
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    readable_size = get_readable_file_size(size)
    readable_downloaded = get_readable_file_size(downloaded)
    readable_speed = get_readable_file_size(speed) + "/s"
    eta_str = get_readable_time(eta) if eta > 0 else "∞"

    result = f"""╭───┬───╮
│ 📥 │ TORRENT │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ ✦ <b>Name:</b> <code>{name}</code>
┨ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┠ 📥 {readable_downloaded}/{readable_size} ━━━━━━ @ {readable_speed}
┨ ⚡ {progress}% [{progress_bar}] {readable_downloaded} / {readable_size}
┨ ⏱️ ETA: {eta_str}"""

    if seeders > 0 or leechers > 0:
        result += f"\n┨ 👤 S: {seeders} | L: {leechers}"

    result += "\n┖ 🔗"

    return result


def format_ytdlp_status(
    title: str,
    size: int,
    downloaded: int,
    speed: int,
    progress: float,
    eta: int,
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    readable_size = get_readable_file_size(size)
    readable_speed = get_readable_file_size(speed) + "/s"
    eta_str = get_readable_time(eta) if eta > 0 else "∞"

    return f"""╭───┬───╮
│ ▶️ │ YT-DLP │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ ✦ <b>Title:</b> <code>{title}</code>
┨ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┠ ▶️ {readable_size} ━━━━━━ @ {readable_speed}
┨ ⏱️ ETA: {eta_str}
┖ ⚡ {progress}% [{progress_bar}]"""


def format_gdrive_status(
    name: str,
    size: int,
    uploaded: int,
    speed: int,
    progress: float,
    url: str = "",
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    readable_size = get_readable_file_size(size)
    readable_uploaded = get_readable_file_size(uploaded)
    readable_speed = get_readable_file_size(speed) + "/s"

    result = f"""╭───┬───╮
│ 📤 │ UPLOAD │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ ✦ <b>Name:</b> <code>{name}</code>
┨ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┠ 📤 {readable_uploaded}/{readable_size} ━━━━━━ @ {readable_speed}
┨ ⚡ {progress}% [{progress_bar}] {readable_uploaded} / {readable_size}"""

    if url:
        result += f"\n┖ 🔗 {url}"

    return result


def format_rclone_status(
    name: str,
    size: int,
    transferred: int,
    speed: int,
    progress: float,
    eta: int,
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    readable_size = get_readable_file_size(size)
    readable_transferred = get_readable_file_size(transferred)
    readable_speed = get_readable_file_size(speed) + "/s"
    eta_str = get_readable_time(eta) if eta > 0 else "∞"

    return f"""╭───┬───╮
│ ☁️ │ RCLONE │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ ✦ <b>Name:</b> <code>{name}</code>
┨ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┠ ☁️ {readable_transferred}/{readable_size} ━━━━━━ @ {readable_speed}
┨ ⏱️ ETA: {eta_str}
┖ ⚡ {progress}% [{progress_bar}]"""


def format_mega_status(
    name: str,
    size: int,
    downloaded: int,
    speed: int,
    progress: float,
    eta: int,
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    readable_size = get_readable_file_size(size)
    readable_downloaded = get_readable_file_size(downloaded)
    readable_speed = get_readable_file_size(speed) + "/s"
    eta_str = get_readable_time(eta) if eta > 0 else "∞"

    return f"""╭───┬───╮
│ 💎 │ MEGA │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ ✦ <b>Name:</b> <code>{name}</code>
┨ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┠ 📥 {readable_downloaded}/{readable_size} ━━━━━━ @ {readable_speed}
┨ ⏱️ ETA: {eta_str}
┖ ⚡ {progress}% [{progress_bar}]"""


def format_extraction_status(
    name: str,
    progress: float,
    extracted_count: int,
    total_count: int,
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    return f"""╭───┬───╮
│ 📦 │ EXTRACT │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ 📦 <b>File:</b> <code>{name}</code>
┨ ⚡ {progress}% [{progress_bar}]
┖ 📋 {extracted_count}/{total_count} files"""


def format_compression_status(
    name: str,
    progress: float,
    current_file: str,
) -> str:
    progress_bar = ""
    for i in range(10):
        if i < int(progress / 10):
            progress_bar += "█"
        else:
            progress_bar += "░"

    return f"""╭───┬───╮
│ 📚 │ COMPRESS │ {progress}%
╰─┬─┴──────┴─────────────────────╯
┠ 📦 <b>File:</b> <code>{name}</code>
┨ ⚡ {progress}% [{progress_bar}]
┖ 📄 {current_file}"""


def format_task_cancelled(task_name: str, task_id: str) -> str:
    return f"""╭──┬───╮
│ ❌ │ CANCELLED │
╰──┴────━┴─────────────────────────────────╯
┠ <b>Task:</b> <code>{task_name}</code>
┖ ID: <code>{task_id}</code>"""


def format_task_completed(
    name: str,
    size: int,
    destination: str,
    url: str = "",
) -> str:
    readable_size = get_readable_file_size(size)

    result = f"""╭──┬───╮
│ ✅ │ COMPLETED │
╰──┴────━┴─────────────────────────────────╯
┠ <b>Name:</b> <code>{name}</code>
┨ 💾 <b>Size:</b> {readable_size}
┨ 📂 <b>To:</b> {destination}"""

    if url:
        result += f"\n┖ 🔗 {url}"
    else:
        result += "\n┖ ✅ Task Completed Successfully!"

    return result


def format_task_failed(task_name: str, error: str) -> str:
    return f"""╭──┬───╮
│ ❌ │ FAILED │
╰──┴────━┴─────────────────────────────────╯
┠ <b>Task:</b> <code>{task_name}</code>
┖ ⚠️ <b>Error:</b> {error}"""


def format_queue_stats(
    download_pending: int,
    upload_pending: int,
    download_running: int,
    upload_running: int,
    total: int,
) -> str:
    return f"""╭──┬───╮
│ ⚙️ │ QUEUE │ [{total}]
╰──┴────━┴─────────────────────────────────╯
┠ <b>Download:</b> {download_running} | <b>Upload:</b> {upload_running}
┨ <b>Pending:</b> {download_pending + upload_pending}
┖ <i>Workers: {download_running + upload_running} active / {total}</i>"""


__all__ = [
    "MirrorStatus",
    "EngineStatus",
    "get_readable_file_size",
    "get_readable_time",
    "format_aria2_status",
    "format_queue_status",
    "format_torrent_status",
    "format_ytdlp_status",
    "format_gdrive_status",
    "format_rclone_status",
    "format_mega_status",
    "format_extraction_status",
    "format_compression_status",
    "format_task_cancelled",
    "format_task_completed",
    "format_task_failed",
    "format_queue_stats",
]
