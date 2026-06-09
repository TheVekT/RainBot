import logging
import asyncpg

logger = logging.getLogger(__name__)


class ScraperConfigManager:
    """Manager class for retrieving scraper settings from PostgreSQL (bandit_scraper_config table)."""

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._retention_days: int = 365

    async def load(self) -> bool:
        """Retrieve and cache the configuration fields from the database.

        Returns:
            bool: True if configuration was successfully loaded, False otherwise.
        """
        try:
            conn = await asyncpg.connect(self.db_url)
            try:
                row = await conn.fetchrow(
                    "SELECT rain_stats_retention_days FROM bandit_scraper_config LIMIT 1"
                )
                if row:
                    self._retention_days = row["rain_stats_retention_days"]
                    return True
                
                logger.warning("[Config] Configuration entry not found in database! Using defaults.")
                return False
            finally:
                await conn.close()
        except Exception as e:
            logger.error("[Config] Failed to load configuration from database: %s", e)
            return False

    @property
    def rain_stats_retention_days(self) -> int:
        """Returns the loaded number of days to retain rain statistics."""
        return self._retention_days