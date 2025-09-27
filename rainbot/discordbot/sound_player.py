import os
import asyncio
import disnake
from disnake.ext import commands
from rainbot.utils.plogging import Plogging

class PlaySoundOnBot:
    def __init__(self, botObject: commands.Bot, plogging=None):
        self.bot = botObject
        self.plogging = plogging or Plogging()

        self._guild_locks: dict[int, asyncio.Lock] = {}

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()
        return self._guild_locks[guild_id]

    async def _safe_connect_to_channel(self, channel: disnake.VoiceChannel) -> disnake.VoiceClient:
        """
        Безопасно получить VoiceClient, подключившись к channel при необходимости.
        Гарантирует, что в конце функции возвращается подключенный VoiceClient,
        или выбрасывается исключение.
        """
        guild = channel.guild
        lock = self._get_lock(guild.id)
        async with lock:
            # Проверяем текущий voice_client для этого гильдии
            voice_client: disnake.VoiceClient | None = disnake.utils.get(self.bot.voice_clients, guild=guild)

            # Если уже есть подключённый клиент
            if voice_client and voice_client.is_connected():
                # Если он уже в нужном канале — вернуть его
                try:
                    vc_channel = getattr(voice_client, "channel", None)
                    if vc_channel and vc_channel.id == channel.id:
                        return voice_client
                except Exception:
                    # на всякий случай получим снова
                    voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)

                # Если клиент подключён к другому каналу — корректно отключаем
                try:
                    await voice_client.disconnect()
                    # небольшая пауза, чтобы состояние обновилось
                    await asyncio.sleep(0.5)
                except Exception as e:
                    await self.plogging.warn(f"Failed to disconnect existing voice_client: {e}")

            # Пробуем подключиться
            try:
                new_vc = await channel.connect(reconnect=False)
                # Если подключение успешно — возвращаем
                return new_vc
            except Exception as e:
                # Если исключение "already connected" или подобное — пробуем забрать существующий voice_client
                await self.plogging.warn(f"Exception on connect: {e}. Trying to get existing voice_client.")
                voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
                if voice_client and voice_client.is_connected():
                    return voice_client
                # иначе пробуем ещё раз подключиться (одна дополнительная попытка)
                try:
                    await asyncio.sleep(0.3)
                    new_vc = await channel.connect(reconnect=False)
                    return new_vc
                except Exception as e2:
                    await self.plogging.error(f"Could not connect to channel {channel.id}: {e2}")
                    raise

    async def bot_sound(self, play_audio_func=None, *play_audio_args, channel_id=None):
        """
        Подключается к указанному каналу (или по очереди ко всем каналам, где есть юзеры),
        выполняет play_audio_func( *play_audio_args, voice ) если она есть,
        затем корректно отключается.

        Защищено от параллельного подключения на одном сервере.
        """
        try:
            if channel_id is not None:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    await self.plogging.warn("channel not found")
                    return

                # Обеспечим безопасное подключение к конкретному каналу
                try:
                    voice = await self._safe_connect_to_channel(channel)
                except Exception as e:
                    await self.plogging.error(f"Failed to get voice client for channel {channel_id}: {e}")
                    return

                # Вызов проигрывания
                try:
                    if play_audio_func is not None:
                        await play_audio_func(*play_audio_args, voice)
                    else:
                        await asyncio.sleep(0.5)
                except Exception as e:
                    await self.plogging.error(f"Error during play_audio_func: {e}")

                # После использования — отключаемся, если мы действительно подключены к этому каналу
                try:
                    if voice and voice.is_connected():
                        # если voice.channel совпадает с нашим channel — безопасно отключаем
                        if getattr(voice, "channel", None) and voice.channel.id == channel.id:
                            await voice.disconnect()
                        else:
                            # Если voice подключён к другому каналу, не трогаем его (чтобы не мешать другим)
                            await self.plogging.warn("Voice client is connected to another channel, skipping disconnect.")
                except Exception as e:
                    await self.plogging.warn(f"Error on disconnect: {e}")
                return

            # Если channel_id не указан — берем первую гильдию (как в твоём коде)
            if not self.bot.guilds:
                await self.plogging.warn("Bot has no guilds.")
                return

            guild = self.bot.guilds[0]
            voice_channels = guild.voice_channels
            channels_with_users = [ch for ch in voice_channels if len(ch.members) > 0]

            if not channels_with_users:
                return

            for channel in channels_with_users:
                try:
                    voice = await self._safe_connect_to_channel(channel)
                except Exception as e:
                    await self.plogging.error(f"Failed to connect to channel {channel.id}: {e}")
                    continue

                # Вызов проигрывания
                try:
                    if play_audio_func is not None:
                        await play_audio_func(*play_audio_args, voice)
                    else:
                        await asyncio.sleep(0.5)
                except Exception as e:
                    await self.plogging.error(f"Error during play_audio_func in channel {channel.id}: {e}")

                # Отключаемся, если мы именно в этом канале
                try:
                    if voice and voice.is_connected():
                        if getattr(voice, "channel", None) and voice.channel.id == channel.id:
                            await voice.disconnect()
                except Exception as e:
                    await self.plogging.warn(f"Error on disconnect after playing: {e}")

        except Exception as e:
            await self.plogging.error(f"Error in bot_sound: {e}")

    async def play_audio(self, path_to_file, time_sleep, volume, voice: disnake.VoiceClient):
        """
        Воспроизводит файл, ожидает time_sleep и останавливает.
        """
        audio_path = os.path.join("sounds", path_to_file)
        if not os.path.exists(audio_path):
            await self.plogging.error(f"File '{path_to_file}' not found in 'sounds' directory.")
            return

        try:
            # Если уже играет — остановим
            if voice.is_playing():
                voice.stop()
        except Exception:
            # голосовой клиент может быть в нестабильном состоянии
            pass

        try:
            audio_source = disnake.FFmpegPCMAudio(audio_path)
            audio_source = disnake.PCMVolumeTransformer(audio_source)
            audio_source.volume = volume
            voice.play(audio_source)
            await asyncio.sleep(time_sleep)
            if voice.is_playing():
                voice.stop()
        except Exception as e:
            await self.plogging.error(f"Error playing audio '{path_to_file}': {e}")