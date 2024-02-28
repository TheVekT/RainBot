import re
#import discord
import disnake
import os
import datetime

import zipfile
import time
import asyncio
#from discord.ext import commands, tasks
from disnake.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

#Получаем идентификатор текущего процесса (вашего бота)
# current_pid = os.getpid()

# # Устанавливаем приоритет процесса бота
# try:
#     p = psutil.Process(current_pid)
#     p.nice(psutil.HIGH_PRIORITY_CLASS)  # Установка приоритета в HIGH (высокий)
#     print("Установлен приоритет процесса бота в HIGH (высокий).")
# except Exception as e:
#     print(f"Не удалось установить приоритет процесса бота: {e}")



logs_dir = "./logs"
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

time_now_logs = datetime.datetime.now()
formatted_time_logs = time_now_logs.strftime("%Y_%H-%M-%S")
log_filename = f"log_{formatted_time_logs}.txt"
log_filepath = os.path.join(logs_dir, log_filename)

# Проверяем, существуют ли уже файлы журналов в папке
log_files = [file for file in os.listdir(logs_dir) if file.endswith(".txt")]

if log_files:
    # Если есть файлы журналов, архивируем их
    for file in log_files:
        # Создаем архивный файл
        archive_filename = f"{file[:-4]}_archive.zip"  # Имя архива с добавлением _archive
        archive_filepath = os.path.join(logs_dir, archive_filename)
        
        with zipfile.ZipFile(archive_filepath, 'w') as zipf:
            # Добавляем текущий файл журнала в архив
            zipf.write(os.path.join(logs_dir, file), file)
        
        # Удаляем оригинальный файл журнала
        os.remove(os.path.join(logs_dir, file))
        
        print(f"Файл журнала {file} успешно архивирован в {archive_filepath}")



try:
    with open(log_filepath, 'w') as f:
        pass
    print(f"Файл журнала успешно создан: {log_filepath}")
except Exception as e:
    print(f"Ошибка при создании файла журнала: {e}")

async def logging(a):
    with open(log_filepath, "a", encoding="utf-8") as log_file:  # Указываем кодировку UTF-8
        time_now = datetime.datetime.now()  # Вызов метода now() от класса datetime.datetime
        formatted_time = time_now.strftime("%H:%M:%S")
        log_file.write(a + f"     {formatted_time}\n")
    
#logging/

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="/", intents=intents)
TOKEN = 'MTA4NDM4Njk3NDk2NzgxMjE2Nw.GwfT7U.Faj3m69IdGxhvWc2IHAnXFMdoTDrGdfYhIHos0'

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
    global driver
    driver = webdriver.Chrome(service=service, options=options)
    # загрузка страницы и ожидание ее полной загрузки
    url = 'https://bandit.camp/'
    driver.get(url)
    driver.implicitly_wait(10) # ожидание до 10 секунд    
except Exception as e:
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
    
def driver_quit():
    driver.quit()
    
