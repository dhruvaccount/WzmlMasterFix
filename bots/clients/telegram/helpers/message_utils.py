"""
Telegram-specific message utilities

Requires pyrogram (pyrotgfork)
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("wzml.telegram.helpers")

_telegram_client = None


def set_telegram_client(client) -> None:
    global _telegram_client
    _telegram_client = client


def get_telegram_client():
    return _telegram_client


async def send_message(chat_id: int, text: str, reply_markup: Any = None) -> Any:
    if _telegram_client:
        return await _telegram_client.send_message(chat_id, text, reply_markup)
    logger.warning("Telegram client not configured")
    return None


async def edit_message(
    chat_id: int, message_id: int, text: str, reply_markup: Any = None
) -> Any:
    if _telegram_client:
        return await _telegram_client.edit_message(
            chat_id, message_id, text, reply_markup
        )
    logger.warning("Telegram client not configured")
    return None


async def delete_message(chat_id: int, message_id: int) -> bool:
    if _telegram_client:
        return await _telegram_client.delete_message(chat_id, message_id)
    logger.warning("Telegram client not configured")
    return False


async def auto_delete_message(
    chat_id: int, message_id: int, delay: int = 300
) -> asyncio.Task:
    async def _delete():
        await asyncio.sleep(delay)
        try:
            await delete_message(chat_id, message_id)
        except Exception as e:
            logger.error(f"Auto delete failed: {e}")

    return asyncio.create_task(_delete())


async def send_media(
    chat_id: int,
    media_type: str,
    file_path: str,
    caption: str = "",
    reply_markup: Any = None,
) -> Any:
    if not _telegram_client:
        logger.warning("Telegram client not configured")
        return None

    try:
        if media_type == "photo":
            return await _telegram_client.send_photo(
                chat_id, file_path, caption, reply_markup
            )
        elif media_type == "video":
            return await _telegram_client.send_video(
                chat_id, file_path, caption, reply_markup
            )
        elif media_type == "document":
            return await _telegram_client.send_document(
                chat_id, file_path, caption, reply_markup
            )
        elif media_type == "audio":
            return await _telegram_client.send_audio(
                chat_id, file_path, caption, reply_markup
            )
    except Exception as e:
        logger.error(f"Send media error: {e}")
    return None


async def send_photo(
    chat_id: int, photo: str, caption: str = "", reply_markup: Any = None
) -> Any:
    return await send_media(chat_id, "photo", photo, caption, reply_markup)


async def send_video(
    chat_id: int, video: str, caption: str = "", reply_markup: Any = None
) -> Any:
    return await send_media(chat_id, "video", video, caption, reply_markup)


async def send_document(
    chat_id: int, document: str, caption: str = "", reply_markup: Any = None
) -> Any:
    return await send_media(chat_id, "document", document, caption, reply_markup)


async def send_audio(
    chat_id: int, audio: str, caption: str = "", reply_markup: Any = None
) -> Any:
    return await send_media(chat_id, "audio", audio, caption, reply_markup)


def get_readable_time(seconds: int) -> str:
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value = seconds // period_seconds
            seconds = seconds % period_seconds
            result += f"{period_value}{period_name}"
    return result or "0s"


def get_readable_bytes(size: int) -> str:
    if not size:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    size = float(size)
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f}{units[index]}"


def get_extension(url: str) -> str:
    return os.path.splitext(url)[1].lower().lstrip(".")


def get_filename(url: str) -> str:
    return url.split("/")[-1].split("?")[0]


def get_mime_type(url: str) -> str:
    import mimetypes

    mimetypes.init()
    return mimetypes.guess_type(url)[0] or "application/octet-stream"


def arg_parser(text: str) -> dict:
    args = text.split()
    result = {
        "link": "",
        "-d": "",  # destination
        "-i": 0,  # bulk links
        "-s": False,  # select
        "-b": False,  # batch
        "-doc": False,  # document
        "-med": False,  # media
        "-z": False,  # zip
        "-e": False,  # extract
        "-f": False,  # force
        "-ss": False,  # stop seeding
        "-m": "",  # multi name
        "-n": "",  # subfolder name
        "-up": "",  # upload destination
        "list": [],
    }

    if not args:
        return result

    # Skip the command itself (e.g. /leech)
    i = 1 if args[0].startswith("/") else 0

    while i < len(args):
        arg = args[i]
        if arg in result:
            if isinstance(result[arg], bool):
                result[arg] = True
            else:
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    result[arg] = (
                        int(args[i + 1])
                        if isinstance(result[arg], int)
                        else args[i + 1]
                    )
                    i += 1
        elif arg.startswith("-") and arg not in result:
            # Handle unknown flags generically if needed, or ignore
            pass
        else:
            if not result["link"]:
                result["link"] = arg
            else:
                result["list"].append(arg)
        i += 1

    return result


def is_gdrive_id(text: str) -> bool:
    if len(text) < 30:
        return False
    return any(c.isdigit() for c in text)


def pre_task_check(text: str) -> tuple:
    return None, None


async def get_content_type(url: str) -> str:
    return get_mime_type(url)


def is_url(url: str) -> bool:
    return url.startswith(("http://", "https://", "ftp://", "ftps://"))


def is_magnet(url: str) -> bool:
    return url.startswith("magnet:")


def is_torrent(url: str) -> bool:
    return url.endswith(".torrent") or url.startswith("magnet:")


def is_gdrive_link(url: str) -> bool:
    return "drive.google.com" in url


def is_mega_link(url: str) -> bool:
    return "mega.nz" in url or "mega.co.nz" in url


def is_nzb_link(url: str) -> bool:
    return url.endswith(".nzb")


def is_youtube_link(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_telegram_link(url: str) -> bool:
    return url.startswith(("https://t.me/", "tg://"))


def is_rclone_path(path: str) -> bool:
    return bool(path and (path.startswith("rclone:") or ":" in path))


__all__ = [
    "set_telegram_client",
    "get_telegram_client",
    "send_message",
    "edit_message",
    "delete_message",
    "auto_delete_message",
    "send_photo",
    "send_video",
    "send_document",
    "send_audio",
    "get_readable_time",
    "get_readable_bytes",
    "get_extension",
    "get_filename",
    "get_mime_type",
    "arg_parser",
    "is_gdrive_id",
    "pre_task_check",
    "get_content_type",
    "is_url",
    "is_magnet",
    "is_torrent",
    "is_gdrive_link",
    "is_mega_link",
    "is_nzb_link",
    "is_youtube_link",
    "is_telegram_link",
    "is_rclone_path",
]
