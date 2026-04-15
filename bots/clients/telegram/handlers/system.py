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
from bots.clients.telegram.handlers import BotHandler, CommandContext

logger = logging.getLogger("wzml.bot.handlers.system")


class PingHandler(BotHandler):
    """Handler for ping command"""

    def __init__(self):
        self._start_time = datetime.now()

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> float:
        start = time.time()
        msg = await client.send_message(context.chat_id, "Pong!")
        latency = (time.time() - start) * 1000

        uptime = datetime.now() - self._start_time
        uptime_str = str(uptime).split(".")[0]

        text = f"Pong!\n\nLatency: {latency:.2f} ms\nUptime: {uptime_str}"
        await client.edit_message(context.chat_id, msg.id, text)

        return latency


class StatsHandler(BotHandler):
    """Handler for stats command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
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

        await client.send_message(context.chat_id, text)

        return stats


class LogHandler(BotHandler):
    """Handler for log command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> str:
        args = arg_parser(context.text)
        lines = int(args.get("-n", 50))

        log_dir = "logs"

        if not os.path.exists(log_dir):
            await client.send_message(context.chat_id, "No logs found!")
            return ""

        log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]

        if not log_files:
            await client.send_message(context.chat_id, "No logs found!")
            return ""

        latest_log = os.path.join(log_dir, sorted(log_files)[-1])

        with open(latest_log, "r") as f:
            content = f.readlines()

        log_text = "".join(content[-lines:])

        if len(log_text) > 3500:
            log_text = log_text[-3500:]

        log_text = f"<pre>{log_text}</pre>"
        await client.send_message(context.chat_id, log_text)

        return log_text


class RestartHandler(BotHandler):
    """Handler for restart command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        mode: str = "bot",
    ) -> str:
        if mode == "bot":
            await client.send_message(context.chat_id, "Restarting Bot...")
            return "Bot restart initiated"
        elif mode == "services":
            await client.send_message(context.chat_id, "Restarting Services...")
            return "Services restart initiated"
        elif mode == "all":
            await client.send_message(context.chat_id, "Restarting All...")
            return "Full restart initiated"


class ExecHandler(BotHandler):
    """Handler for exec command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        is_async: bool = False,
    ) -> str:
        args = arg_parser(context.text)
        command = args.get("link", "")

        if not command:
            await client.send_message(
                context.chat_id,
                "Send Shell Command along with /exec Command!",
            )
            return ""

        msg = await client.send_message(context.chat_id, "Executing...")

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
            await client.delete_message(context.chat_id, msg.id)
        except:
            pass

        await client.send_message(context.chat_id, output)

        return output


class ShellHandler(BotHandler):
    """Handler for shell command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> str:
        import asyncio

        args = arg_parser(context.text)
        cmd = args.get("link", "")

        if not cmd:
            await client.send_message(context.chat_id, "Send Shell Command!")
            return ""

        await client.send_message(context.chat_id, f"Executing: {cmd}")

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
        await client.send_message(context.chat_id, result)

        return result


class BroadcastHandler(BotHandler):
    """Handler for broadcast command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        message: str = None,
    ) -> int:
        args = arg_parser(context.text)
        message = args.get("link", "") or message

        if not message:
            await client.send_message(
                context.chat_id,
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

        await client.send_message(
            context.chat_id,
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
