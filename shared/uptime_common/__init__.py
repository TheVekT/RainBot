"""Common, independent uptime observation and PostgreSQL persistence."""
import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import asyncpg

log = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    status: str
    details: dict = field(default_factory=dict)
    reason: str | None = None


class UptimeStore(ABC):
    @abstractmethod
    async def record(self, key, name, interval, result):
        pass

    @abstractmethod
    async def close(self):
        pass


class PostgresUptimeStore(UptimeStore):
    def __init__(self, dsn):
        self.dsn = dsn
        self.connection = None

    async def close(self):
        if self.connection is not None and not self.connection.is_closed():
            await self.connection.close()
        self.connection = None

    async def record(self, key, name, interval, result):
        if self.connection is None or self.connection.is_closed():
            self.connection = await asyncpg.connect(self.dsn, timeout=5)
        conn = self.connection
        now = datetime.now(timezone.utc)
        details = json.dumps(result.details, ensure_ascii=False, sort_keys=True)
        async with conn.transaction():
            component = await conn.fetchrow('''INSERT INTO uptime_component (key, name, poll_interval_seconds)
                VALUES ($1,$2,$3) ON CONFLICT (key) DO UPDATE SET name=EXCLUDED.name,
                poll_interval_seconds=EXCLUDED.poll_interval_seconds RETURNING id''', key, name, interval)
            cid = component['id']
            period = await conn.fetchrow('SELECT * FROM uptime_period WHERE component_id=$1 AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1 FOR UPDATE', cid)
            if period and now - period['last_seen_at'] > timedelta(seconds=interval * 3):
                # No observation is evidence after last_seen_at, including during power loss.
                await conn.execute('UPDATE uptime_period SET ended_at=$1 WHERE id=$2', period['last_seen_at'], period['id'])
                await conn.execute('''INSERT INTO uptime_period (component_id,status,started_at,ended_at,last_seen_at,reason,details)
                    VALUES ($1,'unknown',$2,$3,$3,'No monitoring data','{}'::jsonb)''', cid, period['last_seen_at'], now)
                period = None
            changed = period is None or period['status'] != result.status or period['reason'] != result.reason
            if changed:
                if period:
                    await conn.execute('UPDATE uptime_period SET ended_at=$1 WHERE id=$2', now, period['id'])
                await conn.execute('''INSERT INTO uptime_period (component_id,status,started_at,ended_at,last_seen_at,reason,details)
                    VALUES ($1,$2,$3,NULL,$3,$4,$5::jsonb)''', cid, result.status, now, result.reason, details)
            else:
                await conn.execute('UPDATE uptime_period SET last_seen_at=$1,details=$2::jsonb WHERE id=$3', now, details, period['id'])
            last = await conn.fetchrow('SELECT observed_at,status,details,reason FROM uptime_snapshot WHERE component_id=$1 ORDER BY observed_at DESC LIMIT 1', cid)
            last_details = json.loads(last['details']) if last and isinstance(last['details'], str) else (last['details'] if last else None)
            if changed or not last or last_details != result.details or now-last['observed_at'] >= timedelta(hours=1):
                await conn.execute('''INSERT INTO uptime_snapshot (component_id,observed_at,status,details,reason)
                    VALUES ($1,$2,$3,$4::jsonb,$5)''', cid, now, result.status, details, result.reason)


class Observer:
    def __init__(self, component_key, probe, interval_seconds=30, name=None, store=None):
        self.key, self.probe, self.interval = component_key, probe, interval_seconds
        self.name = name or component_key.replace('_', ' ').title()
        self.store = store or PostgresUptimeStore(os.environ.get('DATABASE_URL'))
        self.task = None

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self._run(), name='uptime-' + self.key)
        return self

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        try:
            await self.store.close()
        except Exception:
            log.exception('Could not close uptime store: %s', self.key)

    async def _run(self):
        while True:
            try:
                try:
                    result = await asyncio.wait_for(self.probe(), timeout=min(self.interval, 10))
                    if result.status not in ('up', 'down', 'degraded', 'unknown'):
                        raise ValueError('invalid uptime status')
                except Exception:
                    log.exception('Uptime probe failed: %s', self.key)
                    result = ProbeResult('unknown', reason='Probe failed')
                await self.store.record(self.key, self.name, self.interval, result)
            except Exception:
                log.exception('Uptime storage failed: %s', self.key)
                try:
                    await self.store.close()
                except Exception:
                    pass
            await asyncio.sleep(self.interval)
