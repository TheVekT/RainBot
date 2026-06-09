import asyncpg
from typing import Any

class ConfigField:
    """
    Live parameter routing queries directly to PostgreSQL using key-value schema.
    """
    def __init__(self, pool: asyncpg.Pool, key_name: str, default: Any) -> None:
        self.pool = pool
        self.key_name = key_name
        self.default = default

    async def get(self) -> Any:
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT value FROM discord_bot_config WHERE key = $1", 
                self.key_name
            )
            return value if value is not None else self.default

    async def set(self, value: Any) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO discord_bot_config (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, self.key_name, str(value))


class DatabaseConfigProvider:
    """
    Production configuration bridge built over existing database connections.
    """
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._retention = ConfigField(pool, "rain_channel_id", None)
        self._voice = ConfigField(pool, "voice_notify_enabled", True)
        self._text = ConfigField(pool, "text_notify_enabled", True)

    @property
    def rain_channel_id(self) -> ConfigField:
        return self._retention

    @property
    def voice_notify_enabled(self) -> ConfigField:
        return self._voice

    @property
    def text_notify_enabled(self) -> ConfigField:
        return self._text