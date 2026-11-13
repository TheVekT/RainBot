"""Check planned maintenance is not confused with actual scraper failures."""
import datetime
import time
import unittest
from types import SimpleNamespace

from uptime_observer.scraper.observer import ScraperProbe


class ScraperUptimeTests(unittest.TestCase):
    def setUp(self):
        now = time.monotonic()
        self.parser = SimpleNamespace(
            driver=None, _last_readiness_check=now, _readiness_driver=None,
            _page_ready=True, _state_uncertain=False, _consecutive_errors=0,
            restarting_browser=True, _post_rain_restart_started_at=now,
            last_event_time=datetime.datetime.now(), cooldown_after_rain=1200,
            rain_now=False,
        )
        self.tracker = SimpleNamespace(pool=object())
        self.probe = ScraperProbe(self.parser, self.tracker)

    def run_probe(self):
        # The probe only reads cached fields and performs no asynchronous I/O.
        try:
            self.probe().__await__().send(None)
        except StopIteration as done:
            return done.value
        self.fail('Probe unexpectedly suspended')

    def test_planned_restart_is_up_even_with_closed_browser(self):
        result = self.run_probe()
        self.assertEqual(result.status, 'up')
        self.assertEqual(result.details['browser'], 'restarting')
        self.assertEqual(result.details['chat'], 'unknown')
        self.assertEqual(result.details['maintenance'], 'post_rain_restart')

    def test_new_driver_does_not_reuse_previous_page_readiness(self):
        self.parser.driver = object()
        self.parser.restarting_browser = False
        result = self.run_probe()
        self.assertEqual(result.status, 'up')
        self.assertEqual(result.details['chat'], 'unknown')

    def test_emergency_restart_remains_down(self):
        self.parser._post_rain_restart_started_at = None
        self.assertEqual((self.run_probe()).status, 'down')

    def test_hung_restart_is_down(self):
        self.parser._post_rain_restart_started_at -= 121
        self.assertEqual((self.run_probe()).status, 'down')

    def test_outside_cooldown_is_not_maintenance(self):
        self.parser.last_event_time -= datetime.timedelta(seconds=1201)
        self.assertEqual((self.run_probe()).status, 'down')

    def test_active_rain_is_not_maintenance(self):
        self.parser.rain_now = True
        self.assertEqual((self.run_probe()).status, 'down')

    def test_database_or_uncertain_state_not_hidden(self):
        self.tracker.pool = None
        self.assertEqual((self.run_probe()).status, 'degraded')
        self.tracker.pool = object()
        self.parser._state_uncertain = True
        self.assertEqual((self.run_probe()).status, 'degraded')

    def test_fresh_readiness_must_belong_to_current_driver(self):
        self.parser.driver = object()
        self.parser._post_rain_restart_started_at = None
        self.parser.restarting_browser = False
        self.assertEqual((self.run_probe()).status, 'unknown')
        self.parser._readiness_driver = self.parser.driver
        self.assertEqual((self.run_probe()).status, 'up')


if __name__ == '__main__':
    unittest.main()
