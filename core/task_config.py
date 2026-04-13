"""
Modular Task Configuration for WZML-X

Replaces the monolithic TaskConfig from bot/helper/common.py
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TaskConfig:
    """Configuration for a task/mirror/leech operation"""

    message: Any = None
    client: Any = None

    chat_id: int = 0
    user_id: int = 0
    user_dict: dict = field(default_factory=dict)

    link: str = ""
    up_dest: str = ""
    leech_dest: str = ""

    name: str = ""
    folder_name: str = ""
    tag: str = ""

    dir: str = ""
    up_dir: str = ""

    split_size: int = 0
    max_split_size: int = 2097152000

    multi: int = 0
    size: int = 0

    is_leech: bool = False
    is_yt: bool = False
    is_qbit: bool = False
    is_mega: bool = False
    is_nzb: bool = False
    is_jd: bool = False
    is_clone: bool = False
    is_uphoster: bool = False
    is_gdrive: bool = False
    is_rclone: bool = False
    is_ytdlp: bool = False
    is_torrent: bool = False

    extract: bool = False
    compress: bool = False
    select: bool = False
    seed: bool = False
    join: bool = False

    stop_duplicate: bool = False
    sample_video: bool = False
    convert_audio: bool = False
    convert_video: bool = False
    screen_shots: bool = False

    as_doc: bool = False
    as_med: bool = False
    bot_trans: bool = False
    user_trans: bool = False

    user_transmission: bool = False
    hybrid_leech: bool = False
    private_link: bool = False

    thumbnail_layout: str = ""
    thumbnail: str = ""

    ffmpeg_cmds: Optional[list] = None

    metadata_title: str = ""
    metadata_dict: dict = field(default_factory=dict)

    excluded_extensions: list = field(default_factory=list)
    files_to_proceed: list = field(default_factory=list)

    is_cancelled: bool = False
    force_run: bool = False

    mode: tuple = field(default_factory=tuple)

    @property
    def is_premium_user(self) -> bool:
        """Check if user has premium (Telegram)"""
        return getattr(self, "_is_premium_user", False)

    @property
    def max_split_size_effective(self) -> int:
        """Get effective max split size"""
        if self.user_transmission and hasattr(self, "MAX_SPLIT_SIZE"):
            return getattr(self, "MAX_SPLIT_SIZE", 2097152000)
        return 2097152000

    def get_user_setting(self, key: str, default: Any = None) -> Any:
        """Get user setting from user_dict or config"""
        from config import get_setting

        user_val = self.user_dict.get(key)
        if user_val is not None:
            return user_val
        config_val = get_setting("telegram", key)
        if config_val is not None:
            return config_val
        return default

    def get_upload_dest(self) -> str:
        """Get upload destination"""
        if self.is_leech:
            return self.leech_dest or self.get_user_setting("LEECH_DUMP_CHAT", "")
        return self.up_dest or self.get_user_setting("DEFAULT_GDRIVE_ID", "")

    def is_multi(self) -> bool:
        """Check if this is a multi task"""
        return self.multi > 1

    def get_mode_string(self) -> str:
        """Get mode hashtags for status"""
        in_mode = "#TgMedia"
        if self.is_ytdlp:
            in_mode = "#ytdlp"
        elif self.is_qbit:
            in_mode = "#qBit"
        elif self.is_mega:
            in_mode = "#Mega"
        elif self.is_nzb:
            in_mode = "#SABnzbd"
        elif self.is_jd:
            in_mode = "#JDown"
        elif self.is_gdrive:
            in_mode = "#GDrive"
        elif self.is_rclone:
            in_mode = "#RCloneDL"

        out_mode = "#Mirror"
        if self.is_leech:
            out_mode = "#Leech"
        elif self.is_uphoster:
            out_mode = "#UphosterUpload"
        elif self.is_clone:
            out_mode = "#Clone"
        elif self.up_dest:
            if self.up_dest.startswith("rc") or "rclone" in self.up_dest.lower():
                out_mode = "#RClone"
            elif "gdrive" in self.up_dest.lower():
                out_mode = "#GDrive"

        if self.compress:
            out_mode += " (Zip)"
        elif self.extract:
            out_mode += " (Unzip)"

        return f"{in_mode} {out_mode}"

    async def check_token_exists(self, path: str, status: str) -> bool:
        """Check if token exists for GDrive/RClone"""
        from core.helpers.links_utils import is_gdrive_link, is_rclone_path

        if is_rclone_path(path):
            config_path = (
                f"rclone/{self.user_id}.conf" if status == "up" else "rclone.conf"
            )
            from aiofiles.os import path as aiopath

            if not await aiopath.exists(config_path):
                raise ValueError(f"Rclone Config: {config_path} not Exists!")
            return True

        if is_gdrive_link(path) or (
            status == "up" and self.get_user_setting("USER_TOKENS")
        ):
            token_path = "tokens/{self.user_id}.pickle"
            from aiofiles.os import path as aiopath

            if not await aiopath.exists(token_path):
                raise ValueError(f"NO TOKEN! {token_path} not Exists!")
            return True

        return False

    def cancel(self):
        """Mark task as cancelled"""
        self.is_cancelled = True

    def __repr__(self) -> str:
        return (
            f"TaskConfig(chat={self.chat_id}, user={self.user_id}, "
            f"link={self.link[:50] if self.link else ''}, "
            f"is_leech={self.is_leech}, is_clone={self.is_clone})"
        )


__all__ = ["TaskConfig"]
