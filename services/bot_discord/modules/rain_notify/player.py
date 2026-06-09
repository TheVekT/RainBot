"""Notification player - priority voice alerts.

Plays audio files from disk through Discord voice channels. When music is
already playing, the ``VoiceManager`` is used to interrupt (pause) the music,
play the notification, and then resume seamlessly.

Duration, volume, and sound-file lookup are handled entirely within this player.
"""

import asyncio
import logging
import shutil
from pathlib import Path

import disnake
from disnake.ext import commands

from modules.voice_core.manager import VoiceManager

logger = logging.getLogger(__name__)


class RainNotifyPlayer:
    """Player for playing priority voice notifications.

    Parameters
    ----------
    bot : commands.Bot
        The Discord bot instance.
    voice_manager : VoiceManager
        Shared voice-connection and interrupt manager.
    default_volume : float
        Default playback volume for notifications (0.0–2.0).
    sounds_dir : str | Path, optional
        Custom directory to look for audio files. Defaults to ``<project_root>/sounds/``.
    """

    def __init__(
        self,
        bot: commands.Bot,
        voice_manager: VoiceManager,
        default_volume: float = 1.0,
        sounds_dir: str | Path | None = None,
    ) -> None:
        self.bot = bot
        self._manager = voice_manager
        self.default_volume = default_volume

        # Configure custom sounds directory or fallback to project root sounds/
        if sounds_dir:
            self.sounds_dir = Path(sounds_dir).resolve()
        else:
            root = self._project_root()
            self.sounds_dir = root / "sounds"
            if not self.sounds_dir.exists():
                fallback = root / "bot_discord" / "sounds"
                if fallback.exists():
                    self.sounds_dir = fallback


    @staticmethod
    def _project_root() -> Path:
        """Return the project root (three levels above this file)."""
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _resolve_ffmpeg() -> str:
        """Find a usable ffmpeg executable (local or system)."""
        root = RainNotifyPlayer._project_root()
        local_dirs = [root / "ffmpeg", root / "bot_discord" / "ffmpeg"]
        for local_dir in local_dirs:
            for name in ("ffmpeg", "ffmpeg.exe"):
                candidate = local_dir / name
                if candidate.exists():
                    return str(candidate)
        return shutil.which("ffmpeg") or "ffmpeg"


    async def _play_file(
        self,
        voice: disnake.VoiceClient,
        file_path: str | None,
        duration: float | None,
        volume: float | None = None,
    ) -> None:
        """Play a local audio file through the given voice client.

        If file_path or duration is not provided, sleep for a short delay
        without playing anything (intentional silent connect/disconnect behavior).

        Parameters
        ----------
        voice:
            An already-connected ``VoiceClient``.
        file_path:
            Optional path relative to ``self.sounds_dir``.
        duration:
            Optional duration (seconds) to stay connected.
        volume:
            Playback volume; falls back to ``self.default_volume``.
        """
        if not file_path or duration is None or duration <= 0:
            await asyncio.sleep(1.0)
            return

        audio_path = self.sounds_dir / file_path
        if not audio_path.exists():
            logger.warning("Audio file not found: %s", audio_path)
            await asyncio.sleep(1.0)
            return

        try:
            if voice.is_playing():
                voice.stop()
        except Exception:
            pass

        try:
            ffmpeg = self._resolve_ffmpeg()
            source = disnake.FFmpegPCMAudio(str(audio_path), executable=ffmpeg)
            source = disnake.PCMVolumeTransformer(source)
            source.volume = volume if volume is not None else self.default_volume
            voice.play(source)
            await asyncio.sleep(duration)
            if voice.is_playing():
                voice.stop()
        except Exception as e:
            logger.error("Error playing audio file: %s", e)


    async def play_notification(
        self,
        file_path: str | None = None,
        duration: float | None = None,
        volume: float | None = None,
        channel_id: int | None = None,
    ) -> None:
        """Play a voice notification with priority interrupt.

        If music is playing, the manager will pause it, play the
        notification, and resume automatically afterwards.

        If file_path or duration is not provided, the bot will perform a silent
        connect and disconnect after a short delay (1.0 second) without playing audio.

        Parameters
        ----------
        file_path:
            Optional path relative to ``self.sounds_dir``.
        duration:
            Optional duration in seconds to stay in the channel.
        volume:
            Optional volume override (0.0–2.0).
        channel_id:
            If given, play only in that channel. Otherwise broadcast
            to every populated voice channel in the first guild.
        """
        target_guild: disnake.Guild | None = None

        if channel_id:
            ch = self.bot.get_channel(channel_id)
            if ch:
                target_guild = ch.guild
        elif self.bot.guilds:
            target_guild = self.bot.guilds[0]

        # --- Interrupt active music ---
        guild_id = target_guild.id if target_guild else None
        token = None
        if guild_id is not None:
            token = await self._manager.interrupt(guild_id)

        # --- Play the notification ---
        try:
            if channel_id is not None:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        voice = await self._manager.connect(channel)
                        await self._play_file(voice, file_path, duration, volume)
                        if (
                            voice
                            and voice.is_connected()
                            and voice.channel.id == channel.id
                        ):
                            await voice.disconnect(force=True)
                    except Exception as e:
                        logger.error("Notification error: %s", e)
            else:
                if self.bot.guilds:
                    guild = self.bot.guilds[0]
                    for channel in guild.voice_channels:
                        if len(channel.members) == 0:
                            continue
                        try:
                            voice = await self._manager.connect(channel)
                            await self._play_file(
                                voice, file_path, duration, volume,
                            )
                            if (
                                voice
                                and voice.is_connected()
                                and voice.channel.id == channel.id
                            ):
                                await voice.disconnect(force=True)
                        except Exception:
                            pass
        except Exception as e:
            logger.error("Error in play_notification: %s", e)

        # --- Resume interrupted music ---
        if token is not None:
            await self._manager.resume(token)
