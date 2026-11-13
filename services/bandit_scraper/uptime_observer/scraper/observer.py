"""Observe cached parser state without issuing competing browser commands."""
import time

from uptime_common import ProbeResult


class ScraperProbe:
    def __init__(self, parser, tracker):
        self.parser = parser
        self.tracker = tracker

    async def __call__(self):
        parser = self.parser
        browser = parser.driver is not None
        check = parser._last_readiness_check
        fresh = check is not None and time.monotonic() - check <= 60
        ready = bool(browser and fresh and parser._page_ready)
        database = self.tracker.pool is not None
        details = {
            'browser': 'ready' if browser else 'unavailable',
            'chat': 'ready' if ready else ('unknown' if not fresh else 'unavailable'),
            'database': 'pool_initialized' if database else 'unavailable',
            'state': 'uncertain' if parser._state_uncertain else 'normal',
            'restarting': bool(parser.restarting_browser),
        }
        if not browser or parser.restarting_browser:
            return ProbeResult(status='down', details=details, reason='browser unavailable or restarting')
        if not fresh:
            return ProbeResult(status='unknown', details=details, reason='page readiness check is stale')
        if not ready:
            return ProbeResult(status='down', details=details, reason='chat is not ready')
        if not database or parser._state_uncertain or parser._consecutive_errors:
            return ProbeResult(status='degraded', details=details, reason='scraper state or statistics storage is impaired')
        return ProbeResult(status='up', details=details)
