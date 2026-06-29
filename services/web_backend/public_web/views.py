import json
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from datetime import datetime
from django.http import HttpResponse
from django.views.decorators.cache import cache_page
from orchestrator.models import DiscordAccount
from .services import get_global_voice_stats, get_user_archive_stats, get_user_today_stats

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

def user_detail_view(request, account_id):
    user = get_object_or_404(DiscordAccount, account_id=account_id)
    
    # Handle calendar target date evaluation
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = timezone.now().date()
    else:
        target_date = timezone.now().date()
        
    today_date = timezone.now().date()
    today_str = today_date.strftime('%Y-%m-%d')
    target_date_str = target_date.strftime('%Y-%m-%d')
    
    # Fetch global daily stats (can be shared across other views)
    global_intervals, global_channels = get_global_voice_stats(target_date, today_date)
    
    # Fast route for dynamic JSON timeline polling requests
    if request.GET.get('format') == 'json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponse(json.dumps(global_intervals), content_type='application/json')

    # Prepare timeline frames bounds
    start_of_today = timezone.make_aware(datetime.combine(today_date, datetime.min.time()))
    channels_dict = {}
    channels_dict.update(global_channels)

    # Fetch dedicated target user payloads
    user_archive, archive_channels = get_user_archive_stats(user, account_id, today_str, start_of_today)
    channels_dict.update(archive_channels)
    
    user_today, today_channels = get_user_today_stats(user, account_id, today_str, start_of_today)
    channels_dict.update(today_channels)

    context = {
        'user_profile': user,
        'today_date': today_str,
        'selected_date': target_date_str,
        'yearly_archive_json': json.dumps(user_archive),
        'user_today_json': json.dumps(user_today),
        'global_voice_json': json.dumps(global_intervals),
        'channels_mapping_json': json.dumps(channels_dict),
    }
    return render(request, 'public_web/user_detail.html', context)