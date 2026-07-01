import asyncpg

class TelegramDB:
    """
    Database interface for managing Telegram user alert settings.
    """
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_user_threshold(self, user_id: int) -> int:
        """
        Retrieves the notification threshold for a user, defaulting to -1.
        
        Args:
            user_id (int): Telegram user ID.
            
        Returns:
            int: The scrap amount threshold.
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT threshold FROM telegram_users WHERE user_id = $1", 
                user_id
            )
            return result if result is not None else -1

    async def set_user_threshold(self, user_id: int, threshold: int):
        """
        Saves or updates the notification threshold for a user.
        
        Args:
            user_id (int): Telegram user ID.
            threshold (int): Minimum scrap amount to notify.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO telegram_users (user_id, threshold)
                VALUES ($1, $2)
                ON CONFLICT (user_id) 
                DO UPDATE SET threshold = EXCLUDED.threshold
                """,
                user_id, threshold
            )

    async def remove_user(self, user_id: int):
        """
        Deletes a user from the database.
        
        Args:
            user_id (int): Telegram user ID.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM telegram_users WHERE user_id = $1", 
                user_id
            )

    async def get_all_users(self) -> list[dict]:
        """
        Retrieves all registered users and their thresholds.
        
        Returns:
            list[dict]: A list of user dictionaries.
        """
        async with self.pool.acquire() as conn:
            records = await conn.fetch("SELECT user_id, threshold FROM telegram_users")
            return [{"user_id": r["user_id"], "threshold": r["threshold"]} for r in records]