"""Telegraph helper for creating pages"""

import logging
from typing import Optional

logger = logging.getLogger("wzml.telegraph")


class TelegraphHelper:
    """Helper for creating Telegraph pages"""

    def __init__(self, author_name: str = None, author_url: str = None):
        self.author_name = author_name or "WZML-X Bot"
        self.author_url = author_url or "https://github.com"
        self._access_token = None

    async def create_account(self) -> bool:
        """Create a Telegraph account"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.telegraph.org/api/account/create",
                    data={
                        "short_name": "WZML-X",
                        "author_name": self.author_name,
                        "author_url": self.author_url,
                    },
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._access_token = data.get("access_token")
                        return True
        except Exception as e:
            logger.error(f"Failed to create Telegraph account: {e}")
        return False

    async def create_page(
        self, title: str, content: str, author_name: str = None, author_url: str = None
    ) -> Optional[dict]:
        """Create a Telegraph page"""
        try:
            import aiohttp

            if not self._access_token:
                await self.create_account()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.telegraph.org/api/page/create",
                    data={
                        "access_token": self._access_token,
                        "title": title,
                        "author_name": author_name or self.author_name,
                        "author_url": author_url or self.author_url,
                        "content": content,
                    },
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Created Telegraph page: {title}")
                        return data.get("result", {})
        except Exception as e:
            logger.error(f"Failed to create Telegraph page: {e}")
        return None

    async def edit_page(
        self,
        path: str,
        title: str,
        content: str,
        author_name: str = None,
        author_url: str = None,
    ) -> Optional[dict]:
        """Edit a Telegraph page"""
        try:
            import aiohttp

            if not self._access_token:
                await self.create_account()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.telegraph.org/api/page/edit",
                    data={
                        "access_token": self._access_token,
                        "path": path,
                        "title": title,
                        "author_name": author_name or self.author_name,
                        "author_url": author_url or self.author_url,
                        "content": content,
                    },
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Edited Telegraph page: {path}")
                        return data.get("result", {})
        except Exception as e:
            logger.error(f"Failed to edit Telegraph page: {e}")
        return None

    async def get_page(self, path: str) -> Optional[dict]:
        """Get a Telegraph page"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.telegraph.org/api/page/get?path={path}"
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("result", {})
        except Exception as e:
            logger.error(f"Failed to get Telegraph page: {e}")
        return None


_telegraph: Optional[TelegraphHelper] = None


def get_telegraph() -> TelegraphHelper:
    """Get or create Telegraph helper"""
    global _telegraph
    if _telegraph is None:
        _telegraph = TelegraphHelper()
    return _telegraph


async def create_telegraph_page(title: str, content: str) -> Optional[str]:
    """Create a Telegraph page and return URL"""
    telegraph = get_telegraph()
    result = await telegraph.create_page(title, content)
    if result:
        return f"https://telegra.ph/{result.get('path', '')}"
    return None


async def edit_telegraph_page(path: str, title: str, content: str) -> bool:
    """Edit a Telegraph page"""
    telegraph = get_telegraph()
    result = await telegraph.edit_page(path, title, content)
    return result is not None


__all__ = [
    "TelegraphHelper",
    "get_telegraph",
    "create_telegraph_page",
    "edit_telegraph_page",
]
