import re
import os
import json
import datetime
import asyncio
import psutil
import disnake
from plogging import Plogging
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc  # Измененный импорт
from disnake.ext import commands, tasks
from bs4 import BeautifulSoup

class Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        """Подключает функцию-обработчик к сигналу."""
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        """Вызывает все подключенные функции-обработчики."""
        for slot in self._slots:
            slot(*args, **kwargs)


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

    def get_chrome_options(self):
        """Создаёт и возвращает новый объект ChromeOptions."""
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
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                             'AppleWebKit/537.36 (KHTML, like Gecko) '
                             'Chrome/91.0.4472.124 Safari/537.36')  # Изменение User-Agent на стандартный для Chrome
        options.add_argument('accept-language=en-US,en;q=0.9')
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
        self.bot = botObject
        self.sound = PlaySoundOnBot(self.bot)

    async def driver_quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                await self.plogging.error(f"Error while quitting browser: {e}")
            finally:
                self.driver = None  # Обязательно освобождаем ресурс

    async def close_browsers(self):
        chrome_processes = [proc for proc in psutil.process_iter(['pid', 'name']) if proc.info['name'] == 'chrome.exe']
            
        async def terminate_process_tree(pid):
            try:
                await self.driver_quit()
                process = psutil.Process(pid)
                children = process.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                        await self.plogging.debug(f"Terminated child process with PID: {child.pid}")
                    except Exception as e:
                        await self.plogging.error(f"Failed to terminate child process with PID: {child.pid}, error: {e}")
                process.kill()
                await self.plogging.debug(f"Terminated process with PID: {pid}")
            except Exception as e:
                await self.plogging.error(f"Failed to terminate process with PID: {pid}, error: {e}")

        for proc in chrome_processes:
            await terminate_process_tree(proc.info['pid'])
        await asyncio.sleep(2)  # Небольшая задержка для освобождения ресурсов

    async def restart_browser(self):
        """
        Periodicaly task to restarting browser after event
        """
        
        if self.rain_now is True:
            return
        self.restarting_browser = True
        if self.last_check_time is not None:
            elapsed_time = datetime.datetime.now() - self.last_check_time
            if elapsed_time.total_seconds() < 1500:  # 1500 секунд = 25 минут
                return
            
        await self.plogging.debug("Trying to restart browser...")

        if self.driver is not None:
            try:
                await self.driver_quit()
                await self.plogging.debug("Browser successfully quit.")
            except Exception as e:
                await self.plogging.error(f"Failed to quit browser: {e}")
        self.driver = None

        await self.close_browsers()

        try:
            options = self.get_chrome_options()  # Получаем новый объект ChromeOptions
            self.driver = uc.Chrome(options=options)  # Используем undetected_chromedriver
            self.url = 'https://bandit.camp/'
            self.driver.get(self.url)
            self.driver.implicitly_wait(5)  # ожидание до 5 секунд
            self.restarting_browser = False
        except Exception as e:
            await self.plogging.error(f"An error occurred during browser restart: {e}")

    async def _get_event_data(self):
        if self.driver is not None:
            try:
                # получение HTML-кода страницы после выполнения JavaScript
                html = self.driver.page_source
                self.soup = BeautifulSoup(html, 'html.parser')

                # поиск нужной информации на странице
                event_div = self.soup.find('div', {'class': 'px-4 chat-rain-outer mb-2'})
                time_now = datetime.datetime.now()
                formatted_time = time_now.strftime("%H:%M:%S")
                await self.plogging.debug(str(event_div))

                if event_div is not None:
                    event_data = event_div.text
                    await self.plogging.debug(event_data)  # вывод содержимого переменной event_data в консоль
                else:
                    event_data = None
                return event_data
            except Exception as e:
                await self.plogging.error(f"Error fetching page source: {e}")
                await self.driver_quit()
                await self.restart_browser()
        else:
            return 'Empty'
            
    async def _scrap_check(self): 
        """
        Returning scrap count from event
        """
        event_data = await self._get_event_data()
        if event_data is not None and "event" in event_data.lower():
                
            #match = re.search(r'share\s(\d{1,3}(?:,\d{3})*,\d{2})\sfrom\srain\stips\.', event_data) # search format 1,488,56
            
            match = re.search(r'share\s(\d{1,3}(?:,\d{3})*\.\d{2})\sfrom\srain\stips\.', event_data) # search format 1,488.56
            if match:
                global number
                number = match.group(1)
                await self.plogging.debug("Number founded! " + str(number))
                return number
        else:
            return None
                
    async def send_event_data(self, event_data):
        channel = self.bot.get_channel(1084401349325762623) # замените на ID вашего канала
        await channel.send(event_data)
            
    async def notify_users(self):
        channel = self.bot.get_channel(1084401349325762623) # замените на ID вашего канала
        number = await self._scrap_check()
        await self.plogging.debug("Sending notification")  # отладочный вывод
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
        self.sent_message = await channel.send(content="||@everyone||",embed=embed)
        self.message = self.sent_message
        self.last_message = self.sent_message.id
        await self.plogging.debug(str(self.last_message))
            
            
    async def edit_last_message(self, msg):
        try:
            channel = self.bot.get_channel(1084401349325762623) # замените на ID вашего канала
            if msg.author == self.bot.user:
                await self.plogging.debug(f"Editing last message... | message id : {self.message.id}")
                self.message = await channel.fetch_message(self.last_message)
                if self.message:
                    try:
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
                        await self.message.edit(content="||@everyone||", embed=embed)
                    except Exception as e:
                        await self.plogging.error(e)
        except Exception as e:
            await self.plogging.error(f"Unhandled exception in edit_last_message: {e}")

    async def check_event(self):
        try:
            # проверяем, прошло ли уже 30 минут с момента последнего запуска функции
            if self.restarting_browser is True:
                return
            if self.last_check_time is not None :
                elapsed_time = datetime.datetime.now() - self.last_check_time
                if elapsed_time.total_seconds() < 1500:  # 1800 секунд = 30 минут
                    return
            await self.plogging.debug("Checking for event")  # отладочный вывод
            # проверяем, что на странице сайта есть информация об ивенте
            event_data = await self._get_event_data()
            if event_data is not None and "event" in event_data.lower():
                self.rain_start.emit()
                self.rain_now = True
                await self.plogging.info("Rain DETECTED!")
                # если есть информация об ивенте, отправляем уведомление
                
                await self.plogging.debug("Try to send notify about rain")
                await self.notify_users()
            
                await self.plogging.debug("Trying bot_sound")
                scrap = await self._scrap_check()
                
                sum_of_scrap = await str_to_float(scrap)
                self.rain_scrap.emit(sum_of_scrap)
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
                old_scrap = scrap
                await asyncio.sleep(1)
                while True:
                    scrap = await self._scrap_check()
                    
                    if await str_to_float(scrap) is not None and await str_to_float(old_scrap) is not None:
                        recent_scrap = await str_to_float(scrap) - await str_to_float(old_scrap)
                        
                    else:
                        recent_scrap = 0
                        
                    if old_scrap is not None and recent_scrap >= 400:
                        await self.sound.bot_sound(self.sound.play_audio, *("alert.m4a", 8, 0.6))
                        await self.plogging.info(f"Old scrap lowier than new on {recent_scrap}")
                        old_scrap = scrap
                    elif old_scrap is not None and recent_scrap >= 200:
                        await self.sound.bot_sound(self.sound.play_audio, *("evrei.m4a", 5, 0.4))
                        await self.plogging.info(f"Old scrap lowier than new on {recent_scrap}")
                        old_scrap = scrap
                    elif old_scrap is not None and recent_scrap >= 100:
                        await self.sound.bot_sound(self.sound.play_audio, *("potyzhno.mp3", 2, 1.5))
                        await self.plogging.info(f"Old scrap lowier than new on {recent_scrap}")
                        old_scrap = scrap
                    elif old_scrap is not None and recent_scrap >= 50:
                        await self.sound.bot_sound()
                        await self.plogging.info(f"Old scrap lowier than new on {recent_scrap}")
                        old_scrap = scrap
                    
                    if scrap is not None:
                        self.rain_scrap.emit(await str_to_float(scrap))
                        await self.plogging.debug("try to edit last message...")
                        await self.edit_last_message(self.message)
                        await asyncio.sleep(5)
                        
                    else:
                        self.rain_end.emit()
                        self.rain_now = False   
                        break
            # сохраняем текущее время как время последнего запуска функции
                self.last_check_time = datetime.datetime.now()
        except Exception as e:
            await self.plogging.error(f"Unhandled exception in check_event: {e}")



