"""Base handler for bot commands"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class CommandContext:
    """Context for command handling"""

    chat_id: int
    user_id: int
    message_id: int = 0
    text: str = ""
    reply_to_message: Any = None
    document: Any = None
    photo: Any = None
    video: Any = None
    audio: Any = None
    query: Any = None


class BotHandler(ABC):
    """Base handler interface"""

    @property
    def name(self) -> str:
        """Handler name"""
        return self.__class__.__name__

    @abstractmethod
    async def handle(self, context: CommandContext, client: Any, **kwargs) -> Any:
        """Handle a command"""
        pass

    async def can_handle(self, context: CommandContext, **kwargs) -> bool:
        """Check if this handler can handle the command"""
        return bool(context.text)


__all__ = ["BotHandler", "CommandContext"]
