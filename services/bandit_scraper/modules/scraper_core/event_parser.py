"""Event-driven rain parser using a serialized Selenium worker."""
import asyncio
import datetime
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from .base_parser import RainParser as BrowserParser
from .browser_cleanup import _is_too_many_open_files
from .event_observer import EventObserver

log = logging.getLogger(__name__)


class RainParser(BrowserParser):
    """Observe the rain widget and restart the browser after each rain."""

    def __init__(self):
        super().__init__()
        self._event_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rain-driver')
        self._worker_ident = None
        self._worker_closed = False
        self._observer = None
        self._observed_driver = None
        self._state_uncertain = False
        self._old_scrap = 0.0
        self._old_users = 0
        self._restart_pending = False
        self._last_recovery_attempt = None
        self.recovery_backoff_seconds = 30.0
        self.recovery_error_threshold = 3
        self._consecutive_errors = 0
        self.readiness_grace_seconds = 180.0
        self.readiness_check_interval = 15.0
        self._readiness_driver = None
        self._readiness_unready_since = None
        self._last_readiness_check = None
        self._page_ready = False

    async def _worker(self, fn, *args):
        def invoke():
            self._worker_ident = threading.get_ident()
            return fn(*args)
        return await asyncio.get_running_loop().run_in_executor(self._event_executor, invoke)

    async def restart_browser(self, *, force=False):
        # Base restart calls close_browsers on this same serialized worker.
        if threading.get_ident() == self._worker_ident:
            return await BrowserParser.restart_browser(self, force=force)
        if self.rain_now and not force:
            return False
        old_restart = self.last_restart_time
        log.info('Browser restart started: %s', 'recovery' if force else 'post-rain or initial')

        def restart():
            asyncio.run(BrowserParser.restart_browser(self, force=True))
            if self.driver:
                try:
                    self.driver.command_executor.client_config.timeout = 15
                    self.driver.set_page_load_timeout(60)
                except Exception as exc:
                    if _is_too_many_open_files(exc):
                        raise
                    log.warning('Could not configure browser command timeout: %s', exc)

        await self._worker(restart)
        succeeded = self.driver is not None and self.last_restart_time != old_restart
        if succeeded:
            self._restart_pending = False
            self._consecutive_errors = 0
            log.info('Browser restart completed')
        else:
            log.warning('Browser restart did not complete; will retry')
        return succeeded

    async def close_browsers(self):
        if threading.get_ident() == self._worker_ident:
            return await BrowserParser.close_browsers(self)
        if not self._worker_closed:
            try:
                await self._worker(lambda: asyncio.run(BrowserParser.close_browsers(self)))
            finally:
                self._worker_closed = True
                self._event_executor.shutdown(wait=False, cancel_futures=True)

    async def _drop_observer(self):
        if self._observer is not None:
            observer, self._observer = self._observer, None
            await self._worker(observer.close)
        self._observed_driver = None

    async def _ensure_observer(self):
        if not self.driver:
            return False
        if self.driver is not self._observed_driver or self._observer is None:
            await self._drop_observer()
            self._observer = await self._worker(EventObserver, self.driver)
            self._observed_driver = self.driver
        return True

    async def _recover_if_needed(self, *, missing_driver=False, reason='driver_error'):
        if not missing_driver and self._consecutive_errors < self.recovery_error_threshold:
            return False
        now = time.monotonic()
        if self._last_recovery_attempt is not None and now - self._last_recovery_attempt < self.recovery_backoff_seconds:
            return False
        self._last_recovery_attempt = now
        if self.rain_now:
            self._state_uncertain = True
        log.warning('Attempting emergency browser recovery: %s', reason)
        await self._drop_observer()
        await self.restart_browser(force=True)
        return True

    def _page_is_ready(self):
        # Silence in chat is not evidence of a failed session.
        return bool(self.driver and self.driver.execute_script("""
          const title = (document.title || '').toLowerCase();
          const host = (location.hostname || '').toLowerCase();
          return document.readyState === 'complete' &&
            (host === 'bandit.camp' || host === 'www.bandit.camp') &&
            !!document.querySelector('.chat-messages, .chat-messages-container') &&
            !title.includes('just a moment') &&
            !document.getElementById('challenge-running') &&
            !document.getElementById('challenge-form');
        """))

    def _read_ready_snapshot(self):
        if not self._page_is_ready():
            return None, False
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        node = soup.find('div', {'class': 'px-4 chat-rain-outer mb-2'})
        return (node.text if node else None), True

    async def _watch_page_readiness(self):
        driver = self.driver
        if driver is None:
            self._readiness_driver = self._readiness_unready_since = self._last_readiness_check = None
            self._page_ready = False
            return
        if driver is not self._readiness_driver:
            self._readiness_driver = driver
            self._readiness_unready_since = self._last_readiness_check = None
            self._page_ready = False
        now = time.monotonic()
        if self._last_readiness_check is not None and now - self._last_readiness_check < self.readiness_check_interval:
            return
        self._last_readiness_check = now
        ready = await self._worker(self._page_is_ready)
        if self.driver is not driver:
            self._readiness_driver = self._readiness_unready_since = self._last_readiness_check = None
            self._page_ready = False
            return
        if ready:
            if not self._page_ready:
                log.info('Page is ready: chat found on %s', self.url)
            self._page_ready = True
            self._readiness_unready_since = None
        elif self._readiness_unready_since is None:
            self._page_ready = False
            self._readiness_unready_since = now
            log.warning('Page is not ready: chat missing, loading or challenge detected')
        elif now - self._readiness_unready_since >= self.readiness_grace_seconds:
            log.warning('Page remained structurally unready; attempting recovery')
            if await self._recover_if_needed(missing_driver=True, reason='structural_unready'):
                self._readiness_driver = self._readiness_unready_since = self._last_readiness_check = None

    async def _accept_snapshot(self, text):
        active = bool(text and 'event' in text.lower())
        if not self.rain_now:
            if not active:
                return
            scrap, users = await self._scrap_check(text), await self._users_check(text)
            self._old_scrap = scrap if scrap is not None else 0.0
            self._old_users = users if users is not None else 0
            self.rain_now = True
            log.info('Rain started: %s scrap, %s users', self._old_scrap, self._old_users)
            self.on_rain_started.emit(self._old_scrap, self._old_users)
            return
        if not active:
            # A challenge or missing chat does not prove the rain ended.
            if not await self._worker(self._page_is_ready):
                self._state_uncertain = True
                return
            self.on_rain_ended.emit(self._old_scrap, self._old_users)
            self.rain_now = False
            self.last_event_time = datetime.datetime.now()
            self._restart_pending = True
            log.info('Rain ended: %s scrap, %s users', self._old_scrap, self._old_users)
            return
        scrap, users = await self._scrap_check(text), await self._users_check(text)
        if scrap is not None and users is not None and (scrap > self._old_scrap or users != self._old_users):
            self.on_rain_updated.emit(scrap, users)
            self._old_scrap, self._old_users = scrap, users

    async def run(self):
        log.info('Event-driven rain parser started')
        try:
            while True:
                try:
                    if not self.rain_now:
                        if self.driver is None:
                            await self._recover_if_needed(missing_driver=True, reason='initial_or_missing_driver')
                        elif self._restart_pending:
                            now = time.monotonic()
                            if self._last_recovery_attempt is None or now - self._last_recovery_attempt >= self.recovery_backoff_seconds:
                                self._last_recovery_attempt = now
                                await self._drop_observer()
                                await self.restart_browser()
                        if self.last_event_time:
                            elapsed = (datetime.datetime.now() - self.last_event_time).total_seconds()
                            if elapsed < self.cooldown_after_rain:
                                await self._drop_observer()
                                await self._watch_page_readiness()
                                await asyncio.sleep(10)
                                continue
                    await self._watch_page_readiness()
                    if not await self._ensure_observer():
                        await self._recover_if_needed(missing_driver=True)
                        await asyncio.sleep(2)
                        continue
                    event = await self._worker(self._observer.next_event)
                    kind = event.get('kind')
                    if kind == 'error':
                        self._consecutive_errors += 1
                    elif kind in ('snapshot', 'heartbeat'):
                        self._consecutive_errors = 0
                    if kind in ('document_reset', 'document_uncertain', 'error'):
                        if self.rain_now:
                            self._state_uncertain = True
                        if kind == 'error':
                            log.warning('Observer error: %s', event.get('message'))
                            await self._recover_if_needed()
                            await asyncio.sleep(1)
                        continue
                    if event.get('dropped', 0):
                        log.warning('Observer lost %s snapshots; resynchronizing', event['dropped'])
                        self._state_uncertain = True
                    if self._state_uncertain:
                        text, ready = await self._worker(self._read_ready_snapshot)
                        if not ready:
                            continue
                        self._state_uncertain = False
                        await self._drop_observer()
                        await self._accept_snapshot(text)
                    elif kind == 'snapshot':
                        text = await self._worker(self._observer.event_text, event)
                        await self._accept_snapshot(text)
                except Exception as exc:
                    if _is_too_many_open_files(exc):
                        raise
                    log.exception('Observer loop error: %s', exc)
                    self._consecutive_errors += 1
                    if self.rain_now:
                        self._state_uncertain = True
                    await self._recover_if_needed()
                    await asyncio.sleep(1)
        finally:
            await self._drop_observer()
