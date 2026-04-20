"""MediaInfo handler"""

import logging
import subprocess
import tempfile
import os
from typing import Any

from bots.clients.telegram.helpers.message_utils import arg_parser
from core.status_utils import get_readable_file_size
from pyrogram import Client, types
from bots.clients.telegram.handlers import BotHandler
from bots.clients.telegram.helpers.message_utils import send_message

logger = logging.getLogger("wzml.bot.handlers.mediainfo")


class MediaInfoHandler(BotHandler):
    """Handler for mediainfo command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
    ) -> str:
        media = None

        if context.document:
            media = context.document
        elif context.video:
            media = context.video
        elif context.audio:
            media = context.audio

        args = arg_parser(message.text)
        link = args.get("link", "")

        if not media and not link and not context.reply_to_message:
            help_msg = (
                "By replying to media:\n"
                "/mediainfo [media]\n\n"
                "By reply/sending download link:\n"
                "/mediainfo [link]"
            )
            await send_message(
            message,
            help_msg)
            return ""

        msg = await send_message(
            message,
            "Generating MediaInfo...",
        )

        try:
            file_path = link
            temp_file = None
            file_size = 0

            if link and link.startswith("http"):
                import aiohttp

                temp_dir = tempfile.gettempdir()
                file_name = link.split("/")[-1].split("?")[0] or "mediainfo_temp"
                temp_file = os.path.join(temp_dir, file_name)

                async with aiohttp.ClientSession() as session:
                    async with session.get(link) as response:
                        if response.status == 200:
                            content = await response.read()
                            with open(temp_file, "wb") as f:
                                f.write(content)
                            file_path = temp_file
                            file_size = len(content)
            elif media:
                file_size = getattr(media, "file_size", 0)

                if file_size > 50000000:
                    await client.edit_message(
                        message.chat.id,
                        msg.id,
                        "File too large for media info",
                    )
                    return ""

                download_dir = tempfile.gettempdir()
                file_path = await client.download_media(
                    media,
                    file_name=download_dir,
                )

            if not file_path or not os.path.exists(file_path):
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "Failed to download file",
                )
                return ""

            result = subprocess.run(
                ["mediainfo", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            output = result.stdout

            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)

            if not output:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "MediaInfo not available. Install mediainfo CLI.",
                )
                return ""

            info_text = self._parse_mediainfo(output, file_size)

            if len(info_text) > 3500:
                info_text = info_text[:3500] + "\n... (truncated)"

            await client.edit_message(
                message.chat.id,
                msg.id,
                info_text,
            )

            return info_text

        except Exception as e:
            logger.error(f"MediaInfo error: {e}")
            await client.edit_message(
                message.chat.id,
                msg.id,
                f"Error: {str(e)}",
            )
            return ""

    def _parse_mediainfo(self, output: str, file_size: int = 0) -> str:
        lines = output.split("\n")
        info = "Media Info\n\n"

        section_icons = {
            "General": "General",
            "Video": "Video",
            "Audio": "Audio",
            "Text": "Text",
        }

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line in section_icons:
                info += f"\n{line}\n"
            elif ":" in line:
                key, value = line.split(":", 1)
                info += f"{key.strip()}: {value.strip()}\n"

        if file_size:
            info += f"\nSize: {get_readable_file_size(file_size)}"

        return info


__all__ = ["MediaInfoHandler"]
