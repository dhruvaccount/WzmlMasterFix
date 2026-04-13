"""Telegram client adapter"""

from bots.clients.telegram.client import TelegramClient, get_telegram_client
from bots.clients.telegram.callbacks import register_callbacks

__all__ = ["TelegramClient", "get_telegram_client", "register_callbacks"]
