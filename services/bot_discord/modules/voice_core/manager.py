"""Voice connection manager with priority interrupt/resume support.

Provides a central coordinator for all voice channel operations in a guild.
Handles connection lifecycle, retry logic, and the priority interrupt system
that allows voice notifications to temporarily pause music playback.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import disnake

logger = logging.getLogger(__name__)


@dataclass
class InterruptToken:
    """Opaque token returned by ``interrupt()``, passed back to ``resume()``.

    The ``saved_state`` dict is produced by the active player's save callback
    and is completely opaque to the manager — only the player knows how to
    interpret it.
    """

    guild_id: int
    saved_state: dict[str, Any] | None = None


# Type alias for the save/restore callbacks registered by players.
SaveCallback = Callable[[int], Awaitable[dict[str, Any] | None]]
RestoreCallback = Callable[[int, dict[str, Any]], Awaitable[None]]


class RobustVoiceClient(disnake.VoiceClient):
    """VoiceClient subclass that prevents crashes due to uninitialized websocket."""

    async def poll_voice_ws(self, ws=None, *args, **kwargs) -> None:
        try:
            while True:
                # Use self.ws if it's a valid websocket, otherwise fallback to ws
                current_ws = self.ws if hasattr(self.ws, "poll_event") else ws
                if hasattr(current_ws, "poll_event"):
                    await current_ws.poll_event()
                else:
                    # If no valid websocket is available, exit the polling loop
                    break
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("Error occurred while polling voice websocket: %s", e)
            await self.disconnect(force=True)


class VoiceManager:
    """Central voice-connection and priority-interrupt manager.

    Responsibilities:
    * Connecting / disconnecting to voice channels with retry logic.
    * Providing the current ``VoiceClient`` for a guild.
    * Coordinating priority interrupts (pause music → play notification →
      resume music) without the notification or music modules knowing about
      each other.

    Parameters
    ----------
    bot : commands.Bot
        The Discord bot instance used to query voice clients and guilds.
    """

    def __init__(self, bot: disnake.ext.commands.Bot) -> None:
        self._bot = bot
        self._guild_locks: dict[int, asyncio.Lock] = {}

        # Registered player callbacks for interrupt/resume.
        self._save_cb: SaveCallback | None = None
        self._restore_cb: RestoreCallback | None = None

    # ------------------------------------------------------------------
    # Player callback registration
    # ------------------------------------------------------------------

    def register_player(
        self,
        save_callback: SaveCallback,
        restore_callback: RestoreCallback,
    ) -> None:
        """Register callbacks so the manager can save/restore player state.

        Parameters
        ----------
        save_callback:
            ``async (guild_id) -> dict | None`` — serialise the current
            playback state so it can be restored later.
        restore_callback:
            ``async (guild_id, state_dict) -> None`` — restore playback
            from a previously saved state dict.
        """
        self._save_cb = save_callback
        self._restore_cb = restore_callback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        """Return a per-guild asyncio lock, creating one if needed."""
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()
        return self._guild_locks[guild_id]

    async def _force_cleanup_voice(self, guild: disnake.Guild) -> None:
        """Force-remove all voice clients for *guild*, cleaning up state."""
        to_remove = [
            vc for vc in self._bot.voice_clients
            if vc.guild and vc.guild.id == guild.id
        ]
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
                if vc in self._bot.voice_clients:
                    self._bot.voice_clients.remove(vc)
            except (ValueError, AttributeError):
                pass
        if to_remove:
            await asyncio.sleep(0.5)

    async def _wait_for_voice_ready(
        self, vc: disnake.VoiceClient, timeout: float = 10.0,
    ) -> bool:
        """Wait until the voice WebSocket is fully established."""
        start = time.time()
        while time.time() - start < timeout:
            if vc.is_connected():
                return True
            await asyncio.sleep(0.1)
        return False

    # ------------------------------------------------------------------
    # Public API — connection management
    # ------------------------------------------------------------------

    async def connect(
        self,
        channel: disnake.VoiceChannel,
        max_retries: int = 3,
        reconnect: bool = True,
    ) -> disnake.VoiceClient:
        """Connect to *channel* with full retry and cleanup logic.

        Returns a connected ``VoiceClient``.

        Raises
        ------
        Exception
        		If all retry attempts are exhausted.
        """
        guild = channel.guild
        lock = self._get_lock(guild.id)

        async with lock:
            for attempt in range(1, max_retries + 1):
                voice_client = disnake.utils.get(
                    self._bot.voice_clients, guild=guild,
                )

                if voice_client is not None:
                    if voice_client.is_connected():
                        vc_channel = getattr(voice_client, "channel", None)
                        if vc_channel and vc_channel.id == channel.id:
                            return voice_client
                        try:
                            await voice_client.move_to(channel)
                            if await self._wait_for_voice_ready(
                                voice_client, timeout=5.0,
                            ):
                                return voice_client
                        except Exception as e:
                            logger.warning("move_to failed: %s", e)

                    logger.info("Stale voice client, forcing cleanup...")
                    await self._force_cleanup_voice(guild)

                try:
                    new_vc = await channel.connect(
                        timeout=15.0, reconnect=reconnect, cls=RobustVoiceClient,
                    )
                    if await self._wait_for_voice_ready(new_vc, timeout=10.0):
                        logger.info("Connected to %s", channel.name)
                        return new_vc
                    else:
                        logger.warning(
                            "Voice not ready after connect (attempt %d)",
                            attempt,
                        )
                        await self._force_cleanup_voice(guild)
                except disnake.errors.ClientException as e:
                    logger.warning(
                        "ClientException: %s (attempt %d)", e, attempt,
                    )
                    await self._force_cleanup_voice(guild)
                except asyncio.TimeoutError:
                    logger.warning(
                        "Timeout connecting (attempt %d)", attempt,
                    )
                    await self._force_cleanup_voice(guild)
                except Exception as e:
                    logger.error(
                        "Connect error: %s (attempt %d)", e, attempt,
                    )
                    await self._force_cleanup_voice(guild)

            raise Exception(
                f"Failed to connect to {channel.name} "
                f"after {max_retries} attempts"
            )

    async def disconnect(self, guild_id: int) -> None:
        """Safely disconnect from voice in the given guild."""
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return
        voice_client = disnake.utils.get(
            self._bot.voice_clients, guild=guild,
        )
        if voice_client:
            try:
                await voice_client.disconnect(force=True)
            except Exception:
                pass

    def get_voice_client(self, guild_id: int) -> disnake.VoiceClient | None:
        """Return the current ``VoiceClient`` for *guild_id*, or ``None``."""
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return None
        return disnake.utils.get(self._bot.voice_clients, guild=guild)

    # ------------------------------------------------------------------
    # Public API — priority interrupt / resume
    # ------------------------------------------------------------------

    async def interrupt(self, guild_id: int) -> InterruptToken:
        """Interrupt the active player, saving its state.

        Call this **before** playing a priority notification.  Pass the
        returned token to ``resume()`` afterwards.
        """
        saved: dict[str, Any] | None = None

        if self._save_cb:
            try:
                saved = await self._save_cb(guild_id)
            except Exception as e:
                logger.error("Failed to save player state: %s", e)

        # If something was playing, stop the voice client so the channel
        # is free for the notification audio.
        if saved is not None:
            vc = self.get_voice_client(guild_id)
            if vc:
                try:
                    vc.stop()
                except Exception:
                    pass
                await asyncio.sleep(0.2)

        return InterruptToken(guild_id=guild_id, saved_state=saved)

    async def resume(self, token: InterruptToken) -> None:
        """Resume the player from a previously saved interrupt state."""
        if token.saved_state is None:
            return

        await asyncio.sleep(0.5)

        if self._restore_cb:
            try:
                await self._restore_cb(token.guild_id, token.saved_state)
            except Exception as e:
                logger.error("Failed to restore player state: %s", e)
