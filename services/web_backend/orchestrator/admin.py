from django.contrib import admin
from django import forms
from .models import (TelegramUser, DiscordUserPresence, RainStat, DiscordBotConfig, DiscordAccount,
                     BanditScraperConfig, DiscordVoiceChannel, UptimeComponent, UptimePeriod, UptimeSnapshot)


class UptimeComponentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.name} ({obj.key})'


class UptimePeriodForm(forms.ModelForm):
    class Meta:
        model = UptimePeriod
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        start, end, last_seen = (cleaned.get(name) for name in ('started_at', 'ended_at', 'last_seen_at'))
        if start and end and end < start:
            self.add_error('ended_at', 'The end time cannot be earlier than the start time.')
        if start and last_seen and last_seen < start:
            self.add_error('last_seen_at', 'The last observation cannot be earlier than the start time.')
        return cleaned


class UptimeRecordAdmin(admin.ModelAdmin):
    list_select_related = ('component',)
    search_fields = ('component__key', 'component__name', 'reason')
    list_filter = ('status', 'component')
    list_per_page = 50

    @admin.display(description='Component', ordering='component__name')
    def component_name(self, obj):
        return f'{obj.component.name} ({obj.component.key})'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'component':
            kwargs['form_class'] = UptimeComponentChoiceField
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(UptimeComponent)
class UptimeComponentAdmin(admin.ModelAdmin):
    list_display = ('key', 'name', 'poll_interval_seconds')
    search_fields = ('key', 'name')
    ordering = ('name',)
    readonly_fields = ('key', 'name', 'poll_interval_seconds')
    fieldsets = ((None, {
        'fields': ('key', 'name', 'poll_interval_seconds'),
        'description': 'Components and polling intervals are managed by the observer configuration.',
    }),)

    def has_add_permission(self, request):
        return False


@admin.register(UptimePeriod)
class UptimePeriodAdmin(UptimeRecordAdmin):
    form = UptimePeriodForm
    list_display = ('component_name', 'status', 'started_at', 'ended_at', 'last_seen_at', 'reason')
    list_filter = ('status', 'component', 'started_at')
    date_hierarchy = 'started_at'
    ordering = ('-started_at',)


@admin.register(UptimeSnapshot)
class UptimeSnapshotAdmin(UptimeRecordAdmin):
    list_display = ('component_name', 'status', 'observed_at', 'reason')
    list_filter = ('status', 'component', 'observed_at')
    date_hierarchy = 'observed_at'
    ordering = ('-observed_at',)

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
        'rain_channel_id', 
        'voice_notify_enabled', 
        'text_notify_enabled',
        "params",
        )
    search_fields = ('guild_id',)
    
@admin.register(BanditScraperConfig)
class BanditScraperConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'rain_stats_retention_days')
    search_fields = ('id',)
