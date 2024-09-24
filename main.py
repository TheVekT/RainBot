import re
import disnake
import os
import datetime
import json
import gzip
import time
import asyncio
import psutil
from plogging import plogging
import stats
from disnake.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from disnake import app_commands






global last_use_time
last_use_time = {}

#async def str_to_float(value_str):
#    if value_str is None:
#        return None  # Возвращаем None, если передано значение None
#    elif ',' in str(value_str):  # Проверяем наличие запятой в строке
#        value_str = value_str.replace(',', '.')
#        return float(value_str)
#    else:
#        return float(value_str)
    
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

async def format_duration(seconds):
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

async def create_config_directory_and_file():
    if not os.path.exists('config'):
        os.makedirs('config')
    if not os.path.exists('config/config.json'):
        default_config = {
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
        with open('config/config.json', 'w') as f:
            json.dump(default_config, f, indent=4)
    else:
        with open('config/config.json', 'r') as f:
            try:
                config_data = json.load(f)
                # Проверяем структуру JSON файла
                if 'default' not in config_data or \
                   'commands_cooldown' not in config_data['default']:
                    raise ValueError("Структура config.json нарушена.")
                # Проверка других ключей и типов данных, если необходимо
            except (json.JSONDecodeError, ValueError) as e:
                await plogging(f"Ошибка в структуре config.json: {e}")


async def check_user_cooldown(member_id, command_name, last_command_use):
    try:
        if last_command_use is not None:
            with open('config/config.json', 'r') as f:
                config_data = json.load(f)
                user_group = 'default'  # По умолчанию считаем, что пользователь принадлежит к группе default
                if str(member_id) in config_data:
                    user_group = str(member_id)  # Если пользователь есть в конфиге, считаем его специальным
                cooldown_time = config_data[user_group]['commands_cooldown'].get(command_name)
                if cooldown_time is None:
                    # Если кулдаун для команды не установлен, возвращаем значение по умолчанию
                    cooldown_time = config_data['default']['commands_cooldown'].get(command_name)
                if last_command_use is not None:
                    # Вычисляем оставшееся время кулдауна
                    current_time = datetime.datetime.now()
                    time_difference = current_time - last_command_use
                    # Проверяем тип cooldown_time - если это целое число (количество секунд), преобразуем его в timedelta
                    if isinstance(cooldown_time, int):
                        cooldown_time = datetime.timedelta(seconds=cooldown_time)
                    remaining_cooldown = cooldown_time.total_seconds() - time_difference.total_seconds()
                    # Округляем оставшееся время кулдауна до целого числа (без миллисекунд)
                    remaining_cooldown = round(remaining_cooldown)
                    # Если оставшееся время кулдауна меньше или равно нулю, возвращаем ноль
                    if remaining_cooldown <= 0:
                        return 0
                    else:
                        return remaining_cooldown
        elif last_command_use is None:
            return None
    except Exception as e:
        await plogging(f"An error occurred while checking user cooldown: {e}")
        return None




    

    
    
#logging/











intents = disnake.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
activity = disnake.Activity(
    name="геноцид.",
    type=disnake.ActivityType.streaming,
)
bot = commands.Bot(command_prefix="/", intents=intents, activity=activity)
TOKEN = 'MTA4NDM4Njk3NDk2NzgxMjE2Nw.GwfT7U.Faj3m69IdGxhvWc2IHAnXFMdoTDrGdfYhIHos0'


#██████╗░██████╗░░█████╗░░██╗░░░░░░░██╗░██████╗███████╗██████╗░
#██╔══██╗██╔══██╗██╔══██╗░██║░░██╗░░██║██╔════╝██╔════╝██╔══██╗
#██████╦╝██████╔╝██║░░██║░╚██╗████╗██╔╝╚█████╗░█████╗░░██████╔╝
#██╔══██╗██╔══██╗██║░░██║░░████╔═████║░░╚═══██╗██╔══╝░░██╔══██╗
#██████╦╝██║░░██║╚█████╔╝░░╚██╔╝░╚██╔╝░██████╔╝███████╗██║░░██║
#╚═════╝░╚═╝░░╚═╝░╚════╝░░░░╚═╝░░░╚═╝░░╚═════╝░╚══════╝╚═╝░░╚═╝

#██████╗░███████╗░██████╗████████╗░█████╗░██████╗░████████╗██╗███╗░░██╗░██████╗░
#██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔══██╗██╔══██╗╚══██╔══╝██║████╗░██║██╔════╝░
#██████╔╝█████╗░░╚█████╗░░░░██║░░░███████║██████╔╝░░░██║░░░██║██╔██╗██║██║░░██╗░
#██╔══██╗██╔══╝░░░╚═══██╗░░░██║░░░██╔══██║██╔══██╗░░░██║░░░██║██║╚████║██║░░╚██╗
#██║░░██║███████╗██████╔╝░░░██║░░░██║░░██║██║░░██║░░░██║░░░██║██║░╚███║╚██████╔╝
#╚═╝░░╚═╝╚══════╝╚═════╝░░░░╚═╝░░░╚═╝░░╚═╝╚═╝░░╚═╝░░░╚═╝░░░╚═╝╚═╝░░╚══╝░╚═════╝░

driver = None
def driver_quit():
    driver.quit()
    
last_check_time = None
last_check_time2 = None

async def close_old_browsers():
    chrome_processes = [proc for proc in psutil.process_iter(['pid', 'name']) if proc.info['name'] == 'chrome.exe']
    
    async def terminate_process_tree(pid):
        try:
            process = psutil.Process(pid)
            children = process.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                    await plogging(f"Terminated child process with PID: {child.pid}")
                except Exception as e:
                    await plogging(f"Failed to terminate child process with PID: {child.pid}, error: {e}")
            process.kill()
            await plogging(f"Terminated process with PID: {pid}")
        except Exception as e:
            await plogging(f"Failed to terminate process with PID: {pid}, error: {e}")

    for proc in chrome_processes:
        await terminate_process_tree(proc.info['pid'])
    await asyncio.sleep(2)  # Небольшая задержка для освобождения ресурсов

service = Service('c:\\Program Files\\chromedriver-win64\\chromedriver.exe') # путь к драйверу браузера
options = Options()
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
options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')  # Изменение User-Agent на стандартный для Chrome
options.add_argument('accept-language=en-US,en;q=0.9')
options.add_argument("--window-position=-2000,0")
# Отключение изображений
prefs = {
    "profile.managed_default_content_settings.images": 2,  # Отключение изображений
}
options.add_experimental_option("prefs", prefs)

# Убираем дополнительные capabilities для упрощения конфигурации

driver = None
last_check_time2 = None

@tasks.loop(seconds=300)
async def restart_browser():
    global last_check_time2, driver

    if last_check_time2 is not None:
        elapsed_time = datetime.datetime.now() - last_check_time2
        if elapsed_time.total_seconds() < 1680:
            return
    
    await plogging("Trying to restart browser...")

    if driver is not None:
        try:
            driver.quit()
            print("Browser successfully quit.")
        except Exception as e:
            print(f"Failed to quit browser: {e}")
        driver = None

    await close_old_browsers()

    try:
        driver = webdriver.Chrome(service=service, options=options)
        url = 'https://bandit.camp/'
        driver.get(url)
        driver.implicitly_wait(5)  # ожидание до 5 секунд
    except Exception as e:
        await plogging(f"An error occurred during browser restart: {e}")

#██████╗░░█████╗░██╗███╗░░██╗  ░██████╗███████╗░█████╗░██████╗░░█████╗░██╗░░██╗
#██╔══██╗██╔══██╗██║████╗░██║  ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██║░░██║
#██████╔╝███████║██║██╔██╗██║  ╚█████╗░█████╗░░███████║██████╔╝██║░░╚═╝███████║
#██╔══██╗██╔══██║██║██║╚████║  ░╚═══██╗██╔══╝░░██╔══██║██╔══██╗██║░░██╗██╔══██║
#██║░░██║██║░░██║██║██║░╚███║  ██████╔╝███████╗██║░░██║██║░░██║╚█████╔╝██║░░██║
#╚═╝░░╚═╝╚═╝░░╚═╝╚═╝╚═╝░░╚══╝  ╚═════╝░╚══════╝╚═╝░░╚═╝╚═╝░░╚═╝░╚════╝░╚═╝░░╚═╝


            
async def get_event_data():
    if driver is not None:
        # получение HTML-кода страницы после выполнения JavaScript
        html = driver.execute_script("return document.documentElement.outerHTML")
        soup = BeautifulSoup(html, 'html.parser')

        # поиск нужной информации на странице
        event_div = soup.find('div', {'class': 'px-4 chat-rain-outer mb-2'})
        time_now = datetime.datetime.now()
        formatted_time = time_now.strftime("%H:%M:%S")
        await plogging(str(event_div))

        if event_div is not None:

            event_data = event_div.text
            await plogging(event_data) # вывод содержимого переменной event_data в консоль
        else:
            event_data = None
        return event_data
    else:
        return 'E'
    
async def scrap_check(): 
    event_data = await get_event_data()
    if event_data is not None and "event" in event_data.lower():
        
        #match = re.search(r'share\s(\d{1,3}(?:,\d{3})*,\d{2})\sfrom\srain\stips\.', event_data)
        match = re.search(r'share\s(\d{1,3}(?:,\d{3})*\.\d{2})\sfrom\srain\stips\.', event_data)
        if match:
            global number
            number = match.group(1)
            await plogging("Number founded! " + str(number))
            return number
    else:
        return None
        
async def send_event_data(event_data):
    channel = bot.get_channel(1084401349325762623) # замените на ID вашего канала
    await channel.send(event_data)
    
async def notify_users():
    global message
    global last_message
    channel = bot.get_channel(1084401349325762623) # замените на ID вашего канала
    number = await scrap_check()
    await plogging("Sending notification")  # отладочный вывод
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
    sent_message = await channel.send(content="||@everyone||",embed=embed)
    message = sent_message
    last_message = sent_message.id
    await plogging(str(last_message))
    
    
async def edit_last_message(msg):
    global last_message
    channel = bot.get_channel(1084401349325762623) # замените на ID вашего канала
    if msg.author == bot.user:
        await plogging("Editing last message...")
        message = await channel.fetch_message(last_message)
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
        await message.edit(content="||@everyone||", embed=embed)


delay = 10
@tasks.loop(seconds=delay)
async def check_event():
    global last_check_time
    # проверяем, прошло ли уже 30 минут с момента последнего запуска функции
    if last_check_time is not None:
        elapsed_time = datetime.datetime.now() - last_check_time
        if elapsed_time.total_seconds() < 1500:  # 1800 секунд = 30 минут
            return
    await plogging("Checking for event")  # отладочный вывод

    # проверяем, что на странице сайта есть информация об ивенте
    event_data = await get_event_data()
    if event_data is not None and "event" in event_data.lower():
        global last_check_time2
        last_check_time2 = datetime.datetime.now()
       
        await plogging("Rain DETECTED!")
        # если есть информация об ивенте, отправляем уведомление
        
        await plogging("try to send notify")
        await notify_users()
       
        await plogging("try to bot_sound")
        scrap = await scrap_check()
        sum_of_scrap = await str_to_float(scrap)
        if sum_of_scrap <= 300:
            await bot_sound(play_audio, *("sound.wav", 3.5))
        elif sum_of_scrap >= 1000:
            await bot_sound(play_audio, *("gimn.mp3", 19))
        else:
            await bot_sound(play_audio, *("alert.m4a", 12))
        old_scrap = scrap
        while True:
            scrap = await scrap_check()
            if await str_to_float(scrap) is not None and await str_to_float(old_scrap) is not None:
                recent_scrap = await str_to_float(scrap) - await str_to_float(old_scrap)
            if old_scrap is not None and recent_scrap >= 250:
                await plogging(f"Old scrap lowier than new on {recent_scrap}")
                await bot_sound(play_audio, *("alert.m4a", 8))
            elif old_scrap is not None and recent_scrap >= 50:
                await plogging(f"Old scrap lowier than new on {recent_scrap}")
                await bot_sound()
            
            if scrap is not None:
                await plogging("try to edit last message...")
                await edit_last_message(message)
                time.sleep(5)
                old_scrap = scrap
            else:
                break
    # сохраняем текущее время как время последнего запуска функции
        last_check_time = datetime.datetime.now()
    

async def play_audio(path_to_file, time_sleep, voice):
    # Получаем полный путь к файлу звука, начиная с папки 'sounds'
    audio_path = os.path.join("sounds", path_to_file)
    
    # Проверяем, существует ли файл звука
    if not os.path.exists(audio_path):
        await plogging(f"File '{path_to_file}' not found in 'sounds' directory.")
        return

    # Проверяем, воспроизводится ли уже звук, и если да, останавливаем его
    if voice.is_playing():
        voice.stop()

    audio_source = disnake.FFmpegPCMAudio(audio_path)
    # Обертываем аудиоисточник для установки громкости
    audio_source = disnake.PCMVolumeTransformer(audio_source)
    audio_source.volume = 0.6
    
    # Воспроизводим аудиоисточник в голосовом канале
    voice.play(audio_source)
    await asyncio.sleep(time_sleep)
    
    
async def bot_sound(play_audio_func=None, *play_audio_args, channel_id=None):
    try:
        if channel_id is not None:
            channel = bot.get_channel(channel_id)
            if channel is None:
                await plogging("channel not found")
                return

            # Проверяем, подключен ли бот к голосовому каналу
            voice_client = disnake.utils.get(bot.voice_clients, guild=channel.guild)
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
        guild = bot.guilds[0]
        voice_channels = guild.voice_channels

        # Создаем список каналов с пользователями
        channels_with_users = [channel for channel in voice_channels if len(channel.members) > 0]

        # Если нет каналов с пользователями, то выходим из функции
        if len(channels_with_users) == 0:
            return

        # Подключаемся по очереди ко всем каналам с пользователями
        for channel in channels_with_users:
            # Если уже подключены к голосовому каналу, отключаемся перед подключением к следующему
            voice_client = disnake.utils.get(bot.voice_clients, guild=channel.guild)
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
        await plogging(f"Error in bot_sound: {e}")

    
#░█████╗░░█████╗░███╗░░░███╗███╗░░░███╗░█████╗░███╗░░██╗██████╗░░██████╗
#██╔══██╗██╔══██╗████╗░████║████╗░████║██╔══██╗████╗░██║██╔══██╗██╔════╝
#██║░░╚═╝██║░░██║██╔████╔██║██╔████╔██║███████║██╔██╗██║██║░░██║╚█████╗░
#██║░░██╗██║░░██║██║╚██╔╝██║██║╚██╔╝██║██╔══██║██║╚████║██║░░██║░╚═══██╗
#╚█████╔╝╚█████╔╝██║░╚═╝░██║██║░╚═╝░██║██║░░██║██║░╚███║██████╔╝██████╔╝
#░╚════╝░░╚════╝░╚═╝░░░░░╚═╝╚═╝░░░░░╚═╝╚═╝░░╚═╝╚═╝░░╚══╝╚═════╝░╚═════╝░

# Определяем ID разрешённых голосовых каналов
ALLOWED_VOICE_CHANNEL_IDS = [1168637408896622672, 901174980673425408, 1168637791278739497]

# Функция для автодополнения
async def autocomplete_voice_channels(interaction: disnake.ApplicationCommandInteraction, user_input: str):
    # Получаем все голосовые каналы на сервере
    guild = interaction.guild
    allowed_channels = [
        channel for channel in guild.voice_channels
        if channel.id in ALLOWED_VOICE_CHANNEL_IDS
    ]

    # Фильтруем каналы по имени с учётом пользовательского ввода
    choices = [
        disnake.OptionChoice(name=channel.name, value=str(channel.id))
        for channel in allowed_channels
        if user_input.lower() in channel.name.lower()
    ]

    return choices[:25]  # Ограничиваем 25 вариантами

@bot.slash_command(name="shlepki", description="Play sound shlepki.")
async def shlepki(ctx):
    await plogging(f"Command 'shlepki' was used by {ctx.author.display_name}")

    await ctx.response.defer(ephemeral=True)

    channel_id = ctx.author.voice.channel.id if ctx.author.voice else None
    if not channel_id:
        await ctx.followup.send("You need to be in a voice channel to use this command.")
        return
    user_id = ctx.author.id
    if not hasattr(shlepki, 'last_use_time'):
        shlepki.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
    
    user_id = ctx.author.id
    if user_id in shlepki.last_use_time:
        last_use_time = shlepki.last_use_time[user_id]
        cooldown = await check_user_cooldown(member_id=user_id, command_name="shlepki", last_command_use=last_use_time)
        if cooldown != 0:
            await ctx.followup.send(f"You have {cooldown} sec. cooldown left for this command.")
            await plogging(f"User have a {cooldown} sec. cooldown.")
            return   
        
  # Устанавливаем текущее время как время последнего использования команды для данного пользователя
    shlepki.last_use_time[user_id] = datetime.datetime.now()

    # Запускаем воспроизведение звука асинхронно
    asyncio.create_task(bot_sound(play_audio, *("shlepki.mp3", 72), channel_id=channel_id))

    embed = disnake.Embed(
        description="Playing sound.",
        colour=0xF0C43F,
    )
    embed.set_footer(
        text="© RainBot",
    )
    await ctx.followup.send(embed=embed)  
  
  

@bot.slash_command(name="moving", description="Move a user tuda syuda.")
async def moving(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member):
    try:
        await ctx.response.defer(ephemeral=True)
        
        await plogging(f"Command   'moving'   was used by   {ctx.author.display_name}\nTry to moving {member.display_name}")
        # Проверяем, присоединен ли участник к голосовому каналу
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await plogging(f"User {ctx.author.display_name} is not in a voice channel.")
            embed = disnake.Embed(
                description=f"You are not in a voice channel!",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
            return
        if member.voice is None or member.voice.channel is None:
            embed = disnake.Embed(
                description=f"{member.mention} is not connected to a voice channel.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
            return
    #koja protection
        if member.id in (595255205348507678, 1084386974967812167):
            embed = disnake.Embed(
                description=f"This user has immunity.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
        
            return
        
        user_id = ctx.author.id
        if not hasattr(moving, 'last_use_time'):
            moving.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
           
        
        user_id = ctx.author.id
        if user_id in moving.last_use_time:
            last_use_time = moving.last_use_time[user_id]
            cooldown = await check_user_cooldown(member_id=user_id, command_name="moving", last_command_use=last_use_time)
            if cooldown != 0:
                embed = disnake.Embed(
                    description=f"You have {cooldown} sec. cooldown left for this command.",
                    colour=0xF0C43F,
                )
                embed.set_footer(
                    text="© RainBot",
                ) 
                await ctx.followup.send(embed=embed)
                await plogging(f"User have a {cooldown} sec. cooldown.")
                return

        # Устанавливаем текущее время как время последнего использования команды для данного пользователя
        moving.last_use_time[user_id] = datetime.datetime.now()

        # Получаем текущий канал участника
        current_channel = member.voice.channel
        channel1 = ctx.guild.get_channel(1212058316138872902)
        channel2 = ctx.guild.get_channel(1212058374796218459)
        for i in range(1, 2, 1):
            # Перемещаем участника в указанный канал
            await member.move_to(channel1)
            # Перемещаем участника обратно в исходный канал
            await member.move_to(channel2)
        await member.move_to(current_channel)
        embed = disnake.Embed(
            description="Successfully.",
            colour=0xF0C43F,
        )
        embed.set_footer(
            text="© RainBot",
        ) 
        await ctx.followup.send(embed=embed)
    except disnake.errors.Forbidden:
        await ctx.followup.send("I don't have permissions to move users.")
    except disnake.errors.HTTPException:
        await ctx.followup.send("Failed to move the user.")
        
@bot.slash_command(name="move", description="Move a user to a specified voice channel.")
async def move(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member, channel: str = commands.Param(autocomplete=autocomplete_voice_channels)):
    
    try:
        channel = ctx.guild.get_channel(int(channel))
        await ctx.response.defer(ephemeral=True)
        
        await plogging(f"Command 'move' was used by {ctx.author.display_name}\nTry to move {member.display_name} to {channel.name}")
        # Проверяем, подключен ли участник к каналу
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            embed = disnake.Embed(
                description="You are not in a voice channel!",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            )
            await plogging(f"User {ctx.author.display_name} is not in a voice channel.")
            await ctx.followup.send(embed=embed)
            return
        if member.voice is None or member.voice.channel is None:
            embed = disnake.Embed(
                description=f"{member.mention} is not connected to a voice channel.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            )
            await ctx.followup.send(embed=embed)
            return
    #koja protection
        if member.id in (595255205348507678, 1084386974967812167):
            embed = disnake.Embed(
                description=f"This user has immunity.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
        
            return
        
        

        user_id = ctx.author.id
        if not hasattr(move, 'last_use_time'):
            move.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
        
        user_id = ctx.author.id
        if user_id in move.last_use_time:
            last_use_time = move.last_use_time[user_id]
            cooldown = await check_user_cooldown(member_id=user_id, command_name="move", last_command_use=last_use_time)
            if cooldown != 0:
                embed = disnake.Embed(
                description=f"You have {cooldown} sec. cooldown left for this command.",
                colour=0xF0C43F,
                )
                embed.set_footer(
                    text="© RainBot",
                )
                await ctx.followup.send(embed=embed)
                await plogging(f"User have a {cooldown} sec. cooldown.")
                return

        # Устанавливаем текущее время как время последнего использования команды для данного пользователя
        move.last_use_time[user_id] = datetime.datetime.now()
        
        await member.move_to(channel)
        embed = disnake.Embed(
            description=f"{member.mention} successfully moved to {channel.mention}.",
            colour=0xF0C43F,
        )
        embed.set_footer(
            text="© RainBot",
        )
        await ctx.followup.send(embed=embed)        
    except disnake.errors.Forbidden:
        await ctx.followup.send("I don't have permissions to move users.")
    except disnake.errors.HTTPException:
        await ctx.followup.send("Failed to move the user.")
    except Exception as e:
        await ctx.followup.send(f"An error occurred: {e}", ephemeral=True)

@bot.slash_command(name="getstats", description="Get user statistics.")
async def getstats(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member):

    await plogging(f"Command 'getstats' was used by {ctx.author.display_name}")

    await ctx.response.defer(ephemeral=True)
    user_id = ctx.author.id
    if not hasattr(getstats, 'last_use_time'):
        getstats.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
    
    user_id = ctx.author.id
    if user_id in getstats.last_use_time:
        last_use_time = getstats.last_use_time[user_id]
        cooldown = await check_user_cooldown(member_id=user_id, command_name="getstats", last_command_use=last_use_time)
        if cooldown != 0:
            await ctx.followup.send(f"You have {cooldown} sec. cooldown left for this command.")
            await plogging(f"User have a {cooldown} sec. cooldown.")
            return   
    stats_data = stats.get_user_statistics(member.id)
    if stats_data:
        embed = disnake.Embed(
            title=f"Statistics for {member.name}",
            description="Here is the requested user statistics:",
            colour=0xF0C43F,
        )
        embed.set_thumbnail(url=member.avatar.url)  # Иконка мембера
        embed.add_field(name="**Voice Time:**", value=await format_duration(stats_data['voice_time']), inline=False)
        embed.add_field(name="**Mute Time:**", value=await format_duration(stats_data['mute_time']), inline=False)
        embed.add_field(name="**Deaf Time:**", value=await format_duration(stats_data['deaf_time']), inline=False)
        embed.add_field(name="**Alone Time:**", value=await format_duration(stats_data['alone_time']), inline=False)
        embed.add_field(name="**AFK Time:**", value=await format_duration(stats_data['afk_time']), inline=False)
        embed.set_footer(text="© RainBot")
        
        await ctx.followup.send(embed=embed)
    else:
        await ctx.followup.send("No statistics found for this user.")
    
    
    getstats.last_use_time[user_id] = datetime.datetime.now()    
    
    
    
    
    
    
@bot.slash_command(name="test", description="test command.")
async def test(ctx):

    await plogging(f"Command 'test' was used by {ctx.author.display_name}")

    await ctx.response.defer(ephemeral=True)
    user_id = ctx.author.id
    if not hasattr(test, 'last_use_time'):
        test.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
    
    user_id = ctx.author.id
    if user_id in test.last_use_time:
        last_use_time = test.last_use_time[user_id]
        cooldown = await check_user_cooldown(member_id=user_id, command_name="test", last_command_use=last_use_time)
        if cooldown != 0:
            await ctx.followup.send(f"You have {cooldown} sec. cooldown left for this command.")
            await plogging(f"User have a {cooldown} sec. cooldown.")
            return   
        
  # Устанавливаем текущее время как время последнего использования команды для данного пользователя
    test.last_use_time[user_id] = datetime.datetime.now()
    embed = disnake.Embed(
        description="Test successfully.",
        colour=0xF0C43F,
    )
    embed.set_footer(
    text="© RainBot",
    )
    await ctx.followup.send(embed=embed)  
    







@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if after.channel is None:
            await plogging(f"{member.display_name} left the voice channel {before.channel.name}.")
        elif before.channel is None:   
            await plogging(f"{member.display_name} joined to {after.channel.name}.")
        else:   
            await plogging(f"{member.display_name} moved from {before.channel.name} to {after.channel.name}.")    

    
    
    
    
    
@bot.event
async def on_ready():
    await create_config_directory_and_file()
    stats.initialize_module(bot)
    restart_browser.start()
    check_event.start()
    channel = bot.get_channel(1084401349325762623)
    await plogging('Bot is ready!')
    # await channel.send("> **Now the bot is active.:green_circle:**")
        
    
     

async def try_connect():
    while True:
        try:
            # Запускаем бота, используя свой цикл событий
            await bot.start(TOKEN)
        except (disnake.HTTPException, disnake.GatewayNotFound, disnake.ConnectionClosed, OSError) as e:
            await plogging(f"An error occurred: {e}")
            await plogging("Retrying in 30 seconds...")
            await asyncio.sleep(30)  # Ожидаем 30 секунд перед повторной попыткой
        else:
            # Если подключение прошло успешно, выходим из цикла
            break

if __name__ == "__main__":
    # Используем собственный цикл событий для управления переподключениями
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(try_connect())
    finally:
        loop.close()