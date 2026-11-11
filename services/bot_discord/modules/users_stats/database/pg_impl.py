import asyncpg
import logging
from datetime import datetime
from .interface import AbstractPresenceRepository

logger = logging.getLogger(__name__)


class PostgresPresenceRepository(AbstractPresenceRepository):
    """PostgreSQL presence repository with account/channel existence caches."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._account_cache = set()
        self._channel_cache = set()

    async def is_account_exist(self, account_id: int) -> bool:
        if account_id in self._account_cache:
            return True
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM discord_accounts WHERE account_id = $1", account_id)
            if row:
                self._account_cache.add(account_id)
                return True
        return False

    async def create_account(self, account_id: int, username: str, nickname: str,
                             avatar_url: str, current_status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO discord_accounts (account_id, username, nickname, avatar_url, current_status, is_member)
                VALUES ($1, $2, $3, $4, $5, TRUE)
                ON CONFLICT (account_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    nickname = EXCLUDED.nickname,
                    avatar_url = EXCLUDED.avatar_url,
                    current_status = EXCLUDED.current_status,
                    is_member = TRUE
            """, account_id, username, nickname, avatar_url, current_status)
        self._account_cache.add(account_id)

    async def update_account_status(self, account_id: int, current_status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE discord_accounts SET current_status = $2 WHERE account_id = $1",
                account_id, current_status
            )

    async def set_account_membership(self, account_id: int, is_member: bool) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE discord_accounts SET is_member = $2 WHERE account_id = $1",
                account_id, is_member
            )

    async def reconcile_members(self, member_ids: list[int]) -> None:
        """Mark accounts absent from a verified complete guild snapshot as former members."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE discord_accounts SET is_member = FALSE
                WHERE is_member = TRUE AND NOT (account_id = ANY($1::bigint[]))
            """, member_ids)

    async def bulk_upsert_accounts(self, accounts: list[tuple]) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO discord_accounts (account_id, username, nickname, avatar_url, current_status, is_member)
                VALUES ($1, $2, $3, $4, $5, TRUE)
                ON CONFLICT (account_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    nickname = EXCLUDED.nickname,
                    avatar_url = EXCLUDED.avatar_url,
                    current_status = EXCLUDED.current_status,
                    is_member = TRUE
            """, accounts)
        self._account_cache.update(acc[0] for acc in accounts)

    async def is_channel_exist(self, channel_id: int) -> bool:
        if channel_id in self._channel_cache:
            return True
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM discord_voice_channels WHERE channel_id = $1", channel_id)
            if row:
                self._channel_cache.add(channel_id)
                return True
        return False

    async def create_channel(self, channel_id: int, name: str, is_active: bool) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO discord_voice_channels (channel_id, name, is_active)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id) DO UPDATE SET is_active = EXCLUDED.is_active
            """, channel_id, name, is_active)
        self._channel_cache.add(channel_id)

    async def bulk_upsert_channels(self, channels: list[tuple]) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO discord_voice_channels (channel_id, name, is_active)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    is_active = EXCLUDED.is_active
            """, channels)
        self._channel_cache.update(ch[0] for ch in channels)

    async def reconcile_channels(self, channel_ids: list[int]) -> None:
        """Mark channels absent from a complete guild snapshot as inactive."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE discord_voice_channels SET is_active = FALSE
                WHERE is_active = TRUE AND NOT (channel_id = ANY($1::bigint[]))
            """, channel_ids)

    async def sync_channels(self, channels: list[tuple]) -> None:
        """Atomically apply a complete snapshot, including an empty guild channel list."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if channels:
                    await conn.executemany("""
                        INSERT INTO discord_voice_channels (channel_id, name, is_active)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (channel_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            is_active = EXCLUDED.is_active
                    """, channels)
                await conn.execute("""
                    UPDATE discord_voice_channels SET is_active = FALSE
                    WHERE is_active = TRUE AND NOT (channel_id = ANY($1::bigint[]))
                """, [channel[0] for channel in channels])
        self._channel_cache.update(channel[0] for channel in channels)

    async def save_period(self, account_id: int, state: str, start_time: datetime,
                          end_time: datetime, channel_id: int | None = None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO discord_user_presence (account_id, state, start_time, end_time, channel_id)
                VALUES ($1, $2, $3, $4, $5)
            """, account_id, state, start_time, end_time, channel_id)

    async def bulk_save_periods(self, periods: list[tuple]) -> None:
        """Insert a batch atomically using one connection and one executemany call."""
        if not periods:
            return
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO discord_user_presence (account_id, state, start_time, end_time, channel_id)
                VALUES ($1, $2, $3, $4, $5)
            """, periods)

    async def clean_old_records(self, cutoff_date: datetime) -> None:
        async with self.pool.acquire() as conn:
            status = await conn.execute("DELETE FROM discord_user_presence WHERE end_time < $1", cutoff_date)
        logger.debug("[UserStats DB] Cleaned up old records: %s", status)

    async def compress_records(self, since: datetime) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch("""
                    SELECT id, account_id, state, start_time, end_time, channel_id
                    FROM discord_user_presence
                    WHERE start_time >= $1
                    ORDER BY account_id, start_time
                """, since)
                if not rows:
                    return

                merged, ids_to_delete = [], []
                prev = None
                for row in rows:
                    current = dict(row)
                    ids_to_delete.append(current['id'])
                    if (prev and prev['account_id'] == current['account_id'] and
                            prev['state'] == current['state'] and
                            prev['channel_id'] == current['channel_id'] and
                            (current['start_time'] - prev['end_time']).total_seconds() <= 1):
                        prev['end_time'] = current['end_time']
                        continue
                    if prev:
                        merged.append(prev)
                    prev = current
                if prev:
                    merged.append(prev)

                await conn.execute("DELETE FROM discord_user_presence WHERE id = ANY($1::int[])", ids_to_delete)
                await conn.executemany("""
                    INSERT INTO discord_user_presence (account_id, state, start_time, end_time, channel_id)
                    VALUES ($1, $2, $3, $4, $5)
                """, [(m['account_id'], m['state'], m['start_time'], m['end_time'], m['channel_id']) for m in merged])
                logger.debug("[UserStats DB] Compression complete: compressed %d rows into %d",
                             len(ids_to_delete), len(merged))
