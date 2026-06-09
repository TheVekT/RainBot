"""Database configuration fetcher for Discord Bot."""

import logging
import asyncpg

logger = logging.getLogger(__name__)


class DiscordConfigManager:
    """Manager class for retrieving bot settings from PostgreSQL (discord_bot_config table)."""

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        self.pool = db_pool
        self._guild_id: int | None = None
        self._user_stats_retention_days: int = 365

    async def load(self, guild_id: int | None = None) -> bool:
        """Retrieve and cache the configuration for a specific guild or the first available one.

        Returns:
            bool: True if configuration was successfully loaded, False otherwise.
        """
        async with self.pool.acquire() as conn:
            if guild_id:
                row = await conn.fetchrow(
                    """
                    SELECT guild_id, user_stats_retention_days 
                    FROM discord_bot_config 
                    WHERE guild_id = $1
                    """,
                    guild_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT guild_id, user_stats_retention_days 
                    FROM discord_bot_config 
                    LIMIT 1
                    """
                )

            if row:
                self._guild_id = row["guild_id"]
                self._user_stats_retention_days = row["user_stats_retention_days"]
                return True

            logger.warning("[Config] Configuration not found in database!")
            return False

    @property
    def guild_id(self) -> int | None:
        """Returns the loaded Discord Server (Guild) ID."""
        return self._guild_id

    @property
    def user_stats_retention_days(self) -> int:
        """Returns the loaded number of days to retain user stats."""
        return self._user_stats_retention_days