"""
WZML-X Main Entry Point

Unified entry point that starts:
- Configuration
- Database
- Plugins
- Workers
- API Server
- Telegram Bot
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] - %(message)s",
    datefmt="%d-%b-%y %I:%M:%S %p",
    level=logging.INFO,
)
logger = logging.getLogger("wzml.main")


class WZMLApp:
    def __init__(self):
        self.config = None
        self.db = None
        self.workers = None
        self.api_server = None
        self.bot = None
        self._running = False

    async def start(self):
        logger.info("=" * 50)
        logger.info("WZML-X Starting...")
        logger.info("=" * 50)

        try:
            await self.load_config()
            logger.info("[OK] Configuration loaded")

            await self.connect_database()
            logger.info("[OK] Database connected")

            await self.load_plugins()
            logger.info("[OK] Plugins loaded")

            await self.start_workers()
            logger.info("[OK] Workers started")

            await self.start_api()
            logger.info("[OK] API server started")

            await self.start_bot()
            logger.info("[OK] Telegram bot started")

            self._running = True

            logger.info("=" * 50)
            logger.info("WZML-X Started Successfully!")
            logger.info("=" * 50)
            logger.info(f"API: http://{self.config.telegram.BASE_URL or 'localhost:8080'}")
            logger.info(f"Bot: @{self.config.telegram.BOT_USERNAME or 'Telegram bot'}")

            return True

        except Exception as e:
            logger.error(f"Failed to start: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def load_config(self):
        from config import get_config

        self.config = get_config()
        self.config.load_all()

        if not self.config.telegram.BOT_TOKEN:
            logger.warning("BOT_TOKEN not configured - bot will not start")

    async def connect_database(self):
        if self.config.database.DATABASE_URL:
            try:
                from db.mongodb import connect_db

                await connect_db(self.config.database.DATABASE_URL)
                logger.info("MongoDB connected")
            except Exception as e:
                logger.warning(f"MongoDB not available: {e}")
        else:
            logger.warning("DATABASE_URL not set - using in-memory storage")

    async def load_plugins(self):
        from plugins import get_available_plugins

        plugins = get_available_plugins()
        logger.info(f"Loaded {len(plugins)} plugins")

    async def start_workers(self):
        from core.worker import WorkerPool

        self.workers = WorkerPool(max_workers=self.config.limits.MAX_WORKERS or 4)
        await self.workers.start()
        logger.info(f"Worker pool started with {self.config.limits.MAX_WORKERS or 4} workers")

    async def start_api(self):
        import uvicorn
        from api.main import app

        config = uvicorn.Config(
            app=app,
            host=self.config.limits.API_HOST or "0.0.0.0",
            port=self.config.limits.API_PORT or 8080,
            log_level="info",
        )
        self.api_server = uvicorn.Server(config)
        
        asyncio.create_task(self.api_server.serve())
        logger.info(f"API server starting on {self.config.limits.API_HOST or '0.0.0.0'}:{self.config.limits.API_PORT or 8080}")

    async def start_bot(self):
        if not self.config.telegram.BOT_TOKEN:
            logger.warning("Skipping Telegram bot - no BOT_TOKEN")
            return

        try:
            from bots.telegram.client import BotClient

            self.bot = BotClient(self.config.telegram.BOT_TOKEN)
            await self.bot.start(self.config.telegram.BOT_TOKEN)
            logger.info("Telegram bot started")
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")

    async def stop(self):
        logger.info("WZML-X Shutting down...")

        self._running = False

        if self.bot:
            await self.bot.stop()
            logger.info("[OK] Bot stopped")

        if self.workers:
            await self.workers.stop()
            logger.info("[OK] Workers stopped")

        logger.info("WZML-X Stopped")

    async def run_forever(self):
        while self._running:
            await asyncio.sleep(1)


_app: Optional[WZMLApp] = None


async def main():
    global _app

    _app = WZMLApp()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        if _app:
            asyncio.create_task(_app.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    success = await _app.start()
    if not success:
        sys.exit(1)

    await _app.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)