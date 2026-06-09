import re
import datetime
import asyncio
import os
import shutil
from pathlib import Path
import psutil
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

from utils.signal import Signal
from utils.str_to_float import str_to_float

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class RainParser:
    """
    A selenium-based parser for detecting and tracking rain events on bandit.camp.
    
    Exposes signals to notify subscribers when a rain starts, changes, or ends.
    """
    def __init__(self):
        self.driver = None
        self.url = 'https://bandit.camp/'
        
        self.poll_interval: int = 10
        self.browser_restart_interval: int = 600
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

    async def driver_quit(self):
        """
        Safely quits and cleans up the active browser driver session.
        """
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"[ERROR] Failed to quit browser session: {e}")
            finally:
                self.driver = None

    async def close_browsers(self):
        """
        Kills any leftover Chrome/Chromium child processes spawned by this runner session.
        """
        chrome_names = {'chrome', 'chromium', 'chromium-browser', 'google-chrome'}
        try:
            await self.driver_quit()
            
            current_process = psutil.Process(os.getpid())
            children = current_process.children(recursive=True)
            
            for child in children:
                try:
                    if child.name() in chrome_names:
                        child.kill()
                        print(f"[DEBUG] Killed leftover Chrome child process PID: {child.pid}")
                except Exception as e:
                    print(f"[WARN] Failed to kill child process PID {child.pid}: {e}")
        except Exception as e:
            print(f"[ERROR] Failed to clean up process tree: {e}")
            
        await asyncio.sleep(2)

    async def restart_browser(self):
        """
        Restarts the browser session periodically to avoid cache bloat and memory leaks.
        """
        if self.rain_now:
            return  # Do not restart browser if a rain is currently in progress!
        
        if self.last_event_time is not None:
            elapsed_time = datetime.datetime.now() - self.last_event_time
            if elapsed_time.total_seconds() < self.browser_restart_interval:
                return
        
        if self.last_restart_time is not None:
            elapsed_time = datetime.datetime.now() - self.last_restart_time
            if elapsed_time.total_seconds() < self.browser_restart_interval:
                return

        self.restarting_browser = True
                
        print("[INFO] Performing scheduled browser restart...")

        await self.close_browsers()
        
        try:
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
                    print(f"[INFO] Using chromedriver version_main={major_version} from environment.")
                except (ValueError, IndexError):
                    print(f"[WARN] Invalid CHROMEDRIVER_VERSION format: '{version_env}'. Using auto-detection.")
            
            self.driver = uc.Chrome(**chrome_kwargs)
            self.driver.get(self.url)
            self.driver.implicitly_wait(5)
            
            self.last_restart_time = datetime.datetime.now()
            print("[INFO] Browser successfully restarted.")
            
        except Exception as e:
            print(f"[ERROR] Critical error during browser launch: {e}")
            
        finally:
            self.restarting_browser = False

    async def _get_event_data(self) -> str | None:
        """
        Retrieves the page source code and extracts the text inside the rain container.
        
        Returns:
            str | None: Inner text of the rain container if present, otherwise None.
        """
        if not self.driver:
            return None
            
        try:
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            event_div = soup.find('div', {'class': 'px-4 chat-rain-outer mb-2'})
            
            return event_div.text if event_div else None
        except Exception as e:
            print(f"[ERROR] Error reading page source: {e}")
            await self.restart_browser() # Emergency restart when access fails
            return None

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
            print(f"[ERROR] Failed to parse participant user count: {e}")
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
            print(f"[ERROR] Failed to parse scrap amount: {e}")
        return None

    async def run(self):
        """
        Main infinite loop running the scrapper browser and emitting signals on state changes.
        """
        print("[INFO] Parser started. Monitoring rain events...")
        
        while True:
            try:
                await self.restart_browser()
                
                # Check cooldown after the last rain event ended
                if self.last_event_time:
                    elapsed = (datetime.datetime.now() - self.last_event_time).total_seconds()
                    if elapsed < self.cooldown_after_rain:
                        await asyncio.sleep(10)
                        continue

                if self.restarting_browser:
                    await asyncio.sleep(2)
                    continue

                event_data = await self._get_event_data()
                
                # If a rain event container is found on the page
                if event_data and "event" in event_data.lower():
                    self.rain_now = True
                    print("[EVENT] Rain DETECTED!")
                    
                    current_scrap = await self._scrap_check(event_data)
                    current_users = await self._users_check(event_data)
                    
                    # Fallback defaults if initial parsing fails
                    scrap_amount = current_scrap if current_scrap is not None else 0.0
                    user_count = current_users if current_users is not None else 0
                    
                    # EMIT: Rain started
                    self.on_rain_started.emit(scrap_amount, user_count)
                    
                    old_scrap = scrap_amount
                    old_users = user_count
                    
                    # Track changes during the active rain event
                    while True:
                        await asyncio.sleep(3)
                        
                        event_data = await self._get_event_data()
                        
                        # If the rain container has disappeared
                        if not event_data or "event" not in event_data.lower():
                            print(f"[EVENT] Rain ENDED. Summary: {old_scrap} scrap, {old_users} users.")
                            # EMIT: Rain ended (positional arguments)
                            self.on_rain_ended.emit(old_scrap, old_users)
                            
                            self.rain_now = False
                            self.last_event_time = datetime.datetime.now()
                            break
                        
                        current_scrap = await self._scrap_check(event_data)
                        current_users = await self._users_check(event_data)
                        
                        # Skip this cycle on temporary/transient parsing errors
                        if current_scrap is None or current_users is None:
                            continue
                        
                        # EMIT: Rain updated (only if data changed, positional arguments)
                        if current_scrap > old_scrap or current_users != old_users:
                            # print(f"[DEBUG] Update: {current_scrap} scrap, {current_users} users")
                            self.on_rain_updated.emit(current_scrap, current_users)
                            
                            old_scrap = current_scrap
                            old_users = current_users

                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                print(f"[ERROR] Unhandled exception in main runner loop: {e}")
                await asyncio.sleep(5)