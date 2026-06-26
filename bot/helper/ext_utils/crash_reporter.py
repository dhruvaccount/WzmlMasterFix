import json as json_mod
from datetime import datetime
from gzip import compress as gzip_compress
from hashlib import sha256
from hmac import new as hmac_new
from sys import platform
from traceback import format_exception

from httpx import AsyncClient
from pytz import timezone as tz_lookup

from bot import LOGGER, bot_loop
from bot.core.config_manager import Config
from bot.version import get_version

CRASH_REPORT_URL = "https://telemetry.wzmlx.com/api/v1/send-crash-report"
API_KEY = hmac_new(b"wzmlx-crash-report", Config.BOT_TOKEN.encode(), sha256).hexdigest()


def _make_payload(exc_type, exc_value, exc_traceback):
    tz = tz_lookup(Config.TIMEZONE)
    tb_lines = format_exception(exc_type, exc_value, exc_traceback)
    return {
        "version": get_version(),
        "exception": f"{exc_type.__name__}: {exc_value}",
        "traceback": "".join(tb_lines),
        "platform": platform,
        "timestamp": datetime.now(tz).isoformat(),
        "api_key": API_KEY,
    }


def _should_send():
    return bool(CRASH_REPORT_URL) and Config.ENABLE_TELEMETRY


def send_unhandled_exception(exc_type, exc_value, exc_traceback):
    if not _should_send():
        return
    payload = _make_payload(exc_type, exc_value, exc_traceback)
    bot_loop.create_task(_post_report(payload))


def send_async_exception(context):
    if not _should_send():
        return
    exc = context.get("exception")
    if not exc:
        return
    tb = exc.__traceback__
    payload = _make_payload(type(exc), exc, tb)
    message = context.get("message", "")
    if message:
        payload["logs"] = message
    bot_loop.create_task(_post_report(payload))


async def _post_report(payload):
    try:
        encoded = json_mod.dumps(payload).encode()
        headers = {"Authorization": f"Bearer {API_KEY}"}
        if len(encoded) > 0x19000:
            encoded = gzip_compress(encoded)
            headers["Content-Encoding"] = "gzip"
        async with AsyncClient(timeout=15) as client:
            r = await client.post(CRASH_REPORT_URL, content=encoded, headers=headers)
        if r.status_code == 200:
            LOGGER.info("Crash report sent to WZML-X devs")
        else:
            LOGGER.warning(f"Crash report failed: HTTP {r.status_code}")
    except Exception as e:
        LOGGER.warning(f"Crash report failed: {e}")
