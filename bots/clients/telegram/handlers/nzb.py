"""NZB search handler"""

import logging
from typing import Any, List

import aiohttp
import xml.etree.ElementTree as ET

from bots.clients.telegram.helpers.message_utils import arg_parser
from core.status_utils import get_readable_file_size
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from pyrogram import Client, types
from bots.clients.telegram.handlers import BotHandler
from bots.clients.telegram.helpers.message_utils import send_message

HYDRA_IP = ""
HYDRA_API_KEY = ""


def _load_hydra_config():
    global HYDRA_IP, HYDRA_API_KEY
    from config import get_config

    cfg = get_config()
    HYDRA_IP = cfg.telegram.HYDRA_IP or ""
    HYDRA_API_KEY = cfg.telegram.HYDRA_API_KEY or ""


_load_hydra_config()

logger = logging.getLogger("wzml.bot.handlers.nzb")


class NZBSearchHandler(BotHandler):
    """Handler for nzbsearch command"""

    async def handle(
        self,
        client: Client,
        message: types.Message,
        query: str = None,
    ) -> List[dict]:
        args = arg_parser(message.text)
        query = args.get("link", "") or query

        if not query:
            await send_message(
            message,
            "Send Search Query!\n\n/nzbsearch movie name",
            )
            return []

        msg = await send_message(
            message,
            f"Searching NZB for: {query}",
        )

        try:
            if not HYDRA_IP or not HYDRA_API_KEY:
                await client.edit_message(
                    message.chat.id,
                    msg.id,
                    "NZBHydra not configured. Set HYDRA_IP and HYDRA_API_KEY.",
                )
                return []

            search_url = f"{HYDRA_IP}/api"
            params = {
                "apikey": HYDRA_API_KEY,
                "t": "search",
                "q": query,
                "limit": 50,
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url,
                    params=params,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        await client.edit_message(
                            message.chat.id,
                            msg.id,
                            f"Search failed: Status {response.status}",
                        )
                        return []

                    content = await response.text()
                    root = ET.fromstring(content)
                    items = root.findall(".//item")

                    if not items:
                        await client.edit_message(
                            message.chat.id,
                            msg.id,
                            f"No results for: {query}",
                        )
                        return []

                    sorted_items = sorted(
                        [
                            (
                                int(item.find("size").text)
                                if item.find("size") is not None
                                and item.find("size").text
                                else 0,
                                item,
                            )
                            for item in items[:100]
                        ],
                        reverse=True,
                        key=lambda x: x[0],
                    )

                    results = []
                    result_text = f"NZB Results for: {query}\n\n"

                    for idx, (size_bytes, item) in enumerate(sorted_items[:10], 1):
                        title = (
                            item.find("title").text
                            if item.find("title") is not None
                            else "No Title"
                        )
                        download_url = (
                            item.find("link").text
                            if item.find("link") is not None
                            else ""
                        )
                        size = get_readable_file_size(size_bytes)

                        results.append(
                            {
                                "title": title,
                                "size": size,
                                "url": download_url,
                            }
                        )

                        result_text += f"{idx}. {title[:60]}\n   Size: {size}\n\n"

                    buttons = ButtonMaker()
                    for i, r in enumerate(results, 1):
                        if r["url"]:
                            buttons.url_button(f"{i}", r["url"])
                    reply_markup = buttons.build_menu(1)

                    if len(result_text) > 3500:
                        result_text = result_text[:3500] + "\n... (truncated)"

                    await client.edit_message(
                        message.chat.id,
                        msg.id,
                        result_text,
                        reply_markup,
                    )

                    return results

        except Exception as e:
            logger.error(f"NZB search error: {e}")
            await client.edit_message(
                message.chat.id,
                msg.id,
                f"Error: {str(e)}",
            )
            return []


__all__ = ["NZBSearchHandler"]
