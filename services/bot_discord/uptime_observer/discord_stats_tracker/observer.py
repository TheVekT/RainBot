"""Monitor tracker readiness and its required background tasks."""

from uptime_common import Observer, ProbeResult
from .adapter import DiscordStatsAdapter


def create_observer(tracker, bot):
    adapter = DiscordStatsAdapter(tracker, bot)

    async def probe():
        details = adapter.snapshot()
        if details['tracker'] != 'ready':
            return ProbeResult('down', details, 'Tracker is not ready')
        if details['gateway'] != 'ready' or details['guild'] != 'available':
            return ProbeResult('down', details, 'Discord gateway or guild is unavailable')
        if details['background_tasks'] != 'running':
            return ProbeResult('degraded', details, 'Tracker background task stopped')
        # Readiness indicates prerequisites only: queues can still fail to write.
        return ProbeResult('up', details)

    return Observer('discord_stats_tracker', probe, interval_seconds=60)
