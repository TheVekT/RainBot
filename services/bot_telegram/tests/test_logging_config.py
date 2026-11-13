import logging
import os
import unittest
from unittest.mock import patch
from urllib.parse import quote

from utils.logging_config import TelegramTokenFormatter


class LoggingRedactionTests(unittest.TestCase):
    def setUp(self):
        self.formatter = TelegramTokenFormatter('%(message)s')
        self.token = '123456789:TEST_fake_telegram_secret'

    def record(self, message, args=(), exc_info=None):
        return logging.LogRecord('httpx', logging.INFO, __file__, 1, message, args, exc_info)

    def test_redacts_url_and_preserves_method_and_status(self):
        url = 'https://api.telegram.org/bot' + self.token + '/getUpdates'
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': self.token}):
            output = self.formatter.format(self.record('HTTP Request: %s %s %s', ('POST', url, '200 OK')))
        self.assertNotIn(self.token, output)
        self.assertIn('/bot[REDACTED]/getUpdates', output)
        self.assertIn('200 OK', output)

    def test_redacts_encoded_and_exception_credentials(self):
        try:
            raise ValueError('failed token ' + self.token)
        except ValueError:
            import sys
            record = self.record('encoded=%s', (quote(self.token, safe=''),), sys.exc_info())
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': self.token}):
            output = self.formatter.format(record)
        self.assertNotIn(self.token, output)
        self.assertNotIn(quote(self.token, safe=''), output)
        self.assertIn('ValueError', output)

    def test_redacts_telegram_url_even_without_token_environment(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': ''}):
            output = self.formatter.format(self.record('https://api.telegram.org/bot%s/getMe', (self.token,)))
        self.assertNotIn(self.token, output)
        self.assertIn('/bot[REDACTED]/getMe', output)


if __name__ == '__main__':
    unittest.main()
