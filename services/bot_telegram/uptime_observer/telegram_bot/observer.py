"""Observe the local Telegram process, not end-to-end message delivery."""
from uptime_common import Observer, ProbeResult

from .adapter import TelegramAdapter


class TelegramProbe:
    def __init__(self, adapter):
        self.adapter = adapter

    async def __call__(self):
        details = self.adapter.snapshot()
        if details['application_running'] and details['polling_running']:
            return ProbeResult('up', details)
        if details['application_running']:
            return ProbeResult('degraded', details, 'Telegram polling is not running')
        return ProbeResult('down', details, 'Telegram application is not running')


def create_observer(bot):
    return Observer('telegram_bot', TelegramProbe(TelegramAdapter(bot)), interval_seconds=60,
                    name='Telegram Bot')
