"""Observe the public API's read-only readiness endpoint."""
import asyncio
import json
import urllib.error
import urllib.request

from uptime_common import Observer, ProbeResult


class ApiProbe:
    def __init__(self, url):
        self.url = url

    def _check(self):
        try:
            request = urllib.request.Request(self.url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=4) as response:
                body = json.loads(response.read(1024))
                if response.status == 200 and body == {'status': 'ok'}:
                    return ProbeResult('up', {'api': 'reachable', 'database': 'reachable'})
                return ProbeResult('down', {'api': 'unexpected_response'}, 'API returned an unexpected status')
        except urllib.error.HTTPError as error:
            if error.code == 503:
                try:
                    if json.loads(error.read(1024)) == {'status': 'unavailable'}:
                        return ProbeResult('degraded', {'api': 'reachable', 'database': 'unavailable'}, 'Database unavailable')
                except (ValueError, OSError):
                    pass
            return ProbeResult('down', {'api': 'unexpected_response'}, 'API returned an unexpected status')
        except (OSError, TimeoutError, ValueError):
            return ProbeResult('down', {'api': 'unreachable'}, 'API unreachable')

    async def __call__(self):
        return await asyncio.to_thread(self._check)


def create_observer(url='http://web-backend:8000/api/v1/health/'):
    return Observer('api', ApiProbe(url), interval_seconds=10, name='API')
