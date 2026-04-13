"""RSS handler"""

import logging
from typing import Any, List

from core.task import create_task
from core.queue import enqueue_task
from bots.clients.telegram.helpers.message_utils import arg_parser
from bots.clients.telegram.handlers import BotHandler, CommandContext

logger = logging.getLogger("wzml.bot.handlers.rss")


class RSSHandler(BotHandler):
    """Handler for rss commands"""

    def __init__(self):
        self._feeds = {}

    async def handle(
        self,
        context: CommandContext,
        client: Any,
        action: str = "list",
    ) -> Any:
        args = arg_parser(context.text)
        feed_url = args.get("link", "")

        if action == "add" or action == "addfeed":
            if not feed_url:
                await client.send_message(
                    context.chat_id,
                    "Send RSS Feed URL along with /rss add Command!",
                )
                return None

            if context.user_id not in self._feeds:
                self._feeds[context.user_id] = []

            self._feeds[context.user_id].append(feed_url)

            task = await create_task(
                source=feed_url,
                pipeline_id="rss_gdrive",
                user_id=context.user_id,
            )
            await enqueue_task(task)

            await client.send_message(
                context.chat_id,
                f"RSS Feed Added!\n\n{feed_url}",
            )
            return feed_url

        elif action == "list" or action == "feeds":
            feeds = self._feeds.get(context.user_id, [])
            if feeds:
                feed_text = "Your RSS Feeds:\n\n"
                for i, f in enumerate(feeds, 1):
                    feed_text += f"{i}. {f}\n"
            else:
                feed_text = "No RSS Feeds Added!\n\nUse /rss add <feed_url>"

            await client.send_message(context.chat_id, feed_text)
            return feeds

        elif action == "remove" or action == "rm":
            feeds = self._feeds.get(context.user_id, [])
            if feed_url in feeds:
                feeds.remove(feed_url)
                await client.send_message(
                    context.chat_id,
                    f"Removed: {feed_url}",
                )
            else:
                await client.send_message(context.chat_id, "Feed not found!")
            return feeds

        elif action == "refresh":
            feeds = self._feeds.get(context.user_id, [])
            for url in feeds:
                task = await create_task(
                    source=url,
                    pipeline_id="rss_gdrive",
                    user_id=context.user_id,
                )
                await enqueue_task(task)

            await client.send_message(
                context.chat_id,
                f"Refreshing {len(feeds)} Feeds...",
            )
            return feeds

        return []


__all__ = ["RSSHandler"]
