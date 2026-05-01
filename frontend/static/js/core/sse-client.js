/**
 * sse-client.js — Server-Sent Events client (R.2)
 * ═══════════════════════════════════════════════════════════════════════════════
 * Connects to /api/events and dispatches CustomEvents on document.
 *
 * Usage:
 *   document.addEventListener('sse:chat', e => console.log(e.detail));
 *   document.addEventListener('sse:agent', e => console.log(e.detail));
 *   document.addEventListener('sse:bus', e => console.log(e.detail));
 */
(function() {
  'use strict';

  var _source = null;
  var _retryMs = 2000;
  var _maxRetry = 30000;

  function connect() {
    if (_source) {
      try { _source.close(); } catch(e) {}
    }
    _source = new EventSource('/api/events');

    _source.onopen = function() {
      _retryMs = 2000;
      if (window.__SWARM_DEBUG) console.debug('[SSE] connected');
    };

    _source.onerror = function() {
      console.warn('[SSE] connection lost, retrying in ' + _retryMs + 'ms');
      _source.close();
      _source = null;
      setTimeout(connect, _retryMs);
      _retryMs = Math.min(_retryMs * 1.5, _maxRetry);
    };

    // Listen for typed events
    ['chat', 'agent', 'bus'].forEach(function(type) {
      _source.addEventListener(type, function(e) {
        try {
          var data = JSON.parse(e.data);
          document.dispatchEvent(new CustomEvent('sse:' + type, { detail: data }));
        } catch(err) {
          console.warn('[SSE] parse error for ' + type, err);
        }
      });
    });
  }

  // Auto-connect when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }

  // Expose for manual reconnect
  window.__sseReconnect = connect;
})();
