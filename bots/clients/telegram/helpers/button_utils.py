"""
Telegram-specific button builder

Uses pyrogram InlineKeyboardButton/InlineKeyboardMarkup
"""

from typing import Any, Optional

TELEGRAM_AVAILABLE = False

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    TELEGRAM_AVAILABLE = True
except ImportError:
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None


class ButtonMaker:
    def __init__(self):
        self.buttons = {
            "default": [],
            "header": [],
            "f_body": [],
            "l_body": [],
            "footer": [],
        }

    def url_button(self, key: str, link: str, position: Optional[str] = None) -> None:
        pos = position if position in self.buttons else "default"
        self._add_button(key, link, pos, is_url=True)

    def data_button(self, key: str, data: str, position: Optional[str] = None) -> None:
        pos = position if position in self.buttons else "default"
        self._add_button(key, data, pos, is_url=False)

    def _add_button(self, key: str, value: str, position: str, is_url: bool) -> None:
        if not TELEGRAM_AVAILABLE:
            return

        button = (
            InlineKeyboardButton(text=key, url=value)
            if is_url
            else InlineKeyboardButton(text=key, callback_data=value)
        )
        self.buttons[position].append(button)

    def build_menu(
        self,
        b_cols: int = 1,
        h_cols: int = 8,
        position: str = "default",
    ) -> Optional[Any]:
        if not TELEGRAM_AVAILABLE:
            return None

        buttons = self.buttons[position]
        if not buttons:
            return None

        rows = [buttons[i : i + b_cols] for i in range(0, len(buttons), b_cols)]
        return InlineKeyboardMarkup(rows)

    def build(self, inline: bool = False) -> Optional[Any]:
        if not TELEGRAM_AVAILABLE:
            return None

        all_buttons = (
            self.buttons["header"]
            + self.buttons["f_body"]
            + self.buttons["default"]
            + self.buttons["l_body"]
            + self.buttons["footer"]
        )

        if not all_buttons:
            return None

        rows = [all_buttons[i : i + 1] for i in range(0, len(all_buttons), 1)]
        return InlineKeyboardMarkup(rows) if inline else all_buttons

    def reset(self) -> None:
        self.__init__()


__all__ = ["ButtonMaker"]
