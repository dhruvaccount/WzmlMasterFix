"""Status handler - API first approach"""

import logging
import time
import psutil
from typing import Optional, Any
from pyrogram import enums

from core.task import get_tasks, TaskStatus, Task
from core.queue import get_queue_stats
from bots.clients.telegram.handlers import BotHandler, CommandContext
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from config.telegram import TelegramConfig

logger = logging.getLogger("wzml.bot.handlers.status")

bot_start_time = time.time()
SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def get_readable_file_size(size_in_bytes: float) -> str:
    if not size_in_bytes:
        return "0B"
    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1
    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds: float) -> str:
    seconds = int(seconds)
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f"{int(period_value)}{period_name}"
    return result or "0s"


def get_progress_bar_string(pct: float) -> str:
    p = min(max(pct, 0), 100)
    cFull = int(p // 8)
    p_str = "■" * cFull
    p_str += "□" * (12 - cFull)
    return f"[{p_str}]"


class StatusHandler(BotHandler):
    async def handle(
        self,
        context: CommandContext,
        client: Any,
        task_id: str = None,
    ) -> Optional[str]:
        from bots.clients.telegram.helpers.message_utils import arg_parser

        args = arg_parser(context.text)
        target_id = args.get("link", "")

        user_filter = None
        if target_id:
            if target_id == "me":
                user_filter = context.user_id
            elif target_id.isdigit():
                user_filter = int(target_id)

        tasks = await get_tasks(user_id=user_filter)
        active_tasks = [t for t in tasks if t.is_active]

        if not active_tasks:
            await client.send_message(context.chat_id, "No active tasks!")
            return "No tasks"

        stats = await get_queue_stats()

        msg = "<b>Active Tasks</b>\n\n"
        for i, task in enumerate(active_tasks[:10], 1):  # Limit to 10 for now
            msg += self._format_task(i, task)

        msg += self._format_bot_stats(stats)

        buttons = ButtonMaker()
        buttons.data_button("🔄 Refresh", "status_refresh", position="header")

        await client.send_message(
            context.chat_id,
            msg,
            reply_markup=buttons.build_menu(2),
            parse_mode=enums.ParseMode.HTML,
        )
        return "Status sent"

    def _format_task(self, index: int, task: Task) -> str:
        name = (
            task.config.destination
            or task.config.source.split("/")[-1]
            or task.config.source
        )
        if len(name) > 50:
            name = name[:47] + "..."

        msg = f"<b>{index}.</b> <b><i>{name}</i></b>\n"

        prog = task.progress
        pct = prog.progress if prog else 0.0

        msg += f"├ {get_progress_bar_string(pct)} <i>{pct:.1f}%</i>\n"

        if prog:
            if prog.total > 0:
                down_str = get_readable_file_size(prog.downloaded)
                total_str = get_readable_file_size(prog.total)
                msg += f"├ <b>Processed:</b> <i>{down_str} of {total_str}</i>\n"

            msg += f"├ <b>Status:</b> <b>{task.status.title()}</b>"
            if prog.stage:
                msg += f" - {prog.stage.title()}"
            msg += "\n"

            if prog.speed > 0:
                speed_str = get_readable_file_size(prog.speed) + "/s"
                msg += f"├ <b>Speed:</b> <i>{speed_str}</i>\n"

            if prog.eta > 0:
                msg += f"├ <b>ETA:</b> <i>{get_readable_time(prog.eta)}</i>\n"

        msg += f"├ <b>Engine:</b> <i>{task.config.pipeline_id}</i>\n"
        msg += f"└ <b>Cancel:</b> <i>/cancel {task.id}</i>\n\n"

        return msg

    def _format_bot_stats(self, q_stats) -> str:
        msg = "<b><u>Bot Stats</u></b>\n"

        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage("/")
        disk = disk_usage.percent
        free_disk = get_readable_file_size(disk_usage.free)
        uptime = get_readable_time(time.time() - bot_start_time)

        msg += f"├ <b>CPU:</b> {cpu}% | <b>RAM:</b> {ram}%\n"
        msg += f"├ <b>Free Disk:</b> {free_disk} ({100 - disk:.1f}%)\n"
        msg += f"├ <b>Uptime:</b> {uptime}\n"
        msg += f"└ <b>Queue:</b> {q_stats.running}R | {q_stats.queued}Q | {q_stats.pending}P\n"

        return msg

    def _parse_args(self, text: str) -> dict:
        args = {}
        parts = text.split()
        for part in parts[1:]:
            if part.startswith("-"):
                args[part] = True
            elif part.isdigit() or part == "me":
                args["link"] = part
        return args


__all__ = ["StatusHandler"]
