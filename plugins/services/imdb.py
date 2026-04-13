import asyncio
import logging
from typing import Any, Optional

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

try:
    from imdbinfo import search_title, get_movie
except ImportError:
    search_title = None
    get_movie = None

try:
    import pycountry
except ImportError:
    pycountry = None


logger = logging.getLogger("wzml.imdb")


IMDB_GENRE_EMOJI = {
    "Action": "🚀",
    "Adult": "🔞",
    "Adventure": "🌋",
    "Animation": "🎠",
    "Biography": "📜",
    "Comedy": "🪗",
    "Crime": "🔪",
    "Documentary": "🎞",
    "Drama": "🎭",
    "Family": "👨‍👩‍👧‍👦",
    "Fantasy": "🫧",
    "Film Noir": "🎯",
    "Game Show": "🎮",
    "History": "🏛",
    "Horror": "🧟",
    "Musical": "🎻",
    "Music": "🎸",
    "Mystery": "🧳",
    "News": "📰",
    "Reality-TV": "🖥",
    "Romance": "🥰",
    "Sci-Fi": "🌠",
    "Short": "📝",
    "Sport": "⛳",
    "Talk-Show": "👨‍🍳",
    "Thriller": "🗡",
    "War": "⚔",
    "Western": "🪩",
}

LIST_ITEMS = 4


def list_to_str(k):
    if not k:
        return ""
    elif len(k) == 1:
        return str(k[0])
    elif LIST_ITEMS:
        k = k[: int(LIST_ITEMS)]
        return " ".join(f"{elem}," for elem in k)[:-1] + " ..."
    else:
        return " ".join(f"{elem}," for elem in k)[:-1]


def list_to_hash(items, emoji=False):
    if not items:
        return ""
    if emoji:
        items = [IMDB_GENRE_EMOJI.get(str(item), str(item)) for item in items]
    return ", ".join(str(i) for i in items)


def get_readable_time(seconds):
    if seconds == 0:
        return "0s"
    result = ""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if days > 0:
        result += f"{days}d "
    if hours > 0:
        result += f"{hours}h "
    if minutes > 0:
        result += f"{minutes}m "
    if secs > 0:
        result += f"{secs}s "
    return result.strip() or "0s"


def get_poster(query, bulk=False, id=False, file=None):
    import re
    from re import findall

    if not id:
        query = (query.strip()).lower()
        title = query
        year = findall(r"[1-2]\d{3}$", query, re.IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = findall(r"[1-2]\d{3}", file, re.IGNORECASE)
            if year:
                year = list_to_str(year[:1])
        else:
            year = None
        movieid = search_title(title.lower()).titles
        if not movieid:
            return None
        if year:
            filtered = (
                list(filter(lambda k: str(k.year or "") == str(year), movieid))
                or movieid
            )
        else:
            filtered = movieid
        movieid = (
            list(filter(lambda k: k.kind in ["movie", "tvSeries"], filtered))
            or filtered
        )
        if bulk:
            return movieid
        movieid = movieid[0].id
    else:
        movieid = query
    movie = get_movie(movieid)
    if getattr(movie, "release_date", None):
        date = movie.release_date
    elif getattr(movie, "year", None):
        date = movie.year
    else:
        date = "N/A"

    plot = None
    for keyword in ["plot", "summaries", "synopses"]:
        plot_data = getattr(movie, keyword, None)
        if type(plot_data) is list:
            plot = plot_data[0]
        else:
            plot = plot_data
        if plot:
            break

    if plot and len(plot) > 300:
        plot = f"{plot[:300]}..."

    trailer_list = getattr(movie, "trailers", None)
    trailer = trailer_list[-1] if trailer_list else None

    return {
        "title": movie.title,
        "trailer": trailer or "https://imdb.com/",
        "votes": str(getattr(movie, "votes", "N/A") or "N/A"),
        "aka": list_to_str(getattr(movie, "title_akas", []) or []) or "N/A",
        "seasons": (
            len(movie.info_series.display_seasons)
            if getattr(movie, "info_series", None)
            and getattr(movie.info_series, "display_seasons", None)
            else "N/A"
        ),
        "box_office": getattr(movie, "worldwide_gross", "N/A") or "N/A",
        "localized_title": getattr(movie, "title_localized", "N/A") or "N/A",
        "kind": (getattr(movie, "kind", "N/A") or "N/A").capitalize(),
        "imdb_id": f"tt{movie.imdb_id}",
        "cast": list_to_str([i.name for i in getattr(movie, "stars", [])]) or "N/A",
        "runtime": get_readable_time(int(getattr(movie, "duration", 0) or "0") * 60)
        or "N/A",
        "countries": list_to_hash(getattr(movie, "countries", []) or []) or "N/A",
        "languages": list_to_hash(getattr(movie, "languages_text", []) or []) or "N/A",
        "director": list_to_str([i.name for i in getattr(movie, "directors", [])])
        or "N/A",
        "writer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("writer", [])]
        )
        or "N/A",
        "producer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("producer", [])]
        )
        or "N/A",
        "composer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("composer", [])]
        )
        or "N/A",
        "cinematographer": list_to_str(
            [
                i.name
                for i in getattr(movie, "categories", {}).get("cinematographer", [])
            ]
        )
        or "N/A",
        "music_team": list_to_str(
            [
                i.name
                for i in getattr(movie, "categories", {}).get("music_department", [])
            ]
        )
        or "N/A",
        "release_date": getattr(movie, "release_date", "N/A") or "N/A",
        "year": str(getattr(movie, "year", "N/A") or "N/A"),
        "genres": list_to_hash(getattr(movie, "genres", []) or [], emoji=True) or "N/A",
        "poster": getattr(
            movie, "cover_url", "https://telegra.ph/file/5af8d90a479b0d11df298.jpg"
        )
        or "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
        "plot": plot or "N/A",
        "rating": str(getattr(movie, "rating", "N/A") or "N/A") + " / 10",
        "url": getattr(movie, "url", "N/A") or "N/A",
        "url_cast": f"https://www.imdb.com/title/tt{movieid}/fullcredits#cast",
        "url_releaseinfo": f"https://www.imdb.com/title/tt{movieid}/releaseinfo",
    }


