import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import asyncpg


class CogConfigField:
    def __init__(
        self,
        pool: asyncpg.Pool,
        guild_id: int,
        cog_name: str,
        field_name: str,
        default: Any
    ) -> None:
        self.pool = pool
        self.guild_id = guild_id
        self.cog_name = cog_name
        self.field_name = field_name
        self.default = default

    async def get(self) -> Any:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT params -> $2::text -> $3::text AS value
                FROM discord_bot_config
                WHERE guild_id = $1
                """,
                self.guild_id,
                self.cog_name,
                self.field_name
            )

        if row is None:
            raise LookupError(
                f"Guild config {self.guild_id} does not exist"
            )

        data = row["value"]

        if data is None:
            return deepcopy(self.default)

        return json.loads(data)

    async def set(self, value: Any) -> None:
        serialized = json.dumps(value)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE discord_bot_config
                SET params = jsonb_set(
                    COALESCE(params, '{}'::jsonb),
                    ARRAY[$2::text],
                    COALESCE(
                        params -> $2::text,
                        '{}'::jsonb
                    ) || jsonb_build_object(
                        $3::text,
                        $4::jsonb
                    ),
                    true
                )
                WHERE guild_id = $1
                RETURNING guild_id
                """,
                self.guild_id,
                self.cog_name,
                self.field_name,
                serialized
            )

        if row is None:
            raise LookupError(
                f"Guild config {self.guild_id} does not exist"
            )


class CogConfigProvider:
    def __init__(
        self,
        pool: asyncpg.Pool,
        guild_id: int
    ) -> None:
        self.pool = pool
        self.guild_id = guild_id

    def register(
        self,
        cog: object,
        fields: dict[str, Any],
        name: str | None = None
    ) -> SimpleNamespace:

        cog_name = name or type(cog).__name__

        if not cog_name:
            raise ValueError("Cog name cannot be empty")

        registered_fields = {}

        for field_name, default in fields.items():
            if not field_name.isidentifier():
                raise ValueError(
                    f"Invalid config field name: {field_name}"
                )

            registered_fields[field_name] = CogConfigField(
                pool=self.pool,
                guild_id=self.guild_id,
                cog_name=cog_name,
                field_name=field_name,
                default=default
            )

        return SimpleNamespace(**registered_fields)