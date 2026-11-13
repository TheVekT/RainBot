"""Observe cached parser state without issuing competing browser commands."""
import datetime
import time

from uptime_common import ProbeResult


class ScraperProbe:
    # A hung launch must not remain healthy for an entire cooldown.
    PLANNED_RESTART_GRACE_SECONDS = 120

    def __init__(self, parser, tracker):
        self.parser = parser
        self.tracker = tracker

    async def __call__(self):
        parser = self.parser
        browser = parser.driver is not None
        check = parser._last_readiness_check
        fresh = (check is not None and time.monotonic() - check <= 60
                 and parser._readiness_driver is parser.driver and browser)
        ready = bool(browser and fresh and parser._page_ready)
        database = self.tracker.pool is not None
        started = parser._post_rain_restart_started_at
        elapsed = (datetime.datetime.now() - parser.last_event_time).total_seconds() if parser.last_event_time else None
        maintenance = (started is not None and 0 <= time.monotonic() - started <= self.PLANNED_RESTART_GRACE_SECONDS
                       and elapsed is not None and 0 <= elapsed < parser.cooldown_after_rain and not parser.rain_now)
        details = {
            'browser': ('restarting' if parser.restarting_browser else
                        ('starting' if maintenance else ('ready' if browser else 'unavailable'))),
            'chat': 'unknown' if parser.restarting_browser or maintenance else ('ready' if ready else ('unknown' if not fresh else 'unavailable')),
            'database': 'pool_initialized' if database else 'unavailable',
            'state': 'uncertain' if parser._state_uncertain else 'normal',
            'restarting': bool(parser.restarting_browser),
        }
        if maintenance:
            details['maintenance'] = 'post_rain_restart'
            if not database or parser._state_uncertain or parser._consecutive_errors:
                return ProbeResult(status='degraded', details=details, reason='scraper state or statistics storage is impaired')
            return ProbeResult(status='up', details=details)
        if not browser or parser.restarting_browser:
            return ProbeResult(status='down', details=details, reason='browser unavailable or restarting')
        if not fresh:
            return ProbeResult(status='unknown', details=details, reason='page readiness check is stale')
        if not ready:
            return ProbeResult(status='down', details=details, reason='chat is not ready')
        if not database or parser._state_uncertain or parser._consecutive_errors:
            return ProbeResult(status='degraded', details=details, reason='scraper state or statistics storage is impaired')
        return ProbeResult(status='up', details=details)
