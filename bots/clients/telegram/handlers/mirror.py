"""Mirror, Leech, Ytdlp, Clone handlers"""

import logging
from typing import Optional, Any
from dataclasses import dataclass

from core.task import Task, TaskStatus, create_task, get_tasks, cancel_task
from core.queue import enqueue_task
from core.status_utils import get_readable_file_size, get_status_buttons
from bots.clients.telegram.helpers.message_utils import (
    arg_parser,
    is_gdrive_link,
    pre_task_check,
)
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.clients.telegram.handlers import BotHandler, CommandContext

logger = logging.getLogger("wzml.bot.handlers.mirror")


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
        is_uphoster: bool = False,
    ) -> MirrorResult:
        args = arg_parser(context.text)
        link = args.get("link", "")

        check_msg, check_button = pre_task_check(context.text)
        if check_msg:
            await client.send_message(context.chat_id, check_msg, check_button)
            return MirrorResult(message=check_msg)

        flags = {
            "-doc": args.get("-doc", False),
            "-med": args.get("-med", False),
            "-d": args.get("-d", False),
            "-j": args.get("-j", False),
            "-s": args.get("-s", False),
            "-b": args.get("-b", False),
            "-e": args.get("-e", False),
            "-z": args.get("-z", False),
            "-sv": args.get("-sv", False),
            "-ss": args.get("-ss", False),
            "-f": args.get("-f", False),
            "-fd": args.get("-fd", False),
            "-fu": args.get("-fu", False),
            "-hl": args.get("-hl", False),
            "-bt": args.get("-bt", False),
            "-ut": args.get("-ut", False),
            "-yt": args.get("-yt", False),
            "-i": int(args.get("-i", 0)),
            "-sp": int(args.get("-sp", 0)),
            "-n": args.get("-n", ""),
            "-m": args.get("-m", ""),
            "-meta": args.get("-meta", ""),
            "-up": args.get("-up", ""),
            "-rcf": args.get("-rcf", ""),
            "-t": args.get("-t", ""),
            "-ca": args.get("-ca", ""),
            "-cv": args.get("-cv", ""),
            "-ns": args.get("-ns", ""),
            "-tl": args.get("-tl", ""),
            "-h": args.get("-h", ""),
        }

        if is_qbit:
            pipeline_id = "torrent_gdrive"
        elif is_jd:
            pipeline_id = "jd_gdrive"
        elif is_nzb:
            pipeline_id = "nzb_gdrive"
        elif is_uphoster:
            pipeline_id = "uphosted_gofile"
        elif is_leech:
            pipeline_id = "telegram"
        else:
            pipeline_id = "download_upload"

        destination = args.get("-d", "")

        task = await create_task(
            source=link,
            pipeline_id=pipeline_id,
            user_id=context.user_id,
            destination=destination,
            metadata={
                "is_leech": is_leech,
                "is_qbit": is_qbit,
                "is_jd": is_jd,
                "is_nzb": is_nzb,
                "flags": flags,
            },
        )

        await enqueue_task(task)

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task.id}")
        reply_markup = buttons.build_menu(1)

        msg = f"Task Queued:\n\nID: {task.id}\n"
        msg += f"Mode: {'Leech' if is_leech else 'Mirror'}\n"
        msg += f"Source: {link[:100]}"

        if link.startswith("http"):
            msg += f"\nSize: Calculating..."

        await client.send_message(context.chat_id, msg, reply_markup)

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
        link = args.get("link", "")

        if not link:
            await client.send_message(
                context.chat_id,
                "Send Link along with command!\n\n/mirror https://youtu.be/...",
            )
            return MirrorResult()

        quality = args.get("-q", "bestvideo+bestaudio/best")
        pipeline_id = "yt_telegram" if is_leech else "yt_gdrive"

        task = await create_task(
            source=link,
            pipeline_id=pipeline_id,
            user_id=context.user_id,
            metadata={
                "quality": quality,
                "thumbnail": True,
                "is_leech": is_leech,
            },
        )

        await enqueue_task(task)

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task.id}")
        reply_markup = buttons.build_menu(1)

        msg = f"YouTube Download Started\n\nTask ID: {task.id[:20]}\nQuality: {quality}"
        await client.send_message(context.chat_id, msg, reply_markup)

        return MirrorResult(task=task, message=msg)


class CloneHandler(BotHandler):
    """Handler for clone command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> MirrorResult:
        args = arg_parser(context.text)
        link = args.get("link", "")

        if not is_gdrive_link(link):
            await client.send_message(
                context.chat_id,
                "Send GDrive Link along with /clone Command!",
            )
            return MirrorResult()

        task = await create_task(
            source=link,
            pipeline_id="gdrive_clone",
            user_id=context.user_id,
        )

        await enqueue_task(task)

        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"cancel {task.id}")
        reply_markup = buttons.build_menu(1)

        msg = f"Clone Started\n\nTask ID: {task.id[:20]}\nSource: {link[:100]}"
        await client.send_message(context.chat_id, msg, reply_markup)

        return MirrorResult(task=task, message=msg)


class CancelHandler(BotHandler):
    """Handler for cancel command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        task_id: str = None,
    ) -> Optional[Task]:
        task = None
        text = context.text
        args = arg_parser(text)
        task_id = args.get("link", "") or task_id

        if task_id:
            task = await cancel_task(task_id)
            if task:
                msg = f"Task Cancelled\n\n{task.id[:20]}"
                await client.send_message(context.chat_id, msg)
                return task

        tasks = await get_tasks(
            user_id=context.user_id,
            status=TaskStatus.RUNNING,
            limit=1,
        )

        if tasks:
            task = tasks[0]
            task.cancel()
            msg = f"Task Cancelled\n\n{task.id[:20]}"
            await client.send_message(context.chat_id, msg)
            return task

        await client.send_message(context.chat_id, "No Running Task Found!")
        return None


class CancelAllHandler(BotHandler):
    """Handler for cancelall command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> int:
        tasks = await get_tasks(
            user_id=context.user_id,
            status=TaskStatus.RUNNING,
            limit=50,
        )

        count = 0
        for task in tasks:
            task.cancel()
            count += 1

        await client.send_message(
            context.chat_id,
            f"{count} Tasks Cancelled!",
        )
        return count


__all__ = [
    "MirrorHandler",
    "YtdlpHandler",
    "CloneHandler",
    "CancelHandler",
    "CancelAllHandler",
]
