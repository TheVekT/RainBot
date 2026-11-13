"""Lifecycle cleanup for the scraper's browser and its driver processes."""

import asyncio
import logging
import os
import subprocess

import psutil

logger = logging.getLogger(__name__)

def _is_too_many_open_files(e: Exception) -> bool:
    """
    Checks if an exception is caused by file descriptor resource exhaustion ([Errno 24] Too many open files).
    """
    return getattr(e, 'errno', None) == 24 or 'too many open files' in str(e).lower()


class BrowserCleanupMixin:
    """Close driver resources and reap the browser child after each session."""

    async def driver_quit(self):
        """
        Safely quits and cleans up the active browser driver session.
        """
        driver, self.driver = self.driver, None
        if driver is None:
            return

        fatal = None
        def failure(operation, error):
            nonlocal fatal
            logger.warning("Browser cleanup %s failed: %s", operation, error)
            if fatal is None and _is_too_many_open_files(error):
                fatal = error

        # UC launches the browser as a direct subprocess but keeps only its PID.
        # Retain a psutil identity before terminating; wait only for our own child.
        browser = None
        try:
            pid = getattr(driver, 'browser_pid', None)
            if isinstance(pid, int) and pid > 0:
                candidate = psutil.Process(pid)
                if candidate.ppid() == os.getpid():
                    browser = candidate
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception as exc:
            failure('capture browser child', exc)
        if browser is not None:
            self._remember_browser_for_reap(browser)

        def get(obj, name):
            try:
                return getattr(obj, name, None)
            except Exception as exc:
                failure('read '+name, exc)
                return None
        service = get(driver, 'service')
        process = get(service, 'process')
        executor = get(driver, 'command_executor')
        try:
            driver.quit()
        except Exception as exc:
            failure('driver.quit', exc)
        finally:
            # UC.__del__ calls quit again, including os.kill(browser_pid).  Once
            # we have signalled the old browser, avoid signalling a reused PID.
            try:
                driver.browser_pid = None
            except Exception as exc:
                failure('clear browser PID', exc)

        if executor is not None:
            try:
                executor.close()
            except Exception as exc:
                failure('close command executor', exc)

        if process is not None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=3)
                except Exception as exc:
                    failure('kill/wait for driver', exc)
            except Exception as exc:
                failure('wait for driver', exc)
            for name in ('stdin', 'stdout', 'stderr'):
                stream = get(process, name)
                if stream is not None:
                    try:
                        stream.close()
                    except Exception as exc:
                        failure('close driver '+name, exc)
        if fatal is not None:
            raise fatal

    def _remember_browser_for_reap(self, browser):
        # Bound the amount of retained process metadata if a child never exits.
        # Existing entries take precedence; overflow remains visible in logs.
        if len(self._pending_browser_reap) >= 32:
            logger.warning('Browser reap backlog is full; cannot retain another child for retry')
            return
        self._pending_browser_reap.append(browser)

    def _owned_browser_processes(self):
        """Capture descendants before driver shutdown can orphan them."""
        return psutil.Process(os.getpid()).children(recursive=True)

    async def close_browsers(self):
        """Close this scraper's browser tree without touching unrelated browsers."""
        chrome_names = {'chrome', 'chromium', 'chromium-browser', 'google-chrome', 'chromedriver', 'undetected_chromedriver'}
        fatal = None
        # Capture identities while they are still descendants. driver.quit()
        # can orphan grandchildren, so collecting only afterward misses them.
        try:
            children = self._owned_browser_processes()
        except Exception as exc:
            children = []
            if _is_too_many_open_files(exc):
                fatal = exc
            logger.warning('Cannot enumerate owned browser processes: %s', exc)
        try:
            await self.driver_quit()
        except Exception as exc:
            if _is_too_many_open_files(exc):
                fatal = exc
            else:
                logger.warning("Driver cleanup failed: %s", exc)
        try:
            for proc in children:
                try:
                    p_name = proc.name()
                    if p_name:
                        base_name = p_name.lower().replace('.exe', '')
                        if base_name in chrome_names or base_name.startswith('undetected_chro'):
                            proc.kill()
                            logger.debug("Killed leftover browser/driver process PID: %s (%s)", proc.pid, p_name)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                except Exception as e:
                    if _is_too_many_open_files(e):
                        raise
                    logger.warning("Failed to kill process PID %s: %s", getattr(proc, 'pid', 'unknown'), e)
        except Exception as e:
            if fatal is None and _is_too_many_open_files(e):
                fatal = e
            logger.error("Failed to clean up process tree: %s", e)
            
        await asyncio.sleep(2)
        pending, self._pending_browser_reap = self._pending_browser_reap, []
        retry_later = []
        for index, browser in enumerate(pending):
            if index >= 4:
                self._remember_browser_for_reap(browser)
                continue
            retry = False
            try:
                # A psutil Process retains its creation time, guarding PID reuse;
                # confirm it remains our child before attempting to reap it.
                if browser.is_running() and browser.ppid() == os.getpid():
                    browser.wait(timeout=0.1)
            except psutil.TimeoutExpired:
                retry = True
            except psutil.AccessDenied:
                logger.warning('Access denied while reaping browser child; will retry')
                retry = True
            except psutil.NoSuchProcess:
                pass
            except Exception as exc:
                if fatal is None and _is_too_many_open_files(exc):
                    fatal = exc
                    retry = True
                logger.warning("Failed to reap browser subprocess: %s", exc)
            if retry:
                retry_later.append(browser)
        # Put timed-out children behind untried ones, so four slow children
        # cannot starve the rest of the bounded backlog forever.
        for browser in retry_later:
            self._remember_browser_for_reap(browser)
        if fatal is not None:
            raise fatal
