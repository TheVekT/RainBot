import os
import asyncio
import disnake
from rainbot.utils import Plogging
from disnake.ext import commands




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