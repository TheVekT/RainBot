import zlib
import pickle
import json
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from datetime import datetime
from django.http import HttpResponse
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from orchestrator.models import DiscordAccount, DiscordUserPresence

@cache_page(60 * 5)
def user_list_view(request):
    """
    Renders the complete list of registered Discord users.
    The view output is cached entirely on the server side to minimize DB load.
    """

    users = DiscordAccount.objects.all().order_by('nickname')
    
    context = {
        'users': users
    }
    return render(request, 'public_web/user_list.html', context)

STATE_MAP = {
    "offline": 0,
    "online": 1,
    "voice_online": 2,
    "voice_mute": 3,
    "voice_deaf": 4,
    "voice_afk": 5,
    "voice_alone": 6
}

def user_detail_view(request, account_id):
    user = get_object_or_404(DiscordAccount, account_id=account_id)
    
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = timezone.now().date()
    else:
        target_date = timezone.now().date()
        
    target_date_str = target_date.strftime('%Y-%m-%d')
    today_date = timezone.now().date()
    today_str = today_date.strftime('%Y-%m-%d')

    channels_dict = {}

    day_cache_key = f"global_voice_stats_{target_date_str}"
    compressed_day_payload = cache.get(day_cache_key)

    if compressed_day_payload is None:
        day_start_utc = timezone.make_aware(datetime.combine(target_date - timedelta(days=1), datetime.min.time()))
        day_end_utc = timezone.make_aware(datetime.combine(target_date + timedelta(days=1), datetime.max.time()))

        co_presences = DiscordUserPresence.objects.filter(
            start_time__lt=day_end_utc,
            end_time__gt=day_start_utc,
            channel__isnull=False
        ).select_related('account', 'channel').order_by('start_time')

        day_intervals = []
        day_channels = {}
        for cp in co_presences:
            cp_state_int = STATE_MAP.get(cp.state, 0)
            ch_id_str = str(cp.channel_id)
            
            day_intervals.append((
                str(cp.account_id),
                cp.account.nickname,
                cp_state_int,
                int(cp.start_time.timestamp()),
                int(cp.end_time.timestamp()),
                ch_id_str
            ))
            day_channels[ch_id_str] = cp.channel.name

        day_payload = {"intervals": day_intervals, "channels": day_channels}
        compressed_day_payload = zlib.compress(json.dumps(day_payload).encode('utf-8'))
        
        day_cache_timeout = 15 if target_date_str == today_str else 86400
        cache.set(day_cache_key, compressed_day_payload, timeout=day_cache_timeout)

    day_data = json.loads(zlib.decompress(compressed_day_payload).decode('utf-8'))
    day_history_json_string = json.dumps(day_data["intervals"])
    channels_dict.update(day_data["channels"])

    # Fast response for dynamic AJAX/JSON requests
    if request.GET.get('format') == 'json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponse(day_history_json_string, content_type='application/json')

    start_of_today_utc = timezone.make_aware(datetime.combine(today_date, datetime.min.time()))
    one_year_ago_utc = start_of_today_utc - timedelta(days=365)

    archive_cache_key = f"user_archive_{account_id}_{today_str}"
    compressed_archive_payload = cache.get(archive_cache_key)
    
    if compressed_archive_payload is None:
        archive_presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=one_year_ago_utc,
            start_time__lt=start_of_today_utc
        ).select_related('channel').order_by('start_time')
        
        archive_intervals = []
        archive_channels = {}
        for p in archive_presences:
            state_int = STATE_MAP.get(p.state, 0)
            ch_id_str = str(p.channel_id) if p.channel_id else None
            
            archive_intervals.append((
                state_int, 
                int(p.start_time.timestamp()), 
                int(p.end_time.timestamp()), 
                ch_id_str
            ))
            if p.channel:
                archive_channels[ch_id_str] = p.channel.name
            
        archive_payload = {"intervals": archive_intervals, "channels": archive_channels}
        compressed_archive_payload = zlib.compress(json.dumps(archive_payload).encode('utf-8'))
        cache.set(archive_cache_key, compressed_archive_payload, timeout=86400)
        
    archive_data = json.loads(zlib.decompress(compressed_archive_payload).decode('utf-8'))
    user_archive_json_string = json.dumps(archive_data["intervals"])
    channels_dict.update(archive_data["channels"])

    today_cache_key = f"user_today_{account_id}_{today_str}"
    compressed_today_payload = cache.get(today_cache_key)
    
    if compressed_today_payload is None:
        today_presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=start_of_today_utc
        ).select_related('channel').order_by('start_time')
        
        today_intervals = []
        today_channels = {}
        for p in today_presences:
            state_int = STATE_MAP.get(p.state, 0)
            ch_id_str = str(p.channel_id) if p.channel_id else None
            
            today_intervals.append((
                state_int, 
                int(p.start_time.timestamp()), 
                int(p.end_time.timestamp()), 
                ch_id_str
            ))
            if p.channel:
                today_channels[ch_id_str] = p.channel.name
            
        today_payload = {"intervals": today_intervals, "channels": today_channels}
        compressed_today_payload = zlib.compress(json.dumps(today_payload).encode('utf-8'))
        cache.set(today_cache_key, compressed_today_payload, timeout=15)
        
    today_data = json.loads(zlib.decompress(compressed_today_payload).decode('utf-8'))
    user_today_json_string = json.dumps(today_data["intervals"])
    channels_dict.update(today_data["channels"])

    context = {
        'user_profile': user,
        'today_date': today_str,
        'selected_date': target_date_str,
        'yearly_archive_json': user_archive_json_string,
        'user_today_json': user_today_json_string,
        'global_voice_json': day_history_json_string,
        'channels_mapping_json': json.dumps(channels_dict),
    }
    return render(request, 'public_web/user_detail.html', context)