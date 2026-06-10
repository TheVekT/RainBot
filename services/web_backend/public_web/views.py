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
    today_str = timezone.now().strftime('%Y-%m-%d')

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

    user_cache_key = f"user_safe_history_v1_{account_id}"
    compressed_user_data = cache.get(user_cache_key)

    if compressed_user_data is None:
        now = timezone.now()
        one_year_ago = now - timedelta(days=365)
        
        presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=one_year_ago
        ).select_related('channel').order_by('start_time')

        raw_intervals = []
        for p in presences:
            state_int = STATE_MAP.get(p.state, 0)
            start_ts = int(p.start_time.timestamp())
            end_ts = int(p.end_time.timestamp())
            ch_name = p.channel.name if p.channel else None
            raw_intervals.append((state_int, start_ts, end_ts, ch_name))

        serialized_user = json.dumps(raw_intervals).encode('utf-8')
        compressed_user_data = zlib.compress(serialized_user)
        cache.set(user_cache_key, compressed_user_data, timeout=86400)
        history_source = "database"
    else:
        history_source = "cache"

    user_history_json_string = zlib.decompress(compressed_user_data).decode('utf-8')

    context = {
        'user_profile': user,
        'today_date': today_str,
        'selected_date': target_date_str,
        'yearly_history_json': user_history_json_string,
        'global_voice_json': day_history_json_string,
        'history_source': history_source,
    }
    return render(request, 'public_web/user_detail.html', context)