"""
Stats cog — ``/stats`` slash command for displaying user statistics.
"""

import disnake
from disnake.ext import commands
import dotenv
import os

dotenv.load_dotenv()

HOST = os.getenv('DOMAIN', 'localhost')

class StatsCog(commands.Cog):
    """
    Cog exposing the ``/stats`` slash command.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.slash_command(name="stats", description="Display user statistics")
    async def stats(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(default=None, description="Select a member to show stats for")
    ) -> None:
        """Display user statistics."""
        if member is None:
            description = f"Here you can see users stats: https://{HOST}/users/"
        else:
            description = f"Here you can see the {member.display_name}'s stats: https://{HOST}/users/{member.id}/"

        embed = disnake.Embed(
            description=description,
            colour=0xF0C43F,
        )
        embed.set_footer(
            text="© RainBot",
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

