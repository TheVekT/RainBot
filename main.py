import re
import disnake
import os
import datetime
import json
import gzip
import time
import asyncio
from disnake.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup



global last_use_time
last_use_time = {}
global moving
moving = {}
global move
move = {}
global test
test = {}
async def str_to_float(value_str):
    if value_str is None:
        return None  # Возвращаем None, если передано значение None
    elif ',' not in str(value_str):  # Преобразуем к строке, чтобы учесть случай, когда передано число
        return float(value_str)
    else:
        # Убираем запятые и заменяем точки на точки с плавающей точкой
        value_str = value_str.replace(',', '').replace('.', '.')
        return float(value_str)


async def create_config_directory_and_file():
    if not os.path.exists('config'):
        os.makedirs('config')
    if not os.path.exists('config/config.json'):
        default_config = {
            'default': {
                'commands_cooldown': {
                    'move': 3,
                    'moving': 10,
                    'test': 5
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



logs_dir = "./logs"
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

time_now_logs = datetime.datetime.now()
formatted_time_logs = time_now_logs.strftime("%d-%m-%Y_%H-%M-%S")
log_filename = f"log_{formatted_time_logs}.txt"
log_filepath = os.path.join(logs_dir, log_filename)

# Проверяем, существуют ли уже файлы журналов в папке
log_files = [file for file in os.listdir(logs_dir) if file.endswith(".txt")]

async def plogging(a):
    time_now = datetime.datetime.now()  # Вызов метода now() от класса datetime.datetime
    formatted_time = time_now.strftime("%H:%M:%S")
    print(f"[{formatted_time}] {a}")
    with open(log_filepath, "a", encoding="utf-8") as log_file:  # Указываем кодировку UTF-8
        log_file.write(f"[{formatted_time}] {a} \n")

if log_files:
    # Если есть файлы журналов, архивируем их
    for file in log_files:
        # Создаем архивный файл
        archive_filename = f"{file[:-4]}_archive.gz"  # Имя архива с добавлением _archive
        archive_filepath = os.path.join(logs_dir, archive_filename)
        
        with open(os.path.join(logs_dir, file), 'rb') as f_in, gzip.open(archive_filepath, 'wb') as f_out:
            f_out.writelines(f_in)
        
        # Удаляем оригинальный файл журнала
        os.remove(os.path.join(logs_dir, file))
        
        print(f"Файл журнала {file} успешно архивирован в {archive_filepath}")

try:
    with open(log_filepath, 'w') as f:
        pass
    print(f"Файл журнала успешно создан: {log_filepath}")
except Exception as e:
    print(f"Ошибка при создании файла журнала: {e}")
    

    
    
#logging/










driver = None

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="/", intents=intents)
TOKEN = 'MTA4NDM4Njk3NDk2NzgxMjE2Nw.GwfT7U.Faj3m69IdGxhvWc2IHAnXFMdoTDrGdfYhIHos0'

def driver_quit():
    driver.quit()
    
last_check_time = None
last_check_time2 = None
    
@tasks.loop(seconds=300)
async def restart_browser():
    global last_check_time2
    if last_check_time2 is not None:
        elapsed_time = datetime.datetime.now() - last_check_time2
        if elapsed_time.total_seconds() < 1980:
            return
    global driver
    await plogging("Trying restart browser...")

    if driver is not None:
        driver.quit()    
    try:
            # запуск браузера с помощью Selenium
        service = Service('c:\\Program Files\\chromedriver-win64\\chromedriver.exe') # путь к драйверу браузера
        options = Options()
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
        # options.headless = True
        
        driver = webdriver.Chrome(service=service, options=options)
        # загрузка страницы и ожидание ее полной загрузки
        url = 'https://bandit.camp/'
        driver.get(url)
        driver.implicitly_wait(10) # ожидание до 10 секунд    
    except Exception as e:
        await plogging(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    




            
async def get_event_data():
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
        
    
async def scrap_check(): 
    event_data = await get_event_data()
    if event_data is not None and "event" in event_data.lower():
        #match = re.search(r'share\s(\d{1,3}(?:\s\d{3})*.\d{2})\sfrom\srain\stips\.', event_data)
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
    await plogging("Sending notification")  # отладочный вывод
    sent_message = await channel.send("||@everyone||\n```fix\nRakeBack Rain NOW!!!\n" + str(datetime.datetime.now().strftime("%H:%M")) + "\n```" + "\n> **" + "--|--" + " $**")
    message = sent_message
    last_message = sent_message.id
    await plogging(str(last_message))
    
    
async def edit_last_message(msg):
    global last_message
    channel = bot.get_channel(1084401349325762623) # замените на ID вашего канала
    if msg.author == bot.user:
        await plogging("Editing last message...")
        message = await channel.fetch_message(last_message)
        new_message = "||@everyone||\n```fix\nRakeBack Rain NOW!!!\n" + str(datetime.datetime.now().strftime("%H:%M")) + "\n```" + "\n> **" + str(number) + " $**"
        await message.edit(content=new_message)


delay = 10
@tasks.loop(seconds=delay)
async def check_event():
    global last_check_time
    # проверяем, прошло ли уже 30 минут с момента последнего запуска функции
    if last_check_time is not None:
        elapsed_time = datetime.datetime.now() - last_check_time
        if elapsed_time.total_seconds() < 1800:  # 1800 секунд = 30 минут
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
        await bot_sound(1, scrap)
        old_scrap = scrap
        while True:
            scrap = await scrap_check()
            if await str_to_float(scrap) is not None and await str_to_float(old_scrap) is not None:
                recent_scrap = await str_to_float(scrap) - await str_to_float(old_scrap)
            if old_scrap is not None and recent_scrap >= 50:
                await plogging(f"Old scrap lowier than new on {recent_scrap}")
                await bot_sound(sound=None)
            
            if scrap is not None:
                await plogging("try to edit last message...")
                await edit_last_message(message)
                time.sleep(5)
                old_scrap = scrap
            else:
                break
    # сохраняем текущее время как время последнего запуска функции
        last_check_time = datetime.datetime.now()
    

async def play_audio(path, time_sleep, voice):
    audio_source = disnake.FFmpegPCMAudio(path)
    # Обертываем аудиоисточник для установки громкости
    audio_source = disnake.PCMVolumeTransformer(audio_source)
    audio_source.volume = 0.5
    # Воспроизводим аудиоисточник в голосовом канале
    voice.play(audio_source)
    # Ждем некоторое время
    await asyncio.sleep(time_sleep)  # Пример: звук будет проигрываться в течение 10 секунд    
    
@bot.event
async def bot_sound(sound, scrap = None):
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
        if bot.voice_clients:
            voice = bot.voice_clients[0]
            if voice.is_connected():
                await voice.disconnect()
                await asyncio.sleep(0.5)
        if sound is None:
            voice = await channel.connect()
        if sound is not None and scrap is not None:
            # Подключаемся к голосовому каналу
            voice = await channel.connect()
            if await str_to_float(scrap) < 300:
                await play_audio("sound.wav", 4, voice)
            elif await str_to_float(scrap) >= 300:
                await play_audio("alert.m4a", 12, voice)
            # Получаем аудиоисточник
        # Покидаем канал
        if voice.is_connected():
            await voice.disconnect()

    

  
  
  
  
  
  
  

@bot.slash_command(name="moving", description="Move a user tuda syuda.")
async def moving(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member):
    try:
        await ctx.response.defer(ephemeral=True)
        
        await plogging(f"Command   'moving'   was used by   {ctx.author.display_name}\nTry to moving {member.display_name}")
        # Проверяем, присоединен ли участник к голосовому каналу
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await plogging(f"User {ctx.author.display_name} is not in a voice channel.")
            await ctx.followup.send(f"You are not in a voice channel!")
            return
        if member.voice is None or member.voice.channel is None:
            await ctx.followup.send(f"{member.mention} is not connected to a voice channel.")
            return
        
        user_id = ctx.author.id
        if not hasattr(moving, 'last_use_time'):
            moving.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
           
        
        user_id = ctx.author.id
        if user_id in moving.last_use_time:
            last_use_time = moving.last_use_time[user_id]
            cooldown = await check_user_cooldown(member_id=user_id, command_name="moving", last_command_use=last_use_time)
            if cooldown != 0:
                await ctx.followup.send(f"You have {cooldown} sec. cooldown left for this command.")
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
        await ctx.followup.send("Successfully")
    except disnake.errors.Forbidden:
        await ctx.followup.send("I don't have permissions to move users.")
    except disnake.errors.HTTPException:
        await ctx.followup.send("Failed to move the user.")
        
@bot.slash_command(name="move", description="Move a user to a specified voice channel.")
async def move(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member, channel: disnake.VoiceChannel):
    try:
        await ctx.response.defer(ephemeral=True)
        
        await plogging(f"Command 'move' was used by {ctx.author.display_name}\nTry to move {member.display_name} to {channel.name}")

        # Проверяем, подключен ли участник к каналу
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await plogging(f"User {ctx.author.display_name} is not in a voice channel.")
            await ctx.followup.send(f"You are not in a voice channel!")
            return
        if member.voice is None or member.voice.channel is None:
            await ctx.followup.send(f"{member.mention} is not connected to a voice channel.")
            return
        user_id = ctx.author.id
        if not hasattr(move, 'last_use_time'):
            move.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
        
        user_id = ctx.author.id
        if user_id in move.last_use_time:
            last_use_time = move.last_use_time[user_id]
            cooldown = await check_user_cooldown(member_id=user_id, command_name="move", last_command_use=last_use_time)
            if cooldown != 0:
                await ctx.followup.send(f"You have {cooldown} sec. cooldown left for this command.")
                await plogging(f"User have a {cooldown} sec. cooldown.")
                return

        # Устанавливаем текущее время как время последнего использования команды для данного пользователя
        move.last_use_time[user_id] = datetime.datetime.now()

        await member.move_to(channel)
        await ctx.followup.send(f"{member.mention} successfully moved to {channel.mention}.")        
    except disnake.errors.Forbidden:
        await ctx.followup.send("I don't have permissions to move users.")
    except disnake.errors.HTTPException:
        await ctx.followup.send("Failed to move the user.")
    except Exception as e:
        await ctx.followup.send(f"An error occurred: {e}", ephemeral=True)

    
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

    await ctx.followup.send("test successfully!")  
    
    
    
    
    
@bot.event
async def on_ready():
    await create_config_directory_and_file()
    restart_browser.start()
    check_event.start()
    channel = bot.get_channel(1084401349325762623)
    await plogging('Bot is ready!')
    # await channel.send("> **Now the bot is active.:green_circle:**")
        
    

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if after.channel is None:
            await plogging(f"{member.display_name} left the voice channel {before.channel.name}.")
        elif before.channel is None:   
            await plogging(f"{member.display_name} joined to {after.channel.name}.")
        else:   
            await plogging(f"{member.display_name} moved from {before.channel.name} to {after.channel.name}.")
    
    
    
    
    
    
    
    
    
    
    

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"An error occurred: {e}")
