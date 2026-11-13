"""MutationObserver reader for the rain widget.

No network interception. The owner must serialize all Selenium access. The
periodic heartbeat rechecks state to limit damage from missed DOM mutations.
Snapshots are observations, not proof that the site connection is healthy.
"""
from bs4 import BeautifulSoup

_SELECT = r"""
const EXPECTED = 'px-4 chat-rain-outer mb-2';
const SPACE = /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/;
function findRain() {
  for (const el of document.querySelectorAll('div[class*="chat-rain-outer"]')) {
    if ((el.getAttribute('class') || '').split(SPACE).filter(Boolean).join(' ') === EXPECTED) return el;
  }
  return null;
}
function needsFullSource() {
  for (const el of document.querySelectorAll('template,noscript'))
    if (el.outerHTML.toLowerCase().includes('<div')) return true;
  return false;
}
"""

INSTALL_JS = _SELECT + r"""
const maxQueue = arguments[0], key = '__rain_soak_observer_v2';
if (window[key]) return window[key].documentId;
const state = {documentId: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  queue: [], maxQueue, seq: 0, dropped: 0, waiter: null, previous: undefined,
  selected: null, callbacks: 0, relevantCallbacks: 0};
function deliver() {
  if (!state.waiter || !state.queue.length) return;
  const w = state.waiter; state.waiter = null; clearTimeout(w.timer);
  const e = state.queue.shift(); e.dropped = state.dropped; state.dropped = 0; w.done(e);
}
function capture(reason) {
  const selected = findRain();
  const html = selected ? selected.outerHTML : null;
  const fallback = needsFullSource();
  state.selected = selected;
  // Fall back to current full DOM on heartbeat too; template content may change
  // without triggering document subtree MutationObserver.
  const keyValue = JSON.stringify([html, fallback]);
  if (keyValue === state.previous && !(fallback && reason === 'heartbeat')) return;
  state.previous = keyValue;
  const event = {kind:'snapshot', documentId:state.documentId, sequence:++state.seq,
    html, fallback, reason, observedAt:Date.now()};
  if (state.queue.length >= state.maxQueue) { state.queue.shift(); state.dropped++; }
  state.queue.push(event); deliver();
}
function mayContainRain(node) {
  if (!node || node.nodeType !== Node.ELEMENT_NODE) return false;
  return node.matches('div[class*="chat-rain-outer"]') ||
    !!node.querySelector('div[class*="chat-rain-outer"]');
}
function relevant(records) {
  for (const m of records) {
    const t = m.target, selected = state.selected;
    if (selected && (t === selected || selected.contains(t))) return true;
    if (m.type === 'attributes') {
      if (m.attributeName === 'class' && mayContainRain(t)) return true;
      continue;
    }
    if (m.type === 'childList') {
      for (const n of m.removedNodes)
        if ((selected && (n === selected || n.contains(selected))) || mayContainRain(n)) return true;
      for (const n of m.addedNodes) if (mayContainRain(n)) return true;
    }
  }
  return false;
}
state.wait = function(timeoutMs, done) {
  if (state.waiter) { done({kind:'error', message:'concurrent wait'}); return; }
  state.waiter = {done};
  state.waiter.timer = setTimeout(() => {
    if (!state.waiter) return;
    capture('heartbeat');
    if (!state.waiter) return;
    state.waiter = null;
    done({kind:'heartbeat', documentId:state.documentId, callbacks:state.callbacks,
      relevantCallbacks:state.relevantCallbacks});
  }, timeoutMs);
  deliver();
};
state.stop = function() {
  state.observer.disconnect();
  if (state.waiter) { clearTimeout(state.waiter.timer); state.waiter = null; }
  delete window[key];
};
state.observer = new MutationObserver(records => {
  state.callbacks++;
  if (relevant(records)) { state.relevantCallbacks++; capture('mutation'); }
});
state.observer.observe(document, {childList:true, subtree:true, characterData:true, attributes:true});
window[key] = state; capture('initial'); return state.documentId;
"""

WAIT_JS = r"""
const state=window.__rain_soak_observer_v2, done=arguments[arguments.length-1];
if (!state) { done({kind:'observer_missing'}); return; }
state.wait(arguments[0], done);
"""


class EventObserver:
    """Emit snapshots, heartbeats, uncertainty and errors; never fabricate END."""
    def __init__(self, driver, queue_size=256, timeout_ms=1000):
        if queue_size < 1 or not 1 <= timeout_ms <= 5000:
            raise ValueError('invalid queue size or timeout')
        self.driver, self.queue_size, self.timeout_ms = driver, queue_size, timeout_ms
        self.document_id = None
        self.need_install = True
        self.driver.set_script_timeout(timeout_ms / 1000 + 2)

    def next_event(self):
        try:
            if self.need_install:
                new = self.driver.execute_script(INSTALL_JS, self.queue_size)
                old, self.document_id, self.need_install = self.document_id, new, False
                if old != new:
                    return {'kind':'document_reset', 'oldDocumentId':old, 'documentId':new}
            event = self.driver.execute_async_script(WAIT_JS, self.timeout_ms)
            if not isinstance(event, dict):
                self.need_install = True
                return {'kind':'error', 'message':'empty observer response'}
            if event.get('kind') == 'observer_missing':
                self.need_install = True
                return {'kind':'document_uncertain', 'message':'observer missing'}
            if event.get('kind') == 'snapshot' and event.get('fallback'):
                # Full serialization has to be read now; queued historic
                # snapshots cannot reconstruct full DOM at their earlier time.
                event['html'] = self.driver.page_source
                event['resync'] = True
            return event
        except Exception as exc:
            # Preserve the original scraper's deliberate fatal response to
            # file descriptor exhaustion so Docker can restart the process.
            if getattr(exc, 'errno', None) == 24 or 'too many open files' in str(exc).lower():
                raise
            self.need_install = True
            return {'kind':'error', 'message':str(exc)}

    @staticmethod
    def event_text(event):
        if event.get('kind') != 'snapshot':
            raise ValueError('only successful snapshots have event text')
        html = event.get('html')
        if html is None:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        node = soup.find('div', {'class':'px-4 chat-rain-outer mb-2'})
        return node.text if node else None

    def close(self):
        try:
            self.driver.execute_script("const s=window.__rain_soak_observer_v2; if(s) s.stop();")
        except Exception as exc:
            if getattr(exc, 'errno', None) == 24 or 'too many open files' in str(exc).lower():
                raise
