"""RSS handler"""

import logging
from typing import Any, List

from bots.clients.telegram.helpers.message_utils import arg_parser
from pyrogram import Client, types
from bots.clients.telegram.handlers import BotHandler
from bots.clients.telegram.helpers.message_utils import send_message
from bots.api import api_client

logger = logging.getLogger("wzml.bot.handlers.rss")


class RSSHandler(BotHandler):
    """Handler for rss commands"""

    def __init__(self):
        self._feeds = {}

    async def handle(
        self,
        client: Client,
        message: types.Message,
        action: str = "list",
    ) -> Any:
        args = arg_parser(message.text)
        feed_url = args.get("link", "")

        if action == "add" or action == "addfeed":
            if not feed_url:
                await send_message(
                    message,
                    "Send RSS Feed URL along with /rss add Command!",
                )
                return None

            if message.from_user.id not in self._feeds:
                self._feeds[message.from_user.id] = []

            self._feeds[message.from_user.id].append(feed_url)

            response = await api_client.create_rss(
                feed_url=feed_url,
                user_id=message.from_user.id,
            )

            if "error" in response:
                await send_message(
                    message,
                    f"Failed to add RSS Feed:\n{response['error']}",
                )
                return None

            await send_message(
                message,
                f"RSS Feed Added!\n\n{feed_url}",
            )
            return feed_url

        elif action == "list" or action == "feeds":
            feeds = self._feeds.get(message.from_user.id, [])
            if feeds:
                feed_text = "Your RSS Feeds:\n\n"
                for i, f in enumerate(feeds, 1):
                    feed_text += f"{i}. {f}\n"
            else:
                feed_text = "No RSS Feeds Added!\n\nUse /rss add <feed_url>"

            await send_message(
                message,
                feed_text
            )
            return feeds

        elif action == "remove" or action == "rm":
            feeds = self._feeds.get(message.from_user.id, [])
            if feed_url in feeds:
                feeds.remove(feed_url)
                await send_message(
                    message,
                    f"Removed: {feed_url}",
                )
            else:
                await send_message(
                    message,
                    "Feed not found!"
                )
            return feeds

        elif action == "refresh":
            feeds = self._feeds.get(message.from_user.id, [])
            success_count = 0
            for url in feeds:
                response = await api_client.create_rss(
                    feed_url=url,
                    user_id=message.from_user.id,
                )
                if "error" not in response:
                    success_count += 1

            await send_message(
                message,
                f"Refreshed {success_count}/{len(feeds)} Feeds...",
            )
            return feeds

        return []


__all__ = ["RSSHandler"]
