"""Best-effort chat language selection and activity diagnostics."""
import hashlib
import logging
import time

log = logging.getLogger(__name__)


class ChatActivity:
    SAMPLE_SECONDS = 30
    SILENCE_SECONDS = 10 * 60
    LANGUAGE_RETRY_SECONDS = 60

    def __init__(self):
        self.reset()

    def reset(self):
        self.driver = None
        self.last_sample = self.last_language_attempt = None
        self.fingerprint = self.last_change = self.last_warning = None
        self.language_confirmed = False
        self.language_opened = False

    def sample(self, driver):
        if driver is not self.driver:
            self.reset()
            self.driver = driver
        now = time.monotonic()
        if self.last_sample is not None and now - self.last_sample < self.SAMPLE_SECONDS:
            return
        self.last_sample = now
        # Restrict selection to the chat footer, not the site's language menu.
        if not self.language_confirmed:
            if self.language_opened:
                selected = driver.execute_script("""
                    const isVisible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
                    const options = [...document.querySelectorAll('.v-menu__content.menuable__content__active .v-list-item, [role="option"], [role="menuitem"]')];
                    const item = options.find(e => isVisible(e) && /^(english|английский)$/i.test(e.innerText.trim()));
                    if (!item) return false;
                    item.click(); return true;
                """)
                self.language_opened = False
                if not selected:
                    log.warning('Could not find English in the chat language menu')
            if self.last_language_attempt is None or now - self.last_language_attempt >= self.LANGUAGE_RETRY_SECONDS:
                result = driver.execute_script("""
                    const footer = document.querySelector('.sidebar-chat .chat-footer');
                    if (!footer) return 'unavailable';
                    const button = footer.querySelector('button:has([class*="twf-"])');
                    if (!button) return 'unavailable';
                    if (/^english$/i.test(button.innerText.trim())) return 'english';
                    button.click(); return 'opened';
                """)
                self.last_language_attempt = now
                self.language_confirmed = result == 'english'
                self.language_opened = result == 'opened'
                if self.language_confirmed:
                    log.info('Chat language confirmed: English')
                elif result == 'unavailable':
                    log.warning('Chat language selector unavailable; current language is unverified')
        text = driver.execute_script("""
            const chat = document.querySelector('.chat-messages');
            return chat ? chat.textContent : null;
        """)
        if text is None:
            self.fingerprint = self.last_change = self.last_warning = None
            return
        digest = hashlib.sha256(text.encode('utf-8')).digest()
        if self.fingerprint is None or digest != self.fingerprint:
            if self.last_warning is not None:
                log.info('Chat activity resumed')
            self.fingerprint, self.last_change, self.last_warning = digest, now, None
        elif (now - self.last_change >= self.SILENCE_SECONDS and
              (self.last_warning is None or now - self.last_warning >= self.SILENCE_SECONDS)):
            log.warning('Chat has not changed for %.0f minutes; language=%s (silence does not prove a failure)',
                        (now - self.last_change) / 60, 'English' if self.language_confirmed else 'unverified')
            self.last_warning = now
