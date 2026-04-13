"""
Service plugins for WZML-X

These are external service integrations (IMDB, Speedtest, Telegraph, etc.)
Can be loaded dynamically and swapped.
"""

from plugins.services.telegraph import (
    TelegraphHelper,
    get_telegraph,
    create_telegraph_page,
    edit_telegraph_page,
)
from plugins.services.imdb import (
    search_title,
    get_movie,
    IMDB_GENRE_EMOJI,
)

__all__ = [
    "TelegraphHelper",
    "get_telegraph",
    "create_telegraph_page",
    "edit_telegraph_page",
    "search_title",
    "get_movie",
    "IMDB_GENRE_EMOJI",
]
