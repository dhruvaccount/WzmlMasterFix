"""Base handler for bot commands"""

from abc import ABC, abstractmethod
from typing import Any
from pyrogram import Client, types

class BotHandler(ABC):
    """Base handler interface"""

    @property
    def name(self) -> str:
        """Handler name"""
        return self.__class__.__name__

    @abstractmethod
    async def handle(self, client: Client, message: types.Message, **kwargs) -> Any:
        """Handle a command"""
        pass

    async def can_handle(self, client: Client, message: types.Message, **kwargs) -> bool:
        """Check if this handler can handle the command"""
        return bool(message.text)


__all__ = ["BotHandler"]
