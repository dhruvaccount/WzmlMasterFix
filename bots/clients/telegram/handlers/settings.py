"""Settings handlers (user, bot)"""

import logging
from typing import Any

from bots.clients.telegram.helpers.message_utils import arg_parser
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.clients.telegram.handlers import BotHandler, CommandContext

logger = logging.getLogger("wzml.bot.handlers.settings")


class UserSettingsHandler(BotHandler):
    """Handler for usetting command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        action: str = "menu",
    ) -> str:
        args = arg_parser(context.text)
        option = args.get("link", "")

        if action == "menu":
            text = "User Settings\n\nSelect an option:\n\n"
            text += "1. General Settings\n"
            text += "2. Mirror Settings\n"
            text += "3. Leech Settings\n"
            text += "4. Uphoster Settings\n"
            text += "5. FF Media Settings\n"
            text += "6. Advanced Settings"

            buttons = ButtonMaker()
            buttons.data_button("1", "uset general")
            buttons.data_button("2", "uset mirror")
            buttons.data_button("3", "uset leech")
            buttons.data_button("4", "uset uphoster")
            buttons.data_button("5", "uset ffset")
            buttons.data_button("6", "uset advanced")
            reply_markup = buttons.build_menu(2)

            await client.send_message(context.chat_id, text, reply_markup)

        elif action == "get":
            text = "Use /usetting menu"
            await client.send_message(context.chat_id, text)

        elif action == "set":
            await client.send_message(
                context.chat_id,
                "Send setting key=value\n\nExample: THUMBNAIL=true",
            )

        else:
            text = "Use /usetting menu"
            await client.send_message(context.chat_id, text)

        return text


class BotSettingsHandler(BotHandler):
    """Handler for bsetting command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        action: str = "menu",
    ) -> str:
        if action == "menu":
            text = "Bot Settings\n\n"
            text += "1. Sudo Users\n"
            text += "2. Banned Users\n"
            text += "3. Channel Configs\n"
            text += "4. Service Configs\n"
            text += "5. Buttons Configs"

            buttons = ButtonMaker()
            buttons.data_button("1", "bset sudo")
            buttons.data_button("2", "bset banned")
            buttons.data_button("3", "bset channels")
            buttons.data_button("4", "bset services")
            buttons.data_button("5", "bset buttons")
            reply_markup = buttons.build_menu(2)

            await client.send_message(context.chat_id, text, reply_markup)

        elif action == "sudo":
            from config.telegram import SUDO_USERS

            sudo_list = ", ".join(str(s) for s in SUDO_USERS)
            text = f"Sudo Users:\n{sudo_list or 'None'}"
            await client.send_message(context.chat_id, text)

        else:
            text = "Use /bsetting menu"
            await client.send_message(context.chat_id, text)

        return text


class ServicesHandler(BotHandler):
    """Handler for services command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        action: str = "status",
    ) -> str:
        services = ["aria2", "qbittorrent", "rclone", "ffmpeg", "sabnzbd"]
        buttons = ButtonMaker()

        if action == "status":
            text = "Services Status\n\n"

            for svc in services:
                status = "Running" if svc in ["aria2", "qbittorrent"] else "Stopped"
                text += f"{svc}: {status}\n"

            buttons.data_button("Restart All", "service restart")
            reply_markup = buttons.build_menu(1)

            await client.send_message(context.chat_id, text, reply_markup)

        elif action == "start":
            text = "Starting services..."
            await client.send_message(context.chat_id, text)

        elif action == "stop":
            text = "Stopping services..."
            await client.send_message(context.chat_id, text)

        elif action == "restart":
            text = "Restarting services..."
            await client.send_message(context.chat_id, text)

        return text


class IMDBHandler(BotHandler):
    """Handler for imdb command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> dict:
        args = arg_parser(context.text)
        query = args.get("link", "")

        if not query:
            await client.send_message(
                context.chat_id,
                "Send Movie Name along with /imdb Command!\n\n/imdb Inception",
            )
            return {}

        await client.send_message(
            context.chat_id,
            f"Searching: {query}",
        )

        try:
            from core.helpers.imdb import IMDBHandler as IMDB

            imdb = IMDB()
            result = await imdb.get_details(query)

            if result:
                text = f"{result.get('title', 'N/A')}\n\n"
                text += f"Year: {result.get('year', 'N/A')}\n"
                text += f"Rating: {result.get('rating', 'N/A')}\n"
                text += f"Genres: {result.get('genres', 'N/A')}\n"
                text += f"Runtime: {result.get('runtime', 'N/A')}\n"
                text += f"Plot: {result.get('plot', 'N/A')}"

                if result.get("poster"):
                    await client.send_photo(
                        context.chat_id,
                        result["poster"],
                        text,
                    )
                else:
                    await client.send_message(context.chat_id, text)

                return result
            else:
                await client.send_message(context.chat_id, "No results found!")

        except Exception as e:
            logger.error(f"IMDB error: {e}")
            await client.send_message(
                context.chat_id,
                f"Error: {str(e)}",
            )

        return {}


class HelpHandler(BotHandler):
    """Handler for help command"""

    HELP_TEXT = {
        "mirror": (
            "Mirror Command\n\n"
            "/mirror [link] -d [folder_name]\n\n"
            "Options:\n"
            "-d: Set download folder\n"
            "-n: Set file name\n"
            "-up: Upload destination\n"
            "-z: Zip\n"
            "-e: Extract"
        ),
        "leech": (
            "Leech Command\n\n"
            "/leech [link]\n\n"
            "Options:\n"
            "-doc: As document\n"
            "-med: As media\n"
            "-sp: Split size"
        ),
        "search": ("Search Command\n\n/search [query]\n\nSearch torrents"),
    }

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        command: str = None,
    ) -> str:
        args = arg_parser(context.text)
        command = args.get("link", "")

        if command:
            if command in self.HELP_TEXT:
                text = self.HELP_TEXT[command]
            else:
                text = f"Command /{command} not found!"
        else:
            text = "Available Commands\n\n"
            text += "/mirror - Mirror to cloud\n"
            text += "/leech - Leech to Telegram\n"
            text += "/ytdl - YouTube Download\n"
            text += "/clone - Clone GDrive\n"
            text += "/cancel - Cancel task\n"
            text += "/status - Task status\n"
            text += "/search - Torrent search\n"
            text += "/rss - RSS feeds\n"
            text += "/stats - Bot statistics\n"
            text += "/ping - Ping bot\n"
            text += "/help - Help menu"

        await client.send_message(context.chat_id, text)
        return text


__all__ = [
    "UserSettingsHandler",
    "BotSettingsHandler",
    "ServicesHandler",
    "IMDBHandler",
    "HelpHandler",
]
