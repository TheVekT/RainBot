import os
import asyncio
import time
import shutil
from pathlib import Path
import disnake
from disnake.ext import commands
from rainbot.utils.plogging import Plogging
import yt_dlp

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

        self.start_time = 0.0
        self.pause_start = 0.0
        self.elapsed_saved = 0.0

        self.is_playing = False
        self.is_paused = False
        self.volume = 0.5
        self.repeat = False

        self.bass_boost = False
        self.slowed = False
        self.sped_up = False

        self.voice_channel = None
        self.interaction_message = None
        self.menu_timeout_task: asyncio.Task = None

    @property
    def current_speed(self):
        if self.slowed:
            return 0.5
        if self.sped_up:
            return 2.0
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

        style_bb = disnake.ButtonStyle.green if current_state.bass_boost else disnake.ButtonStyle.gray
        label_bb = "Bass: ON" if current_state.bass_boost else "Bass: OFF"
        self.add_item(disnake.ui.Button(label=label_bb, style=style_bb, custom_id="effect_bass", row=0))

        style_slow = disnake.ButtonStyle.green if current_state.slowed else disnake.ButtonStyle.gray
        self.add_item(disnake.ui.Button(label="Slow (0.5x)", style=style_slow, custom_id="effect_slow", row=1))

        style_fast = disnake.ButtonStyle.green if current_state.sped_up else disnake.ButtonStyle.gray
        self.add_item(disnake.ui.Button(label="Fast (2.0x)", style=style_fast, custom_id="effect_fast", row=1))

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
        self.YTDL_OPTS = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "noplaylist": True,
            "skip_download": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android_vr"]
                }
            },
        }

    # --- Utilities ---

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _resolve_ffmpeg_executable(self) -> str | None:
        local_ffmpeg_dir = self._project_root() / "ffmpeg"
        for name in ["ffmpeg", "ffmpeg.exe"]:
            candidate = local_ffmpeg_dir / name
            if candidate.exists():
                return str(candidate)
        return shutil.which("ffmpeg")

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()
        return self._guild_locks[guild_id]

    def _get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.music_states:
            self.music_states[guild_id] = GuildMusicState()
        return self.music_states[guild_id]

    # --- Audio extraction (yt-dlp only) ---

    def _extract_ytdlp_sync(self, url):
        """Synchronous yt-dlp extraction, runs in executor."""
        with yt_dlp.YoutubeDL(self.YTDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info:
                info = info["entries"][0]
            stream_url = info["url"]
            title = info.get("title")
            duration = info.get("duration")
            self.plogging.info(f"yt-dlp extracted: {title}")
            return stream_url, title, duration

    async def _get_audio_source(self, url, seek_time=0, bass_boost=False, slowed=False, sped_up=False):
        """Extract audio and return FFmpegPCMAudio source."""
        loop = asyncio.get_running_loop()
        try:
            stream_url, title, duration = await loop.run_in_executor(
                None, lambda: self._extract_ytdlp_sync(url)
            )
        except Exception as e:
            self.plogging.error(f"Extraction Error: {e}")
            return None, None, None

        if not stream_url:
            return None, None, None

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

        opts['options'] = f'-vn -af "{",".join(filters)}"' if filters else '-vn'

        return disnake.FFmpegPCMAudio(stream_url, **opts), title, duration

    # --- Embed helpers ---

    def _create_embed(self, state: GuildMusicState, status="playing"):
        if status == "playing":
            embed = disnake.Embed(title="Now playing", color=disnake.Color.blurple())
            embed.add_field(name="Title", value=state.title, inline=False)
            embed.add_field(name="Duration", value=f"{state.duration // 60}:{state.duration % 60:02d}", inline=True)

            repeat_status = "On" if state.repeat else "Off"
            embed.add_field(name="Options", value=f"Volume: {int(state.volume * 100)}%\nRepeat: {repeat_status}", inline=True)

            effects = []
            if state.bass_boost:
                effects.append("Bass Boost")
            if state.slowed:
                effects.append("Speed: 0.5x")
            if state.sped_up:
                effects.append("Speed: 2.0x")
            if effects:
                embed.add_field(name="Effects", value=", ".join(effects), inline=False)
            return embed

        elif status == "stopped":
            embed = disnake.Embed(title="Played", color=disnake.Color.dark_grey())
            embed.description = f"**{state.title}**\n{state.active_url}" if state.title and state.active_url else "Unknown track"
            return embed

        return None

    # --- Voice connection management ---

    async def _force_cleanup_voice(self, guild: disnake.Guild):
        """Force-remove all voice clients for a guild, cleaning up internal state."""
        to_remove = [vc for vc in self.bot.voice_clients if vc.guild and vc.guild.id == guild.id]
        for vc in to_remove:
            try:
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
            except Exception:
                pass
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            try:
                vc.cleanup()
            except Exception:
                pass
            try:
                if vc in self.bot.voice_clients:
                    self.bot.voice_clients.remove(vc)
            except (ValueError, AttributeError):
                pass
        if to_remove:
            await asyncio.sleep(0.5)

    async def _wait_for_voice_ready(self, vc: disnake.VoiceClient, timeout: float = 10.0) -> bool:
        """Wait for voice WebSocket to actually establish connection."""
        start = time.time()
        while time.time() - start < timeout:
            if vc.is_connected():
                return True
            await asyncio.sleep(0.1)
        return False

    async def _safe_connect_to_channel(self, channel: disnake.VoiceChannel, max_retries: int = 3) -> disnake.VoiceClient:
        """Safely connect to a voice channel with full retry logic."""
        guild = channel.guild
        lock = self._get_lock(guild.id)

        async with lock:
            for attempt in range(1, max_retries + 1):
                voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)

                if voice_client is not None:
                    if voice_client.is_connected():
                        vc_channel = getattr(voice_client, "channel", None)
                        if vc_channel and vc_channel.id == channel.id:
                            return voice_client
                        try:
                            await voice_client.move_to(channel)
                            if await self._wait_for_voice_ready(voice_client, timeout=5.0):
                                return voice_client
                        except Exception as e:
                            self.plogging.warn(f"move_to failed: {e}")

                    self.plogging.info("Stale voice client, forcing cleanup...")
                    await self._force_cleanup_voice(guild)

                try:
                    new_vc = await channel.connect(timeout=15.0, reconnect=True)
                    if await self._wait_for_voice_ready(new_vc, timeout=10.0):
                        self.plogging.info(f"Connected to {channel.name}")
                        return new_vc
                    else:
                        self.plogging.warn(f"Voice not ready after connect (attempt {attempt})")
                        await self._force_cleanup_voice(guild)
                except disnake.errors.ClientException as e:
                    self.plogging.warn(f"ClientException: {e} (attempt {attempt})")
                    await self._force_cleanup_voice(guild)
                except asyncio.TimeoutError:
                    self.plogging.warn(f"Timeout connecting (attempt {attempt})")
                    await self._force_cleanup_voice(guild)
                except Exception as e:
                    self.plogging.error(f"Connect error: {e} (attempt {attempt})")
                    await self._force_cleanup_voice(guild)

            raise Exception(f"Failed to connect to {channel.name} after {max_retries} attempts")

    async def _disconnect_voice_safe(self, guild_id):
        """Safely disconnect from voice."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client:
            try:
                await voice_client.disconnect(force=True)
            except Exception:
                pass

    # --- Player message updates ---

    async def _revert_to_main_delayed(self, guild_id):
        try:
            await asyncio.sleep(10)
            await self.update_player_message(guild_id, view_type="main")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.plogging.warn(f"Revert task error: {e}")

    async def update_player_message(self, guild_id, view_type="main", force_status=None):
        state = self._get_state(guild_id)
        if not state.interaction_message:
            return

        if state.menu_timeout_task:
            state.menu_timeout_task.cancel()
            state.menu_timeout_task = None

        status = force_status or ("playing" if state.is_playing else "stopped")

        if status == "stopped":
            embed = self._create_embed(state, status="stopped")
            try:
                await state.interaction_message.edit(embed=embed, view=None)
            except Exception:
                pass
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

    # --- Playback logic ---

    async def _play_track(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        state = self._get_state(guild_id)
        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)

        if not voice_client or not voice_client.is_connected():
            self.plogging.error("Voice client unavailable for playback.")
            return

        source, title, duration = await self._get_audio_source(
            state.active_url,
            bass_boost=state.bass_boost,
            slowed=state.slowed,
            sped_up=state.sped_up
        )
        if not source:
            self.plogging.error("Failed to get audio source.")
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
                    asyncio.run_coroutine_threadsafe(self._play_track(guild_id), self.bot.loop)
                else:
                    state.is_playing = False
                    asyncio.run_coroutine_threadsafe(self.update_player_message(guild_id, force_status="stopped"), self.bot.loop)
                    asyncio.run_coroutine_threadsafe(self._disconnect_voice_safe(guild_id), self.bot.loop)

        try:
            if voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.05)
            voice_client.play(source, after=after_playing)
            await self.update_player_message(guild_id, view_type="main")
        except Exception as e:
            self.plogging.error(f"Failed to start playback: {e}")

    # --- Controls ---

    async def change_volume(self, guild_id, change_amount):
        state = self._get_state(guild_id)
        state.volume = max(0.0, min(2.0, state.volume + change_amount))

        guild = self.bot.get_guild(guild_id)
        if guild:
            vc = disnake.utils.get(self.bot.voice_clients, guild=guild)
            if vc and vc.source:
                try:
                    vc.source.volume = state.volume
                except Exception:
                    pass

        await self.update_player_message(guild_id, view_type="volume")

    async def toggle_repeat(self, guild_id):
        state = self._get_state(guild_id)
        state.repeat = not state.repeat
        await self.update_player_message(guild_id, view_type="options")

    async def toggle_effect(self, guild_id, effect_type):
        """Toggle an audio effect and restart the stream."""
        state = self._get_state(guild_id)

        if effect_type == 'bass':
            state.bass_boost = not state.bass_boost
        elif effect_type == 'slow':
            state.slowed = not state.slowed
            if state.slowed:
                state.sped_up = False
        elif effect_type == 'fast':
            state.sped_up = not state.sped_up
            if state.sped_up:
                state.slowed = False

        await self._reload_player_state(guild_id)
        await self.update_player_message(guild_id, view_type="effects")

    async def _reload_player_state(self, guild_id):
        """Hot-swap: restart playback with new effects while preserving position."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        state = self._get_state(guild_id)
        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)

        if not state.is_playing or not voice_client:
            return

        # Calculate current position
        if state.is_paused:
            current_pos = state.elapsed_saved
        else:
            current_pos = (time.time() - state.start_time) * state.current_speed

        # Stop current playback (set flag first to prevent after_playing callback)
        state.is_playing = False
        if voice_client.is_connected():
            voice_client.stop()
        await asyncio.sleep(0.1)

        # Reconnect if needed
        if not voice_client.is_connected():
            if not state.voice_channel:
                return
            try:
                voice_client = await self._safe_connect_to_channel(state.voice_channel)
            except Exception:
                return

        # Create new source at the saved position
        source, _, _ = await self._get_audio_source(
            state.active_url,
            seek_time=int(current_pos),
            bass_boost=state.bass_boost,
            slowed=state.slowed,
            sped_up=state.sped_up
        )
        if not source:
            return

        source = disnake.PCMVolumeTransformer(source)
        source.volume = state.volume

        state.start_time = time.time() - (current_pos / state.current_speed)
        state.is_playing = True

        def after_playing_restart(error):
            if state.is_playing:
                if state.repeat:
                    asyncio.run_coroutine_threadsafe(self._play_track(guild_id), self.bot.loop)
                else:
                    state.is_playing = False
                    asyncio.run_coroutine_threadsafe(self.update_player_message(guild_id, force_status="stopped"), self.bot.loop)
                    asyncio.run_coroutine_threadsafe(self._disconnect_voice_safe(guild_id), self.bot.loop)

        try:
            voice_client.play(source, after=after_playing_restart)
        except Exception:
            pass

        if state.is_paused:
            voice_client.pause()
            state.pause_start = time.time()

    async def toggle_pause(self, guild_id, interaction=None):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
        state = self._get_state(guild_id)

        if not voice_client:
            if interaction:
                await interaction.send("Bot is not connected.", ephemeral=True)
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
            state.elapsed_saved = (state.pause_start - state.start_time) * state.current_speed

    async def stop_music(self, guild_id, interaction=None, new_track_starting=False):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        voice_client = disnake.utils.get(self.bot.voice_clients, guild=guild)
        state = self._get_state(guild_id)

        if state.menu_timeout_task:
            state.menu_timeout_task.cancel()
            state.menu_timeout_task = None

        state.is_playing = False
        state.is_paused = False

        if voice_client:
            if new_track_starting:
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                    await asyncio.sleep(0.05)
            else:
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass

        if not new_track_starting and state.interaction_message:
            try:
                final_embed = self._create_embed(state, status="stopped")
                await state.interaction_message.edit(embed=final_embed, view=None)
            except Exception as e:
                self.plogging.warn(f"Error editing stop message: {e}")

    # --- Main entry point ---

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
            await self._safe_connect_to_channel(voice_channel)
        except Exception as e:
            await interaction.edit_original_response(content=f"Error connecting: {e}")
            return

        state.active_url = url
        state.volume = volume
        state.repeat = repeat
        state.bass_boost = bass_boost
        state.slowed = False
        state.sped_up = False
        state.voice_channel = voice_channel

        embed = disnake.Embed(title="Loading...", color=disnake.Color.blurple())
        msg = await interaction.edit_original_response(content=None, embed=embed, view=None)
        state.interaction_message = msg

        await self._play_track(interaction.guild.id)

    # --- Bot sound (priority interruption system) ---

    async def bot_sound(self, play_audio_func=None, *play_audio_args, channel_id=None):
        interrupted_state = None
        target_guild = None

        if channel_id:
            ch = self.bot.get_channel(channel_id)
            if ch:
                target_guild = ch.guild
        elif self.bot.guilds:
            target_guild = self.bot.guilds[0]

        # Save current music state if playing (priority mode)
        if self.priority_mode and target_guild:
            state = self._get_state(target_guild.id)
            if state.is_playing:
                current_elapsed = (state.pause_start - state.start_time) if state.is_paused else (time.time() - state.start_time)
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
                    'was_paused': state.is_paused,
                }

                vc = disnake.utils.get(self.bot.voice_clients, guild=target_guild)
                if vc:
                    state.is_playing = False
                    vc.stop()
                await asyncio.sleep(0.2)

        # Play the bot sound
        try:
            if channel_id is not None:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        voice = await self._safe_connect_to_channel(channel)
                        if play_audio_func:
                            await play_audio_func(*play_audio_args, voice)
                        else:
                            await asyncio.sleep(0.5)
                        if voice and voice.is_connected() and voice.channel.id == channel.id:
                            await voice.disconnect(force=True)
                    except Exception as e:
                        self.plogging.error(f"BotSound Error: {e}")
            else:
                if self.bot.guilds:
                    guild = self.bot.guilds[0]
                    for channel in [ch for ch in guild.voice_channels if len(ch.members) > 0]:
                        try:
                            voice = await self._safe_connect_to_channel(channel)
                            if play_audio_func:
                                await play_audio_func(*play_audio_args, voice)
                            else:
                                await asyncio.sleep(0.5)
                            if voice and voice.is_connected() and voice.channel.id == channel.id:
                                await voice.disconnect(force=True)
                        except Exception:
                            pass
        except Exception as e:
            self.plogging.error(f"Error in bot_sound: {e}")

        # Resume interrupted music
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
                    state.is_paused = interrupted_state['was_paused']

                    cur_speed = 0.5 if interrupted_state['slowed'] else (2.0 if interrupted_state['sped_up'] else 1.0)
                    state.start_time = time.time() - (interrupted_state['seek'] / cur_speed)
                    state.voice_channel = channel

                    def after_playing(error):
                        if state.is_playing:
                            if state.repeat:
                                asyncio.run_coroutine_threadsafe(self._play_track(target_guild.id), self.bot.loop)
                            else:
                                state.is_playing = False
                                asyncio.run_coroutine_threadsafe(self.update_player_message(target_guild.id, force_status="stopped"), self.bot.loop)
                                asyncio.run_coroutine_threadsafe(self._disconnect_voice_safe(target_guild.id), self.bot.loop)

                    voice_client.play(source, after=after_playing)

                    if state.is_paused:
                        voice_client.pause()
                        state.pause_start = time.time()

            except Exception as e:
                self.plogging.error(f"Failed to resume music: {e}")

    async def play_audio(self, path_to_file, time_sleep, volume, voice: disnake.VoiceClient):
        audio_path = self._project_root() / "sounds" / path_to_file
        if not audio_path.exists():
            return
        try:
            if voice.is_playing():
                voice.stop()
        except Exception:
            pass
        try:
            ffmpeg_executable = self._resolve_ffmpeg_executable() or "ffmpeg"
            audio_source = disnake.FFmpegPCMAudio(str(audio_path), executable=ffmpeg_executable)
            audio_source = disnake.PCMVolumeTransformer(audio_source)
            audio_source.volume = volume
            voice.play(audio_source)
            await asyncio.sleep(time_sleep)
            if voice.is_playing():
                voice.stop()
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
