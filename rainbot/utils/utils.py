import re
import os
import json
import datetime
from rainbot.utils.plogging import Plogging

class Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        """Подключает функцию-обработчик к сигналу."""
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        """Вызывает все подключенные функции-обработчики."""
        try:
            for slot in self._slots:
                slot(*args, **kwargs)
        except Exception as e:
            print(f"Error in signal slot: {e}")


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
            self.plogging.error(f"Ошибка в структуре config.json: {e}")

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
            self.plogging.error(f"An error occurred while checking user cooldown: {e}")
            return None

    async def _calculate_remaining_cooldown(self, cooldown_time, last_command_use):
        current_time = datetime.datetime.now()
        time_difference = current_time - last_command_use
        if isinstance(cooldown_time, int):
            cooldown_time = datetime.timedelta(seconds=cooldown_time)
        remaining_cooldown = cooldown_time.total_seconds() - time_difference.total_seconds()
        remaining_cooldown = round(remaining_cooldown)
        return max(0, remaining_cooldown)

        

#############
# Functions #
#############

def str_to_float(value_str):
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



