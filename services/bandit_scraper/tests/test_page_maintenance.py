import asyncio
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from modules.scraper_core.event_parser import RainParser


class PageMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.parser = RainParser()
        self.parser.driver = Mock()
        self.parser._last_page_load = time.monotonic() - 4201
        self.parser._worker = AsyncMock(side_effect=lambda fn, *args: fn(*args))
        self.parser._drop_observer = AsyncMock()
        self.parser._read_ready_snapshot = Mock(return_value=(None, True))
        self.parser._accept_snapshot = AsyncMock()

    async def asyncTearDown(self):
        self.parser._event_executor.shutdown(wait=True, cancel_futures=True)

    async def test_due_page_is_refreshed_and_timer_reset(self):
        self.assertTrue(await self.parser._refresh_page_if_due())
        self.parser.driver.refresh.assert_called_once()
        self.assertLess(time.monotonic() - self.parser._last_page_load, 5)
        self.assertFalse(await self.parser._refresh_page_if_due())

    async def test_visible_rain_is_accepted_before_refresh(self):
        self.parser._read_ready_snapshot.return_value = ('rain', True)
        async def accept(text):
            self.assertEqual(text, 'rain')
            self.parser.rain_now = True
        self.parser._accept_snapshot.side_effect = accept
        self.assertFalse(await self.parser._refresh_page_if_due())
        self.parser.driver.refresh.assert_not_called()

    async def test_unready_or_uncertain_page_is_not_refreshed(self):
        self.parser._read_ready_snapshot.return_value = (None, False)
        self.assertFalse(await self.parser._refresh_page_if_due())
        self.parser.driver.refresh.assert_not_called()
        self.parser._state_uncertain = True
        self.assertFalse(await self.parser._refresh_page_if_due())

    async def test_failed_refresh_triggers_recovery(self):
        self.parser.driver.refresh.side_effect = RuntimeError('failed')
        self.parser._recover_if_needed = AsyncMock()
        self.assertFalse(await self.parser._refresh_page_if_due())
        self.parser._recover_if_needed.assert_awaited_once_with(missing_driver=True, reason='page_refresh_failed')


if __name__ == '__main__':
    unittest.main()
