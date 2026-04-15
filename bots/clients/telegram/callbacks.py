"""Telegram callback query handlers"""

import logging
import re
from typing import Any, Callable, Dict, Optional

try:
    import pyrogram
    from pyrogram import Client, types
except ImportError:
    raise ImportError("pyrogram required: pip install pyrotgfork")

logger = logging.getLogger("wzml.callbacks")

_callback_handlers: Dict[str, Callable] = {}


def callback_handler(pattern: str):
    """Decorator to register callback handlers"""

    def decorator(func: Callable):
        _callback_handlers[pattern] = func
        return func

    return decorator


@callback_handler(r"^status(?P<page>\d+)?$")
async def status_pages(client: Client, callback: types.CallbackQuery):
    """Handle status pagination"""
    try:
        match = re.match(r"^status(\d+)?$", callback.data)
        page = int(match.group(1)) if match and match.group(1) else 1

        from bots.clients.telegram.handlers.status import StatusHandler

        handler = StatusHandler()
        # Default to all tasks for now, unless we encode user_id in callback data later
        msg, reply_markup = await handler.get_status_message(
            user_filter=None, page=page
        )

        if not msg:
            await callback.answer("No active tasks!", show_alert=True)
            await callback.message.delete()
            return

        import pyrogram

        await callback.message.edit_text(
            msg, reply_markup=reply_markup, parse_mode=pyrogram.enums.ParseMode.HTML
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Status callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^status_refresh$")
async def status_refresh(client: Client, callback: types.CallbackQuery):
    """Refresh status on current page"""
    try:
        from bots.clients.telegram.handlers.status import StatusHandler

        handler = StatusHandler()
        # Simplified: just request page 1
        msg, reply_markup = await handler.get_status_message(user_filter=None, page=1)

        if not msg:
            await callback.answer("No active tasks!", show_alert=True)
            await callback.message.delete()
            return

        import pyrogram

        await callback.message.edit_text(
            msg, reply_markup=reply_markup, parse_mode=pyrogram.enums.ParseMode.HTML
        )
        await callback.answer()
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Status refresh error: {e}")
        await callback.answer()


@callback_handler(r"^stats(?P<page>\d+)?$")
async def stats_pages(client: Client, callback: types.CallbackQuery):
    """Handle stats pagination"""
    try:
        await callback.answer()
        await callback.message.edit_text("Statistics\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"Stats callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^log(?P<page>\d+)?$")
async def log_cb(client: Client, callback: types.CallbackQuery):
    """Handle log pagination"""
    try:
        await callback.answer()
        await callback.message.edit_text("Log Viewer\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"Log callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^start(?P<action>\w+)?$")
async def start_cb(client: Client, callback: types.CallbackQuery):
    """Handle start menu callbacks"""
    try:
        action = (
            callback.data.replace("start_", "")
            if callback.data.startswith("start_")
            else None
        )

        await callback.answer()
        if action == "mirror":
            await callback.message.edit_text("Use /mirror to start mirroring")
        elif action == "search":
            await callback.message.edit_text("Use /search to search files")
        else:
            await callback.message.edit_text("Welcome to WZML-X!")
    except Exception as e:
        logger.error(f"Start callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^botset(?P<action>\w+)?$")
async def edit_bot_settings(client: Client, callback: types.CallbackQuery):
    """Handle bot settings callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text("Bot Settings\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"Bot settings callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^userset(?P<user_id>\d+)?$")
async def edit_user_settings(client: Client, callback: types.CallbackQuery):
    """Handle user settings callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "User Settings\n\n-- implementation pending --"
        )
    except Exception as e:
        logger.error(f"User settings callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^canall$")
async def cancel_all_update(client: Client, callback: types.CallbackQuery):
    """Handle cancel all confirmation"""
    try:
        from core.task import get_tasks, TaskStatus
        from core.queue import get_queue_manager
        import pyrogram

        user_id = callback.from_user.id
        tasks = await get_tasks(user_id=user_id)
        active_tasks = [t for t in tasks if t.is_active]

        if not active_tasks:
            await callback.answer("No active tasks found!", show_alert=True)
            return

        count = 0
        manager = get_queue_manager()
        for task in active_tasks:
            try:
                await manager.cancel(task.id)
                count += 1
            except Exception:
                pass

        await callback.answer(f"Successfully cancelled {count} tasks.", show_alert=True)

        # Refresh status message
        from bots.clients.telegram.handlers.status import StatusHandler

        handler = StatusHandler()
        msg, reply_markup = await handler.get_status_message(user_filter=None, page=1)
        if msg:
            await callback.message.edit_text(
                msg, reply_markup=reply_markup, parse_mode=pyrogram.enums.ParseMode.HTML
            )
        else:
            await callback.message.delete()

    except Exception as e:
        logger.error(f"Cancel all callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^(?:stopm|cancel)\s*(?P<task_id>\w+)?$")
async def cancel_multi(client: Client, callback: types.CallbackQuery):
    """Handle single or multi-task cancellation via inline button"""
    try:
        match = re.match(r"^(?:stopm|cancel)\s*(\w+)?$", callback.data)
        task_id = match.group(1) if match and match.group(1) else None

        if not task_id:
            await callback.answer("Task ID not provided!", show_alert=True)
            return

        from core.task import cancel_task
        from core.queue import get_queue_manager

        try:
            task = await cancel_task(task_id)
            if task:
                await get_queue_manager().cancel(task.id)
                await callback.answer(f"Task cancelled: {task.id[:8]}", show_alert=True)
            else:
                await callback.answer(
                    "Task not found or already completed.", show_alert=True
                )
        except Exception as e:
            logger.error(f"Error cancelling task {task_id}: {e}")
            await callback.answer("Failed to cancel task.", show_alert=True)

    except Exception as e:
        logger.error(f"Cancel multi callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^sel(?P<selection>\w+)?$")
async def confirm_selection(client: Client, callback: types.CallbackQuery):
    """Handle file selection confirmation"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "Selection Confirmed\n\n-- implementation pending --"
        )
    except Exception as e:
        logger.error(f"Selection callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^rss(?P<feed_id>\w+)?$")
async def rss_listener(client: Client, callback: types.CallbackQuery):
    """Handle RSS feed callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text("RSS Feed\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"RSS callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^imdb(?P<movie_id>\w+)?$")
async def imdb_callback(client: Client, callback: types.CallbackQuery):
    """Handle IMDB callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text("IMDB Info\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"IMDB callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^torser(?P<query>\w+)?$")
async def torrent_search_update(client: Client, callback: types.CallbackQuery):
    """Handle torrent search pagination"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "Torrent Search\n\n-- implementation pending --"
        )
    except Exception as e:
        logger.error(f"Torrent search callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^plugins(?P<action>\w+)?$")
async def edit_plugins_menu(client: Client, callback: types.CallbackQuery):
    """Handle plugin menu callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "Plugin Manager\n\n-- implementation pending --"
        )
    except Exception as e:
        logger.error(f"Plugin callback error: {e}")
        await callback.answer("Error", show_alert=True)


async def register_callbacks(client: Client) -> bool:
    """Register all callback query handlers with the client"""
    try:
        for pattern, handler in _callback_handlers.items():
            client.add_handler(
                pyrogram.handlers.CallbackQueryHandler(handler),
                filters=re.compile(pattern),
            )
        logger.info(f"Registered {len(_callback_handlers)} callback handlers")
        return True
    except Exception as e:
        logger.error(f"Failed to register callbacks: {e}")
        return False


async def handle_callback(client: Client, callback: types.CallbackQuery):
    """Route callback query to appropriate handler"""
    data = callback.data

    for pattern, handler in _callback_handlers.items():
        if re.match(pattern, data):
            await handler(client, callback)
            return

    await callback.answer("Unknown action", show_alert=True)


__all__ = [
    "register_callbacks",
    "handle_callback",
    "callback_handler",
    "_callback_handlers",
]
