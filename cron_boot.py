"""
WZML-X Health Check / Cron Boot Script

Pings the API server every 10 minutes to keep it alive.
On failure, retries every 2 seconds.

Can be run standalone: python cron_boot.py
"""

import asyncio
import os
import sys
import logging
import time
from urllib.request import urlopen, URLError
from urllib.error import HTTPError

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] - %(message)s",
    datefmt="%d-%b-%y %I:%M:%S %p",
    level=logging.INFO,
)
logger = logging.getLogger("wzml.cron")


HEALTH_INTERVAL = 600
RETRY_INTERVAL = 2
MAX_RETRIES = 10


async def health_check(url: str) -> bool:
    try:
        response = urlopen(url, timeout=10)
        return response.status == 200
    except (URLError, HTTPError, Exception) as e:
        logger.warning(f"Health check failed: {e}")
        return False


async def wait_for_api(url: str) -> bool:
    logger.info("Waiting for API to become available...")

    for i in range(MAX_RETRIES):
        if await health_check(url):
            logger.info("API is now available!")
            return True

        logger.info(f"Retry {i+1}/{MAX_RETRIES} in {RETRY_INTERVAL}s...")
        await asyncio.sleep(RETRY_INTERVAL)

    logger.error("API did not become available!")
    return False


async def start_health_check():
    logger.info("=" * 50)
    logger.info("WZML-X Health Check Started")
    logger.info("=" * 50)

    try:
        from config import get_config

        config = get_config()
        config.load_all()

        base_url = config.telegram.BASE_URL or os.environ.get("BASE_URL", "")
        
        if not base_url:
            base_url = f"http://localhost:{config.limits.API_PORT or 8080}"
    except Exception as e:
        logger.warning(f"Config error, using defaults: {e}")
        base_url = os.environ.get("BASE_URL", "http://localhost:8080")

    health_url = f"{base_url}/health"
    logger.info(f"Health URL: {health_url}")

    logger.info("Starting health check loop...")

    while True:
        try:
            if await health_check(health_url):
                logger.debug(f"Health OK: {time.strftime('%H:%M:%S')}")
            else:
                logger.warning("Health check failed, waiting for recovery...")
                await wait_for_api(health_url)

        except Exception as e:
            logger.error(f"Health check error: {e}")

        await asyncio.sleep(HEALTH_INTERVAL)


def main():
    try:
        asyncio.run(start_health_check())
    except KeyboardInterrupt:
        logger.info("Health check stopped")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()