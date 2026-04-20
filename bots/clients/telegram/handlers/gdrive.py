"""GDrive handlers (count, delete, list)"""

import logging
from typing import Any, List, Optional

from bots.clients.telegram.helpers.message_utils import arg_parser, is_gdrive_link
from core.status_utils import get_readable_file_size
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from core.plugin_loader import get_plugin
from pyrogram import Client, types
from bots.clients.telegram.handlers import BotHandler
from bots.clients.telegram.helpers.message_utils import send_message

logger = logging.getLogger("wzml.bot.handlers.gdrive")


class GDriveCountHandler(BotHandler):
    """Handler for gdcount command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> dict:
        args = arg_parser(message.text)
        link = args.get("link", "")

        if not link and context.reply_to_message:
            link = context.reply_to_message.text.split(maxsplit=1)[0].strip()

        if not is_gdrive_link(link):
            await send_message(
            message,
            "Send Gdrive link along with command or by replying to the link by command",
            )
            return {}

        msg = await send_message(
            message,
            f"Counting: {link[:100]}",
        )

        try:
            gdrive = get_plugin("gdrive")
            if not gdrive:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "GDrive plugin not initialized",
                )
                return {}

            file_id = link.split("/d/")[-1].split("/")[0].split("?")[0].split("id=")[-1]
            file = await gdrive.get_file(file_id)

            if not file:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "File not found",
                )
                return {}

            name = file.get("name", "Unknown")
            mime_type = file.get("mimeType", "Unknown")
            size = file.get("size", "0")

            result = {
                "name": name,
                "type": mime_type,
                "size": get_readable_file_size(int(size) if size.isdigit() else 0),
            }

            text = f"Name: {name}\nSize: {result['size']}\nType: {mime_type}"
            await client.edit_message(message.chat.id, msg.id, text)

            return result

        except Exception as e:
            logger.error(f"GDrive count error: {e}")
            await client.edit_message(
                message.chat.id,
                msg.id,
                f"Error: {str(e)}",
            )
            return {}


class GDriveDeleteHandler(BotHandler):
    """Handler for gddelete command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> bool:
        args = arg_parser(message.text)
        link = args.get("link", "")

        if not link and context.reply_to_message:
            link = context.reply_to_message.text.split(maxsplit=1)[0].strip()

        if not is_gdrive_link(link):
            await send_message(
            message,
            "Send Gdrive link along with command or by replying to the link by command",
            )
            return False

        msg = await send_message(
            message,
            "Deleting...")

        try:
            gdrive = get_plugin("gdrive")
            if not gdrive:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "GDrive plugin not initialized",
                )
                return False

            file_id = link.split("/d/")[-1].split("/")[0].split("?")[0].split("id=")[-1]
            success = await gdrive.delete_file(file_id)

            if success:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "File deleted successfully",
                )
            else:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "Failed to delete file",
                )

            return success

        except Exception as e:
            logger.error(f"GDrive delete error: {e}")
            await client.edit_message(
                message.chat.id,
                msg.id,
                f"Error: {str(e)}",
            )
            return False


class GDriveListHandler(BotHandler):
    """Handler for gdlist command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> List[dict]:
        args = arg_parser(message.text)
        query = args.get("link", "")

        if not query and context.reply_to_message:
            query = context.reply_to_message.text.split(maxsplit=1)[1].strip()

        if not query:
            await send_message(
            message,
            "Send a search query along with list command",
            )
            return []

        msg = await send_message(
            message,
            f"Searching GDrive for: {query}",
        )

        try:
            gdrive = get_plugin("gdrive")
            if not gdrive:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "GDrive plugin not initialized",
                )
                return []

            results = await gdrive.search(query)

            if not results:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    f"No results found for: {query}",
                )
                return []

            text = f"Found {len(results)} results for: {query}\n\n"

            buttons = ButtonMaker()
            for i, result in enumerate(results[:10], 1):
                name = result.get("name", "Unknown")[:50]
                text += f"{i}. {name}\n"

                file_id = result.get("id")
                buttons.data_button(f"{i}", f"gdfselect {file_id}")

            reply_markup = buttons.build_menu(2) if results else None

            await client.edit_message(
                message.chat.id,
                msg.id,
                text,
                reply_markup,
            )

            return results

        except Exception as e:
            logger.error(f"GDrive list error: {e}")
            await client.edit_message(
                message.chat.id,
                msg.id,
                f"Error: {str(e)}",
            )
            return []


__all__ = [
    "GDriveCountHandler",
    "GDriveDeleteHandler",
    "GDriveListHandler",
]
