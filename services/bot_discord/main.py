"""
Entry point for the Discord Bot service.

Initializes the Discord bot, establishes database connections,
sets up the notification router, voice managers, user statistics tracking,
and starts the gRPC server to listen for orchestrator events.
"""

import asyncio
import logging
import os
import sys

import asyncpg

from bot import RainDiscordBot
from config import DiscordConfigManager
from grpc_server import DiscordServicer, start_grpc_server
from modules.rain_notify.player import RainNotifyPlayer
from modules.rain_notify.router import RainEventRouter
from modules.rain_notify.text_notifier import RainTextNotifier
from modules.voice_core.manager import VoiceManager
from modules.users_stats.database.pg_impl import PostgresPresenceRepository
from modules.users_stats.stats import UserPresenceTracker
from modules.youtube_player import YouTubePlayer
from cogs.music_cog import MusicCog
from rain_notify_config_provider import DatabaseConfigProvider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main asynchronous entry point for the bot and gRPC server."""
    logger.info("Initializing Discord bot service...")

    # 1. Load environment variables
    db_url = os.getenv("DATABASE_URL")
    grpc_port = os.getenv("GRPC_PORT", "50053")
    sounds_dir = os.getenv("SOUNDS_DIR", "./shared_media")
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables!")
        sys.exit(1)
    if not db_url:
        logger.error("Critical: Missing required environment variable DATABASE_URL.")
        sys.exit(1)

    db_pool = None
    presence_tracker = None
    try:
        # 2. Initialize database connection pool
        logger.info("Connecting to PostgreSQL...")
        db_pool = await asyncpg.create_pool(db_url)

        # 3. Fetch configuration from the database
        logger.info("Fetching server configuration from database...")
        config_manager = DiscordConfigManager(db_pool)
        await config_manager.load()
        
        if not config_manager.guild_id:
            logger.error("Critical: No configuration found in the database (discord_bot_config).")
            sys.exit(1)

        if not config_manager.user_stats_retention_days:
            logger.error("Critical: user_stats_retention_days is not configured in the database. Statistics tracking cannot start.")
            sys.exit(1)

        logger.info("Configuration loaded for guild %s.", config_manager.guild_id)

        # 4. Initialize the Discord Bot instance
        bot = RainDiscordBot(bot_token)
        
        # 5. Initialize user statistics tracking
        logger.info("Initializing user presence tracker...")
        presence_repo = PostgresPresenceRepository(db_pool)
        presence_tracker = UserPresenceTracker(
            bot=bot,
            guild_id=config_manager.guild_id,
            repo=presence_repo,
            retention_days=config_manager.user_stats_retention_days
        )

        # 6. Initialize audio and notification components
        config_provider = DatabaseConfigProvider(db_pool, config_manager.guild_id)
        
        voice_manager = VoiceManager(bot)
        notification_player = RainNotifyPlayer(
            bot=bot, 
            voice_manager=voice_manager, 
            sounds_dir=sounds_dir
        )
        text_notifier = RainTextNotifier(bot, config_provider)
        
        youtube_player = YouTubePlayer(bot, voice_manager)
        music_cog = MusicCog(bot, youtube_player)
        bot.add_cog(music_cog)
        
        # 7. Initialize the logic router
        rain_router = RainEventRouter(
            bot=bot,
            player=notification_player,
            text_notifier=text_notifier,
            config_provider=config_provider
        )

        # 8. Initialize gRPC Servicer and connect signals
        servicer = DiscordServicer()
        servicer.on_rain_started.connect(rain_router.handle_rain_start)
        servicer.on_rain_updated.connect(rain_router.handle_rain_update)
        servicer.on_rain_ended.connect(rain_router.handle_rain_end)

        # 9. Run tasks concurrently
        logger.info("Starting gRPC server and Discord bot concurrently...")
        grpc_task = asyncio.create_task(start_grpc_server(servicer, port=grpc_port))
        bot_task = asyncio.create_task(bot.run_async())

        await asyncio.gather(grpc_task, bot_task)

    except asyncio.CancelledError:
        logger.info("Shutdown signal received. Closing connections...")
    except Exception as e:
        logger.exception("An unexpected error occurred during execution: %s", e)
    finally:
        if presence_tracker:
            logger.info("Stopping user presence tracker...")
            await presence_tracker.stop()
        if db_pool:
            logger.info("Closing database connection pool...")
            await db_pool.close()
        logger.info("Service shut down successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user.")