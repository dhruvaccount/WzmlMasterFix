"""
TELEGRAM_COMMANDS - Telegram Bot Command Definitions
"""

TELEGRAM_COMMANDS = {
    "mirror": {
        "description": "Mirror link to cloud",
        "usage": "/mirror [link] -d [folder_name]",
        "flags": "-d: destination, -n: name, -up: upload dest, -z: zip, -e: extract",
    },
    "leech": {
        "description": "Leech link to Telegram",
        "usage": "/leech [link]",
        "flags": "-doc: as document, -med: as media, -sp: split size",
    },
    "ytdl": {
        "description": "YouTube Download",
        "usage": "/ytdl [url]",
        "flags": "-q: quality, -sp: split size",
    },
    "clone": {
        "description": "Clone GDrive files",
        "usage": "/clone [gdrive_link]",
    },
    "cancel": {
        "description": "Cancel a task",
        "usage": "/cancel [task_id]",
    },
    "cancelall": {
        "description": "Cancel all tasks",
        "usage": "/cancelall",
    },
    "status": {
        "description": "Check task status",
        "usage": "/status [task_id]",
    },
    "search": {
        "description": "Search torrents",
        "usage": "/search [query]",
    },
    "rss": {
        "description": "Manage RSS feeds",
        "usage": "/rss add [url], /rss list, /rss delete",
    },
    "stats": {
        "description": "Bot statistics",
        "usage": "/stats",
    },
    "ping": {
        "description": "Ping bot",
        "usage": "/ping",
    },
    "help": {
        "description": "Help menu",
        "usage": "/help [command]",
    },
    "log": {
        "description": "Get bot logs",
        "usage": "/log [-n lines]",
    },
    "restart": {
        "description": "Restart bot",
        "usage": "/restart [bot|services|all]",
    },
    "exec": {
        "description": "Execute shell command",
        "usage": "/exec [command]",
    },
    "shell": {
        "description": "Execute async shell command",
        "usage": "/shell [command]",
    },
    "broadcast": {
        "description": "Broadcast message to all users",
        "usage": "/broadcast [message]",
    },
    "gdcount": {
        "description": "Count GDrive files",
        "usage": "/gdcount [link]",
    },
    "gddelete": {
        "description": "Delete GDrive files",
        "usage": "/gddelete [link]",
    },
    "gdlist": {
        "description": "List GDrive files",
        "usage": "/gdlist [query]",
    },
    "mediainfo": {
        "description": "Get media info",
        "usage": "/mediainfo [reply_to_media]",
    },
    "nzbsearch": {
        "description": "Search NZB",
        "usage": "/nzbsearch [query]",
    },
    "imdb": {
        "description": "Search IMDB",
        "usage": "/imdb [movie_name]",
    },
    "usetting": {
        "description": "User settings",
        "usage": "/usetting [menu|get|set]",
    },
    "bsetting": {
        "description": "Bot settings",
        "usage": "/bsetting [menu]",
    },
}


def get_command_help(command: str) -> dict:
    """Get help for a specific command"""
    return TELEGRAM_COMMANDS.get(command, {})


def get_all_commands() -> dict:
    """Get all commands"""
    return TELEGRAM_COMMANDS


__all__ = ["TELEGRAM_COMMANDS", "get_command_help", "get_all_commands"]
