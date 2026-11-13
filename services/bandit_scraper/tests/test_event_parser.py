"""Focused event-parser tests; no browser, network, database or Docker needed."""

import asyncio
import datetime
import errno
import unittest
from unittest.mock import AsyncMock, patch

from modules.scraper_core import event_parser
from modules.scraper_core.parser import RainParser


class EventParserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.parser = RainParser()
        self.parser.driver = object()
        self.parser._page_is_ready = lambda: True
        self.events = []
        self.parser.on_rain_started.connect(lambda amount, users: self.events.append(('start', amount, users)))
        self.parser.on_rain_updated.connect(lambda amount, users: self.events.append(('update', amount, users)))
        self.parser.on_rain_ended.connect(lambda amount, users: self.events.append(('end', amount, users)))

    async def asyncTearDown(self):
        self.parser._event_executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def rain(amount, users):
        return f'Rakeback Rain {users} event share {amount} from rain tips.'

    async def test_start_update_end_preserves_signals_and_final_values(self):
        p = self.parser
        await p._accept_snapshot(self.rain('12.5', 20))
        await p._accept_snapshot(self.rain('14.5', 22))
        await p._accept_snapshot(None)

        self.assertEqual(self.events, [
            ('start', 12.5, 20), ('update', 14.5, 22), ('end', 14.5, 22)
        ])
        self.assertFalse(p.rain_now)
        self.assertTrue(p._restart_pending)
        self.assertIsNotNone(p.last_event_time)

    async def test_unready_page_does_not_end_rain(self):
        p = self.parser
        await p._accept_snapshot(self.rain('12.5', 20))
        p._page_is_ready = lambda: False
        await p._accept_snapshot(None)

        self.assertEqual(self.events, [('start', 12.5, 20)])
        self.assertTrue(p.rain_now)
        self.assertTrue(p._state_uncertain)
        self.assertFalse(p._restart_pending)

        p._page_is_ready = lambda: True
        await p._accept_snapshot(None)
        self.assertEqual(self.events[-1], ('end', 12.5, 20))
        self.assertTrue(p._restart_pending)

    async def test_one_restart_after_end_and_no_repeated_restart_in_cooldown(self):
        p = self.parser
        await p._accept_snapshot(self.rain('12.5', 20))
        await p._accept_snapshot(None)
        p._watch_page_readiness = AsyncMock()
        sleep_calls = 0

        async def stop_after_two_iterations(_):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls == 2:
                raise asyncio.CancelledError

        async def successful_restart(instance, *, force=False):
            self.assertIs(instance, p)
            self.assertTrue(force)
            instance.driver = object()
            instance.last_restart_time = datetime.datetime.now()

        with patch.object(event_parser.BrowserParser, 'restart_browser', autospec=True,
                          side_effect=successful_restart) as restart, \
             patch.object(event_parser.asyncio, 'sleep', side_effect=stop_after_two_iterations):
            with self.assertRaises(asyncio.CancelledError):
                await p.run()

        self.assertEqual(restart.await_count, 1)
        self.assertFalse(p._restart_pending)
        self.assertEqual(sleep_calls, 2)

    async def test_emfile_during_post_rain_restart_escapes_run(self):
        p = self.parser
        p._restart_pending = True
        p.last_event_time = datetime.datetime.now()
        p._worker = AsyncMock(side_effect=OSError(errno.EMFILE, 'Too many open files'))
        with self.assertRaises(OSError) as caught:
            await p.run()
        self.assertEqual(caught.exception.errno, errno.EMFILE)
        self.assertTrue(p._restart_pending)


if __name__ == '__main__':
    unittest.main()
