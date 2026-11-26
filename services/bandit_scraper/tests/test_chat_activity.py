import unittest
from unittest.mock import Mock, patch

from modules.scraper_core.chat_activity import ChatActivity


class ChatActivityTests(unittest.TestCase):
    def test_silence_warns_and_message_change_recovers(self):
        chat = ChatActivity()
        driver = Mock()
        driver.execute_script.side_effect = ['english', 'hello', 'hello', 'new message']
        with patch('modules.scraper_core.chat_activity.time.monotonic', side_effect=[0, 601, 632]), \
             self.assertLogs('modules.scraper_core.chat_activity', level='INFO') as logs:
            chat.sample(driver)
            chat.sample(driver)
            chat.sample(driver)
        self.assertTrue(any('has not changed' in message for message in logs.output))
        self.assertTrue(any('activity resumed' in message for message in logs.output))
        self.assertFalse(any('new message' in message for message in logs.output))

    def test_missing_chat_does_not_trigger_silence_warning(self):
        chat = ChatActivity()
        driver = Mock()
        driver.execute_script.side_effect = ['unavailable', None, 'unavailable', None]
        with patch('modules.scraper_core.chat_activity.time.monotonic', side_effect=[0, 601]), \
             patch('modules.scraper_core.chat_activity.log') as log:
            chat.sample(driver)
            chat.sample(driver)
        self.assertFalse(any('has not changed' in str(c) for c in log.warning.call_args_list))
