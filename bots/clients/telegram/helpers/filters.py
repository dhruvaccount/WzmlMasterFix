"""
Telegram-specific filters

Uses pyrogram for user/chat checking.
"""

import asyncio
from typing import Optional, Any


class CustomFilters:
    """Telegram filter helpers - requires pyrogram when used"""

    @staticmethod
    async def is_owner(user_id: int) -> bool:
        from config import get_setting

        owner_id = get_setting("telegram", "OWNER_ID", 0)
        return user_id == owner_id

    @staticmethod
    async def is_sudo(user_id: int) -> bool:
        from config import get_setting

        owner_id = get_setting("telegram", "OWNER_ID", 0)
        if user_id == owner_id:
            return True
        from core.helpers.sudo import is_sudo_user

        return is_sudo_user(user_id)

    @staticmethod
    async def is_authorized(user_id: int) -> bool:
        from config import get_setting

        owner_id = get_setting("telegram", "OWNER_ID", 0)
        if user_id == owner_id:
            return True
        from core.helpers.sudo import is_authorized_user, is_sudo_user

        return is_sudo_user(user_id) or is_authorized_user(user_id)

    @staticmethod
    async def is_admin(chat_id: int, user_id: int) -> bool:
        """Check if user is admin in chat"""
        return False

    @staticmethod
    async def is_group(chat_id: int) -> bool:
        """Check if chat is a group"""
        return False

    @staticmethod
    async def is_private(chat_id: int) -> bool:
        """Check if chat is private"""
        return chat_id > 0


def is_auth(user_id: int) -> bool:
    """Quick sync check for authorization"""
    return asyncio.run(CustomFilters.is_authorized(user_id))


def is_admin(chat_id: int, user_id: int) -> bool:
    return asyncio.run(CustomFilters.is_admin(chat_id, user_id))


def is_group(chat_id: int) -> bool:
    return asyncio.run(CustomFilters.is_group(chat_id))


def is_private(chat_id: int) -> bool:
    return asyncio.run(CustomFilters.is_private(chat_id))


__all__ = ["CustomFilters", "is_auth", "is_admin", "is_group", "is_private"]
