from django.contrib import admin
from .models import TelegramUser, DiscordUserPresence, RainStat, DiscordBotConfig, DiscordAccount, BanditScraperConfig, DiscordVoiceChannel

@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'threshold')
    search_fields = ('user_id',)

@admin.register(DiscordAccount)
class DiscordAccountAdmin(admin.ModelAdmin):
    list_display = ('account_id', 'username', 'nickname', 'current_status')
    search_fields = ('username', 'nickname', 'account_id')

@admin.register(DiscordUserPresence)
class DiscordUserPresenceAdmin(admin.ModelAdmin):
    list_display = ('account_id', 'get_username', 'state', 'channel', 'start_time', 'end_time')
    list_filter = ('state',)
    search_fields = ('account__account_id', 'account__username')

    @admin.display(description="Username")
    def get_username(self, obj):
        return obj.account.username
    
@admin.register(DiscordVoiceChannel)
class DiscordVoiceChannelAdmin(admin.ModelAdmin):
    list_display = ('channel_id', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'channel_id')

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