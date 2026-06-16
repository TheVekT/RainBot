import logging
import asyncio

from .player import RainNotifyPlayer
from .text_notifier import RainTextNotifier
from .config import NotifyConfigProvider

logger = logging.getLogger(__name__)

class RainEventRouter:
    def __init__(self, bot, player: RainNotifyPlayer, text_notifier: RainTextNotifier, config_provider: NotifyConfigProvider):
        self.bot = bot
        self.player: RainNotifyPlayer = player
        self.text_notifier: RainTextNotifier = text_notifier
        self.config_provider: NotifyConfigProvider = config_provider
        self.old_scrap_amount = None
        
        self.voice_notify_enabled = None
        self.text_notify_enabled = None

    async def handle_rain_start(self, scrap_amount: float):
        if scrap_amount is None:
            return

        self.voice_notify_enabled = await self.config_provider.voice_notify_enabled.get()
        self.text_notify_enabled = await self.config_provider.text_notify_enabled.get()
        
        self.old_scrap_amount = scrap_amount
        if self.text_notify_enabled:
            await self.text_notifier.send_new_notification(scrap_amount)

        if self.voice_notify_enabled:
            if scrap_amount < 150:
                asyncio.create_task(self.player.play_notification("sound.wav", duration=3.5, volume=0.6))
            elif scrap_amount < 400:
                asyncio.create_task(self.player.play_notification("evrei.m4a", duration=5, volume=0.4))
            elif scrap_amount < 600:
                asyncio.create_task(self.player.play_notification("stony.mp3", duration=7, volume=1.3))
            elif scrap_amount < 1000:
                asyncio.create_task(self.player.play_notification("alert.m4a", duration=12, volume=0.6))
            elif scrap_amount < 5000:
                asyncio.create_task(self.player.play_notification("gimn.mp3", duration=19, volume=0.6))
            else: 
                asyncio.create_task(self.player.play_notification("5000.mp3", duration=12, volume=3))
        
    async def handle_rain_update(self, scrap_amount: float):
        scrap_diff = scrap_amount - self.old_scrap_amount if self.old_scrap_amount is not None else 0
        
        if self.text_notify_enabled:
            await self.text_notifier.update_notification(scrap_amount)
        self.old_scrap_amount = scrap_amount

        if self.voice_notify_enabled:
            if scrap_diff >= 400:
                asyncio.create_task(self.player.play_notification("alert.m4a", duration=8, volume=0.6))
            elif scrap_diff >= 200:
                asyncio.create_task(self.player.play_notification("evrei.m4a", duration=5, volume=0.4))
            elif scrap_diff >= 100:
                asyncio.create_task(self.player.play_notification("potyzhno.mp3", duration=2, volume=1.5))
            elif scrap_diff >= 50:
                asyncio.create_task(self.player.play_notification())
    
    async def handle_rain_end(self, scrap_amount: float):
        self.old_scrap_amount = None
        if self.text_notify_enabled:
            self.text_notifier.reset()