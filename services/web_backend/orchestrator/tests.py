from datetime import datetime, timezone

from django.test import SimpleTestCase

from .models import UptimeComponent, UptimePeriod, UptimeSnapshot


class UptimeLabelsTests(SimpleTestCase):
    def test_component_name_is_used_for_related_objects(self):
        component = UptimeComponent(key='api', name='API', poll_interval_seconds=10)
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        period = UptimePeriod(component=component, status='up', started_at=at, last_seen_at=at)
        snapshot = UptimeSnapshot(component=component, status='down', observed_at=at)

        self.assertEqual(str(component), 'API (api)')
        self.assertIn('API (api): up', str(period))
        self.assertIn('API (api): down', str(snapshot))
