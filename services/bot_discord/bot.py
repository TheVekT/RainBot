import os
import logging
import disnake
from disnake.ext import commands

logger = logging.getLogger(__name__)


class RainDiscordBot(commands.Bot):
    """Custom Discord bot class for the RainBot project.

    Encapsulates intent configuration and automatic bot token retrieval.
    """

    def __init__(self, bot_token: str = None, *args, **kwargs) -> None:
        # 1. Configure default intents
        intents = disnake.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.members = True
        intents.guilds = True
        intents.presences = True

        # 2. Set default parameters (intents and command prefix)
        # while keeping the option to override them during instantiation.
        kwargs["intents"] = kwargs.get("intents", intents)
        kwargs["command_prefix"] = kwargs.get("command_prefix", "/")

        # Initialize the base commands.Bot class
        super().__init__(*args, **kwargs)

        # 3. Retrieve token from environment variables
        self.bot_token = bot_token

    async def on_ready(self) -> None:
        """Fires when the bot successfully connects to Discord."""
        logger.info("[Discord] Bot %s (ID: %s) successfully launched and ready!", self.user, self.user.id)

    async def run_async(self) -> None:
        """Asynchronously start the bot.

        Used instead of the blocking run() method to prevent blocking the
        asyncio event loop, allowing the gRPC server to run concurrently.
        """
        if not self.bot_token:
            raise ValueError("Bot token is missing. Please check your .env file.")

        # start() is a built-in disnake.Client coroutine perfect for this architecture
        await self.start(self.bot_token)