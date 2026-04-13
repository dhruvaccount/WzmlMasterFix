"""Search handler (torrent, bypass)"""

import logging
from typing import Any, List

from core.helpers.bypass import bypass_link
from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.clients.telegram.handlers import BotHandler, CommandContext

logger = logging.getLogger("wzml.bot.handlers.search")


class SearchHandler(BotHandler):
    """Handler for search command"""

    async def handle(
        self,
        context: CommandContext,
        client: Any,
    ) -> List[dict]:
        args = self._parse_args(context.text)
        query = args.get("link", "")

        if not query:
            await client.send_message(
                context.chat_id,
                "Send Name along with /search Command!",
            )
            return []

        await client.send_message(
            context.chat_id,
            f"Searching for: {query}",
        )

        try:
            search_results = await bypass_link(query)
            results = search_results if isinstance(search_results, list) else []
        except Exception as e:
            logger.error(f"Search error: {e}")
            results = []

        self._search_results = results

        if not results:
            await client.send_message(context.chat_id, "No Results Found!")
            return []

        result_text = f"Search Results for: {query}\n\n"
        for i, result in enumerate(results[:10], 1):
            name = result.get("name", "N/A")[:50]
            size = result.get("size", "")
            result_text += f"{i}. {name}"
            if size:
                result_text += f" [{size}]"
            result_text += "\n"

        buttons = ButtonMaker()
        for i, result in enumerate(results[:10], 1):
            buttons.data_button(f"{i}", f"select {i}")
        reply_markup = buttons.build_menu(2)

        await client.send_message(context.chat_id, result_text, reply_markup)

        return results

    def _parse_args(self, text: str) -> dict:
        args = {}
        parts = text.split()
        for i, part in enumerate(parts[1:], 1):
            if part.startswith("-"):
                args[part] = True
            else:
                args["link"] = part
        return args


__all__ = ["SearchHandler"]