class ConfigManager:
    def __init__(self, config_dir='config', config_file='config.json', plogging: Plogging | None = None):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, config_file)
        self.plogging = Plogging() if plogging is None else plogging
        self.default_config = {
            'default': {
                'commands_cooldown': {
                    'move': 3,
                    'moving': 10,
                    'test': 5,
                    'getstats': 30,
                    'shlepki': 900
                }
            }
        }

    async def create_config(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        if not os.path.exists(self.config_file):
            await self._write_default_config()
        else:
            await self._validate_config()

    async def _write_default_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.default_config, f, indent=4)

    async def _validate_config(self):
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
                # Проверяем структуру JSON файла
                if 'default' not in config_data or 'commands_cooldown' not in config_data['default']:
                    raise ValueError("Структура config.json нарушена.")
        except (json.JSONDecodeError, ValueError) as e:
            await self.plogging.error(f"Ошибка в структуре config.json: {e}")

    async def check_user_cooldown(self, member_id, command_name, last_command_use):
        try:
            if last_command_use is not None:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                    user_group = 'default'  # По умолчанию пользователь принадлежит к группе default
                    if str(member_id) in config_data:
                        user_group = str(member_id)  # Если пользователь в конфиге, считаем его специальным
                    cooldown_time = config_data[user_group]['commands_cooldown'].get(command_name)
                    if cooldown_time is None:
                        # Если кулдаун для команды не установлен, возвращаем значение по умолчанию
                        cooldown_time = config_data['default']['commands_cooldown'].get(command_name)
                    
                    if last_command_use is not None:
                        return await self._calculate_remaining_cooldown(cooldown_time, last_command_use)
            elif last_command_use is None:
                return None
        except Exception as e:
            await self.plogging.error(f"An error occurred while checking user cooldown: {e}")
            return None

    async def _calculate_remaining_cooldown(self, cooldown_time, last_command_use):
        current_time = datetime.datetime.now()
        time_difference = current_time - last_command_use
        if isinstance(cooldown_time, int):
            cooldown_time = datetime.timedelta(seconds=cooldown_time)
        remaining_cooldown = cooldown_time.total_seconds() - time_difference.total_seconds()
        remaining_cooldown = round(remaining_cooldown)
        return max(0, remaining_cooldown)
    


