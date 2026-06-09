import asyncpg
from typing import Any

class ConfigField:
    """
    Live parameter routing queries directly to PostgreSQL using Django column-per-setting schema.
    """
    def __init__(self, pool: asyncpg.Pool, guild_id: int, column_name: str, default: Any) -> None:
        self.pool = pool
        self.guild_id = guild_id
        self.column_name = column_name
        self.default = default

    async def get(self) -> Any:
        async with self.pool.acquire() as conn:
            query = f"SELECT {self.column_name} FROM discord_bot_config WHERE guild_id = $1"
            value = await conn.fetchval(query, self.guild_id)
            return value if value is not None else self.default

    async def set(self, value: Any) -> None:
        async with self.pool.acquire() as conn:
            query = f"""
                INSERT INTO discord_bot_config (guild_id, {self.column_name}) 
                VALUES ($1, $2)
                ON CONFLICT (guild_id) 
                DO UPDATE SET {self.column_name} = EXCLUDED.{self.column_name}
            """
            await conn.execute(query, self.guild_id, value)


class DatabaseConfigProvider:
    """
    Production configuration bridge built over existing database connections.
    """
    def __init__(self, pool: asyncpg.Pool, guild_id: int) -> None:
        self._retention = ConfigField(pool, guild_id, "rain_channel_id", None)
        self._voice = ConfigField(pool, guild_id, "voice_notify_enabled", True)
        self._text = ConfigField(pool, guild_id, "text_notify_enabled", True)

    @property
    def rain_channel_id(self) -> ConfigField:
        return self._retention

    @property
    def voice_notify_enabled(self) -> ConfigField:
        return self._voice

    @property
    def text_notify_enabled(self) -> ConfigField:
        return self._text