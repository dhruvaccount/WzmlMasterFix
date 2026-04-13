"""
Core helpers - Generic utilities that don't depend on Telegram/pyrogram

These are platform-agnostic and can be used by any bot client (Telegram, Discord, etc.)
"""

from core.helpers.links_utils import (
    encode_slink,
    decode_slink,
    is_magnet as is_magnet_url,
    is_gdrive_link,
    is_mega_link,
    is_share_link,
    is_rclone_path,
    is_gdrive_id,
    is_magnet,
    is_url,
    is_telegram_link,
)
from core.helpers.bypass import bypass_link, is_bypass_supported
from core.helpers.sudo import (
    is_sudo_user,
    is_authorized_user,
    add_sudo_user,
    remove_sudo_user,
    get_sudo_users,
    add_auth_chat,
    remove_auth_chat,
    get_auth_chats,
)
from core.status_utils import get_readable_file_size, get_readable_time

__all__ = [
    "encode_slink",
    "decode_slink",
    "is_magnet_url",
    "is_gdrive_link",
    "is_mega_link",
    "is_share_link",
    "is_rclone_path",
    "is_gdrive_id",
    "is_magnet",
    "is_url",
    "is_telegram_link",
    "is_bypass_supported",
    "bypass_link",
    "is_sudo_user",
    "is_authorized_user",
    "add_sudo_user",
    "remove_sudo_user",
    "get_sudo_users",
    "add_auth_chat",
    "remove_auth_chat",
    "get_auth_chats",
    "get_readable_file_size",
    "get_readable_time",
]
