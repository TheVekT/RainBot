import disnake
from disnake.ext import tasks
import json
import os
from datetime import datetime, timedelta, timezone

# Директория для хранения файлов статистики
STATS_DIR = "stats"
TEMP_SUFFIX = "_temp"

if not os.path.exists(STATS_DIR):
    os.makedirs(STATS_DIR)

def load_user_stats(user_id):
    """Загрузка основной статистики пользователя из файла, если файл существует."""
    stats_path = os.path.join(STATS_DIR, f"{user_id}.json")
    if os.path.exists(stats_path):
        with open(stats_path, "r") as f:
            stats = json.load(f)
    else:
        # Создаем новый словарь по умолчанию, если основной файл не найден
        stats = {
            "name": "",
            "voice_time": 0,
            "mute_time": 0,
            "deaf_time": 0,
            "alone_time": 0,
            "afk_time": 0
        }
    return stats

def save_user_stats(user_id, user_name, stats):
    """Сохранение статистики пользователя в основной файл."""
    stats_path = os.path.join(STATS_DIR, f"{user_id}.json")
    stats["name"] = user_name  # Добавляем имя пользователя
    with open(stats_path, "w") as f:
        json.dump(stats, f)

def load_temp_stats(user_id):
    """Загрузка временной статистики пользователя."""
    temp_path = os.path.join(STATS_DIR, f"{user_id}{TEMP_SUFFIX}.json")
    if os.path.exists(temp_path):
        with open(temp_path, "r") as f:
            temp_stats = json.load(f)
    else:
        temp_stats = {
            "voice_time": 0,
            "mute_time": 0,
            "deaf_time": 0,
            "alone_time": 0,
            "afk_time": 0
        }
    return temp_stats

def save_temp_stats(user_id, stats):
    """Сохранение временной статистики пользователя."""
    temp_path = os.path.join(STATS_DIR, f"{user_id}{TEMP_SUFFIX}.json")
    with open(temp_path, "w") as f:
        json.dump(stats, f)

async def update_stats(user, stat_key, delta_time):
    """Обновление статистики пользователя."""
    # Создаем основной файл статистики, если он не существует
    if not os.path.exists(os.path.join(STATS_DIR, f"{user.id}.json")):
        save_user_stats(user.id, user.name, load_user_stats(user.id))
    
    # Обновляем временную статистику
    temp_stats = load_temp_stats(user.id)
    temp_stats[stat_key] += delta_time.total_seconds()
    save_temp_stats(user.id, temp_stats)

async def update_all_users_stats(guild):
    """Обновление статистики для всех пользователей на сервере."""
    for member in guild.members:
        if member.voice:
            if member.voice.self_deaf:
                await update_stats(member, "deaf_time", timedelta(seconds=3))
            elif member.voice.self_mute:
                await update_stats(member, "mute_time", timedelta(seconds=3))
            elif member.voice.channel == member.guild.afk_channel:
                await update_stats(member, "afk_time", timedelta(seconds=3))
            elif len(member.voice.channel.members) == 1:
                await update_stats(member, "alone_time", timedelta(seconds=3))
            else:
                await update_stats(member, "voice_time", timedelta(seconds=3))

@tasks.loop(seconds=3)
async def periodic_stats_update(bot):
    """Фоновая задача для периодического обновления статистики."""
    for guild in bot.guilds:
        await update_all_users_stats(guild)

@tasks.loop(minutes=5)
async def save_stats_periodically():
    """Фоновая задача для периодического сохранения временной статистики в основной файл."""
    for file in os.listdir(STATS_DIR):
        if file.endswith(TEMP_SUFFIX + ".json"):
            user_id = file.replace(TEMP_SUFFIX + ".json", "")
            main_stats = load_user_stats(user_id)
            temp_stats = load_temp_stats(user_id)
            
            # Обновляем основную статистику временной
            for key in ["voice_time", "mute_time", "deaf_time", "alone_time", "afk_time"]:
                main_stats[key] += temp_stats[key]
            
            # Сохраняем обновленную основную статистику
            save_user_stats(user_id, main_stats.get("name", ""), main_stats)
            
            # Обнуляем временный файл
            save_temp_stats(user_id, {key: 0 for key in temp_stats})

def initialize_module(bot):
    """Инициализация модуля статистики при старте бота."""
    periodic_stats_update.start(bot)
    save_stats_periodically.start()

def get_user_statistics(user_id):
    """Получение статистики пользователя по ID."""
    stats = load_user_stats(user_id)
    return stats