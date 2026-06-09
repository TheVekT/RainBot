"""
Entry point for the Telegram Bot service.

Initializes the Telegram application, establishes database connections via asyncpg,
sets up gRPC event notification handlers, and runs tasks concurrently inside a single event loop.
"""

import asyncio
import logging
import os
import sys

import asyncpg

from db import TelegramDB
from bot import TelegramBot
from grpc_server import TelegramServicer, start_grpc_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main asynchronous entry point for the bot application and gRPC listener."""
    logger.info("Initializing Telegram bot service...")

    # 1. Load configuration from environment variables
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    db_url = os.getenv("DATABASE_URL")
    grpc_port = os.getenv("GRPC_PORT", "50052")

    if not token:
        logger.error("Critical: TELEGRAM_BOT_TOKEN environment variable is missing!")
        sys.exit(1)

    if not db_url:
        logger.error("Critical: DATABASE_URL environment variable is missing!")
        sys.exit(1)

    db_pool = None
    try:
        # 2. Initialize database connection pool via asyncpg
        logger.info("Connecting to PostgreSQL...")
        db_pool = await asyncpg.create_pool(db_url)
        
        db = TelegramDB(db_pool)

        # 3. Initialize the Telegram Bot instance wrapper
        # Injecting the raw asyncpg pool to decouple from legacy blockings
        tg_bot = TelegramBot(token, db)
        await tg_bot.set_commands()

        # 4. Initialize gRPC Servicer and connect signals to wrapper notification methods
        servicer = TelegramServicer()
        servicer.on_rain_started.connect(tg_bot.broadcast_rain_start)
        servicer.on_rain_updated.connect(tg_bot.broadcast_rain_update)
        servicer.on_rain_ended.connect(tg_bot.broadcast_rain_end)

        # 5. Initialize python-telegram-bot application internals
        await tg_bot.application.initialize()
        await tg_bot.application.start()
        await tg_bot.application.updater.start_polling()
        logger.info("Telegram Bot API polling started successfully.")

        # 6. Run gRPC server and hold the loop concurrently
        logger.info("Starting gRPC server and keeping event loop alive...")
        grpc_task = asyncio.create_task(start_grpc_server(servicer, port=grpc_port))

        # Gather targets to keep them running asynchronously
        await asyncio.gather(grpc_task)

    except asyncio.CancelledError:
        logger.info("Shutdown signal received. Initiating graceful cleanup...")
    except Exception as e:
        logger.exception("A critical error occurred during runtime: %s", e)
    finally:
        # 7. Graceful teardown of all application allocations
        logger.info("Stopping components...")
        if 'tg_bot' in locals():
            await tg_bot.application.updater.stop()
            await tg_bot.application.stop()
            await tg_bot.application.shutdown()
        
        if db_pool:
            logger.info("Closing database connection pool...")
            await db_pool.close()
            
        logger.info("Telegram Bot service shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service execution interrupted by user.")