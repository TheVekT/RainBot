import json
import zlib
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.cache import cache
from orchestrator.models import DiscordAccount, DiscordUserPresence, DiscordVoiceChannel
from .constants import STATE_MAP

def get_global_voice_stats(target_date, today_date):
    """
    Fetches voice intervals for all users within a 3-day window buffer.
    Can be reused safely by any view or API endpoint.
    """
    target_date_str = target_date.strftime('%Y-%m-%d')
    cache_key = f"global_voice_stats_{target_date_str}"
    compressed_payload = cache.get(cache_key)

    if compressed_payload is None:
        day_start = timezone.make_aware(datetime.combine(target_date - timedelta(days=1), datetime.min.time()))
        day_end = timezone.make_aware(datetime.combine(target_date + timedelta(days=1), datetime.max.time()))

        presences = DiscordUserPresence.objects.filter(
            start_time__lt=day_end,
            end_time__gt=day_start,
            channel__isnull=False
        ).order_by('start_time')

        intervals = []
        for cp in presences:
            ch_id_str = str(cp.channel_id)
            intervals.append((
                str(cp.account_id),
                STATE_MAP.get(cp.state, 0),
                int(cp.start_time.timestamp()),
                int(cp.end_time.timestamp()),
                ch_id_str
            ))

        payload = {"intervals": intervals}
        compressed_payload = zlib.compress(json.dumps(payload).encode('utf-8'))
        
        timeout = 15 if target_date >= today_date else 86400
        cache.set(cache_key, compressed_payload, timeout=timeout)

    data = json.loads(zlib.decompress(compressed_payload).decode('utf-8'))
    return data["intervals"]


def get_user_archive_stats(user, account_id, today_str, start_of_today):
    """
    Fetches compressed historical long-term data excluding current day.
    """
    cache_key = f"user_archive_{account_id}_{today_str}"
    compressed_payload = cache.get(cache_key)

    if compressed_payload is None:
        one_year_ago = start_of_today - timedelta(days=365)
        presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=one_year_ago,
            start_time__lt=start_of_today
        ).select_related('channel').order_by('start_time')

        intervals = []
        channels = {}
        for p in presences:
            ch_id_str = str(p.channel_id) if p.channel_id else None
            intervals.append((
                STATE_MAP.get(p.state, 0),
                int(p.start_time.timestamp()),
                int(p.end_time.timestamp()),
                ch_id_str
            ))
            if p.channel:
                channels[ch_id_str] = p.channel.name

        payload = {"intervals": intervals, "channels": channels}
        compressed_payload = zlib.compress(json.dumps(payload).encode('utf-8'))
        cache.set(cache_key, compressed_payload, timeout=86400)

    data = json.loads(zlib.decompress(compressed_payload).decode('utf-8'))
    return data["intervals"], data["channels"]


def get_user_today_stats(user, account_id, today_str, start_of_today):
    """
    Fetches real-time volatile metrics for the target user (contains online state).
    """
    cache_key = f"user_today_{account_id}_{today_str}"
    compressed_payload = cache.get(cache_key)

    if compressed_payload is None:
        presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=start_of_today
        ).select_related('channel').order_by('start_time')

        intervals = []
        channels = {}
        for p in presences:
            ch_id_str = str(p.channel_id) if p.channel_id else None
            intervals.append((
                STATE_MAP.get(p.state, 0),
                int(p.start_time.timestamp()),
                int(p.end_time.timestamp()),
                ch_id_str
            ))
            if p.channel:
                channels[ch_id_str] = p.channel.name

        payload = {"intervals": intervals, "channels": channels}
        compressed_payload = zlib.compress(json.dumps(payload).encode('utf-8'))
        cache.set(cache_key, compressed_payload, timeout=15)

    data = json.loads(zlib.decompress(compressed_payload).decode('utf-8'))
    return data["intervals"], data["channels"]

def get_all_voice_channels():
    """
    Fetches the complete topology of active voice channels.
    Caches the payload for 24 hours (86400s) since updates occur daily.
    """
    cache_key = "all_voice_channels_topology"
    compressed_payload = cache.get(cache_key)

    if compressed_payload is None:
        # Fetch channels containing full metadata
        channels_queryset = DiscordVoiceChannel.objects.all().values('channel_id', 'name', 'is_active')
        channels_list = list(channels_queryset)

        # Cast bigint IDs to string for safe Javascript precision handling
        for ch in channels_list:
            ch['channel_id'] = str(ch['channel_id'])

        compressed_payload = zlib.compress(json.dumps(channels_list).encode('utf-8'))
        cache.set(cache_key, compressed_payload, timeout=86400)

    channels_data = json.loads(zlib.decompress(compressed_payload).decode('utf-8'))
    return channels_data

def get_all_discord_accounts():
    """
    Fetches details of all Discord accounts (account_id, nickname, avatar_url)
    and caches them for 24 hours (86400s) to minimize DB hits.
    """
    cache_key = "all_discord_accounts_metadata"
    compressed_payload = cache.get(cache_key)
    
    if compressed_payload is None:
        accounts = DiscordAccount.objects.all().values('account_id', 'nickname', 'avatar_url')
        accounts_list = list(accounts)
        
        # Cast account_id to string for safe Javascript representation
        for acc in accounts_list:
            acc['account_id'] = str(acc['account_id'])
            
        compressed_payload = zlib.compress(json.dumps(accounts_list).encode('utf-8'))
        cache.set(cache_key, compressed_payload, timeout=86400)
        
    return json.loads(zlib.decompress(compressed_payload).decode('utf-8'))