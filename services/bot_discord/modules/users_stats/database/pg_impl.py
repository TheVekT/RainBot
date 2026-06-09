import asyncpg
import logging
from datetime import datetime
from .interface import AbstractPresenceRepository

logger = logging.getLogger(__name__)

class PostgresPresenceRepository(AbstractPresenceRepository):
    """
    PostgreSQL implementation of the presence repository interface using asyncpg.
    Implements multi-level existential caching to maximize polling speed.
    """
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._account_cache = set()

    async def is_account_exist(self, account_id: int) -> bool:
        # Check hot memory cache first
        if account_id in self._account_cache:
            return True

        # Fallback to cold database lookup on cache miss (e.g. after server restart)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM discord_accounts WHERE account_id = $1", 
                account_id
            )
            if row:
                self._account_cache.add(account_id)
                return True
        return False

    async def create_account(self, account_id: int, nickname: str, avatar_url: str, current_status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO discord_accounts (account_id, nickname, avatar_url, current_status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (account_id) DO NOTHING
            """, account_id, nickname, avatar_url, current_status)
        self._account_cache.add(account_id)

    async def update_account_status(self, account_id: int, current_status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE discord_accounts SET current_status = $2 WHERE account_id = $1",
                account_id, current_status
            )

    async def bulk_upsert_accounts(self, accounts: list[tuple]) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO discord_accounts (account_id, nickname, avatar_url, current_status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (account_id) DO UPDATE SET
                    nickname = EXCLUDED.nickname,
                    avatar_url = EXCLUDED.avatar_url,
                    current_status = EXCLUDED.current_status
            """, accounts)
        for acc in accounts:
            self._account_cache.add(acc[0])

    async def save_period(self, account_id: int, state: str, start_time: datetime, end_time: datetime) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO discord_user_presence (account_id, state, start_time, end_time)
                VALUES ($1, $2, $3, $4)
            """, account_id, state, start_time, end_time)

    async def clean_old_records(self, cutoff_date: datetime) -> None:
        async with self.pool.acquire() as conn:
            status = await conn.execute(
                "DELETE FROM discord_user_presence WHERE end_time < $1",
                cutoff_date
            )
        logger.debug(f"[UserStats DB] Cleaned up old records: {status}")

    async def compress_records(self, since: datetime) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch("""
                    SELECT id, account_id, state, start_time, end_time
                    FROM discord_user_presence
                    WHERE start_time >= $1
                    ORDER BY account_id, start_time
                """, since)

                if not rows:
                    return

                merged = []
                prev = None
                ids_to_delete = []

                for r in rows:
                    current = dict(r)
                    ids_to_delete.append(current['id'])

                    if prev and prev['account_id'] == current['account_id'] and prev['state'] == current['state']:
                        gap = (current['start_time'] - prev['end_time']).total_seconds()
                        if gap <= 1:
                            prev['end_time'] = current['end_time']
                            continue
                    if prev:
                        merged.append(prev)
                    prev = current
                
                if prev:
                    merged.append(prev)

                await conn.execute("""
                    DELETE FROM discord_user_presence WHERE id = ANY($1::int[])
                """, ids_to_delete)

                await conn.executemany("""
                    INSERT INTO discord_user_presence (account_id, state, start_time, end_time)
                    VALUES ($1, $2, $3, $4)
                """, [(m['account_id'], m['state'], m['start_time'], m['end_time']) for m in merged])
                
                logger.debug(f"[UserStats DB] Compression complete: compressed {len(ids_to_delete)} rows into {len(merged)}")