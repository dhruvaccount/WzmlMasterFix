"""Telegram client using split handlers"""

import logging
import asyncio
import json
import websockets
from typing import Any, Callable, Dict, Optional

try:
    import pyrogram
    from pyrogram import Client, types
except ImportError:
    raise ImportError("pyrogram required: pip install pyrotgfork")

from config import get_config
from bots.base import ClientAdapter
from bots.clients.telegram.handlers import BotHandler

logger = logging.getLogger("wzml.telegram.client")


_status_handler_instance = None

def get_status_handler():
    return _status_handler_instance

class TelegramClient(ClientAdapter):
    """Telegram client adapter using split handlers"""

    name = "telegram"
    platform = "telegram"

    def __init__(self, bot_token: str = None):
        self.bot_token = bot_token
        self._bot: Optional[Client] = None
        self._running = False
        self._handlers: Dict[str, Callable] = {}
        self._callback_handlers: Dict[str, Callable] = {}

        self._search_results = {}
        self._rss_feeds = {}
        self._gdrive_search_results = {}

    async def start(self, bot_token: str = None) -> bool:
        token = bot_token or self.bot_token
        if not token:
            raise ValueError("No bot token")

        from config import get_config
        from config import ALL_CONFIGS

        cfg = get_config()

        logger.info(
            f"Connecting to Telegram with API={cfg.telegram.API}, HASH={cfg.telegram.HASH[:10]}..."
        )

        self._bot = pyrogram.Client(
            name="wzml_bot",
            api_id=cfg.telegram.API,
            api_hash=cfg.telegram.HASH,
            bot_token=token,
        )
        await self._bot.start()

        from bots.clients.telegram.helpers.message_utils import set_telegram_client
        from bots.clients.telegram.callbacks import register_callbacks

        set_telegram_client(self._bot)

        me = await self._bot.get_me()
        logger.info(f"Bot started: @{me.username}")

        self._register_handlers()
        await self._register_pyrogram_handlers()
        await register_callbacks(self._bot)

        self._running = True
        logger.info(f"Telegram client initialized with {len(self._handlers)} handlers")
        
        import asyncio
        self._ws_task = asyncio.create_task(self.listen_to_ws())

        return True

    async def listen_to_ws(self):
        cfg = get_config()
        host = cfg.limits.API_HOST if cfg.limits.API_HOST != "0.0.0.0" else "127.0.0.1"
        uri = f"ws://{host}:{cfg.limits.API_PORT}/api/status/ws"
        while self._running:
            try:
                async with websockets.connect(uri) as ws:
                    logger.info("Connected to core API websocket EventBus")
                    async for message in ws:
                        event = json.loads(message)
                        await self._dispatch_ws_event(event)
            except Exception as e:
                logger.error(f"WS disconnected: {e}")
                await asyncio.sleep(3) # reconnect backoff

    async def _dispatch_ws_event(self, event):
        # Update matching status messages directly from RAM/cache mapping
        from bots.clients.telegram.client import get_status_handler
        status_handler = get_status_handler()
        if status_handler:
            await status_handler.handle_ws_event(self._bot, event)

    async def stop(self) -> bool:
        if self._bot:
            await self._bot.stop()
        self._running = False
        if hasattr(self, "_ws_task"):
            self._ws_task.cancel()
        logger.info("Telegram client stopped")
        return True

    def _register_handlers(self):
        """Register all handlers"""
        from bots.clients.telegram.handlers.mirror import (
            MirrorHandler,
            YtdlpHandler,
            CloneHandler,
            CancelHandler,
            CancelAllHandler,
        )
        from bots.clients.telegram.handlers.status import StatusHandler
        from bots.clients.telegram.handlers.search import SearchHandler
        from bots.clients.telegram.handlers.rss import RSSHandler
        from bots.clients.telegram.handlers.gdrive import (
            GDriveCountHandler,
            GDriveDeleteHandler,
            GDriveListHandler,
        )
        from bots.clients.telegram.handlers.mediainfo import MediaInfoHandler
        from bots.clients.telegram.handlers.nzb import NZBSearchHandler
        from bots.clients.telegram.handlers.system import (
            PingHandler,
            StatsHandler,
            LogHandler,
            RestartHandler,
            ExecHandler,
            ShellHandler,
            BroadcastHandler,
        )
        from bots.clients.telegram.handlers.settings import (
            UserSettingsHandler,
            BotSettingsHandler,
            ServicesHandler,
            IMDBHandler,
            HelpHandler,
        )

        mirror = MirrorHandler()
        ytdlp = YtdlpHandler()
        clone = CloneHandler()
        cancel = CancelHandler()
        cancel_all = CancelAllHandler()
        status = StatusHandler()
        
        global _status_handler_instance
        _status_handler_instance = status
        
        search = SearchHandler()
        rss = RSSHandler()
        gdrive_count = GDriveCountHandler()
        gdrive_delete = GDriveDeleteHandler()
        gdrive_list = GDriveListHandler()
        mediainfo = MediaInfoHandler()
        nzb = NZBSearchHandler()
        ping = PingHandler()
        stats = StatsHandler()
        log = LogHandler()
        restart = RestartHandler()
        exec_cmd = ExecHandler()
        shell = ShellHandler()
        broadcast = BroadcastHandler()
        user_settings = UserSettingsHandler()
        bot_settings = BotSettingsHandler()
        services = ServicesHandler()
        imdb = IMDBHandler()
        help_cmd = HelpHandler()

        self._handlers = {
            "start": lambda c, c2: help_cmd.handle(c, c2),
            "mirror": mirror.handle,
            "leech": lambda c, c2: mirror.handle(c, c2, is_leech=True),
            "qb_mirror": lambda c, c2: mirror.handle(c, c2, is_qbit=True),
            "qb_leech": lambda c, c2: mirror.handle(c, c2, is_leech=True, is_qbit=True),
            "jd_mirror": lambda c, c2: mirror.handle(c, c2, is_jd=True),
            "jd_leech": lambda c, c2: mirror.handle(c, c2, is_leech=True, is_jd=True),
            "nzb_mirror": lambda c, c2: mirror.handle(c, c2, is_nzb=True),
            "nzb_leech": lambda c, c2: mirror.handle(c, c2, is_leech=True, is_nzb=True),
            "ytdl": ytdlp.handle,
            "ytdl_leech": lambda c, c2: ytdlp.handle(c, c2, is_leech=True),
            "clone": clone.handle,
            "cancel": cancel.handle,
            "cancelall": cancel_all.handle,
            "status": status.handle,
            "search": search.handle,
            "rss": rss.handle,
            "gdcount": gdrive_count.handle,
            "gddelete": gdrive_delete.handle,
            "gdlist": gdrive_list.handle,
            "mediainfo": mediainfo.handle,
            "nzbsearch": nzb.handle,
            "ping": ping.handle,
            "stats": stats.handle,
            "log": log.handle,
            "restart": restart.handle,
            "exec": lambda c, c2: exec_cmd.handle(c, c2, is_async=False),
            "aexec": lambda c, c2: exec_cmd.handle(c, c2, is_async=True),
            "shell": shell.handle,
            "broadcast": broadcast.handle,
            "usetting": user_settings.handle,
            "bsetting": bot_settings.handle,
            "services": services.handle,
            "imdb": imdb.handle,
            "help": help_cmd.handle,
        }

    async def _register_pyrogram_handlers(self):
        """Register message handlers with pyrogram client"""
        import re
        from pyrogram import filters

        commands = list(self._handlers.keys())
        logger.info(f"Registering commands: {commands}")

        @self._bot.on_message(filters.command(commands) & filters.private)
        async def handle_message(client, message):
            logger.info(f"Received message: {message.text}")
            command = message.command[0].lower() if message.command else ""
            logger.info(f"Command: {command}")

            from bots.clients.telegram.helpers.filters import CustomFilters

            user_id = message.from_user.id if message.from_user else 0
            
            if not await CustomFilters.is_authorized(user_id):
                logger.warning(f"Unauthorized user {user_id}")
                await message.reply("Unauthorized")
                return

            if command in self._handlers:
                try:
                    await self._handlers[command](self._bot, message)
                    logger.info(f"Handled command: {command}")
                except Exception as e:
                    logger.error(f"Handler error for {command}: {e}")
                    import traceback

                    traceback.print_exc()
            else:
                logger.warning(f"Command {command} not in handlers")

    async def send_message(
        self, chat_id: int, text: str, reply_markup: Any = None, **kwargs
    ) -> Optional[types.Message]:
        if not self._bot:
            return None
        try:
            return await self._bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup, **kwargs
            )
        except Exception as e:
            logger.error(f"Send message error: {e}")
            return None

    async def send_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str = "",
    ) -> Optional[types.Message]:
        if not self._bot:
            return None
        try:
            return await self._bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
            )
        except Exception as e:
            logger.error(f"Send photo error: {e}")
            return None

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Any = None,
        **kwargs,
    ) -> Optional[types.Message]:
        if not self._bot:
            return None
        try:
            return await self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Edit message error: {e}")
            return None

    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        if not self._bot:
            return False
        try:
            await self._bot.delete_messages(
                chat_id=chat_id,
                message_ids=message_id,
            )
            return True
        except Exception as e:
            logger.error(f"Delete message error: {e}")
            return False

    async def download_media(
        self,
        media,
        file_name: str = None,
    ) -> str:
        if not self._bot:
            return None
        try:
            return await self._bot.download_media(media, file_name=file_name)
        except Exception as e:
            logger.error(f"Download media error: {e}")
            return None


_telegram_client: Optional[TelegramClient] = None


async def get_telegram_client(bot_token: str = None) -> TelegramClient:
    """Get or create telegram client"""
    global _telegram_client

    if _telegram_client is None:
        if not bot_token:
            from config import get_config

            config = get_config()
            config.load_all()
            bot_token = config.telegram.BOT_TOKEN

        if not bot_token:
            raise ValueError("No bot token")

        _telegram_client = TelegramClient(bot_token)
        await _telegram_client.start(bot_token)

    return _telegram_client


__all__ = ["TelegramClient", "get_telegram_client"]
