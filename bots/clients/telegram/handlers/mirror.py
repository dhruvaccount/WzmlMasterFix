"""Mirror, Leech, Ytdlp, Clone handlers - API first approach"""

import logging
from typing import Optional, Any
from dataclasses import dataclass
from pyrogram import enums

from pyrogram import Client, types
from bots.clients.telegram.helpers.message_utils import arg_parser, send_message
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.clients.telegram.handlers import BotHandler
from bots.api import api_client

logger = logging.getLogger("wzml.bot.handlers.mirror")

MIRROR_USAGE = """<b>Mirror/Leech Usage</b>

<i>Direct Links:</i>
/mirror <link> - Mirror to cloud
/leech <link> - Leech to telegram

<i>Torrents:</i>
/qb_mirror <link> - QBitTorrent mirror
/qb_leech <link> - QBitTorrent leech
/jd_mirror <link> - JDownloader mirror
/jd_leech <link> - JDownloader leech
/nzb_mirror <link> - NZB mirror
/nzb_leech <link> - NZB leech

<i>Options:</i>
-d <dir> - Destination folder
-i <num> - Number of links (bulk)
-s - Skip file selection
-b - Batch mode
-doc - Upload as document
-med - Upload as media
-z - Extract archive
-f - Force upload
-ss - Stop seeding after upload
-m <name> - Multi tag name
-n <name> - Subfolder name
"""

YTDLP_USAGE = """<b>YT-DLP Usage</b>

/ytdl <url> - Download video to cloud
/ytdl_leech <url> - Download video to telegram

<b>Options:</b>
-q <quality> - Video quality (default: best)
"""

CLONE_USAGE = """<b>Clone Usage</b>

/clone <gdrive_link> - Clone Google Drive folder
"""

@dataclass
class MirrorResult:
    task: Optional[Any] = None
    message: str = ""

class MirrorHandler(BotHandler):
    """Handler for mirror, leech, qb, jd, nzb commands"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
        is_leech: bool = False,
        is_qbit: bool = False,
        is_jd: bool = False,
        is_nzb: bool = False,
    ) -> MirrorResult:
        args = arg_parser(message.text)
        link = args.get("link", "").strip()

        if not link:
            await send_message(message, MIRROR_USAGE, parse_mode=enums.ParseMode.HTML)
            return MirrorResult()

        metadata = {
            "is_jd": is_jd,
            "is_nzb": is_nzb,
            "flags": args,
            "chat_id": message.chat.id,
            "user_id": message.from_user.id,
            "ui_data": {
                "mention": message.from_user.mention(style='html'),
                "user_id": message.from_user.id,
                "message_link": message.link,
                "out_mode": "document" if args.get("-doc") else "media"
            }
        }

        result = await api_client.create_mirror(
            source=link,
            user_id=message.from_user.id,
            destination=args.get("d", ""),
            is_leech=is_leech,
            is_qbit=is_qbit,
            metadata=metadata
        )

        if "error" in result:
            await send_message(message, f"<b>Error:</b> {result['error']}", parse_mode=enums.ParseMode.HTML)
            return MirrorResult()

        task_data = result.get("data", {})
        task_id = task_data.get("id", "Unknown")

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task_id[:20]}")
        reply_markup = buttons.build_menu(1)

        msg = f"<b>Task Queued</b>\n\n"
        msg += f"ID: <code>{task_id[:20]}</code>\n"
        msg += f"Mode: {'Leech' if is_leech else 'Mirror'}\n"
        msg += f"Source: {link[:100]}"

        await send_message(message, msg, reply_markup, parse_mode=enums.ParseMode.HTML)
        return MirrorResult(task=task_data, message=msg)


class YtdlpHandler(BotHandler):
    """Handler for ytdl commands"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
        is_leech: bool = False,
    ) -> MirrorResult:
        args = arg_parser(message.text)
        link = args.get("link", "").strip()

        if not link:
            await send_message(message, YTDLP_USAGE, parse_mode=enums.ParseMode.HTML)
            return MirrorResult()

        quality = args.get("q", "bestvideo+bestaudio/best")

        result = await api_client.create_ytdlp(
            url=link,
            user_id=message.from_user.id,
            quality=quality
        )

        if "error" in result:
            await send_message(message, f"<b>Error:</b> {result['error']}", parse_mode=enums.ParseMode.HTML)
            return MirrorResult()

        task_data = result.get("data", {})
        task_id = task_data.get("id", "Unknown")

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task_id[:20]}")
        reply_markup = buttons.build_menu(1)

        msg = f"<b>YouTube Download Started</b>\n\n"
        msg += f"ID: <code>{task_id[:20]}</code>\n"
        msg += f"Quality: {quality}"

        await send_message(message, msg, reply_markup, parse_mode=enums.ParseMode.HTML)
        return MirrorResult(task=task_data, message=msg)


