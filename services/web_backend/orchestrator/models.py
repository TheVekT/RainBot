from django.db import models

class TelegramUser(models.Model):
    user_id = models.BigIntegerField(primary_key=True, help_text="Telegram User ID")
    threshold = models.IntegerField(default=100, help_text="Threshold for rain notifications")

    class Meta:
        db_table = 'telegram_users'

class DiscordAccount(models.Model):
    account_id = models.BigIntegerField(primary_key=True, help_text="Discord Snowflake User ID")
    nickname = models.CharField(max_length=255, help_text="Current Discord nickname")
    avatar_url = models.TextField(null=True, blank=True, help_text="Discord avatar image URL")
    current_status = models.CharField(max_length=50, help_text="Current real-time status of the user")

    class Meta:
        db_table = 'discord_accounts'

    def __str__(self):
        return f"{self.nickname} ({self.account_id})"

class DiscordUserPresence(models.Model):
    account = models.ForeignKey(
        DiscordAccount,
        on_delete=models.CASCADE,
        related_name="presences",
        db_column="account_id",
        help_text="Reference to the Discord account profile"
    )
    state = models.CharField(max_length=50, help_text="Recorded state of the user")
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()

    class Meta:
        db_table = 'discord_user_presence'
        indexes = [
            models.Index(fields=['account', 'start_time']),
        ]

    def __str__(self):
        return f"Presence {self.account_id}: {self.state} ({self.start_time})"

class RainStat(models.Model):
    scrap_amount = models.FloatField(help_text="Recorded scrap amount of rain")
    user_count = models.IntegerField(help_text="Recorded number of users in this rain event")
    end_time = models.DateTimeField(db_index=True, help_text="Time when the rain was ended")

    class Meta:
        db_table = 'rain_stats'
        
class DiscordBotConfig(models.Model):
    guild_id = models.BigIntegerField(primary_key=True, help_text="Discord Server (Guild) ID")
    user_stats_retention_days = models.IntegerField(default=365, help_text="Number of days to retain user stats")
    
    rain_channel_id = models.BigIntegerField(null=True, blank=True, help_text="Channel ID for rain notifications")
    voice_notify_enabled = models.BooleanField(default=True, help_text="Whether voice notifications are enabled")
    text_notify_enabled = models.BooleanField(default=True, help_text="Whether text notifications are enabled")
    
    get_role_message_id = models.BigIntegerField(null=True, blank=True, help_text="Message ID for 'Get Role' button")
    get_role_role_id = models.BigIntegerField(null=True, blank=True, help_text="Role ID granted by the button")

    class Meta:
        db_table = 'discord_bot_config'
        verbose_name = 'Discord Bot Config'
        verbose_name_plural = 'Discord Bot Configs'

    def __str__(self):
        return f"Guild Config: {self.guild_id}"
    
class BanditScraperConfig(models.Model):
    rain_stats_retention_days = models.IntegerField(default=365, help_text="Number of days to retain rain statistics")
    
    class Meta:
        db_table = 'bandit_scraper_config'
        verbose_name = 'Bandit Scraper Config'
        verbose_name_plural = 'Bandit Scraper Configs'