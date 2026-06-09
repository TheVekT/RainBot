"""YouTube music player module.

Handles yt-dlp audio extraction, FFmpeg source creation, per-guild playback
state tracking (position, effects, volume), and player-message updates.
Delegates all voice-connection work to a ``VoiceManager``.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import disnake
import yt_dlp

from modules.voice_core.manager import VoiceManager

logger = logging.getLogger(__name__)

# ── FFmpeg defaults ──────────────────────────────────────────────────
FFMPEG_BASE_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# ── yt-dlp defaults ─────────────────────────────────────────────────
YTDL_OPTS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "quiet": True,
    "noplaylist": True,
    "skip_download": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android_vr"],
        },
    },
}


# ── Per-guild music state ───────────────────────────────────────────

class GuildMusicState:
    """Mutable playback state for a single guild."""

    def __init__(self) -> None:
        self.active_url: str | None = None
        self.title: str | None = None
        self.duration: int = 0

        self.start_time: float = 0.0
        self.pause_start: float = 0.0
        self.elapsed_saved: float = 0.0

        self.is_playing: bool = False
        self.is_paused: bool = False
        self.volume: float = 0.5
        self.repeat: bool = False

        self.bass_boost: bool = False
        self.slowed: bool = False
        self.sped_up: bool = False

        self.voice_channel: disnake.VoiceChannel | None = None
        self.interaction_message: disnake.Message | None = None
        self.menu_timeout_task: asyncio.Task | None = None

    @property
    def current_speed(self) -> float:
        """Return the effective playback speed multiplier."""
        if self.slowed:
            return 0.5
        if self.sped_up:
            return 2.0
        return 1.0


# ── YouTube Player ──────────────────────────────────────────────────

class YouTubePlayer:
    """YouTube music playback engine.

    All voice-connection operations are delegated to the provided
    ``VoiceManager``.  This class is responsible for:

    * Audio extraction via *yt-dlp*.
    * Building FFmpeg audio sources (with effects & seek).
    * Per-guild playback state (``GuildMusicState``).
    * Player-message embed / view lifecycle.

    Parameters
    ----------
    bot : commands.Bot
        The Discord bot instance.
    manager : VoiceManager
        Shared voice-connection manager.
    """

    def __init__(
        self,
        bot: disnake.ext.commands.Bot,
        manager: VoiceManager,
    ) -> None:
        self._bot = bot
        self._manager = manager
        self._states: dict[int, GuildMusicState] = {}

        # Register save/restore callbacks so the VoiceManager can
        # interrupt and resume music playback generically.
        self._manager.register_player(
            save_callback=self._save_state,
            restore_callback=self._restore_state,
        )

    # ── State helpers ────────────────────────────────────────────────

    def get_state(self, guild_id: int) -> GuildMusicState:
        """Return the music state for *guild_id*, creating if needed."""
        if guild_id not in self._states:
            self._states[guild_id] = GuildMusicState()
        return self._states[guild_id]

    # ── Audio extraction ─────────────────────────────────────────────

    def _extract_sync(self, url: str) -> tuple[str, str | None, int | None]:
        """Synchronous yt-dlp extraction (meant to run in an executor)."""
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info:
                info = info["entries"][0]
            stream_url: str = info["url"]
            title = info.get("title")
            duration = info.get("duration")
            logger.info("yt-dlp extracted: %s", title)
            return stream_url, title, duration

    async def _get_audio_source(
        self,
        url: str,
        seek_time: int = 0,
        bass_boost: bool = False,
        slowed: bool = False,
        sped_up: bool = False,
    ) -> tuple[disnake.FFmpegPCMAudio | None, str | None, int | None]:
        """Extract audio and return an ``FFmpegPCMAudio`` source."""
        loop = asyncio.get_running_loop()
        try:
            stream_url, title, duration = await loop.run_in_executor(
                None, lambda: self._extract_sync(url),
            )
        except Exception as e:
            logger.error("Extraction error: %s", e)
            return None, None, None

        if not stream_url:
            return None, None, None

        opts = FFMPEG_BASE_OPTIONS.copy()
        if seek_time > 0:
            opts["before_options"] += f" -ss {seek_time}"

        filters: list[str] = []
        if bass_boost:
            filters.append("bass=g=20")
        if slowed:
            filters.append("atempo=0.5")
        elif sped_up:
            filters.append("atempo=2.0")

        opts["options"] = (
            f'-vn -af "{",".join(filters)}"' if filters else "-vn"
        )

        return disnake.FFmpegPCMAudio(stream_url, **opts), title, duration

    # ── Embed creation ───────────────────────────────────────────────

    @staticmethod
    def _create_embed(
        state: GuildMusicState, status: str = "playing",
    ) -> disnake.Embed | None:
        """Build the player embed for the given *status*."""
        if status == "playing":
            embed = disnake.Embed(
                title="Now playing", color=disnake.Color.blurple(),
            )
            embed.add_field(name="Title", value=state.title, inline=False)
            embed.add_field(
                name="Duration",
                value=f"{state.duration // 60}:{state.duration % 60:02d}",
                inline=True,
            )

            repeat_status = "On" if state.repeat else "Off"
            embed.add_field(
                name="Options",
                value=(
                    f"Volume: {int(state.volume * 100)}%\n"
                    f"Repeat: {repeat_status}"
                ),
                inline=True,
            )

            effects: list[str] = []
            if state.bass_boost:
                effects.append("Bass Boost")
            if state.slowed:
                effects.append("Speed: 0.5x")
            if state.sped_up:
                effects.append("Speed: 2.0x")
            if effects:
                embed.add_field(
                    name="Effects", value=", ".join(effects), inline=False,
                )
            return embed

        if status == "stopped":
            embed = disnake.Embed(
                title="Played", color=disnake.Color.dark_grey(),
            )
            embed.description = (
                f"**{state.title}**\n{state.active_url}"
                if state.title and state.active_url
                else "Unknown track"
            )
            return embed

        return None

    # ── Player-message lifecycle ─────────────────────────────────────

    async def _revert_to_main_delayed(self, guild_id: int) -> None:
        """After 10 s on a sub-menu, revert the embed back to main."""
        try:
            await asyncio.sleep(10)
            await self.update_player_message(guild_id, view_type="main")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Revert task error: %s", e)

    async def update_player_message(
        self,
        guild_id: int,
        view_type: str = "main",
        force_status: str | None = None,
    ) -> None:
        """Re-render the player message with the specified view."""
        # Deferred import to avoid circular dependency with views module.
        from modules.youtube_player.views import (
            EffectsView,
            MusicView,
            OptionsView,
            VolumeView,
        )

        state = self.get_state(guild_id)
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
                state.menu_timeout_task = asyncio.create_task(
                    self._revert_to_main_delayed(guild_id),
                )
        except Exception as e:
            logger.warning("Failed to update player message: %s", e)

    # ── Internal playback ────────────────────────────────────────────

    async def _play_track(self, guild_id: int) -> None:
        """Start playing the track stored in the guild's state."""
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return

        state = self.get_state(guild_id)
        vc = self._manager.get_voice_client(guild_id)

        if not vc or not vc.is_connected():
            logger.error("Voice client unavailable for playback.")
            return

        source, title, duration = await self._get_audio_source(
            state.active_url,
            bass_boost=state.bass_boost,
            slowed=state.slowed,
            sped_up=state.sped_up,
        )
        if not source:
            logger.error("Failed to get audio source.")
            return

        source = disnake.PCMVolumeTransformer(source)
        source.volume = state.volume

        state.title = title
        state.duration = duration
        state.start_time = time.time()
        state.elapsed_saved = 0.0
        state.is_playing = True
        state.is_paused = False

        def after_playing(error: Exception | None) -> None:
            if error:
                logger.error("Player error: %s", error)
            if state.is_playing:
                if state.repeat:
                    asyncio.run_coroutine_threadsafe(
                        self._play_track(guild_id), self._bot.loop,
                    )
                else:
                    state.is_playing = False
                    asyncio.run_coroutine_threadsafe(
                        self.update_player_message(
                            guild_id, force_status="stopped",
                        ),
                        self._bot.loop,
                    )
                    asyncio.run_coroutine_threadsafe(
                        self._manager.disconnect(guild_id), self._bot.loop,
                    )

        try:
            if vc.is_playing():
                vc.stop()
                await asyncio.sleep(0.05)
            vc.play(source, after=after_playing)
            await self.update_player_message(guild_id, view_type="main")
        except Exception as e:
            logger.error("Failed to start playback: %s", e)

    async def _reload_with_effects(self, guild_id: int) -> None:
        """Hot-swap: restart playback preserving position but with new effects."""
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return

        state = self.get_state(guild_id)
        vc = self._manager.get_voice_client(guild_id)

        if not state.is_playing or not vc:
            return

        # Calculate current position.
        if state.is_paused:
            current_pos = state.elapsed_saved
        else:
            current_pos = (time.time() - state.start_time) * state.current_speed

        # Stop current playback (flag first to prevent after callback).
        state.is_playing = False
        if vc.is_connected():
            vc.stop()
        await asyncio.sleep(0.1)

        # Reconnect if needed.
        if not vc.is_connected():
            if not state.voice_channel:
                return
            try:
                vc = await self._manager.connect(state.voice_channel)
            except Exception:
                return

        # Create new source at saved position.
        source, _, _ = await self._get_audio_source(
            state.active_url,
            seek_time=int(current_pos),
            bass_boost=state.bass_boost,
            slowed=state.slowed,
            sped_up=state.sped_up,
        )
        if not source:
            return

        source = disnake.PCMVolumeTransformer(source)
        source.volume = state.volume

        state.start_time = time.time() - (current_pos / state.current_speed)
        state.is_playing = True

        def after_playing(error: Exception | None) -> None:
            if state.is_playing:
                if state.repeat:
                    asyncio.run_coroutine_threadsafe(
                        self._play_track(guild_id), self._bot.loop,
                    )
                else:
                    state.is_playing = False
                    asyncio.run_coroutine_threadsafe(
                        self.update_player_message(
                            guild_id, force_status="stopped",
                        ),
                        self._bot.loop,
                    )
                    asyncio.run_coroutine_threadsafe(
                        self._manager.disconnect(guild_id), self._bot.loop,
                    )

        try:
            vc.play(source, after=after_playing)
        except Exception:
            pass

        if state.is_paused:
            vc.pause()
            state.pause_start = time.time()

    # ── Public controls ──────────────────────────────────────────────

    async def play(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        url: str,
        volume: float = 0.5,
        repeat: bool = False,
        bass_boost: bool = False,
    ) -> None:
        """Start playing a YouTube URL (main entry point from the cog)."""
        await interaction.response.defer()

        if not interaction.author.voice:
            await interaction.edit_original_response(
                content="You are not in a voice channel.",
            )
            return

        state = self.get_state(interaction.guild.id)

        if state.is_playing:
            await self.stop(interaction.guild.id, new_track_starting=True)

        voice_channel = interaction.author.voice.channel

        try:
            await self._manager.connect(voice_channel)
        except Exception as e:
            await interaction.edit_original_response(
                content=f"Error connecting: {e}",
            )
            return

        state.active_url = url
        state.volume = volume
        state.repeat = repeat
        state.bass_boost = bass_boost
        state.slowed = False
        state.sped_up = False
        state.voice_channel = voice_channel

        embed = disnake.Embed(title="Loading...", color=disnake.Color.blurple())
        msg = await interaction.edit_original_response(
            content=None, embed=embed, view=None,
        )
        state.interaction_message = msg

        await self._play_track(interaction.guild.id)

    async def stop(
        self,
        guild_id: int,
        interaction: disnake.MessageInteraction | None = None,
        new_track_starting: bool = False,
    ) -> None:
        """Stop playback and optionally disconnect."""
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return

        vc = self._manager.get_voice_client(guild_id)
        state = self.get_state(guild_id)

        if state.menu_timeout_task:
            state.menu_timeout_task.cancel()
            state.menu_timeout_task = None

        state.is_playing = False
        state.is_paused = False

        if vc:
            if new_track_starting:
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
                    await asyncio.sleep(0.05)
            else:
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass

        if not new_track_starting and state.interaction_message:
            try:
                final_embed = self._create_embed(state, status="stopped")
                await state.interaction_message.edit(
                    embed=final_embed, view=None,
                )
            except Exception as e:
                logger.warning("Error editing stop message: %s", e)

    async def toggle_pause(
        self,
        guild_id: int,
        interaction: disnake.MessageInteraction | None = None,
    ) -> None:
        """Toggle pause/resume for the current track."""
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return

        vc = self._manager.get_voice_client(guild_id)
        state = self.get_state(guild_id)

        if not vc:
            if interaction:
                await interaction.send(
                    "Bot is not connected.", ephemeral=True,
                )
            return

        if state.is_paused:
            if vc.is_paused():
                vc.resume()
            state.is_paused = False
            state.start_time += time.time() - state.pause_start
        else:
            vc.pause()
            state.is_paused = True
            state.pause_start = time.time()
            state.elapsed_saved = (
                (state.pause_start - state.start_time) * state.current_speed
            )

    async def change_volume(self, guild_id: int, change_amount: float) -> None:
        """Adjust volume by *change_amount* (clamped 0–200 %)."""
        state = self.get_state(guild_id)
        state.volume = max(0.0, min(2.0, state.volume + change_amount))

        guild = self._bot.get_guild(guild_id)
        if guild:
            vc = self._manager.get_voice_client(guild_id)
            if vc and vc.source:
                try:
                    vc.source.volume = state.volume
                except Exception:
                    pass

        await self.update_player_message(guild_id, view_type="volume")

    async def toggle_repeat(self, guild_id: int) -> None:
        """Toggle the repeat flag."""
        state = self.get_state(guild_id)
        state.repeat = not state.repeat
        await self.update_player_message(guild_id, view_type="options")

    async def toggle_effect(self, guild_id: int, effect_type: str) -> None:
        """Toggle an audio effect and hot-swap the stream."""
        state = self.get_state(guild_id)

        if effect_type == "bass":
            state.bass_boost = not state.bass_boost
        elif effect_type == "slow":
            state.slowed = not state.slowed
            if state.slowed:
                state.sped_up = False
        elif effect_type == "fast":
            state.sped_up = not state.sped_up
            if state.sped_up:
                state.slowed = False

        await self._reload_with_effects(guild_id)
        await self.update_player_message(guild_id, view_type="effects")

    # ── Interrupt callbacks (used by VoiceManager) ───────────────────

    async def _save_state(self, guild_id: int) -> dict | None:
        """Serialise the current playback state for later restoration.

        Returns ``None`` if nothing is playing.
        """
        state = self.get_state(guild_id)
        if not state.is_playing:
            return None

        if state.is_paused:
            elapsed = state.elapsed_saved
        else:
            elapsed = (time.time() - state.start_time) * state.current_speed

        state.elapsed_saved = max(0, elapsed)

        saved = {
            "url": state.active_url,
            "volume": state.volume,
            "seek": state.elapsed_saved,
            "channel": state.voice_channel,
            "repeat": state.repeat,
            "bass_boost": state.bass_boost,
            "slowed": state.slowed,
            "sped_up": state.sped_up,
            "was_paused": state.is_paused,
        }

        # Mark as not playing so the after-callback doesn't fire.
        state.is_playing = False
        return saved

    async def _restore_state(
        self, guild_id: int, saved: dict,
    ) -> None:
        """Resume playback from a previously saved state dict."""
        channel = saved.get("channel")
        if not channel:
            return

        try:
            vc = await self._manager.connect(channel)
        except Exception as e:
            logger.error("Failed to reconnect for resume: %s", e)
            return

        source, title, duration = await self._get_audio_source(
            saved["url"],
            seek_time=int(saved["seek"]),
            bass_boost=saved["bass_boost"],
            slowed=saved["slowed"],
            sped_up=saved["sped_up"],
        )
        if not source:
            return

        source = disnake.PCMVolumeTransformer(source)
        source.volume = saved["volume"]

        state = self.get_state(guild_id)
        state.is_playing = True
        state.is_paused = saved["was_paused"]

        cur_speed = (
            0.5 if saved["slowed"] else (2.0 if saved["sped_up"] else 1.0)
        )
        state.start_time = time.time() - (saved["seek"] / cur_speed)
        state.voice_channel = channel

        def after_playing(error: Exception | None) -> None:
            if state.is_playing:
                if state.repeat:
                    asyncio.run_coroutine_threadsafe(
                        self._play_track(guild_id), self._bot.loop,
                    )
                else:
                    state.is_playing = False
                    asyncio.run_coroutine_threadsafe(
                        self.update_player_message(
                            guild_id, force_status="stopped",
                        ),
                        self._bot.loop,
                    )
                    asyncio.run_coroutine_threadsafe(
                        self._manager.disconnect(guild_id), self._bot.loop,
                    )

        vc.play(source, after=after_playing)

        if state.is_paused:
            vc.pause()
            state.pause_start = time.time()
