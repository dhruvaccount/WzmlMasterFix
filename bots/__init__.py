"""
WZML-X Bot Clients

Multi-client architecture supporting Telegram, Discord, etc.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BotHandler(ABC):
    """Base handler interface for bot commands"""

    @abstractmethod
    async def handle(self, update: Any, **kwargs) -> Any:
        """Handle a bot command/update"""
        pass


class ClientAdapter(ABC):
    """Base client adapter interface"""

    name: str = ""
    platform: str = ""

    @abstractmethod
    async def start(self) -> bool:
        """Start the client"""
        pass

    @abstractmethod
    async def stop(self) -> bool:
        """Stop the client"""
        pass

    @abstractmethod
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> Optional[Any]:
        """Send a message"""
        pass

    @abstractmethod
    async def send_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str = "",
    ) -> Optional[Any]:
        """Send a photo"""
        pass

    @abstractmethod
    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> Optional[Any]:
        """Edit a message"""
        pass

    @abstractmethod
    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """Delete a message"""
        pass


def get_client(name: str) -> Optional[ClientAdapter]:
    """Get a client by name"""
    from bots.clients import registry

    return registry.get(name)


def register_client(name: str, client: type) -> None:
    """Register a client"""
    from bots.clients import registry

    registry[name] = client


__all__ = [
    "BotHandler",
    "ClientAdapter",
    "get_client",
    "register_client",
    "clients",
]