class PlaySoundOnBot:
    def __init__(self, botObject: commands.Bot, plogging: Plogging | None = None):
        self.bot = botObject
        self.plogging = Plogging() if plogging is None else plogging
    async def bot_sound(self, play_audio_func=None, *play_audio_args, channel_id=None):
        """
        Параметры:
        - play_audio_func (Callable, опционально): Функция для воспроизведения аудио. 
          Если не указана, бот просто подключится к каналу и отключится через паузу.
        - play_audio_args: Аргументы для функции воспроизведения аудио, если она указана.
        - channel_id (int, опционально): ID голосового канала, к которому нужно подключиться.
          Если не указан, бот будет подключаться ко всем каналам с пользователями на сервере.

        Исключения:
        - Логирует ошибки, проблемы с подключением или воспроизведением аудио.
        """
        
        try:
            if channel_id is not None:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    await self.plogging.warn("channel not found")
                    return

                # Проверяем, подключен ли бот к голосовому каналу
                voice_client = disnake.utils.get(self.bot.voice_clients, guild=channel.guild)
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect()
                    await asyncio.sleep(1)  # Даем время на полное отключение

                # Подключаемся к голосовому каналу
                voice = await channel.connect()

                # Если передана функция play_audio и аргументы для нее, вызываем ее
                if play_audio_func is not None:
                    await play_audio_func(*play_audio_args, voice)
                else:
                    # Ждем 0.5 секунды
                    await asyncio.sleep(0.5)

                # Покидаем канал
                if voice.is_connected():
                    await voice.disconnect()
                return

            # Получаем список всех голосовых каналов на сервере
            guild = self.bot.guilds[0]
            voice_channels = guild.voice_channels

            # Создаем список каналов с пользователями
            channels_with_users = [channel for channel in voice_channels if len(channel.members) > 0]

            # Если нет каналов с пользователями, то выходим из функции
            if len(channels_with_users) == 0:
                return

            # Подключаемся по очереди ко всем каналам с пользователями
            for channel in channels_with_users:
                # Если уже подключены к голосовому каналу, отключаемся перед подключением к следующему
                voice_client = disnake.utils.get(self.bot.voice_clients, guild=channel.guild)
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect()
                    await asyncio.sleep(1)  # Даем время на полное отключение

                # Подключаемся к голосовому каналу
                voice = await channel.connect()

                # Если передана функция play_audio и аргументы для нее, вызываем ее
                if play_audio_func is not None:
                    await play_audio_func(*play_audio_args, voice)

                # Покидаем канал
                if voice.is_connected():
                    await voice.disconnect()
        except Exception as e:
            await self.plogging.error(f"Error in bot_sound: {e}")
    async def play_audio(self, path_to_file, time_sleep, volume, voice: disnake.VoiceClient):
        """
        Параметры:
        - path_to_file (str): Путь к аудиофайлу в папке 'sounds'.
        - time_sleep (float): Время ожидания в секундах после начала воспроизведения.
        - voice (disnake.VoiceClient): Объект голосового клиента для управления воспроизведением в канале.

        Описание:
        - Проверяет, существует ли указанный аудиофайл. Если не существует, логирует ошибку и завершает выполнение.
        - Если в голосовом канале уже воспроизводится звук, останавливает его перед воспроизведением нового.
        - Воспроизводит звук.
        """
        # Получаем полный путь к файлу звука, начиная с папки 'sounds'
        audio_path = os.path.join("sounds", path_to_file)
        
        # Проверяем, существует ли файл звука
        if not os.path.exists(audio_path):
            await self.plogging.error(f"File '{path_to_file}' not found in 'sounds' directory.")
            return

        # Проверяем, воспроизводится ли уже звук, и если да, останавливаем его
        if voice.is_playing():
            voice.stop()

        audio_source = disnake.FFmpegPCMAudio(audio_path)
        # Обертываем аудиоисточник для установки громкости
        audio_source = disnake.PCMVolumeTransformer(audio_source)
        audio_source.volume = volume
        
        # Воспроизводим аудиоисточник в голосовом канале
        voice.play(audio_source)
        await asyncio.sleep(time_sleep)
        voice.stop()
        

