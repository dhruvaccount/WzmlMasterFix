"""Status handler - API first approach"""

import logging
import time
import psutil
from typing import Optional, Any
from pyrogram import enums

from pyrogram import Client, types
from bots.clients.telegram.handlers import BotHandler
from bots.clients.telegram.helpers.message_utils import send_message
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.api import api_client
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
    p_str = "⬢" * cFull
    p_str += "⬡" * (12 - cFull)
    return f"[{p_str}]"


class StatusHandler(BotHandler):
    TASKS_PER_PAGE = 4
    
    def __init__(self):
        super().__init__()
        self._active_status_messages = {}

    async def handle_ws_event(self, client: Client, event: dict):
        if not hasattr(self, "_active_status_messages") or not self._active_status_messages:
            return

        import time
        now = time.time()
        
        # throttle UI updates to at most once per 2.5 seconds roughly
        if not hasattr(self, "_last_ws_update"):
            self._last_ws_update = 0
            
        if now - self._last_ws_update < 2.5:
            return
            
        self._last_ws_update = now
        
        for msg_id, data in list(self._active_status_messages.items()):
            chat_id = data["chat_id"]
            user_filter = data["user_filter"]
            page = data["page"]
            msg_obj = data["message_obj"]
            
            try:
                text, reply_markup = await self.get_status_message(user_filter=user_filter, page=page)
                
                # Check if it actually changed to avoid MessageNotModified exceptions
                if text != data.get("last_text"):
                    from bots.clients.telegram.helpers.message_utils import edit_message
                    await edit_message(
                        message=chat_id,
                        message_id=msg_id,
                        text=text,
                        buttons=reply_markup,
                        parse_mode=enums.ParseMode.HTML
                    )
                    self._active_status_messages[msg_id] = {
                        **data,
                        "last_text": text
                    }
            except Exception as e:
                # if message is deleted by user or bot, pop it
                err_str = str(e).lower()
                if "invalid" in err_str or "deleted" in err_str or "not found" in err_str:
                    logger.debug(f"Removing dead status tracking for msg {msg_id}: {e}")
                    self._active_status_messages.pop(msg_id, None)

    async def handle(
        self,
        client: Client,
        message: types.Message,
        task_id: str = None,
    ) -> Optional[str]:
        from bots.clients.telegram.helpers.message_utils import arg_parser

        args = arg_parser(message.text)
        target_id = args.get("link", "")

        user_filter = None
        if target_id:
            if target_id == "me":
                user_filter = message.from_user.id
            elif target_id.isdigit():
                user_filter = int(target_id)

        msg, reply_markup = await self.get_status_message(
            user_filter=user_filter, page=1
        )

        sent = await send_message(
            message,
            msg,
            reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
        if sent:
            # Storing the message allows the WS event listener to patch it over time automatically
            self._active_status_messages[sent.id] = {
                "chat_id": sent.chat.id,
                "message_obj": sent,
                "user_filter": user_filter,
                "page": 1,
                "last_text": msg
            }

        return "Status sent"

    async def get_status_message(self, user_filter: int = None, page: int = 1):
        res = await api_client.get_active_tasks(user_id=user_filter)
        active_tasks = res.get("data", [])

        if not active_tasks:
            return "No active tasks!", None

        total_tasks = len(active_tasks)
        total_pages = (total_tasks + self.TASKS_PER_PAGE - 1) // self.TASKS_PER_PAGE
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * self.TASKS_PER_PAGE
        end_idx = start_idx + self.TASKS_PER_PAGE
        page_tasks = active_tasks[start_idx:end_idx]

        stats_res = await api_client.get_queue_stats()

        msg = f"<b>Active Tasks ({total_tasks})</b>\n\n"
        for i, task in enumerate(page_tasks, start_idx + 1):
            msg += self._format_task(i, task)

        msg += self._format_bot_stats(stats_res)

        buttons = ButtonMaker()
        if total_pages > 1:
            prev_page = total_pages if page == 1 else page - 1
            next_page = 1 if page == total_pages else page + 1
            buttons.data_button("<<", f"status {prev_page}")
            buttons.data_button(f"{page}/{total_pages}", "status_refresh")
            buttons.data_button(">>", f"status {next_page}")

        buttons.data_button("🔄 Refresh", f"status {page}")
        buttons.data_button("Stop All", "canall")

        return msg, buttons.build_menu(3 if total_pages > 1 else 2)

    def _format_task(self, index: int, task: dict) -> str:
        config = task.get("config", {})
        source = config.get("source", "")
        name = (
            config.get("destination")
            or source.split("/")[-1]
            or source
        )
        if len(name) > 50:
            name = name[:47] + "..."

        msg = f"<b>{index}.</b> <b><i>{name}</i></b>\n"
        
        meta = config.get("metadata", {}).get("ui_data", {})
        if meta and meta.get("mention"):
            msg += f"<b>Task By {meta['mention']}</b> ( #ID{meta['user_id']} ) <i>[<a href='{meta['message_link']}'>Link</a>]</i>\n"

        prog = task.get("progress", {})
        pct = prog.get("progress", 0.0)
        
        msg += f"┟ {get_progress_bar_string(pct)} <i>{pct:.1f}%</i>\n"

        if prog:
            total = prog.get("total", 0)
            down = prog.get("downloaded", 0)
            if total > 0:
                down_str = get_readable_file_size(down)
                total_str = get_readable_file_size(total)
                msg += f"┠ <b>Processed</b> → <i>{down_str} of {total_str}</i>\n"

            msg += f"┠ <b>Status</b> → <b>{str(task.get('status', '')).title()}</b>\n"

            speed = prog.get("speed", 0)
            if speed > 0:
                speed_str = get_readable_file_size(speed) + "/s"
                msg += f"┠ <b>Speed</b> → <i>{speed_str}</i>\n"

            eta = prog.get("eta", 0)
            if eta > 0:
                msg += f"┠ <b>Time</b> → <i>{get_readable_time(eta)}</i>\n"

        msg += f"┠ <b>Engine</b> → <i>{config.get('pipeline_id', 'unknown')}</i>\n"
        msg += f"┖ <b>Stop</b> → <i>/cancel {task.get('id', '')}</i>\n\n"

        return msg

    def _format_bot_stats(self, q_stats: dict) -> str:
        msg = "⌬ <b><u>Bot Stats</u></b>\n"

        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage("/")
        disk = disk_usage.percent
        free_disk = get_readable_file_size(disk_usage.free)
        uptime = get_readable_time(time.time() - bot_start_time)

        msg += f"┟ <b>CPU</b> → {cpu}% | <b>F</b> → {free_disk} [{100 - disk:.1f}%]\n"
        msg += f"┖ <b>RAM</b> → {ram}% | <b>UP</b> → {uptime}\n"

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
