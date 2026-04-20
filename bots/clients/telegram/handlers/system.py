"""System handlers (ping, stats, log, restart)"""

import logging
import subprocess
import os
import time
from datetime import datetime
from typing import Any

from core.task import get_tasks, TaskStatus
from core.queue import get_queue_manager
from bots.clients.telegram.helpers.message_utils import arg_parser
from pyrogram import Client, types
from bots.clients.telegram.handlers import BotHandler
from bots.clients.telegram.helpers.message_utils import send_message

logger = logging.getLogger("wzml.bot.handlers.system")


class PingHandler(BotHandler):
    """Handler for ping command"""

    def __init__(self):
        self._start_time = datetime.now()

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> float:
        start = time.time()
        msg = await send_message(
            message,
            "Pong!")
        latency = (time.time() - start) * 1000

        uptime = datetime.now() - self._start_time
        uptime_str = str(uptime).split(".")[0]

        text = f"Pong!\n\nLatency: {latency:.2f} ms\nUptime: {uptime_str}"
        await client.edit_message(message.chat.id, msg.id, text)

        return latency


class StatsHandler(BotHandler):
    """Handler for stats command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> dict:
        queue_manager = get_queue_manager()
        queue_stats = await queue_manager.get_stats()

        tasks = await get_tasks(limit=1000)

        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        active = sum(
            1 for t in tasks if t.status in [TaskStatus.QUEUED, TaskStatus.RUNNING]
        )

        stats = {
            "total": total,
            "completed": completed,
            "failed": failed,
            "active": active,
            "queued": queue_stats.pending,
            "running": queue_stats.running,
        }

        text = f"Bot Statistics\n\n"
        text += f"Total Tasks: {total}\n"
        text += f"Completed: {completed}\n"
        text += f"Failed: {failed}\n"
        text += f"Active: {active}\n"
        text += f"Queued: {queue_stats.pending}\n"
        text += f"Running: {queue_stats.running}"

        await send_message(
            message,
            text)

        return stats


class LogHandler(BotHandler):
    """Handler for log command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> str:
        args = arg_parser(message.text)
        lines = int(args.get("-n", 50))

        log_dir = "logs"

        if not os.path.exists(log_dir):
            await send_message(
            message,
            "No logs found!")
            return ""

        log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]

        if not log_files:
            await send_message(
            message,
            "No logs found!")
            return ""

        latest_log = os.path.join(log_dir, sorted(log_files)[-1])

        with open(latest_log, "r") as f:
            content = f.readlines()

        log_text = "".join(content[-lines:])

        if len(log_text) > 3500:
            log_text = log_text[-3500:]

        log_text = f"<pre>{log_text}</pre>"
        await send_message(
            message,
            log_text)

        return log_text


class RestartHandler(BotHandler):
    """Handler for restart command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
        mode: str = "bot",
    ) -> str:
        if mode == "bot":
            await send_message(
            message,
            "Restarting Bot...")
            return "Bot restart initiated"
        elif mode == "services":
            await send_message(
            message,
            "Restarting Services...")
            return "Services restart initiated"
        elif mode == "all":
            await send_message(
            message,
            "Restarting All...")
            return "Full restart initiated"


class ExecHandler(BotHandler):
    """Handler for exec command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
        is_async: bool = False,
    ) -> str:
        args = arg_parser(message.text)
        command = args.get("link", "")

        if not command:
            await send_message(
            message,
            "Send Shell Command along with /exec Command!",
            )
            return ""

        msg = await send_message(
            message,
            "Executing...")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout if result.stdout else result.stderr
        except Exception as e:
            output = str(e)

        if len(output) > 3500:
            output = output[:3500] + "\n... (truncated)"

        output = f"<pre>{output}</pre>"

        try:
            await client.delete_message(message.chat.id, msg.id)
        except:
            pass

        await send_message(
            message,
            output)

        return output


class ShellHandler(BotHandler):
    """Handler for shell command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> str:
        import asyncio

        args = arg_parser(message.text)
        cmd = args.get("link", "")

        if not cmd:
            await send_message(
            message,
            "Send Shell Command!")
            return ""

        await send_message(
            message,
            f"Executing: {cmd}")

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            result = stdout.decode() if stdout else stderr.decode()
        except Exception as e:
            result = str(e)

        if len(result) > 3500:
            result = result[:3500] + "\n... (truncated)"

        result = f"<pre>{result}</pre>"
        await send_message(
            message,
            result)

        return result


class BroadcastHandler(BotHandler):
    """Handler for broadcast command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
        message: str = None,
    ) -> int:
        args = arg_parser(message.text)
        message = args.get("link", "") or message

        if not message:
            await send_message(
            message,
            "Send message to broadcast!",
            )
            return 0

        users = set()
        all_tasks = await get_tasks(limit=1000)

        for task in all_tasks:
            users.add(task.user_id)

        count = 0
        for user_id in users:
            try:
                await client.send_message(user_id, message)
                count += 1
            except Exception as e:
                logger.error(f"Broadcast to {user_id} failed: {e}")

        await send_message(
            message,
            f"Broadcasted to {count} Users",
        )

        return count


__all__ = [
    "PingHandler",
    "StatsHandler",
    "LogHandler",
    "RestartHandler",
    "ExecHandler",
    "ShellHandler",
    "BroadcastHandler",
]
