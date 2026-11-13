"""Map Discord client state onto the shared uptime contract."""

from uptime_common import Observer, ProbeResult
from .adapter import DiscordBotAdapter


def create_observer(bot):
    adapter = DiscordBotAdapter(bot)

    async def probe():
        details = adapter.snapshot()
        if details['gateway'] == 'connected':
            return ProbeResult(status='up', details=details)
        if details['gateway'] == 'ready_unverified':
            return ProbeResult(status='unknown', details=details,
                               reason='Discord gateway connection cannot be verified')
        return ProbeResult(status='down', details=details,
                           reason='Discord gateway is not ready')

    return Observer('discord_bot', probe, interval_seconds=30)
