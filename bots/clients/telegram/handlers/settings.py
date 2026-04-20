"""Settings handlers (user, bot)"""

import logging
from typing import Any

from bots.clients.telegram.helpers.message_utils import arg_parser
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from pyrogram import Client, types
from bots.clients.telegram.handlers import BotHandler
from bots.clients.telegram.helpers.message_utils import send_message

SUDO_USERS = []


def _load_sudo_users():
    global SUDO_USERS
    from config import get_config

    cfg = get_config()
    SUDO_USERS = cfg.telegram.SUDO_USERS or []


_load_sudo_users()

logger = logging.getLogger("wzml.bot.handlers.settings")


class UserSettingsHandler(BotHandler):
    """Handler for usetting command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
        action: str = "menu",
    ) -> str:
        args = arg_parser(message.text)
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

            await send_message(
            message,
            text, reply_markup)

        elif action == "get":
            text = "Use /usetting menu"
            await send_message(
            message,
            text)

        elif action == "set":
            await send_message(
            message,
            "Send setting key=value\n\nExample: THUMBNAIL=true",
            )

        else:
            text = "Use /usetting menu"
            await send_message(
            message,
            text)

        return text


class BotSettingsHandler(BotHandler):
    """Handler for bsetting command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
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

            await send_message(
            message,
            text, reply_markup)

        elif action == "sudo":
            sudo_list = ", ".join(str(s) for s in SUDO_USERS)
            text = f"Sudo Users:\n{sudo_list or 'None'}"
            await send_message(
            message,
            text)

        else:
            text = "Use /bsetting menu"
            await send_message(
            message,
            text)

        return text


class ServicesHandler(BotHandler):
    """Handler for services command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
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

            await send_message(
            message,
            text, reply_markup)

        elif action == "start":
            text = "Starting services..."
            await send_message(
            message,
            text)

        elif action == "stop":
            text = "Stopping services..."
            await send_message(
            message,
            text)

        elif action == "restart":
            text = "Restarting services..."
            await send_message(
            message,
            text)

        return text


class IMDBHandler(BotHandler):
    """Handler for imdb command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> dict:
        args = arg_parser(message.text)
        query = args.get("link", "")

        if not query:
            await send_message(
            message,
            "Send Movie Name along with /imdb Command!\n\n/imdb Inception",
            )
            return {}

        await send_message(
            message,
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
                        message.chat.id,
                        result["poster"],
                        text,
                    )
                else:
                    await send_message(
            message,
            text)

                return result
            else:
                await send_message(
            message,
            "No results found!")

        except Exception as e:
            logger.error(f"IMDB error: {e}")
            await send_message(
            message,
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
        client: Client,
        message: types.Message,
        command: str = None,
    ) -> str:
        args = arg_parser(message.text)
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

        await send_message(
            message,
            text)
        return text


__all__ = [
    "UserSettingsHandler",
    "BotSettingsHandler",
    "ServicesHandler",
    "IMDBHandler",
    "HelpHandler",
]
