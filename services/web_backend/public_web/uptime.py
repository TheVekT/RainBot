"""Build a status history without treating missing observations as uptime."""
from datetime import timedelta
from types import SimpleNamespace

from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from orchestrator.models import UptimeComponent, UptimePeriod

EXPECTED_COMPONENTS = (
    ('scraper', 'Rain scraper', 30),
    ('discord_bot', 'Discord bot', 30),
    ('discord_stats_tracker', 'Discord user statistics', 60),
    ('telegram_bot', 'Telegram bot', 60),
    ('api', 'API', 10),
    ('website', 'Website', 30),
)


def format_duration(seconds):
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f'{hours}h')
    if minutes:
        parts.append(f'{minutes}m')
    if seconds or not parts:
        parts.append(f'{seconds}s')
    return ' '.join(parts)


def uptime_view(request):
    now = timezone.now()
    window_start = now - timedelta(days=90)
    components = list(UptimeComponent.objects.all().order_by('name'))
    periods = UptimePeriod.objects.filter(
        component__in=components, started_at__lt=now,
    ).filter(Q(ended_at__isnull=True) | Q(ended_at__gt=window_start)).order_by('started_at')
    grouped = {component.pk: [] for component in components}
    for period in periods:
        grouped[period.component_id].append(period)

    # Keep missing observers visible without creating database records.
    existing = {component.key for component in components}
    for index, (key, name, interval) in enumerate(EXPECTED_COMPONENTS, 1):
        if key not in existing:
            component = SimpleNamespace(pk=-index, key=key, name=name, poll_interval_seconds=interval)
            components.append(component)
            grouped[component.pk] = []
    components.sort(key=lambda component: component.name.casefold())

    rows = []
    for component in components:
        spans = []
        current = 'unknown'
        for period in grouped[component.pk]:
            end = min(period.ended_at or now, now)
            if period.ended_at is None:
                stale_after = period.last_seen_at + timedelta(seconds=max(90, component.poll_interval_seconds * 3))
                if stale_after < now:
                    end = min(end, period.last_seen_at)
                else:
                    current = period.status
            start = max(period.started_at, window_start)
            if end > start:
                spans.append((start, end, period.status))

        days = []
        total = {'up': 0.0, 'down': 0.0, 'degraded': 0.0, 'unknown': 0.0}
        for index in range(90):
            start = window_start + timedelta(days=index)
            end = min(start + timedelta(days=1), now)
            durations = {'up': 0.0, 'down': 0.0, 'degraded': 0.0, 'unknown': 0.0}
            for pstart, pend, status in spans:
                duration = max(0.0, (min(end, pend) - max(start, pstart)).total_seconds())
                durations[status if status in durations else 'unknown'] += duration
            durations['unknown'] += max(0.0, (end - start).total_seconds() - sum(durations.values()))
            for status, duration in durations.items():
                total[status] += duration
            label = timezone.localtime(start).strftime('%b %d, %H:%M') + ' – ' + timezone.localtime(end).strftime('%b %d, %H:%M')
            length = (end - start).total_seconds()
            up_pct = durations['up'] / length * 100
            degraded_end = up_pct + durations['degraded'] / length * 100
            down_end = degraded_end + durations['down'] / length * 100
            days.append({
                'label': label,
                'up': format_duration(durations['up']),
                'degraded': format_duration(durations['degraded']),
                'down': format_duration(durations['down']),
                'unknown': format_duration(durations['unknown']),
                'up_pct': f'{up_pct:.4f}',
                'degraded_end': f'{degraded_end:.4f}',
                'down_end': f'{down_end:.4f}',
                'has_issue': durations['down'] > 0.001 or durations['degraded'] > 0.001,
            })
        known = total['up'] + total['down'] + total['degraded']
        rows.append({
            'component': component, 'display_name': dict((key, name) for key, name, _ in EXPECTED_COMPONENTS).get(component.key, component.name), 'status': current, 'days': days,
            'uptime': round(total['up'] / known * 100, 2) if known else None,
            'coverage': round(known / sum(total.values()) * 100, 1) if sum(total.values()) else 0,
        })
    return render(request, 'public_web/uptime.html', {'rows': rows})
