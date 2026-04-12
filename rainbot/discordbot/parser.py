import re
import datetime
import asyncio
import sys
import psutil
import disnake
from rainbot.utils import Plogging, str_to_float, Signal
from rainbot.discordbot.sound_player import PlaySoundOnBot
import undetected_chromedriver as uc
from disnake.ext import commands
from bs4 import BeautifulSoup



class RainParser:
    def __init__(self, plogging: Plogging | None = None):
        self.driver = None
        self.last_check_time = None
        self.rain_start = Signal()
        self.rain_end = Signal()
        self.rain_scrap = Signal()
        self.plogging = Plogging() if plogging is None else plogging
        self.bot = None
        self.restarting_browser = False
        self.rain_now = False
        self.url = 'https://bandit.camp/'

    def get_chrome_options(self):
        """Creates and returns a new ChromeOptions object with preconfigured arguments."""
        options = uc.ChromeOptions()
        options.add_argument("--unique-arg")  # Добавляем уникальный аргумент
        options.add_argument('--no-sandbox')  # Отключение песочницы (sandbox)
        options.add_argument('--disable-dev-shm-usage')  # Отключение использования /dev/shm
        options.add_argument('--disable-blink-features=AutomationControlled')  # Отключение определенных функций Blink, связанных с автоматизацией
        options.add_argument('--disable-browser-side-navigation')  # Отключение навигации на стороне браузера
        options.add_argument('--disable-gpu')  # Отключение GPU
        options.add_argument('--window-size=1920,1080')  # Установка размеров окна браузера
        options.add_argument('--disable-notifications')  # Отключение уведомлений
        options.add_argument('--disable-extensions')  # Отключение расширений браузера
        options.add_argument('--ignore-certificate-errors')  # Игнорирование ошибок сертификата
        options.add_argument('--disable-popup-blocking')  # Отключение блокировки всплывающих окон
        options.add_argument('--disable-infobars')  # Отключение информационных панелей
        options.add_argument('--disable-plugins')  # Отключение плагинов браузера
        if sys.platform == 'win32':
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        else:
            user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        options.add_argument(f'--user-agent={user_agent}')
        options.add_argument('--accept-language=en-US,en;q=0.9')
        options.add_argument("--window-position=0,0")
        options.add_argument("--headless=new")  # Запуск браузера в фоновом режиме

        # Отключение изображений
        prefs = {
            "profile.managed_default_content_settings.images": 2,  # Отключение изображений
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument('--disable-blink-features=AutomationControlled')

        return options

    def connect_bot(self, botObject: commands.Bot):
        """Connects a Discord bot to the parser and initializes the sound player."""
        self.bot = botObject
        self.sound = PlaySoundOnBot(self.bot)

    async def driver_quit(self):
        """Closes the current browser driver instance if it exists."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.plogging.error(f"Error while quitting browser: {e}")
            finally:
                self.driver = None

    async def close_browsers(self):
        """Finds and terminates all running Chrome processes along with their children."""
        if sys.platform == 'win32':
            chrome_names = {'chrome.exe'}
        else:
            chrome_names = {'chrome', 'chromium', 'chromium-browser', 'google-chrome'}

        chrome_processes = [proc for proc in psutil.process_iter(['pid', 'name']) if proc.info['name'] in chrome_names]
            
        async def terminate_process_tree(pid):
            try:
                await self.driver_quit()
                process = psutil.Process(pid)
                children = process.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                        self.plogging.debug(f"Terminated child process with PID: {child.pid}")
                    except Exception as e:
                        self.plogging.warn(f"Failed to terminate child process with PID: {child.pid}, error: {e}")
                process.kill()
                self.plogging.debug(f"Terminated process with PID: {pid}")
            except Exception as e:
                self.plogging.warn(f"Failed to terminate process with PID: {pid}, error: {e}")

        for proc in chrome_processes:
            await terminate_process_tree(proc.info['pid'])
        await asyncio.sleep(2)

    async def restart_browser(self):
        """Periodically restarts the browser if no rain event is currently active and enough time has passed."""
        
        if self.rain_now is True:
            return
        self.restarting_browser = True
        if self.last_check_time is not None:
            elapsed_time = datetime.datetime.now() - self.last_check_time
            if elapsed_time.total_seconds() < 1500:
                return
            
        self.plogging.debug("Trying to restart browser...")

        if self.driver is not None:
            try:
                await self.driver_quit()
                self.plogging.debug("Browser successfully quit.")
            except Exception as e:
                self.plogging.error(f"Failed to quit browser: {e}")
        self.driver = None

        await self.close_browsers()
        
        from selenium.common.exceptions import SessionNotCreatedException
        try:
            options = self.get_chrome_options()
            self.driver = uc.Chrome(options=options)  # Используем undetected_chromedriver
            self.driver.get(self.url)
            self.driver.implicitly_wait(5)
            self.restarting_browser = False
            
        except SessionNotCreatedException as e:
            if "ChromeDriver only supports Chrome version" in str(e):
                self.plogging.error("\n[CRITICAL] ChromeDriver version mismatch. Please update ChromeDriver.\n")
            
        except Exception as e:
            self.plogging.error(f"An error occurred during browser restart: {e}")

    async def _get_event_data(self):
        """Fetches and returns event-related data from the webpage HTML."""
        if self.driver is not None:
            try:
                html = self.driver.page_source
                soup = BeautifulSoup(html, 'html.parser')

                event_div = soup.find('div', {'class': 'px-4 chat-rain-outer mb-2'})
                self.plogging.debug(str(event_div))
                if event_div is not None:
                    event_data = event_div.text
                    #self.plogging.debug(event_data)
                else:
                    event_data = None
                return event_data
            except Exception as e:
                self.plogging.error(f"Error fetching page source: {e}")
                await self.driver_quit()
                await self.restart_browser()
        else:
            return 'Empty'
        
    async def _users_check(self) -> int:
        """Parses and returns the number of users who have joined the rain event.

        Returns:
            int | None: Number of users or None if unavailable.
        """
        try:
            event_data = await self._get_event_data()
            if event_data is not None and "event" in event_data.lower():
                match = re.search(r'Rakeback Rain\s+(\d+)\s', event_data)
                if match:
                    count = match.group(1)
                    self.plogging.debug(f"Count of users founded: {count}")
                    count = int(count)
                    return count    
            else:
                return -1
        except Exception as e:
            self.plogging.error(f"Error in count user check: {e}")
            return -1
            
    async def _scrap_check(self): 
        """Parses and returns the amount of scrap shared from the rain tips.

        Returns:
            str | None: Amount of scrap as a string, or None if not found.
        """
        try:
            event_data = await self._get_event_data()
            if event_data is not None and "event" in event_data.lower():  
                #match = re.search(r'share\s(\d{1,3}(?:,\d{3})*,\d{2})\sfrom\srain\stips\.', event_data) # search format 1,488,56
                
                match = re.search(r'share\s(\d{1,3}(?:,\d{3})*\.\d{2})\sfrom\srain\stips\.', event_data) # search format 1,488.56
                if match:
                    number = match.group(1)
                    self.plogging.debug("Number founded! " + str(number))
                    return number
            else:
                return None
        except Exception as e:
            self.plogging.error(f"Error in scrap checking: {e}")
            return -1
                
    async def notify_users(self) -> disnake.Message | None:
        """Sends a Discord notification about the rain event.

        Returns:
            disnake.Message | None: The message object that was sent, or None on failure.
        """
        try:
            channel = self.bot.get_channel(1084401349325762623) # замените на ID вашего канала
            number = await self._scrap_check()
            self.plogging.debug("Sending notification")
            embed = disnake.Embed(
                title="🌧  Rakeback Rain NOW!!!  🌧",
                description=f"**$ {number}**",
                colour=0xF0C43F,
                timestamp=datetime.datetime.now(),
            )
            embed.set_author(
                name="RainBot ",
                url="",
                icon_url="https://cdn.discordapp.com/app-icons/1084386974967812167/4f9cd1faa1a333514fd3dc7446ed5777.png?size=32",
            )
            embed.set_footer(
                text="bandit.camp",
            )
            message = await channel.send(content="||@everyone||",embed=embed)
            return message
        except Exception as e:
            self.plogging.error(f"Error in sending rain notify: {e}")
            
            
            
    async def edit_last_message(self, msg: disnake.Message, number):
        """Edits the last rain notification message with updated scrap data.

        Args:
            msg (disnake.Message): The message object to be edited.
        """
        try:
            # Здесь можно не получать канал заново, если msg уже содержит нужную информацию
            if msg.author == self.bot.user:
                self.plogging.debug(f"Editing message... | message id : {msg.id}")
                embed = disnake.Embed(
                    title="🌧  Rakeback Rain NOW!!!  🌧",
                    description=f"**$ {number}**",
                    colour=0xF0C43F,
                    timestamp=datetime.datetime.now(),
                )
                embed.set_author(
                    name="RainBot ",
                    url="",
                    icon_url="https://cdn.discordapp.com/app-icons/1084386974967812167/4f9cd1faa1a333514fd3dc7446ed5777.png?size=32",
                )
                embed.set_footer(text="bandit.camp")
                await msg.edit(content="||@everyone||", embed=embed)
        except Exception as e:
            self.plogging.error(f"Unhandled exception in edit_last_message: {e}")

    async def _voice_notify_typ1_(self, sum_of_scrap):
        """Plays a voice notification based on the amount of scrap shared in the event."""
        if sum_of_scrap < 150:
            await self.sound.bot_sound(self.sound.play_audio, *("sound.wav", 3.5, 0.6))
        elif sum_of_scrap < 400:
            await self.sound.bot_sound(self.sound.play_audio, *("evrei.m4a", 5, 0.4))
        elif sum_of_scrap < 600:
            await self.sound.bot_sound(self.sound.play_audio, *("stony.mp3", 7, 1.3))
        elif sum_of_scrap < 1000:
            await self.sound.bot_sound(self.sound.play_audio, *("alert.m4a", 12, 0.6))
        elif sum_of_scrap < 5000:
            await self.sound.bot_sound(self.sound.play_audio, *("gimn.mp3", 19, 0.6))
        else: 
            await self.sound.bot_sound(self.sound.play_audio, *("5000.mp3", 12, 3))
            
    async def _voice_notify_typ2_(self, old_scrap, recent_scrap, current_scrap):
        """Plays a voice alert when there's a significant increase in scrap during the rain.

        Args:
            old_scrap (str): Previous scrap value.
            recent_scrap (float): Difference between current and previous scrap.
            current_scrap (str): Current scrap value.

        Returns:
            str: Updated scrap value.
        """
        if old_scrap is not None:
            if recent_scrap >= 400:
                await self.sound.bot_sound(self.sound.play_audio, *("alert.m4a", 8, 0.6))
                self.plogging.info(f"Old scrap lower than new on {recent_scrap}")
                return current_scrap
            elif recent_scrap >= 200:
                await self.sound.bot_sound(self.sound.play_audio, *("evrei.m4a", 5, 0.4))
                self.plogging.info(f"Old scrap lower than new on {recent_scrap}")
                return current_scrap
            elif recent_scrap >= 100:
                await self.sound.bot_sound(self.sound.play_audio, *("potyzhno.mp3", 2, 1.5))
                self.plogging.info(f"Old scrap lower than new on {recent_scrap}")
                return current_scrap
            elif recent_scrap >= 50:
                await self.sound.bot_sound()
                self.plogging.info(f"Old scrap lower than new on {recent_scrap}")
                return current_scrap
        return old_scrap
    
    async def check_event(self):
        """
        Detects and handles rain events. Designed to run periodically.
        """
        try:
            # проверяем, прошло ли уже 30 минут с момента последнего запуска функции
            if self.restarting_browser is True:
                return
            if self.last_check_time is not None :
                elapsed_time = datetime.datetime.now() - self.last_check_time
                if elapsed_time.total_seconds() < 1500:  # 1800 секунд = 30 минут
                    return
            self.plogging.debug("Checking for event")  # отладочный вывод
            # проверяем, что на странице сайта есть информация об ивенте
            event_data = await self._get_event_data()
            if event_data is not None and "event" in event_data.lower():
                self.rain_start.emit()
                self.rain_now = True
                self.plogging.info("Rain DETECTED!")
                # если есть информация об ивенте, отправляем уведомление
                
                self.plogging.debug("Try to send notify about rain")
                message = await self.notify_users()
            
                self.plogging.debug("Trying bot_sound")
                scrap = await self._scrap_check()
                count_of_users = await self._users_check()
                sum_of_scrap = str_to_float(scrap)
                self.rain_scrap.emit(sum_of_scrap)
                await self._voice_notify_typ1_(sum_of_scrap)
                old_scrap = scrap
                old_count = count_of_users
                await asyncio.sleep(1)
                while True:
                    scrap = await self._scrap_check()
                    count_of_users = await self._users_check()
                    old_count = count_of_users if count_of_users != -1 else old_count
                    if str_to_float(scrap) is not None and str_to_float(old_scrap) is not None:
                        recent_scrap = str_to_float(scrap) - str_to_float(old_scrap)

                    else:
                        recent_scrap = 0
                        
                    old_scrap = await self._voice_notify_typ2_(old_scrap, recent_scrap, scrap)
                    
                    if scrap is not None:
                        self.rain_scrap.emit(str_to_float(scrap), count_of_users)
                        self.plogging.debug("try to edit last message...")
                        await self.edit_last_message(message, scrap)
                        await asyncio.sleep(5)
                    else:
                        self.rain_end.emit(str_to_float(old_scrap), old_count)
                        self.rain_now = False   
                        break
            # сохраняем текущее время как время последнего запуска функции
                self.last_check_time = datetime.datetime.now()
        except Exception as e:
            self.plogging.error(f"Unhandled exception in check_event: {e}")

