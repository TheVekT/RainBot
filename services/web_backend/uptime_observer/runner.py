"""Independent HTTP observers for the web site and API."""
import asyncio
import logging
import os

from uptime_observer.api import create_observer as api_observer
from uptime_observer.website import create_observer as website_observer


async def main():
    port = os.getenv('DJANGO_PORT', '8000')
    base = f'http://web-backend:{port}'
    observers = [api_observer(base + '/api/v1/health/'), website_observer(os.getenv('UPTIME_WEBSITE_URL', base + '/users/'))]
    for observer in observers:
        observer.start()
    try:
        await asyncio.Event().wait()
    finally:
        for observer in observers:
            await observer.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
