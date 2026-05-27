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
  var _retryTimer = null;
  var _retryMs = 2000;
  var _maxRetry = 30000;
  var _isPageClosing = false;

  function _clearRetry() {
    if (_retryTimer) {
      clearTimeout(_retryTimer);
      _retryTimer = null;
    }
  }

  function _scheduleReconnect() {
    if (_isPageClosing || !navigator.onLine) return;
    _clearRetry();
    _retryTimer = setTimeout(connect, _retryMs);
    _retryMs = Math.min(_retryMs * 1.5, _maxRetry);
  }

  function _closeSource() {
    if (_source) {
      try { _source.close(); } catch(e) {}
      _source = null;
    }
  }

  function connect() {
    if (_isPageClosing || !navigator.onLine) return;
    _clearRetry();
    _closeSource();
    _source = new EventSource('/api/events');

    _source.onopen = function() {
      _retryMs = 2000;
      if (window.__SWARM_DEBUG) console.debug('[SSE] connected');
    };

    _source.onerror = function() {
      if (window.__SWARM_DEBUG && !_isPageClosing && navigator.onLine) {
        console.debug('[SSE] reconnect in ' + _retryMs + 'ms');
      }
      _closeSource();
      _scheduleReconnect();
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

  window.addEventListener('online', function() {
    if (!_source && !_isPageClosing) connect();
  });

  window.addEventListener('pagehide', function() {
    _isPageClosing = true;
    _clearRetry();
    _closeSource();
  });

  // Auto-connect when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }

  // Expose for manual reconnect
  window.__sseReconnect = connect;
})();
