"""Music cog — ``/play`` slash command for YouTube playback.

Thin wrapper that delegates all logic to the ``YouTubePlayer`` module.
"""

import disnake
from disnake.ext import commands

from modules.youtube_player.player import YouTubePlayer


class MusicCog(commands.Cog):
    """Cog exposing the ``/play`` slash command.

    Parameters
    ----------
    bot : commands.Bot
        The Discord bot instance.
    youtube_player : YouTubePlayer
        Shared YouTube player module.
    """

    def __init__(self, bot: commands.Bot, youtube_player: YouTubePlayer) -> None:
        self.bot = bot
        self.player = youtube_player

    @commands.slash_command(name="play", description="Play music from YouTube")
    async def play(
        self,
        inter: disnake.ApplicationCommandInteraction,
        url: str,
        volume: float = commands.Param(default=0.5, ge=0.0, le=2.0),
        repeat: bool = False,
        bass_boost: bool = False,
    ) -> None:
        """Start YouTube playback in the caller's voice channel."""
        await self.player.play(inter, url, volume, repeat, bass_boost)