class CloneHandler(BotHandler):
    """Handler for clone command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> MirrorResult:
        args = arg_parser(message.text)
        link = args.get("link", "").strip()

        if not link:
            await send_message(message, CLONE_USAGE, parse_mode=enums.ParseMode.HTML)
            return MirrorResult()

        if "drive.google.com" not in link and "docs.google.com" not in link:
            await send_message(
                message,
                "<b>Invalid GDrive Link!</b>\n\nSend a valid Google Drive link.",
                parse_mode=enums.ParseMode.HTML,
            )
            return MirrorResult()

        result = await api_client.create_clone(
            source_id=link,
            user_id=message.from_user.id,
        )

        if "error" in result:
            await send_message(message, f"<b>Error:</b> {result['error']}", parse_mode=enums.ParseMode.HTML)
            return MirrorResult()

        task_data = result.get("data", {})
        task_id = task_data.get("id", "Unknown")

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task_id[:20]}")
        reply_markup = buttons.build_menu(1)

        msg = f"<b>Clone Started</b>\n\n"
        msg += f"ID: <code>{task_id[:20]}</code>\n"
        msg += f"Source: {link[:100]}"

        await send_message(message, msg, reply_markup, parse_mode=enums.ParseMode.HTML)
        return MirrorResult(task=task_data, message=msg)


class CancelHandler(BotHandler):
    """Handler for cancel command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> Optional[dict]:
        args = arg_parser(message.text)
        task_id = args.get("link", "").strip()
        user_id = message.from_user.id

        if task_id:
            if task_id.isdigit():
                # user requested cancel for another user id's tasks
                result = await api_client.get_user_tasks(int(task_id), limit=1)
                tasks = result.get("data", [])
            else:
                res = await api_client.cancel_task_v2(task_id)
                if "error" not in res:
                    task = res.get("data", {})
                    await send_message(
                        message,
                        f"<b>Task Cancelled</b>\n\nID: <code>{task.get('id', '')[:20]}</code>",
                        parse_mode=enums.ParseMode.HTML,
                    )
                    return task
                
                # fallback: get user tasks
                result = await api_client.get_user_tasks(user_id, limit=1)
                tasks = result.get("data", [])
        else:
            result = await api_client.get_user_tasks(user_id, limit=1)
            tasks = result.get("data", [])

        if tasks:
            task = tasks[0]
            await api_client.cancel_task_v2(task["id"])
            await send_message(
                message,
                f"<b>Task Cancelled</b>\n\nID: <code>{task.get('id', '')[:20]}</code>",
                parse_mode=enums.ParseMode.HTML,
            )
            return task

        await send_message(
            message,
            "<b>No Running Task Found!</b>",
            parse_mode=enums.ParseMode.HTML,
        )
        return None


class CancelAllHandler(BotHandler):
    """Handler for cancelall command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> int:
        result = await api_client.get_user_tasks(message.from_user.id, limit=50)
        tasks = result.get("data", [])

        count = 0
        for task in tasks:
            if task.get("status") in ["queued", "running", "paused"]:
                await api_client.cancel_task_v2(task["id"])
                count += 1

        await send_message(
            message,
            f"<b>{count} Tasks Cancelled!</b>",
            parse_mode=enums.ParseMode.HTML,
        )
        return count


__all__ = [
    "MirrorHandler",
    "YtdlpHandler",
    "CloneHandler",
    "CancelHandler",
    "CancelAllHandler",
]