class IMDBHandler:
    def __init__(self, client=None, bot=None):
        self.client = client
        self.bot = bot

    async def search(self, query: str) -> dict:
        import re
        from re import search as re_search

        if re_search(r"tt\d+", query, re.IGNORECASE):
            match = re_search(r"tt(\d+)", query, re.IGNORECASE)
            if match:
                movieid = match.group(1)
                if movie := get_movie(movieid):
                    return await self._format_movie(movie)
                return {}

        movies = get_poster(query, bulk=True)
        if not movies:
            return {}

        results = []
        for movie in movies[:10]:
            results.append(
                {
                    "id": movie.id,
                    "title": getattr(movie, "title", "N/A"),
                    "year": getattr(movie, "year", "N/A"),
                    "kind": getattr(movie, "kind", "N/A"),
                }
            )

        return {"results": results}

    async def _format_movie(self, movie) -> dict:
        return get_poster(str(movie.id))

    async def handle(self, update, query: str = None) -> dict:
        text = query or ""

        if not text or " " not in text:
            if self.client:
                await self.client.send_message(
                    update.chat_id,
                    "Send Movie / TV Series Name along with /imdb Command or send IMDB URL",
                )
            return {}

        try:
            result = await self.search(text.split(" ", 1)[1])
            if not result:
                if self.client:
                    await self.client.send_message(update.chat_id, "No Results Found")
                return {}

            if "results" in result:
                text = "Search Results:\n\n"
                for i, movie in enumerate(result["results"], 1):
                    text += f"{i}. {movie['title']} ({movie['year']})\n"

                if self.client:
                    await self.client.send_message(update.chat_id, text)
                return result

            text = self._format_display(result)

            if self.client:
                await self.client.send_message(update.chat_id, text)
            return result

        except Exception as e:
            logger.error(f"IMDB error: {e}")
            if self.client:
                await self.client.send_message(update.chat_id, f"Error: {e}")
            return {}

    def _format_display(self, movie_data: dict) -> str:
        text = f"""<b>{movie_data.get("title", "N/A")}</b> ({movie_data.get("year", "N/A")})
<b>Rating:</b> {movie_data.get("rating", "N/A")}
<b>Runtime:</b> {movie_data.get("runtime", "N/A")}
<b>Genres:</b> {movie_data.get("genres", "N/A")}
<b>Director:</b> {movie_data.get("director", "N/A")}

<b>Plot:</b> {movie_data.get("plot", "N/A")}

<a href="{movie_data.get("poster", "")}">&#8212;</a>"""
        return text

    async def get_movie_info(self, movie_id: str) -> dict:
        return get_poster(movie_id, id=True)

    async def search_by_title(self, title: str) -> list:
        movies = get_poster(title, bulk=True)
        return [
            {
                "id": m.id,
                "title": getattr(m, "title", "N/A"),
                "year": getattr(m, "year", "N/A"),
                "kind": getattr(m, "kind", "N/A"),
            }
            for m in movies[:10]
        ]


async def create_imdb_handler(client=None, bot=None) -> IMDBHandler:
    return IMDBHandler(client=client, bot=bot)
