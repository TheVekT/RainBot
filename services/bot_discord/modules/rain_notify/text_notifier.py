import logging
import disnake
from datetime import datetime, timezone
from .config import NotifyConfigProvider

logger = logging.getLogger(__name__)


class RainTextNotifier:
    """Manages text notifications about rain events in Discord.

    Stores a reference to the last sent message to allow editing it later.
    """

    def __init__(self, bot: disnake.ext.commands.Bot, config_provider: NotifyConfigProvider):
        self.bot = bot
        self.config_provider = config_provider
        self.active_message: disnake.Message | None = None

    def _build_embed(self, scrap_amount: float) -> disnake.Embed:
        """Internal method to build the notification Embed."""
        embed = disnake.Embed(
            title="🌧  Rakeback Rain NOW!!!  🌧",
            description=f"**$ {scrap_amount:.2f}**",
            colour=0xF0C43F,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(
            name="RainBot",
            icon_url="https://cdn.discordapp.com/app-icons/1084386974967812167/4f9cd1faa1a333514fd3dc7446ed5777.png?size=32",
        )
        embed.set_footer(text="bandit.camp")
        return embed

    async def send_new_notification(self, scrap_amount: float) -> None:
        """Send a new notification about the start of a rain event and store the message reference."""
        channel_id = await self.config_provider.rain_channel_id.get()
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.error("TextNotifier: Channel with ID %s not found.", channel_id)
            return

        embed = self._build_embed(scrap_amount)
        try:
            # Send message and save it in self.active_message
            self.active_message = await channel.send(content="||@everyone||", embed=embed)
            logger.info("TextNotifier: Sent new notification. Scrap: %s", scrap_amount)
        except Exception as e:
            logger.error("TextNotifier: Error sending message: %s", e)
            self.active_message = None

    async def update_notification(self, scrap_amount: float) -> None:
        """Update the last sent message with the new scrap amount.

        Does nothing if there is no active message.
        """
        if not self.active_message:
            logger.warning("TextNotifier: No active message to update.")
            return

        embed = self._build_embed(scrap_amount)
        try:
            await self.active_message.edit(content="||@everyone||", embed=embed)
            logger.debug("TextNotifier: Message updated. New scrap: %s", scrap_amount)
        except disnake.NotFound:
            logger.warning("TextNotifier: Active message was deleted, could not update.")
            self.active_message = None
        except Exception as e:
            logger.error("TextNotifier: Error updating message: %s", e)

    def reset(self) -> None:
        """Reset the active message reference (called when rain ends)."""
        self.active_message = None
