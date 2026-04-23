/* trace-bus.js — Session 29
 * Thin SSE client + DOM ticker. Shared by Trace (top-right) and Traced window.
 *
 * Public surface on window.__trace:
 *   start()                          — connect SSE and render ticker
 *   stop()                           — disconnect
 *   on(event, handler)               — 'event' fires with TraceEvent dict
 *   off(event, handler)
 *   open(filter)                     — open Traced window, preset filter
 *   pin(evId)                        — mark an event for Vortex timeline
 *   recent(n=10)                     — last N events already received
 */
(function () {
  if (window.__trace) return;  // idempotent

  const MAX_BUFFER = 200;
  const TICKER_DISPLAY_MS = 8000;        // each entry sticks for 8s minimum
  const MIN_SEVERITY_TICKER = 'warn';    // ticker only surfaces warn+
  const SEV_ORDER = { debug: 0, info: 1, warn: 2, error: 3, critical: 4 };

  const buffer = [];
  const handlers = { event: [] };
  let es = null;
  let tickerEl = null;
  let lastRender = 0;
  let pending = [];

  function _fire(name, data) {
    (handlers[name] || []).forEach(h => {
      try { h(data); } catch (_) {}
    });
  }

  function on(name, fn) { (handlers[name] = handlers[name] || []).push(fn); }
  function off(name, fn) {
    if (!handlers[name]) return;
    const i = handlers[name].indexOf(fn);
    if (i >= 0) handlers[name].splice(i, 1);
  }

  function recent(n) {
    n = n || 10;
    return buffer.slice(0, Math.min(n, buffer.length));
  }

  function _pushEvent(ev) {
    buffer.unshift(ev);
    if (buffer.length > MAX_BUFFER) buffer.length = MAX_BUFFER;
    _fire('event', ev);
    _maybeTick(ev);
  }

  function _maybeTick(ev) {
    if (!tickerEl) return;
    const sev = ev && ev.severity;
    if (!sev || (SEV_ORDER[sev] || 0) < (SEV_ORDER[MIN_SEVERITY_TICKER] || 2)) return;
    pending.push(ev);
    _renderTicker();
  }

  function _renderTicker() {
    if (!tickerEl) return;
    const now = Date.now();
    if (now - lastRender < 120) {
      setTimeout(_renderTicker, 120);
      return;
    }
    lastRender = now;
    // Keep only the most recent 3 pending entries
    if (pending.length > 3) pending = pending.slice(-3);

    tickerEl.innerHTML = pending.map(ev => {
      const cls = 'trace-item trace-' + (ev.severity || 'info');
      const label = (ev.kind || 'event') + (ev.agent ? ' · ' + ev.agent : '');
      const msg = (ev.message || '').slice(0, 110);
      return `<div class="${cls}" data-ev-id="${ev.id || ''}" title="Click to open Traced">
        <span class="trace-dot"></span>
        <span class="trace-kind">${_esc(label)}</span>
        <span class="trace-msg">${_esc(msg)}</span>
      </div>`;
    }).join('');

    // Bind click → open Traced window (if available)
    tickerEl.querySelectorAll('.trace-item').forEach(el => {
      el.onclick = function () { open({ highlight: el.getAttribute('data-ev-id') }); };
    });

    // Auto-drop oldest after display window
    setTimeout(() => {
      if (pending.length) {
        pending.shift();
        _renderTicker();
      }
    }, TICKER_DISPLAY_MS);
  }

  function _esc(s) {
    if (window.SwarmChat && window.SwarmChat.esc) return window.SwarmChat.esc(s);
    return String(s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function start() {
    if (es) return;
    tickerEl = document.getElementById('trace-ticker');

    // Prime with a small backlog from the DB so the user sees context on open
    fetch('/api/spine/events?limit=20&source=db')
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) return;
        (data.items || []).slice().reverse().forEach(_pushEvent);
      })
      .catch(() => {});

    try {
      es = new EventSource('/api/spine/stream');
      es.onmessage = (msg) => {
        if (!msg || !msg.data) return;
        try {
          const ev = JSON.parse(msg.data);
          _pushEvent(ev);
        } catch (_) {}
      };
      es.onerror = () => {
        // Browser auto-reconnects. Nothing to do here.
      };
    } catch (_) {
      es = null;
    }
  }

  function stop() {
    if (es) { try { es.close(); } catch (_) {} es = null; }
  }

  function open(filter) {
    filter = filter || {};
    if (typeof window.openWindow === 'function') {
      window.openWindow('traced', 'Traced', 'view-traced');
    }
    if (typeof window.loadTracedPanel === 'function') {
      setTimeout(() => window.loadTracedPanel(filter), 60);
    }
  }

  function pin(evId) {
    return fetch('/api/spine/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kind: 'system',
        source: 'trace-pin',
        message: 'Pinned event ' + evId + ' to Vortex timeline',
        payload: { pinned_event_id: evId },
      }),
    }).then(r => r.json()).catch(() => null);
  }

  window.__trace = { start, stop, on, off, recent, open, pin };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
