import re
import asyncio
from typing import Optional
from urllib.parse import urlparse, parse_qs, quote
from urllib.parse import urljoin


async def bypass_link(url: str) -> str:
    if "gofile.io" in url:
        return await gofile_bypass(url)
    elif "terabox.com" in url or "teraboxapp.com" in url:
        return await terabox_bypass(url)
    elif "hubcloud.cfd" in url:
        return await hubcloud_bypass(url)
    elif "directlink.io" in url:
        return await directlink_bypass(url)
    return url


async def gofile_bypass(url: str) -> str:
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                return data.get("directLink", url)
    except Exception:
        return url


async def terabox_bypass(url: str) -> str:
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://hubcloud.cfd/bypass?url={url}") as response:
                data = await response.json()
                return data.get("directLink", url)
    except Exception:
        return url


async def hubcloud_bypass(url: str) -> str:
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                return data.get("directLink", url)
    except Exception:
        return url


async def directlink_bypass(url: str) -> str:
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.text()
                match = re.search(r'href="(https[^"]+)"', data)
                if match:
                    return match.group(1)
        return url
    except Exception:
        return url


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def is_bypass_supported(url: str) -> bool:
    supported_domains = [
        "gofile.io",
        "terabox.com",
        "teraboxapp.com",
        "hubcloud.cfd",
        "directlink.io",
        "1fichier.com",
        "anonfiles.com",
        "mega.nz",
        "mediafire.com",
    ]
    domain = extract_domain(url)
    return any(d in domain for d in supported_domains)
