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

    day_cache_key = f"global_server_voice_safe_day_v1_{target_date_str}"
    compressed_day_data = cache.get(day_cache_key)

    if compressed_day_data is None:
        day_start_utc = timezone.make_aware(datetime.combine(target_date - timedelta(days=1), datetime.min.time()))
        day_end_utc = timezone.make_aware(datetime.combine(target_date + timedelta(days=1), datetime.max.time()))

        co_presences = DiscordUserPresence.objects.filter(
            start_time__lt=day_end_utc,
            end_time__gt=day_start_utc,
            channel__isnull=False
        ).select_related('account').order_by('start_time')

        day_intervals = []
        for cp in co_presences:
            cp_state_int = STATE_MAP.get(cp.state, 0)
            cp_start_ts = int(cp.start_time.timestamp())
            cp_end_ts = int(cp.end_time.timestamp())
            
            day_intervals.append((
                str(cp.account_id),
                cp.account.nickname,
                cp_state_int,
                cp_start_ts,
                cp_end_ts,
                str(cp.channel_id) if cp.channel_id else None
            ))

        serialized_day = json.dumps(day_intervals).encode('utf-8')
        compressed_day_data = zlib.compress(serialized_day)
        
        day_cache_timeout = 15 if target_date_str == today_str else 86400
        cache.set(day_cache_key, compressed_day_data, timeout=day_cache_timeout)

    day_history_json_string = zlib.decompress(compressed_day_data).decode('utf-8')

    if request.GET.get('format') == 'json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponse(day_history_json_string, content_type='application/json')

    now = timezone.now()
    start_of_today_utc = timezone.make_aware(datetime.combine(today_date, datetime.min.time()))
    one_year_ago_utc = now - timedelta(days=365)

    archive_cache_key = f"user_archive_history_v1_{account_id}"
    compressed_archive = cache.get(archive_cache_key)
    
    if compressed_archive is None:
        archive_presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=one_year_ago_utc,
            start_time__lt=start_of_today_utc
        ).select_related('channel').order_by('start_time')
        
        archive_intervals = []
        for p in archive_presences:
            state_int = STATE_MAP.get(p.state, 0)
            archive_intervals.append((state_int, int(p.start_time.timestamp()), int(p.end_time.timestamp()), p.channel.name if p.channel else None))
            
        compressed_archive = zlib.compress(json.dumps(archive_intervals).encode('utf-8'))
        cache.set(archive_cache_key, compressed_archive, timeout=86400)
        
    user_archive_data = json.loads(zlib.decompress(compressed_archive).decode('utf-8'))

    today_cache_key = f"user_today_history_v1_{account_id}"
    compressed_today = cache.get(today_cache_key)
    
    if compressed_today is None:
        today_presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=start_of_today_utc
        ).select_related('channel').order_by('start_time')
        
        today_intervals = []
        for p in today_presences:
            state_int = STATE_MAP.get(p.state, 0)
            today_intervals.append((state_int, int(p.start_time.timestamp()), int(p.end_time.timestamp()), p.channel.name if p.channel else None))
            
        compressed_today = zlib.compress(json.dumps(today_intervals).encode('utf-8'))
        cache.set(today_cache_key, compressed_today, timeout=15)
        
    user_today_data = json.loads(zlib.decompress(compressed_today).decode('utf-8'))

    total_yearly_intervals = user_archive_data + user_today_data
    user_history_json_string = json.dumps(total_yearly_intervals)

    context = {
        'user_profile': user,
        'today_date': today_str,
        'selected_date': target_date_str,
        'yearly_history_json': user_history_json_string,
        'global_voice_json': day_history_json_string,
    }
    return render(request, 'public_web/user_detail.html', context)