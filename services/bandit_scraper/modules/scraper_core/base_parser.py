import re
import datetime
import asyncio
import os
import shutil
import subprocess
from pathlib import Path
import undetected_chromedriver as uc
import logging

from utils.signal import Signal
from utils.str_to_float import str_to_float

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

from .browser_cleanup import BrowserCleanupMixin, _is_too_many_open_files


class _OwnedChrome(uc.Chrome):
    """Keep a reference to a partially initialized driver for teardown.

    This depends on pinned undetected-chromedriver/Selenium internals and is
    experimental; the container-level EMFILE restart remains the fallback.
    """
    def __init__(self, owner, **kwargs):
        owner.driver = self
        super().__init__(**kwargs)


class RainParser(BrowserCleanupMixin):
    """
    A selenium-based parser for detecting and tracking rain events on bandit.camp.
    
    Exposes signals to notify subscribers when a rain starts, changes, or ends.
    """
    def __init__(self):
        self.driver = None
        self._pending_browser_reap = []
        self.url = 'https://bandit.camp/help'
        
        self.cooldown_after_rain: int = 1200
        
        # State
        self.last_event_time = None
        self.last_restart_time = None
        self.restarting_browser = False
        self.rain_now = False
        
        # Signals
        self.on_rain_started = Signal()
        self.on_rain_updated = Signal()
        self.on_rain_ended = Signal()

    def get_chrome_options(self):
        """
        Creates and returns ChromeOptions for undetected_chromedriver.
        
        Returns:
            ChromeOptions: Configured browser options.
        """
        options = uc.ChromeOptions()
        options.add_argument("--unique-arg")
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-browser-side-navigation')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-extensions')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-plugins')
        options.add_argument("--window-position=0,0")
        options.add_argument("--headless=new")
        
        user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        options.add_argument(f'--user-agent={user_agent}')
        options.add_argument('--accept-language=en-US,en;q=0.9')

        prefs = {"profile.managed_default_content_settings.images": 2}
        options.add_experimental_option("prefs", prefs)

        return options

    def _find_browser_binary(self) -> str | None:
        """
        Looks up typical paths and environment variables to locate the Chrome/Chromium binary.
        
        Returns:
            str | None: The path to the executable, or None if not found.
        """
        env_candidates = (os.getenv("CHROME_BINARY"), os.getenv("CHROMIUM_BINARY"))
        for candidate in env_candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate))

        path_candidates = (
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        )
        for candidate in path_candidates:
            if Path(candidate).is_file():
                return candidate

        return shutil.which("google-chrome") or shutil.which("chromium-browser")

    @staticmethod
    def _browser_major_version(browser_binary: str) -> int | None:
        """Determine the installed browser major without changing its profile.

        If version detection fails, leave driver selection to UC.  EMFILE must
        still escape so Docker's existing restart fallback remains effective.
        """
        try:
            result = subprocess.run([browser_binary, '--version'], capture_output=True,
                                    text=True, timeout=5, check=True)
            match = re.search(r'\b(\d+)\.\d+\.\d+\.\d+\b', result.stdout)
            if match:
                return int(match.group(1))
            logger.warning('Could not determine browser major version from --version output')
        except Exception as exc:
            if _is_too_many_open_files(exc):
                raise
            logger.warning('Could not determine browser major version: %s', exc)
        return None

    async def restart_browser(self, *, force: bool = False):
        """
        Replace the browser session. Scheduling is handled by the event parser.
        """
        if self.rain_now and not force:
            return  # Do not restart browser if a rain is currently in progress!
        
        self.restarting_browser = True
                
        logger.info("Starting browser session...")
        
        try:
            await self.close_browsers()
            options = self.get_chrome_options()
            browser_binary = self._find_browser_binary()
            if not browser_binary:
                raise FileNotFoundError("Chrome/Chromium binary executable not found.")

            options.binary_location = browser_binary
            
            chrome_kwargs = {"options": options}
            version_env = os.getenv("CHROMEDRIVER_VERSION")
            if version_env:
                try:
                    # Extracts major version, e.g. "120.0.6099.109" -> 120
                    major_version = int(version_env.split('.')[0])
                    chrome_kwargs["version_main"] = major_version
                    logger.info("Using chromedriver version_main=%s from environment.", major_version)
                except (ValueError, IndexError):
                    logger.warning("Invalid CHROMEDRIVER_VERSION format: '%s'. Using browser version detection.", version_env)

            if 'version_main' not in chrome_kwargs:
                major_version = self._browser_major_version(browser_binary)
                if major_version is not None:
                    chrome_kwargs['version_main'] = major_version
                    logger.info('Detected Chromium/Chrome major version %s.', major_version)
            
            self.driver = _OwnedChrome(self, **chrome_kwargs)
            # Configure navigation limits before the first get().  The driver
            # constructor itself may still block; it is not cancellable here.
            try:
                self.driver.command_executor.client_config.timeout = 75
            except Exception as e:
                if _is_too_many_open_files(e):
                    raise
                logger.warning("Could not configure initial Selenium HTTP timeout: %s", e)
            try:
                self.driver.set_page_load_timeout(60)
            except Exception as e:
                if _is_too_many_open_files(e):
                    raise
                logger.warning("Could not configure initial page load timeout: %s", e)
            self.driver.get(self.url)
            self.driver.implicitly_wait(5)
            
            self.last_restart_time = datetime.datetime.now()
            logger.info("Browser successfully restarted.")
            
        except Exception as e:
            if _is_too_many_open_files(e):
                logger.critical("Fatal resource exhaustion: [Errno 24] Too many open files. Crashing service for clean container restart.")
                try:
                    await self.close_browsers()
                except Exception as cleanup_exc:
                    logger.warning('Cleanup after fatal launch failed: %s', cleanup_exc)
                raise e
            logger.error("Critical error during browser launch: %s", e)
            # Do not retain a partially navigated session on a failed get().
            await self.close_browsers()
            
        finally:
            self.restarting_browser = False

    async def _users_check(self, event_data: str) -> int | None:
        """
        Parses the total participant user count from the event text.
        
        Args:
            event_data (str): Text extracted from the rain event container.
            
        Returns:
            int | None: The number of users if parsed, otherwise None.
        """
        try:
            if event_data and "event" in event_data.lower():
                match = re.search(r'Rakeback Rain\s+(\d+)\s', event_data)
                if match:
                    return int(match.group(1))
        except Exception as e:
            logger.error("Failed to parse participant user count: %s", e)
        return None

    async def _scrap_check(self, event_data: str) -> float | int | None: 
        """
        Parses the total scrap tip amount from the event text.
        
        Args:
            event_data (str): Text extracted from the rain event container.
            
        Returns:
            float | int | None: The total scrap value if parsed, otherwise None.
        """
        try:
            if event_data and "event" in event_data.lower():
                match = re.search(r'share\s+([\d][\d\.,\s]*)\s+from\s+rain\s+tips\.', event_data, re.IGNORECASE)
                if match:
                    return str_to_float(match.group(1))
        except Exception as e:
            logger.error("Failed to parse scrap amount: %s", e)
        return None

