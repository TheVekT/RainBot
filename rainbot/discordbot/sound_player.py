import os
import asyncio
import time
import disnake
from disnake.ext import commands
from functools import partial
from rainbot.utils.plogging import Plogging

# --- IMPORTS FOR PYTUBEFIX ---
try:
    from pytubefix import YouTube, Search
    from pytubefix.cli import on_progress
except ImportError:
    print("CRITICAL: Pytubefix not installed. Run 'pip install pytubefix'")

# --- FFMPEG Options ---
FFMPEG_BASE_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class GuildMusicState:
    """Stores music state for a specific guild."""
    def __init__(self):
        self.active_url = None
        self.title = None
        self.duration = 0
        
        # Тайминги
        self.start_time = 0.0
        self.pause_start = 0.0 
        self.elapsed_saved = 0.0 
        
        self.is_playing = False
        self.is_paused = False
        self.volume = 0.5
        self.repeat = False
        
        # Эффекты
        self.bass_boost = False
        self.slowed = False   # 0.5x
        self.sped_up = False  # 2.0x
        
        self.voice_channel = None 
        self.interaction_message = None 
        
        self.menu_timeout_task: asyncio.Task = None 

    @property
    def current_speed(self):
        if self.slowed: return 0.5
        if self.sped_up: return 2.0
        return 1.0

# --- Views (Buttons) ---

