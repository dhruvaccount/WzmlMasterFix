"""Status handler"""

import logging
from typing import Optional, Any

from core.task import Task, get_task, get_tasks, TaskStatus
from core.status_utils import get_readable_file_size, get_status_buttons
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.clients.telegram.handlers import BotHandler, CommandContext

logger = logging.getLogger("wzml.bot.handlers.status")


class StatusHandler(BotHandler):
    """Handler for status command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        task_id: str = None,
    ) -> Optional[str]:
        text = context.text
        args = self._parse_args(text)
        task_id = args.get("link", "") or task_id

        if task_id:
            task = await get_task(task_id)
            if not task:
                await client.send_message(context.chat_id, "Task not found!")
                return None

            status_text = await self.format_task_status(task)
            buttons = get_status_buttons(task.id)
            await client.send_message(context.chat_id, status_text, buttons)
            return status_text

        tasks = await get_tasks(
            user_id=context.user_id,
            limit=10,
        )

        if not tasks:
            await client.send_message(context.chat_id, "No Active Tasks!")
            return None

        status_lines = []
        for task in tasks:
            icon = (
                "✅"
                if task.status == TaskStatus.COMPLETED
                else "❌"
                if task.status == TaskStatus.FAILED
                else "⏳"
            )
            status_lines.append(
                f"{icon} {task.id[:20]} | {task.status.value} | {task.progress}%"
            )

        buttons = ButtonMaker()
        buttons.data_button("All Tasks", "status all")
        buttons.data_button("Refresh", "status refresh")
        reply_markup = buttons.build_menu(2)

        status_text = "Your Active Tasks:\n\n"
        status_text += "\n".join(status_lines)
        status_text += f"\n\nTotal: {len(tasks)}"

        await client.send_message(context.chat_id, status_text, reply_markup)
        return status_text

    def _parse_args(self, text: str) -> dict:
        """Parse command arguments"""
        args = {}
        parts = text.split()
        for i, part in enumerate(parts[1:], 1):
            if part.startswith("-"):
                args[part] = True
            else:
                args["link"] = part
        return args

    async def format_task_status(self, task: Task) -> str:
        msg = f"Task Details\n\n"
        msg += f"ID: {task.id}\n"
        msg += f"Status: {task.status.value}\n"
        msg += f"Progress: {task.progress}%"

        if task.progress.stage:
            msg += f"\nStage: {task.progress.stage}"

        if task.progress.speed:
            msg += f"\nSpeed: {get_readable_file_size(task.progress.speed)}/s"

        if task.progress.processed:
            msg += f"\nProcessed: {get_readable_file_size(task.progress.processed)}"

        if task.progress.total:
            msg += f"\nSize: {get_readable_file_size(task.progress.total)}"

        if task.error:
            msg += f"\nError: {task.error}"

        return msg


__all__ = ["StatusHandler"]
