import asyncio
import asyncpg
from datetime import datetime, timezone, timedelta

class RainStatsRecorder:
    """
    Records and manages rain event statistics in the database.
    """
    def __init__(self, db_url: str, retention_days: int = 365):
        self.db_url = db_url
        self.retention_days = retention_days
        self.pool = None
        self._cleanup_task = None

    async def start(self):
        """
        Initializes the PostgreSQL connection pool and starts the background cleanup task.
        """
        try:
            print("[Tracker] Connecting to PostgreSQL...")
            self.pool = await asyncpg.create_pool(self.db_url)
            print("[Tracker] Connection established.")
            
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except Exception as e:
            print(f"[Tracker] CRITICAL ERROR connecting to the database: {e}")

    async def stop(self):
        """
        Stops the background cleanup task and closes the connection pool.
        """
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self.pool:
            await self.pool.close()
            print("[Tracker] Connection pool closed.")

    async def record_rain_end(self, scrap_amount: float, user_count: int):
        """
        Records the results of a completed rain event in the database.

        Args:
            scrap_amount (float): Total scrap amount tipped.
            user_count (int): Total number of participants.
        """
        if not self.pool:
            print("[Tracker] Error: Connection pool is not initialized.")
            return
        
        try:
            now_utc = datetime.now(timezone.utc)
            
            async with self.pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO rain_stats (scrap_amount, user_count, end_time)
                    VALUES ($1, $2, $3)
                    ''',
                    scrap_amount, user_count, now_utc
                )
            print(f"[Tracker] Saved stats to DB: {scrap_amount} scrap, {user_count} users")
        except Exception as e:
            print(f"[Tracker] Error saving stats to DB: {e}")

    async def clean_old_stats(self):
        """
        Deletes database records older than the configured retention period.
        """
        if not self.pool:
            return

        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    'DELETE FROM rain_stats WHERE end_time < $1',
                    cutoff_date
                )
            print(f"[Tracker] Database cleanup finished. Result: {result}")
        except Exception as e:
            print(f"[Tracker] Error cleaning up old stats: {e}")

    async def _cleanup_loop(self):
        """
        Background cleanup loop that runs every 24 hours.
        """
        while True:
            await asyncio.sleep(24 * 3600)
            await self.clean_old_stats()