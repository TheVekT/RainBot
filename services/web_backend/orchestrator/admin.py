from django.contrib import admin
from .models import TelegramUser, DiscordUserPresence, RainStat, DiscordBotConfig, DiscordAccount, BanditScraperConfig

@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'threshold')
    search_fields = ('user_id',)

@admin.register(DiscordAccount)
class DiscordAccountAdmin(admin.ModelAdmin):
    list_display = ('account_id', 'nickname', 'current_status')
    search_fields = ('nickname', 'account_id')

@admin.register(DiscordUserPresence)
class DiscordUserPresenceAdmin(admin.ModelAdmin):
    list_display = ('account_id', 'get_nickname', 'state', 'start_time', 'end_time')
    list_filter = ('state',)
    search_fields = ('account__account_id', 'account__nickname')

    @admin.display(description="Nickname")
    def get_nickname(self, obj):
        return obj.account.nickname

@admin.register(RainStat)
class RainStatAdmin(admin.ModelAdmin):
    list_display = ('id', 'scrap_amount', 'user_count', 'end_time')
    list_filter = ('end_time',)
    
@admin.register(DiscordBotConfig)
class DiscordBotConfigAdmin(admin.ModelAdmin):
    list_display = (
        'guild_id', 
        'user_stats_retention_days', 
        'get_role_message_id', 
        'get_role_role_id',     
        'rain_channel_id', 
        'voice_notify_enabled', 
        'text_notify_enabled'
        )
    search_fields = ('guild_id',)
    
@admin.register(BanditScraperConfig)
class BanditScraperConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'rain_stats_retention_days')
    search_fields = ('id',)