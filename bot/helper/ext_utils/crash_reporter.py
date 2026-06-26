from collections import deque
from json import dumps as jdumps
from datetime import datetime
from gzip import compress as gzip_compress
from hashlib import sha256
from hmac import new as hmac_new
from logging import Formatter, Handler, getLogger
from sys import platform
from traceback import format_exception

from httpx import AsyncClient
from pytz import timezone as tz_lookup

from bot import LOGGER, bot_loop
from bot.core.config_manager import Config
from bot.version import get_version

CRASH_REPORT_URL = "https://telemetry.wzmlx.com/api/v1/send-crash-report"
API_KEY = hmac_new(b"wzmlx-crash-report", Config.BOT_TOKEN.encode(), sha256).hexdigest()


class _LogCaptureHandler(Handler):
    def __init__(self, capacity=10):
        super().__init__(level=0)
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        self.buffer.append(self.format(record))


_log_handler = _LogCaptureHandler()
_log_handler.setFormatter(
    Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
getLogger().addHandler(_log_handler)


def _make_payload(exc_type, exc_value, exc_traceback):
    tb_lines = format_exception(exc_type, exc_value, exc_traceback)
    return {
        "version": get_version(),
        "exception": f"{exc_type.__name__}: {exc_value}",
        "traceback": "".join(tb_lines),
        "platform": platform,
        "timestamp": datetime.now(tz_lookup(Config.TIMEZONE)).isoformat(),
        "api_key": API_KEY,
    }


def send_unhandled_exception(exc_type, exc_value, exc_traceback):
    if not Config.ENABLE_TELEMETRY:
        return
    payload = _make_payload(exc_type, exc_value, exc_traceback)
    bot_loop.create_task(_post_report(payload))


def send_async_exception(context):
    if not Config.ENABLE_TELEMETRY:
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


async def _upload_logs(log_lines):
    from .telegraph_helper import telegraph
    try:
        html = "<pre>" + "".join(_esc_html(line) + "\n" for line in log_lines) + "</pre>"
        page = await telegraph.create_page(title="Crash Logs", content=html)
        return page["url"]
    except Exception as e:
        LOGGER.warning(f"Failed to create logs page: {e}")
        return None


def _esc_html(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _post_report(payload):
    try:
        recent_logs = list(_log_handler.buffer)
        if recent_logs:
            logs_url = await _upload_logs(recent_logs)
            if logs_url:
                payload["logs_url"] = logs_url
        encoded = jdumps(payload).encode()
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