last_check_time = None

    
@tasks.loop(seconds=300)
async def restart_browser():
    global last_check_time
    if last_check_time is not None:
        elapsed_time = datetime.datetime.now() - last_check_time
        if elapsed_time.total_seconds() < 1800:  # 1800 секунд = 30 минут
            return
    global driver
    print("Trying restart browser...")
    await logging("Trying restart browser...")

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
        print(f"An error occurred: {e}")
        await logging(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    

    
# # Поиск и установка приоритетов для процессов браузера (пример для Google Chrome)
# browser_name = "chrome.exe"  # Замените на имя процесса вашего браузера

# for process in psutil.process_iter(attrs=['pid', 'name']):
#     if process.info['name'] == browser_name:
#         try:
#             process.nice(psutil.HIGH_PRIORITY_CLASS)  # Установка приоритета для процесса браузера
#             print(f"Установлен приоритет процесса {browser_name} в HIGH (высокий).")
#             await logging(f"Установлен приоритет процесса {browser_name} в HIGH (высокий).")
#         except Exception as e:
#             print(f"Не удалось установить приоритет процесса {browser_name}: {e}")
#             await logging(f"Не удалось установить приоритет процесса {browser_name}: {e}")

            
async def get_event_data():
        # получение HTML-кода страницы после выполнения JavaScript
        html = driver.execute_script("return document.documentElement.outerHTML")
        soup = BeautifulSoup(html, 'html.parser')

        # поиск нужной информации на странице
        event_div = soup.find('div', {'class': 'px-4 chat-rain-outer mb-2'})
        time_now = datetime.datetime.now()
        formatted_time = time_now.strftime("%H:%M:%S")
        print(str(event_div) + " " + str(formatted_time))
        await logging(str(event_div))
        if event_div is not None:

            event_data = event_div.text
            print(event_data) # вывод содержимого переменной event_data в консоль
            await logging(event_data)
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
            print("Number founded! " + str(number) + "\n" + str(datetime.datetime.now().strftime("%H:%M:%S")))
            await logging("Number founded! " + str(number) + "\n")
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
    print("Sending notification")  # отладочный вывод
    await logging("Sending notification")
    sent_message = await channel.send("||@everyone||\n```fix\nRakeBack Rain NOW!!!\n" + str(datetime.datetime.now().strftime("%H:%M")) + "\n```" + "\n> **" + "--|--" + " $**")
    message = sent_message
    last_message = sent_message.id
    print(str(last_message))
    await logging(str(last_message))
    
async def edit_last_message(msg):
    global last_message
    channel = bot.get_channel(1084401349325762623) # замените на ID вашего канала
    if msg.author == bot.user:
        print("Editing last message...")
        await logging("Editing last message...")
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
    print("Checking for event")  # отладочный вывод
    await logging("Checking for event")

    # проверяем, что на странице сайта есть информация об ивенте
    event_data = await get_event_data()
    if event_data is not None and "event" in event_data.lower():
        try:
            restart_browser.stop()
        except:
            pass
        print("Rain DETECTED!")
        await logging("Rain DETECTED!")
        # если есть информация об ивенте, отправляем уведомление
        print("try to send notify")
        await logging("try to send notify")
        await notify_users()
        print("\n\ntry to bot_sound\n")
        await logging("\n\ntry to bot_sound\n")
        await bot_sound()
        while True:
            scrap = await scrap_check()
            if scrap is not None:
                print("try to edit last message...")
                await logging("try to edit last message...")
                await edit_last_message(message)
                time.sleep(5)
            else:
                try:
                    restart_browser.start()
                except:
                    pass
                break
    # сохраняем текущее время как время последнего запуска функции
        last_check_time = datetime.datetime.now()
    
    
        
@bot.event
async def bot_sound():
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
        voice = await channel.connect()
        await asyncio.sleep(1)
        # Покидаем канал
        if voice.is_connected():
            await voice.disconnect()
    
@bot.event
async def on_ready():
    check_event.start()
    restart_browser.start()
    channel = bot.get_channel(1084401349325762623)
    print('Bot is ready!')
    await logging('Bot is ready!')
    # await channel.send("> **Now the bot is active.:green_circle:**")
    

@bot.slash_command(name="moving", description="Move a user tuda syuda.")
async def move(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member):
    try:
        await ctx.response.defer(ephemeral=True)
        with open(log_filepath, "a", encoding="utf-8") as log_file:  # Указываем кодировку UTF-8
            time_now = datetime.datetime.now()  # Вызов метода now() от класса datetime.datetime
            formatted_time = time_now.strftime("%H:%M:%S")
            log_file.write(f"Command   'moving'   was used by   {ctx.author.display_name}   at {formatted_time}\nTry to moving {member.display_name}\n\n")
            print(f"Command   'moving'   was used by   {ctx.author.display_name}   at {formatted_time}\n")
        # Проверяем, присоединен ли участник к голосовому каналу
        if member.voice is None or member.voice.channel is None:
            await ctx.followup.send(f"{member.mention} is not connected to a voice channel.")
            return
        
        # Получаем текущий канал участника
        current_channel = member.voice.channel
        channel1 = ctx.guild.get_channel(1212058316138872902)
        channel2 = ctx.guild.get_channel(1212058374796218459)
        for i in range(1, 3, 1):
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
        with open(log_filepath, "a", encoding="utf-8") as log_file:
            time_now = datetime.datetime.now()
            formatted_time = time_now.strftime("%H:%M:%S")
            log_file.write(f"Command 'move' was used by {ctx.author.display_name}\nTry to move {member.display_name} to {channel.name} at {formatted_time}\n\n")
            print(f"Command 'move' was used by {ctx.author.display_name} Try to move {member.display_name} to {channel.name} at {formatted_time}\n")
        # Проверяем, подключен ли участник к каналу
        if member.voice is None or member.voice.channel is None:
            await ctx.followup.send(f"{member.mention} is not connected to a voice channel.")
            return
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
    await ctx.response.defer(ephemeral=True)
    with open(log_filepath, "a", encoding="utf-8") as log_file:  # Указываем кодировку UTF-8
        time_now = datetime.datetime.now()  # Вызов метода now() от класса datetime.datetime
        formatted_time = time_now.strftime("%H:%M:%S")
        log_file.write(f"Command   'test'   was used by   {ctx.author.display_name}   at {formatted_time}\n")
        print(f"Command   'test'   was used by   {ctx.author.display_name}   at {formatted_time}\n")    
    await ctx.followup.send("test successfully!")


try:
    bot.run(TOKEN)
except Exception as e:
    print(f"An error occurred: {e}")