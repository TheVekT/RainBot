"""Logging configuration that protects Telegram bot credentials."""

import logging
import os
import re
from urllib.parse import quote


_TELEGRAM_URL_TOKEN = re.compile(
    r"(?i)(https?://api\.telegram\.org/bot)[^/\s?#\"']+"
)


class TelegramTokenFormatter(logging.Formatter):
    """Redact credentials after formatting, including exception tracebacks."""

    def format(self, record):
        output = super().format(record)
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        if token:
            output = output.replace(token, '[REDACTED]')
            encoded = quote(token, safe='')
            if encoded != token:
                output = output.replace(encoded, '[REDACTED]')
        return _TELEGRAM_URL_TOKEN.sub(r'\1[REDACTED]', output)


def configure_logging():
    """Apply one redacting formatter to all handlers on the root logger."""
    logging.basicConfig(level=logging.INFO)
    formatter = TelegramTokenFormatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in root.handlers:
        handler.setFormatter(formatter)
