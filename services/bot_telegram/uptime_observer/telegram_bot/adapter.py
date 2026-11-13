"""Read local application state without sending messages to Telegram."""


class TelegramAdapter:
    def __init__(self, bot):
        self.bot = bot

    def snapshot(self):
        application = self.bot.application
        updater = application.updater
        return {
            'application_running': bool(application.running),
            'polling_running': bool(updater and updater.running),
        }
