import zlib
import pickle
import json
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from datetime import datetime
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
    """
    Renders the unified statistical dashboard for a specific Discord user.
    Uses binary compressed zlib layer over Django cache for yearly tracking logs.
    """
    user = get_object_or_404(DiscordAccount, account_id=account_id)
    
    # Ключ кэша для хранения несдвинутых UTC-данных пользователя за год
    cache_key = f"user_binary_history_{account_id}"
    compressed_data = cache.get(cache_key)

    if compressed_data is None:
        # Если кэша нет — берем скользящее окно за последние 365 дней
        now = timezone.now()
        one_year_ago = now - timedelta(days=365)
        
        presences = DiscordUserPresence.objects.filter(
            account=user,
            start_time__gte=one_year_ago
        ).select_related('channel').order_by('start_time')

        # text
        raw_intervals = []
        for p in presences:
            state_int = STATE_MAP.get(p.state, 0)
            start_ts = int(p.start_time.timestamp())
            end_ts = int(p.end_time.timestamp())
            ch_name = p.channel.name if p.channel else None
            
            raw_intervals.append((state_int, start_ts, end_ts, ch_name))

        # Бинарная сериализация и жесткое сжатие потока через zlib
        serialized = pickle.dumps(raw_intervals)
        compressed_data = zlib.compress(serialized)
        
        # Сохраняем сжатый бинарный блоб в кэш ровно на 24 часа (86400 секунд)
        cache.set(cache_key, compressed_data, timeout=86400)
        history_source = "database"
    else:
        history_source = "cache"

    # Декомпрессия данных перед передачей в контекст шаблона
    decompressed = zlib.decompress(compressed_data)
    unpacked_history = pickle.loads(decompressed)

    # <- ИЗМЕНЕНО: Конвертируем питоновский список кортежей в строку JSON-массива
    history_json_string = json.dumps(unpacked_history)

    # Передаем дату для инициализации календаря (сегодняшний день по UTC бэкенда)
    today_str = timezone.now().strftime('%Y-%m-%d')

    context = {
        'user_profile': user,
        'today_date': today_str,
        'yearly_history_json': history_json_string,  # <- ИЗМЕНЕНО: Передаем строку, а не объект списка
        'history_source': history_source,
    }
    return render(request, 'public_web/user_detail.html', context)