#############
# Functions #
#############

async def str_to_float(value_str):
    if value_str is None:
        return None  # Возвращаем None, если передано значение None
    
    # Заменяем запятую на точку, если она есть
    value_str = value_str.replace(',', '.')
    
    # Удаляем разделители тысяч (точки), оставляя только последнюю точку перед дробной частью
    value_str = re.sub(r'(?<=\d)\.(?=\d{3}(?:\.|$))', '', value_str)
    
    # Преобразуем строку в число с плавающей запятой
    value_float = float(value_str)
    
    # Проверяем, является ли число целым (имеет ли дробную часть .0)
    if value_float.is_integer():
        return int(value_float)
    
    return value_float

def format_duration(seconds):
    """Форматирование времени в строку вида 'X days X hours X min. X sec.'."""
    days, remainder = divmod(seconds, 86400)  # 86400 секунд в дне
    hours, remainder = divmod(remainder, 3600)  # 3600 секунд в часе
    minutes, secs = divmod(remainder, 60)  # 60 секунд в минуте

    time_parts = []
    if days > 0:
        time_parts.append(f"{int(days)} day{'s' if days > 1 else ''}")
    if hours > 0:
        time_parts.append(f"{int(hours)} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        time_parts.append(f"{int(minutes)} min.")
    if secs > 0 or not time_parts:  # Показать секунды, если нет других единиц времени
        time_parts.append(f"{int(secs)} sec.")

    return " ".join(time_parts)



