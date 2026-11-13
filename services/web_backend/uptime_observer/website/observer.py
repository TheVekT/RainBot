"""Probe the site's HTTP response without modifying application state."""
import asyncio
import os

import requests

from uptime_common import Observer, ProbeResult


class WebsiteProbe:
    def __init__(self, url=None):
        # This measures availability from the observer container. Configure an
        # external URL explicitly if public DNS/TLS reachability is desired.
        self.url = url or os.getenv('UPTIME_WEBSITE_URL', 'http://web-backend:8000/users/')

    def _request(self):
        try:
            with requests.Session() as client:
                client.trust_env = False
                with client.get(self.url, timeout=5, allow_redirects=False, stream=True) as response:
                    status_code = response.status_code
        except requests.Timeout:
            return ProbeResult('down', {'http': 'timeout'}, 'Website request timed out')
        except requests.RequestException:
            # Avoid storing the URL or exception text; either may contain secrets.
            return ProbeResult('down', {'http': 'unreachable'}, 'Website unavailable')
        if 200 <= status_code < 300:
            return ProbeResult('up', {'http': 'ok'})
        if 300 <= status_code < 400:
            return ProbeResult('degraded', {'http': 'redirect'}, 'Website redirected')
        return ProbeResult('down', {'http': 'error', 'status_code': status_code}, 'Website returned an error')

    async def __call__(self):
        return await asyncio.to_thread(self._request)


def create_observer(url=None):
    return Observer('website', WebsiteProbe(url), interval_seconds=30, name='Website')