class VolumeView(disnake.ui.View):
    def __init__(self, player_class, guild_id):
        super().__init__(timeout=None)
        self.player = player_class
        self.guild_id = guild_id

    @disnake.ui.button(label="- Vol", style=disnake.ButtonStyle.red, row=0)
    async def vol_down(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.player.change_volume(self.guild_id, -0.25)

    @disnake.ui.button(label="+ Vol", style=disnake.ButtonStyle.green, row=0)
    async def vol_up(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.player.change_volume(self.guild_id, 0.25)

    @disnake.ui.button(label="Back", style=disnake.ButtonStyle.secondary, row=1)
    async def back(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.player.update_player_message(self.guild_id, view_type="options")

class OptionsView(disnake.ui.View):
    def __init__(self, player_class, guild_id, current_state: GuildMusicState):
        super().__init__(timeout=None)
        self.player = player_class
        self.guild_id = guild_id

        style = disnake.ButtonStyle.green if current_state.repeat else disnake.ButtonStyle.gray
        label = "Repeat: ON" if current_state.repeat else "Repeat: OFF"
        self.add_item(disnake.ui.Button(label=label, style=style, custom_id="opt_repeat", row=0))

        self.add_item(disnake.ui.Button(label="Volume Settings", style=disnake.ButtonStyle.blurple, custom_id="opt_volume", row=0))
        self.add_item(disnake.ui.Button(label="Back", style=disnake.ButtonStyle.secondary, custom_id="opt_back", row=1))

    async def interaction_check(self, interaction: disnake.MessageInteraction):
        cid = interaction.data.custom_id
        if cid == "opt_repeat":
            await interaction.response.defer()
            await self.player.toggle_repeat(self.guild_id)
        elif cid == "opt_volume":
            await interaction.response.defer()
            await self.player.update_player_message(self.guild_id, view_type="volume")
        elif cid == "opt_back":
            await interaction.response.defer()
            await self.player.update_player_message(self.guild_id, view_type="main")
        return True

class EffectsView(disnake.ui.View):
    def __init__(self, player_class, guild_id, current_state: GuildMusicState):
        super().__init__(timeout=None)
        self.player = player_class
        self.guild_id = guild_id
        
        # Bass Boost
        style_bb = disnake.ButtonStyle.green if current_state.bass_boost else disnake.ButtonStyle.gray
        label_bb = "Bass: ON" if current_state.bass_boost else "Bass: OFF"
        self.add_item(disnake.ui.Button(label=label_bb, style=style_bb, custom_id="effect_bass", row=0))

        # Slow (0.5x)
        style_slow = disnake.ButtonStyle.green if current_state.slowed else disnake.ButtonStyle.gray
        self.add_item(disnake.ui.Button(label="Slow (0.5x)", style=style_slow, custom_id="effect_slow", row=1))

        # Fast (2.0x)
        style_fast = disnake.ButtonStyle.green if current_state.sped_up else disnake.ButtonStyle.gray
        self.add_item(disnake.ui.Button(label="Fast (2.0x)", style=style_fast, custom_id="effect_fast", row=1))

        # Back
        self.add_item(disnake.ui.Button(label="Back", style=disnake.ButtonStyle.secondary, custom_id="effect_back", row=2))

    async def interaction_check(self, interaction: disnake.MessageInteraction):
        cid = interaction.data.custom_id
        if cid == "effect_bass":
            await interaction.response.defer()
            await self.player.toggle_effect(self.guild_id, "bass")
        elif cid == "effect_slow":
            await interaction.response.defer()
            await self.player.toggle_effect(self.guild_id, "slow")
        elif cid == "effect_fast":
            await interaction.response.defer()
            await self.player.toggle_effect(self.guild_id, "fast")
        elif cid == "effect_back":
            await interaction.response.defer()
            await self.player.update_player_message(self.guild_id, view_type="main")
        return True

class MusicView(disnake.ui.View):
    def __init__(self, player_class, guild_id):
        super().__init__(timeout=None)
        self.player = player_class
        self.guild_id = guild_id

    @disnake.ui.button(label="Pause/Resume", style=disnake.ButtonStyle.blurple, custom_id="music_pause_resume", row=0)
    async def pause_resume(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.player.toggle_pause(interaction.guild.id, interaction)

    @disnake.ui.button(label="Stop", style=disnake.ButtonStyle.red, custom_id="music_stop", row=0)
    async def stop(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.player.stop_music(interaction.guild.id, interaction)

    @disnake.ui.button(label="Options", style=disnake.ButtonStyle.secondary, custom_id="music_options", row=0)
    async def options(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.player.update_player_message(interaction.guild.id, view_type="options")

    @disnake.ui.button(label="Effects", style=disnake.ButtonStyle.secondary, custom_id="music_effects", row=0)
    async def effects(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.player.update_player_message(interaction.guild.id, view_type="effects")

class PlaySoundOnBot:
    def __init__(self, botObject: commands.Bot, plogging=None):
        self.bot = botObject
        self.plogging = plogging or Plogging()
        
        self._guild_locks: dict[int, asyncio.Lock] = {}
        self.music_states: dict[int, GuildMusicState] = {}
        self.priority_mode = True 

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()
        return self._guild_locks[guild_id]

    def _get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.music_states:
            self.music_states[guild_id] = GuildMusicState()
        return self.music_states[guild_id]

    # --- Helpers ---

    def _create_embed(self, state: GuildMusicState, status="playing"):
        if status == "playing":
            embed = disnake.Embed(title="Now playing", color=disnake.Color.blurple())
            embed.add_field(name="Title", value=state.title, inline=False)
            embed.add_field(name="Duration", value=f"{state.duration // 60}:{state.duration % 60:02d}", inline=True)
            
            repeat_status = "On" if state.repeat else "Off"
            options_val = f"Volume: {int(state.volume*100)}%\nRepeat: {repeat_status}"
            embed.add_field(name="Options", value=options_val, inline=True)
            
            effects_str = []
            if state.bass_boost:
                effects_str.append("Bass Boost")
            if state.slowed:
                effects_str.append("Speed: 0.5x")
            if state.sped_up:
                effects_str.append("Speed: 2.0x")
            
            if effects_str:
                embed.add_field(name="Effects", value=", ".join(effects_str), inline=False)
                
            return embed
        
        elif status == "stopped":
            embed = disnake.Embed(title="Played", color=disnake.Color.dark_grey())
            description = f"**{state.title}**\n{state.active_url}" if state.title and state.active_url else "Unknown track"
            embed.description = description
            return embed
        return None

    # --- PYTUBEFIX EXTRACTION LOGIC ---
    def _extract_pytubefix_sync(self, url_or_query):
        """Синхронная функция для поиска и извлечения через pytubefix"""
        try:
            # 1. Проверяем, ссылка ли это
            if url_or_query.startswith(('http://', 'https://')):
                yt = YouTube(url_or_query, use_oauth=True, allow_oauth_cache=True)
            else:
                # 2. Если не ссылка, используем Поиск
                self.plogging.info(f"Searching for: {url_or_query}")
                search = Search(url_or_query)
                if not search.videos:
                    raise Exception("No results found.")
                # Берем первое видео и инициализируем с OAuth
                first_video = search.videos[0]
                yt = YouTube(first_video.watch_url, use_oauth=True, allow_oauth_cache=True)

            # 3. Извлекаем данные
            title = yt.title
            duration = yt.length
            
            # Получаем аудио поток (m4a обычно стабильнее всего)
            stream = yt.streams.get_audio_only()
            if not stream:
                # Fallback если аудио не найдено (редко)
                stream = yt.streams.filter(only_audio=True).first()
            
            return stream.url, title, duration
        except Exception as e:
            self.plogging.error(f"Pytubefix Sync Error: {e}")
            raise e

    async def _get_audio_source(self, url, seek_time=0, bass_boost=False, slowed=False, sped_up=False):
        loop = asyncio.get_event_loop()
        try:
            # Запускаем синхронный pytubefix в executor, чтобы не блочить бота
            stream_url, title, duration = await loop.run_in_executor(None, lambda: self._extract_pytubefix_sync(url))
        except Exception as e:
            self.plogging.error(f"Extraction Error: {e}")
            return None, None, None

        if not stream_url:
            return None, None, None

        # Настраиваем FFMPEG с ссылкой от pytubefix
        opts = FFMPEG_BASE_OPTIONS.copy()
        if seek_time > 0:
            opts['before_options'] += f' -ss {seek_time}'
        
        filters = []
        if bass_boost:
            filters.append("bass=g=20")
        
        if slowed:
            filters.append("atempo=0.5")
        elif sped_up:
            filters.append("atempo=2.0")
            
        if filters:
            opts['options'] = f'-vn -af "{",".join(filters)}"'
        else:
            opts['options'] = '-vn'

        return disnake.FFmpegPCMAudio(stream_url, **opts), title, duration

    async def _revert_to_main_delayed(self, guild_id):
        try:
            await asyncio.sleep(10)
            await self.update_player_message(guild_id, view_type="main")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.plogging.warn(f"Revert task error: {e}")

    async def _disconnect_voice_safe(self, guild_id):
        """Helper to disconnect asynchronously from sync context."""
        guild = self.bot.get_guild(guild_id)
        if not guild: return
        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client:
            await voice_client.disconnect()

    async def update_player_message(self, guild_id, view_type="main", force_status=None):
        state = self._get_state(guild_id)
        if not state.interaction_message:
            return
        
        if state.menu_timeout_task:
            state.menu_timeout_task.cancel()
            state.menu_timeout_task = None

        status = force_status if force_status else ("playing" if state.is_playing else "stopped")
        
        if status == "stopped":
             embed = self._create_embed(state, status="stopped")
             try:
                await state.interaction_message.edit(embed=embed, view=None)
             except Exception: pass
             return

        embed = self._create_embed(state, status="playing")
        
        if view_type == "effects":
            view = EffectsView(self, guild_id, state)
        elif view_type == "options":
            view = OptionsView(self, guild_id, state)
        elif view_type == "volume":
            view = VolumeView(self, guild_id)
        else:
            view = MusicView(self, guild_id)

        try:
            await state.interaction_message.edit(embed=embed, view=view)
            if view_type != "main":
                state.menu_timeout_task = asyncio.create_task(self._revert_to_main_delayed(guild_id))
        except Exception as e:
            self.plogging.warn(f"Failed to update player message: {e}")

    # --- Internal Play Logic ---

    async def _play_track(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if not guild: return
        
        state = self._get_state(guild_id)
        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)

        if not voice_client:
            self.plogging.error("Voice client unavailable for playback.")
            return

        source, title, duration = await self._get_audio_source(
            state.active_url, 
            seek_time=0, 
            bass_boost=state.bass_boost,
            slowed=state.slowed,
            sped_up=state.sped_up
        )
        if not source:
            self.plogging.error("Failed to get audio source in loop.")
            return

        source = disnake.PCMVolumeTransformer(source)
        source.volume = state.volume

        state.title = title
        state.duration = duration
        state.start_time = time.time()
        state.elapsed_saved = 0.0
        state.is_playing = True
        state.is_paused = False

        def after_playing(error):
            if error:
                self.plogging.error(f"Player error: {error}")
            
            if state.is_playing: 
                if state.repeat:
                    coro = self._play_track(guild_id)
                    asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                else:
                    state.is_playing = False
                    coro_msg = self.update_player_message(guild_id, force_status="stopped")
                    asyncio.run_coroutine_threadsafe(coro_msg, self.bot.loop)
                    coro_disc = self._disconnect_voice_safe(guild_id)
                    asyncio.run_coroutine_threadsafe(coro_disc, self.bot.loop)

        try:
            voice_client.play(source, after=after_playing)
            await self.update_player_message(guild_id, view_type="main")
        except Exception as e:
            self.plogging.error(f"Failed to start playback: {e}")

    # --- Controls ---

    async def change_volume(self, guild_id, change_amount):
        state = self._get_state(guild_id)
        new_vol = max(0.0, min(2.0, state.volume + change_amount))
        state.volume = new_vol

        guild = self.bot.get_guild(guild_id)
        if guild:
            vc = disnake.utils.get(self.bot.voice_clients, guild=guild)
            if vc and vc.source:
                try:
                    vc.source.volume = new_vol
                except Exception: pass
        
        await self.update_player_message(guild_id, view_type="volume")

    async def toggle_repeat(self, guild_id):
        state = self._get_state(guild_id)
        state.repeat = not state.repeat
        await self.update_player_message(guild_id, view_type="options")

    async def toggle_effect(self, guild_id, effect_type):
        """Переключает эффекты и перезапускает поток."""
        state = self._get_state(guild_id)
        
        if effect_type == 'bass':
            state.bass_boost = not state.bass_boost
        elif effect_type == 'slow':
            state.slowed = not state.slowed
            if state.slowed: state.sped_up = False 
        elif effect_type == 'fast':
            state.sped_up = not state.sped_up
            if state.sped_up: state.slowed = False 

        await self._reload_player_state(guild_id)
        await self.update_player_message(guild_id, view_type="effects")

    async def _reload_player_state(self, guild_id):
        """Безопасный перезапуск плеера (Hot Swap)."""
        guild = self.bot.get_guild(guild_id)
        if not guild: return
        
        state = self._get_state(guild_id)
        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)

        if not state.is_playing: return
        if not voice_client: return

        # 1. Расчет позиции
        if state.is_paused:
            current_pos = state.elapsed_saved
        else:
            elapsed_wall = time.time() - state.start_time
            current_pos = elapsed_wall * state.current_speed 

        # 2. Ставим флаг manual stop
        state.is_playing = False 
        
        # 3. Стопаем
        if voice_client.is_connected():
            voice_client.stop() 
        
        await asyncio.sleep(0.1)
        
        # 4. Реконнект
        if not voice_client.is_connected():
            try:
                if state.voice_channel:
                    voice_client = await self._safe_connect_to_channel(state.voice_channel)
                else: return 
            except Exception: return

        # 5. Новый source
        seek_pos_int = int(current_pos)
        source, _, _ = await self._get_audio_source(
            state.active_url, 
            seek_time=seek_pos_int, 
            bass_boost=state.bass_boost,
            slowed=state.slowed,
            sped_up=state.sped_up
        )

        if source:
            source = disnake.PCMVolumeTransformer(source)
            source.volume = state.volume
            
            new_speed = state.current_speed
            state.start_time = time.time() - (current_pos / new_speed)
            state.is_playing = True
            
            def after_playing_restart(error):
                if state.is_playing:
                    if state.repeat:
                        coro = self._play_track(guild_id)
                        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                    else:
                        state.is_playing = False
                        coro_msg = self.update_player_message(guild_id, force_status="stopped")
                        asyncio.run_coroutine_threadsafe(coro_msg, self.bot.loop)
                        coro_disc = self._disconnect_voice_safe(guild_id)
                        asyncio.run_coroutine_threadsafe(coro_disc, self.bot.loop)

            try:
                voice_client.play(source, after=after_playing_restart)
            except Exception: pass
            
            if state.is_paused:
                voice_client.pause()
                state.pause_start = time.time()

    async def toggle_pause(self, guild_id, interaction=None):
        guild = self.bot.get_guild(guild_id)
        if not guild: return
            
        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
        state = self._get_state(guild_id)
        
        if not voice_client:
            if interaction: await interaction.send("Bot is not connected.", ephemeral=True)
            return

        if state.is_paused:
            if voice_client.is_paused():
                voice_client.resume()
            state.is_paused = False
            state.start_time += (time.time() - state.pause_start)
        else:
            voice_client.pause()
            state.is_paused = True
            state.pause_start = time.time()
            elapsed_wall = state.pause_start - state.start_time
            state.elapsed_saved = elapsed_wall * state.current_speed
            

    async def stop_music(self, guild_id, interaction=None, new_track_starting=False):
        guild = self.bot.get_guild(guild_id)
        if not guild: return

        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
        state = self._get_state(guild_id)
        
        if state.menu_timeout_task:
            state.menu_timeout_task.cancel()
            state.menu_timeout_task = None

        state.is_playing = False 
        state.is_paused = False
        
        if voice_client:
            if new_track_starting:
                 voice_client.stop() 
            else:
                 await voice_client.disconnect()

        if not new_track_starting and state.interaction_message:
            try:
                final_embed = self._create_embed(state, status="stopped")
                await state.interaction_message.edit(embed=final_embed, view=None)
            except Exception as e:
                self.plogging.warn(f"Error editing stop message: {e}")

    # --- Main Entry Point (Restored) ---

    async def play_youtube_logic(self, interaction: disnake.ApplicationCommandInteraction, url: str, volume: float = 0.5, repeat: bool = False, bass_boost: bool = False):
        await interaction.response.defer()
        
        if not interaction.author.voice:
            await interaction.edit_original_response(content="You are not in a voice channel.")
            return

        state = self._get_state(interaction.guild.id)
        
        if state.is_playing:
             await self.stop_music(interaction.guild.id, new_track_starting=True)

        voice_channel = interaction.author.voice.channel
        
        try:
            voice_client = await self._safe_connect_to_channel(voice_channel)
        except Exception as e:
            await interaction.edit_original_response(content=f"Error connecting: {e}")
            return

        state.active_url = url
        state.volume = volume
        state.repeat = repeat
        state.bass_boost = bass_boost
        # Сброс остальных эффектов при старте нового трека
        state.slowed = False
        state.sped_up = False
        state.voice_channel = voice_channel
        
        embed = disnake.Embed(title="Loading...", color=disnake.Color.blurple())
        msg = await interaction.edit_original_response(content=None, embed=embed, view=None)
        state.interaction_message = msg

        await self._play_track(interaction.guild.id)

    # --- Safe Connect & Bot Sound (No changes needed) ---

    async def _safe_connect_to_channel(self, channel: disnake.VoiceChannel) -> disnake.VoiceClient:
        guild = channel.guild
        lock = self._get_lock(guild.id)
        async with lock:
            voice_client: disnake.VoiceClient | None = disnake.utils.get(self.bot.voice_clients, guild=guild)
            if voice_client and voice_client.is_connected():
                try:
                    vc_channel = getattr(voice_client, "channel", None)
                    if vc_channel and vc_channel.id == channel.id:
                        return voice_client
                except Exception:
                    voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
                try:
                    await voice_client.disconnect()
                    await asyncio.sleep(0.5)
                except Exception: pass

            try:
                new_vc = await channel.connect(reconnect=False)
                return new_vc
            except Exception:
                voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
                if voice_client and voice_client.is_connected():
                    return voice_client
                try:
                    await asyncio.sleep(0.3)
                    new_vc = await channel.connect(reconnect=False)
                    return new_vc
                except Exception as e2:
                    self.plogging.error(f"Could not connect to channel {channel.id}: {e2}")
                    raise

    async def bot_sound(self, play_audio_func=None, *play_audio_args, channel_id=None):
        interrupted_state = None
        target_guild = None

        if channel_id:
            ch = self.bot.get_channel(channel_id)
            if ch: target_guild = ch.guild
        elif self.bot.guilds:
            target_guild = self.bot.guilds[0]

        if self.priority_mode and target_guild:
            state = self._get_state(target_guild.id)
            if state.is_playing:
                if state.is_paused:
                    current_elapsed = state.pause_start - state.start_time
                else:
                    current_elapsed = time.time() - state.start_time
                
                state.elapsed_saved = max(0, current_elapsed * state.current_speed)
                
                interrupted_state = {
                    'url': state.active_url,
                    'volume': state.volume,
                    'seek': state.elapsed_saved,
                    'channel': state.voice_channel,
                    'repeat': state.repeat,
                    'bass_boost': state.bass_boost,
                    'slowed': state.slowed,
                    'sped_up': state.sped_up,
                    'was_paused': state.is_paused # ADDED: Save pause state
                }
                
                vc = disnake.utils.get(self.bot.voice_clients, guild=target_guild)
                if vc: 
                    state.is_playing = False 
                    vc.stop()
                await asyncio.sleep(0.2)

        try:
            if channel_id is not None:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        voice = await self._safe_connect_to_channel(channel)
                        if play_audio_func: await play_audio_func(*play_audio_args, voice)
                        else: await asyncio.sleep(0.5)
                        if voice and voice.is_connected() and voice.channel.id == channel.id:
                            await voice.disconnect()
                    except Exception as e: self.plogging.error(f"BotSound Error: {e}")
            else:
               if self.bot.guilds:
                   guild = self.bot.guilds[0]
                   channels_with_users = [ch for ch in guild.voice_channels if len(ch.members) > 0]
                   for channel in channels_with_users:
                       try:
                           voice = await self._safe_connect_to_channel(channel)
                           if play_audio_func: await play_audio_func(*play_audio_args, voice)
                           else: await asyncio.sleep(0.5)
                           if voice and voice.is_connected() and voice.channel.id == channel.id:
                               await voice.disconnect()
                       except Exception: pass
        except Exception as e:
            self.plogging.error(f"Error in bot_sound: {e}")

        if interrupted_state and target_guild:
            await asyncio.sleep(0.5)
            try:
                channel = interrupted_state['channel']
                voice_client = await self._safe_connect_to_channel(channel)
                
                source, title, duration = await self._get_audio_source(
                    interrupted_state['url'], 
                    seek_time=int(interrupted_state['seek']),
                    bass_boost=interrupted_state['bass_boost'],
                    slowed=interrupted_state['slowed'],
                    sped_up=interrupted_state['sped_up']
                )
                
                if source:
                    source = disnake.PCMVolumeTransformer(source)
                    source.volume = interrupted_state['volume']
                    
                    state = self._get_state(target_guild.id)
                    state.is_playing = True
                    state.is_paused = interrupted_state['was_paused'] # RESTORE: Set paused state
                    
                    cur_speed = 1.0
                    if interrupted_state['slowed']: cur_speed = 0.5
                    elif interrupted_state['sped_up']: cur_speed = 2.0
                    
                    state.start_time = time.time() - (interrupted_state['seek'] / cur_speed)
                    state.voice_channel = channel

                    def after_playing(error):
                         if state.is_playing:
                            if state.repeat:
                                coro = self._play_track(target_guild.id)
                                asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                            else:
                                state.is_playing = False
                                coro_msg = self.update_player_message(target_guild.id, force_status="stopped")
                                asyncio.run_coroutine_threadsafe(coro_msg, self.bot.loop)
                                coro_disc = self._disconnect_voice_safe(target_guild.id)
                                asyncio.run_coroutine_threadsafe(coro_disc, self.bot.loop)

                    voice_client.play(source, after=after_playing)
                    
                    # RESTORE: Immediate pause if it was paused
                    if state.is_paused:
                        voice_client.pause()
                        state.pause_start = time.time()

            except Exception as e:
                self.plogging.error(f"Failed to resume music: {e}")

    async def play_audio(self, path_to_file, time_sleep, volume, voice: disnake.VoiceClient):
        audio_path = os.path.join("sounds", path_to_file)
        if not os.path.exists(audio_path): return
        try:
            if voice.is_playing(): voice.stop()
        except: pass
        try:
            audio_source = disnake.FFmpegPCMAudio(audio_path)
            audio_source = disnake.PCMVolumeTransformer(audio_source)
            audio_source.volume = volume
            voice.play(audio_source)
            await asyncio.sleep(time_sleep)
            if voice.is_playing(): voice.stop()
        except Exception as e:
            self.plogging.error(f"Error playing audio: {e}")

class MusicCog(commands.Cog):
    def __init__(self, bot, sound_player: PlaySoundOnBot):
        self.bot = bot
        self.sound_player = sound_player

    @commands.slash_command(name="play", description="Play music from YouTube")
    async def play(
        self, 
        inter: disnake.ApplicationCommandInteraction, 
        url: str, 
        volume: float = commands.Param(default=0.5, ge=0.0, le=2.0),
        repeat: bool = False,
        bass_boost: bool = False
    ):
        await self.sound_player.play_youtube_logic(inter, url, volume, repeat, bass_boost)