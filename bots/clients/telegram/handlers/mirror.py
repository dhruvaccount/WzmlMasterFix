"""Mirror, Leech, Ytdlp, Clone handlers - API first approach"""

import logging
from typing import Optional, Any
from dataclasses import dataclass
from pyrogram import enums

from core.task import Task, TaskStatus, create_task, get_tasks, cancel_task
from core.queue import enqueue_task, get_queue_manager
from bots.clients.telegram.helpers.message_utils import arg_parser
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.clients.telegram.handlers import BotHandler, CommandContext

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

STATUS_USAGE = """<b>Status Usage</b>

/status - Show all active tasks
/status me - Show your tasks
/status <user_id> - Show specific user's tasks
"""


@dataclass
class MirrorResult:
    task: Optional[Task] = None
    message: str = ""


class MirrorHandler(BotHandler):
    """Handler for mirror, leech, qb, jd, nzb commands"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        is_leech: bool = False,
        is_qbit: bool = False,
        is_jd: bool = False,
        is_nzb: bool = False,
    ) -> MirrorResult:
        args = arg_parser(context.text)
        link = args.get("link", "").strip()

        if not link:
            await client.send_message(
                context.chat_id, MIRROR_USAGE, parse_mode=enums.ParseMode.HTML
            )
            return MirrorResult()

        if is_qbit:
            pipeline_id = "qb_leech" if is_leech else "qb_mirror"
        elif is_jd:
            pipeline_id = "jd_leech" if is_leech else "jd_mirror"
        elif is_nzb:
            pipeline_id = "nzb_leech" if is_leech else "nzb_mirror"
        elif is_leech:
            pipeline_id = "telegram"
        else:
            pipeline_id = "gdrive"

        metadata = {
            "is_leech": is_leech,
            "is_qbit": is_qbit,
            "is_jd": is_jd,
            "is_nzb": is_nzb,
            "flags": args,
            "chat_id": context.chat_id,
            "user_id": context.user_id,
        }

        task = await create_task(
            source=link,
            pipeline_id=pipeline_id,
            user_id=context.user_id,
            destination=args.get("d", ""),
            metadata=metadata,
        )

        await enqueue_task(task)

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task.id[:20]}")
        reply_markup = buttons.build_menu(1)

        msg = f"<b>Task Queued</b>\n\n"
        msg += f"ID: <code>{task.id[:20]}</code>\n"
        msg += f"Mode: {'Leech' if is_leech else 'Mirror'}\n"
        msg += f"Source: {link[:100]}"

        await client.send_message(
            context.chat_id, msg, reply_markup, parse_mode=enums.ParseMode.HTML
        )

        return MirrorResult(task=task, message=msg)


class YtdlpHandler(BotHandler):
    """Handler for ytdl commands"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        is_leech: bool = False,
    ) -> MirrorResult:
        args = arg_parser(context.text)
        link = args.get("link", "").strip()

        if not link:
            await client.send_message(
                context.chat_id, YTDLP_USAGE, parse_mode=enums.ParseMode.HTML
            )
            return MirrorResult()

        pipeline_id = "yt_telegram" if is_leech else "yt_gdrive"
        quality = args.get("q", "bestvideo+bestaudio/best")

        metadata = {
            "quality": quality,
            "is_leech": is_leech,
            "chat_id": context.chat_id,
            "user_id": context.user_id,
        }

        task = await create_task(
            source=link,
            pipeline_id=pipeline_id,
            user_id=context.user_id,
            metadata=metadata,
        )

        await enqueue_task(task)

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task.id[:20]}")
        reply_markup = buttons.build_menu(1)

        msg = f"<b>YouTube Download Started</b>\n\n"
        msg += f"ID: <code>{task.id[:20]}</code>\n"
        msg += f"Quality: {quality}"

        await client.send_message(
            context.chat_id, msg, reply_markup, parse_mode=enums.ParseMode.HTML
        )

        return MirrorResult(task=task, message=msg)


class CloneHandler(BotHandler):
    """Handler for clone command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> MirrorResult:
        args = arg_parser(context.text)
        link = args.get("link", "").strip()

        if not link:
            await client.send_message(
                context.chat_id, CLONE_USAGE, parse_mode=enums.ParseMode.HTML
            )
            return MirrorResult()

        if "drive.google.com" not in link and "docs.google.com" not in link:
            await client.send_message(
                context.chat_id,
                "<b>Invalid GDrive Link!</b>\n\nSend a valid Google Drive link.",
                parse_mode=enums.ParseMode.HTML,
            )
            return MirrorResult()

        metadata = {
            "chat_id": context.chat_id,
            "user_id": context.user_id,
        }

        task = await create_task(
            source=link,
            pipeline_id="gdrive_clone",
            user_id=context.user_id,
            metadata=metadata,
        )

        await enqueue_task(task)

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task.id[:20]}")
        reply_markup = buttons.build_menu(1)

        msg = f"<b>Clone Started</b>\n\n"
        msg += f"ID: <code>{task.id[:20]}</code>\n"
        msg += f"Source: {link[:100]}"

        await client.send_message(
            context.chat_id, msg, reply_markup, parse_mode=enums.ParseMode.HTML
        )

        return MirrorResult(task=task, message=msg)


class CancelHandler(BotHandler):
    """Handler for cancel command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> Optional[Task]:
        args = arg_parser(context.text)
        task_id = args.get("link", "").strip()

        if task_id:
            if task_id.isdigit():
                tasks = await get_tasks(
                    user_id=int(task_id), status=TaskStatus.RUNNING, limit=1
                )
            else:
                try:
                    task = await cancel_task(task_id)
                    if task:
                        await client.send_message(
                            context.chat_id,
                            f"<b>Task Cancelled</b>\n\nID: <code>{task.id[:20]}</code>",
                            parse_mode=enums.ParseMode.HTML,
                        )
                        return task
                except Exception:
                    pass

                tasks = await get_tasks(
                    user_id=context.user_id, status=TaskStatus.RUNNING, limit=1
                )
        else:
            tasks = await get_tasks(
                user_id=context.user_id, status=TaskStatus.RUNNING, limit=1
            )

        if tasks:
            task = tasks[0]
            await get_queue_manager().cancel(task.id)
            await client.send_message(
                context.chat_id,
                f"<b>Task Cancelled</b>\n\nID: <code>{task.id[:20]}</code>",
                parse_mode=enums.ParseMode.HTML,
            )
            return task

        await client.send_message(
            context.chat_id,
            "<b>No Running Task Found!</b>",
            parse_mode=enums.ParseMode.HTML,
        )
        return None


class CancelAllHandler(BotHandler):
    """Handler for cancelall command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> int:
        tasks = await get_tasks(
            user_id=context.user_id, status=TaskStatus.RUNNING, limit=50
        )

        count = 0
        for task in tasks:
            await get_queue_manager().cancel(task.id)
            count += 1

        await client.send_message(
            context.chat_id,
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
