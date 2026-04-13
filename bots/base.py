"""Base client adapter interface"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger("wzml.clientadapter")


class ClientAdapter(ABC):
    """Base class for bot clients (Telegram, Discord, etc.)"""

    name: str = ""
    platform: str = ""

    def __init__(self):
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, *args, **kwargs) -> bool:
        """Start the client"""
        self._running = True
        logger.info(f"{self.name} client started")
        return True

    async def stop(self) -> bool:
        """Stop the client"""
        self._running = False
        logger.info(f"{self.name} client stopped")
        return True

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> Optional[Any]:
        """Send a message - override in subclass"""
        raise NotImplementedError("Subclass must implement send_message")

    async def send_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str = "",
    ) -> Optional[Any]:
        """Send a photo - override in subclass"""
        raise NotImplementedError("Subclass must implement send_photo")

    async def send_video(
        self,
        chat_id: int,
        video: str,
        caption: str = "",
    ) -> Optional[Any]:
        """Send a video"""
        raise NotImplementedError("Subclass must implement send_video")

    async def send_audio(
        self,
        chat_id: int,
        audio: str,
        caption: str = "",
    ) -> Optional[Any]:
        """Send audio"""
        raise NotImplementedError("Subclass must implement send_audio")

    async def send_document(
        self,
        chat_id: int,
        document: str,
        caption: str = "",
    ) -> Optional[Any]:
        """Send document"""
        raise NotImplementedError("Subclass must implement send_document")

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> Optional[Any]:
        """Edit a message - override in subclass"""
        raise NotImplementedError("Subclass must implement edit_message")

    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """Delete a message - override in subclass"""
        raise NotImplementedError("Subclass must implement delete_message")

    async def download_media(
        self,
        media: Any,
        file_name: str = None,
    ) -> Optional[str]:
        """Download media - override in subclass"""
        raise NotImplementedError("Subclass must implement download_media")

    async def forward_message(
        self,
        from_chat_id: int,
        to_chat_id: int,
        message_id: int,
    ) -> Optional[Any]:
        """Forward a message"""
        raise NotImplementedError("Subclass must implement forward_message")

    async def send_media_group(
        self,
        chat_id: int,
        media: list,
    ) -> Optional[list]:
        """Send media group"""
        raise NotImplementedError("Subclass must implement send_media_group")

    async def answer_callback(
        self,
        callback_id: str,
        text: str = "",
        show_alert: bool = False,
    ) -> bool:
        """Answer callback query"""
        raise NotImplementedError("Subclass must implement answer_callback")

    async def get_chat(self, chat_id: int) -> Optional[Any]:
        """Get chat info"""
        raise NotImplementedError("Subclass must implement get_chat")

    async def get_me(self) -> Optional[Any]:
        """Get bot info"""
        raise NotImplementedError("Subclass must implement get_me")

    async def get_user(self, user_id: int) -> Optional[Any]:
        """Get user info"""
        raise NotImplementedError("Subclass must implement get_user")

    async def ban_user(self, chat_id: int, user_id: int) -> bool:
        """Ban user from chat"""
        raise NotImplementedError("Subclass must implement ban_user")

    async def unban_user(self, chat_id: int, user_id: int) -> bool:
        """Unban user from chat"""
        raise NotImplementedError("Subclass must implement unban_user")

    async def kick_user(self, chat_id: int, user_id: int) -> bool:
        """Kick user from chat"""
        return await self.ban_user(chat_id, user_id)

    async def restrict_chat_member(
        self,
        chat_id: int,
        user_id: int,
        permissions: dict,
    ) -> bool:
        """Restrict chat member permissions"""
        raise NotImplementedError("Subclass must implement restrict_chat_member")

    async def promote_chat_member(
        self,
        chat_id: int,
        user_id: int,
        can_change_info: bool = False,
        can_post_messages: bool = False,
        can_edit_messages: bool = False,
        can_delete_messages: bool = False,
        can_invite_users: bool = False,
        can_pin_messages: bool = False,
    ) -> bool:
        """Promote chat member"""
        raise NotImplementedError("Subclass must implement promote_chat_member")

    async def set_chat_title(self, chat_id: int, title: str) -> bool:
        """Set chat title"""
        raise NotImplementedError("Subclass must implement set_chat_title")

    async def set_chat_description(self, chat_id: int, description: str) -> bool:
        """Set chat description"""
        raise NotImplementedError("Subclass must implement set_chat_description")

    async def pin_chat_message(self, chat_id: int, message_id: int) -> bool:
        """Pin chat message"""
        raise NotImplementedError("Subclass must implement pin_chat_message")

    async def unpin_chat_message(self, chat_id: int, message_id: int) -> bool:
        """Unpin chat message"""
        raise NotImplementedError("Subclass must implement unpin_chat_message")

    async def leave_chat(self, chat_id: int) -> bool:
        """Leave chat"""
        raise NotImplementedError("Subclass must implement leave_chat")

    async def get_chat_administrators(self, chat_id: int) -> list:
        """Get chat administrators"""
        raise NotImplementedError("Subclass must implement get_chat_administrators")

    async def get_chat_member(self, chat_id: int, user_id: int) -> Optional[Any]:
        """Get chat member"""
        raise NotImplementedError("Subclass must implement get_chat_member")

    async def get_chat_members_count(self, chat_id: int) -> int:
        """Get chat members count"""
        raise NotImplementedError("Subclass must implement get_chat_members_count")

    async def export_chat_invite_link(self, chat_id: int) -> Optional[str]:
        """Export chat invite link"""
        raise NotImplementedError("Subclass must implement export_chat_invite_link")

    async def create_chat_invite_link(
        self,
        chat_id: int,
        name: str = None,
        expire_date: int = None,
        member_limit: int = None,
    ) -> Optional[str]:
        """Create chat invite link"""
        raise NotImplementedError("Subclass must implement create_chat_invite_link")

    def validate_chat_id(self, chat_id: Any) -> bool:
        """Validate chat ID format"""
        try:
            int(chat_id)
            return True
        except (ValueError, TypeError):
            return False

    def validate_user_id(self, user_id: Any) -> bool:
        """Validate user ID format"""
        try:
            uid = int(user_id)
            return uid > 0
        except (ValueError, TypeError):
            return False

    def format_message_link(self, chat_id: int, message_id: int) -> str:
        """Format message link"""
        return f"https://t.me/c/{chat_id}/{message_id}"

    def format_user_link(self, user_id: int, username: str = None) -> str:
        """Format user mention link"""
        if username:
            return f"@{username}"
        return f"tg://user?id={user_id}"


__all__ = ["ClientAdapter"]
