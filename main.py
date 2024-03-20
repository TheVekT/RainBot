import asyncio
import re
import discord
import datetime
import time
import atexit
import os

from discord.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

intents = discord.Intents.default()
intents.members = True
number = None
message = None
last_message = None


bot = commands.Bot(command_prefix='/', description='Event bot', intents=intents)
TOKEN = 'MTA4NDM4Njk3NDk2NzgxMjE2Nw.GwfT7U.Faj3m69IdGxhvWc2IHAnXFMdoTDrGdfYhIHos0'

async def get_event_data():
    try:
        # запуск браузера с помощью Selenium
        service = Service('/path/to/chromedriver') # путь к драйверу браузера
        options = Options()
        options.add_argument('--disable-gpu') # скрыть окно браузера
        driver = webdriver.Chrome(service=service, options=options)

        # загрузка страницы и ожидание ее полной загрузки
        url = 'https://bandit.camp/'
        driver.get(url)
        driver.implicitly_wait(3) # ожидание до 3 секунд

        # получение HTML-кода страницы после выполнения JavaScript
        html = driver.execute_script("return document.documentElement.outerHTML")
        soup = BeautifulSoup(html, 'html.parser')

        # поиск нужной информации на странице
        event_div = soup.find('div', {'class': 'px-4 chat-rain-outer mb-2'})
        time_now = datetime.datetime.now()
        formatted_time = time_now.strftime("%H:%M:%S")
        print(str(event_div) + " " + str(formatted_time))
        if event_div is not None:
            event_data = event_div.text
            print("Rain detected") # вывод содержимого переменной event_data в консоль
        else:
            event_data = None
        return event_data
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        driver.quit() # закрытие браузера
       
async def scrap_check(): 
    event_data = await get_event_data()
    if event_data is not None and "event" in event_data.lower():
        match = re.search(r'share\s(\d+,\d+)\sfrom\srain\stips\.', event_data)
        if match:
            global number
            number = match.group(1)
            print("Number founded! " + str(number) + "\n" + str(datetime.datetime.now().strftime("%H:%M:%S")))
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
    sent_message = await channel.send("||@everyone||\n```fix\nRakeBack Rain NOW!!!\n" + str(datetime.datetime.now().strftime("%H:%M")) + "\n```" + "\n> **--|-- $**")
    message = sent_message
    last_message = sent_message.id
    print(str(last_message))
    
async def edit_last_message(msg):
    global last_message
    channel = bot.get_channel(1084401349325762623) # замените на ID вашего канала
    if msg.author == bot.user:
        print("Editing last message...")
        message = await channel.fetch_message(last_message)
        new_message = "||@everyone||\n```fix\nRakeBack Rain NOW!!!\n" + str(datetime.datetime.now().strftime("%H:%M")) + "\n```" + "\n> **" + str(number) + " $**" 
        await message.edit(content=new_message)
    
last_check_time = None

@tasks.loop(seconds=30)
async def check_event():
    global last_check_time

    # проверяем, прошло ли уже 30 минут с момента последнего запуска функции
    if last_check_time is not None:
        elapsed_time = datetime.datetime.now() - last_check_time
        if elapsed_time.total_seconds() < 1800:  # 1800 секунд = 30 минут
            return
    print("Checking for event")  # отладочный вывод

    # проверяем, что на странице сайта есть информация об ивенте
    event_data = await get_event_data()
    if event_data is not None and "event" in event_data.lower():
        print("Rain DETECTED!")
        # если есть информация об ивенте, отправляем уведомление
        print("try to send notify")
        await notify_users()
    # сохраняем текущее время как время последнего запуска функции
        last_check_time = datetime.datetime.now()
        while True:
            scrap = await scrap_check()
            if scrap is not None:
                print("try to edit last message...")
                await edit_last_message(message)
                time.sleep(5)
            else:
                break
            

@bot.command()
async def rbstop(ctx):
    await ctx.send("> **Now the bot is inactive.:red_circle:**")
    print("BOT Stopped")
    await bot.close()
    
@bot.event
async def on_ready():
    check_event.start()
    channel = bot.get_channel(1084401349325762623)
    print('Bot is ready!')
    await channel.send("> **Now the bot is active.:green_circle:**")


@atexit.register
async def exit_handler():
    check_event.stop()
    print('Bot has stopped!')
    await bot.close()

async def close_driver():
    global driver
    driver.quit()
    

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"An error occurred: {e}")