/**
 * SwarmChat — shared primitives for the chat surface.
 *
 * Phase-4 foundation module. This is intentionally tiny and side-effect free
 * so it can be loaded before every view script, giving all of chat.js,
 * home-chat.js, conversations.js, library.js, skills.js, onboarding.js,
 * localai.js, studio.js, access.js and friday-auth.js a single canonical
 * HTML-escape helper.
 *
 * Contract:
 *   window.SwarmChat.esc(value)      → string, HTML-entity-escaped
 *   window.SwarmChat.escAttr(value)  → string, safe for quoted attribute
 *
 * Rules:
 *   - Always coerce via String(value ?? '').
 *   - Escape the OWASP-recommended set: & < > " '.
 *   - Never call DOM APIs. Must work during initial script parse.
 *   - Do not clobber an existing window.SwarmChat from other modules.
 */
(function () {
  'use strict';

  if (typeof window === 'undefined') return;
  var ns = window.SwarmChat || (window.SwarmChat = {});
  if (typeof ns.esc === 'function') return; // idempotent

  var AMP = /&/g, LT = /</g, GT = />/g, DQ = /"/g, SQ = /'/g;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(AMP, '&amp;')
      .replace(LT, '&lt;')
      .replace(GT, '&gt;')
      .replace(DQ, '&quot;')
      .replace(SQ, '&#39;');
  }

  ns.esc = esc;
  ns.escAttr = esc; // attribute context uses the same escape set

  // Version marker so call sites can feature-detect a minimum contract
  // without having to sniff for method existence.
  ns.version = ns.version || '1';
})();


/**
 * SwarmChat.armToConfirm — shared two-click "Delete → Confirm" helper.
 *
 * Session 28 Workstream A. Replaces native confirm() modals with an inline
 * arm-then-fire pattern: first click relabels the button to Confirm (red),
 * second click within the timeout window fires the callback, and tab-out /
 * outside-click / timeout disarms.
 *
 * Contract:
 *   SwarmChat.armToConfirm(btn, onConfirm, opts?) -> boolean
 *     returns true  if this click was the confirm click (callback fired)
 *     returns false if this click just armed the button
 *
 *   opts: {
 *     label?: string,          // default: the button's current textContent
 *     confirmLabel?: string,   // default: 'Confirm'
 *     timeoutMs?: number,      // default: 4000; time to confirm before reverting
 *     confirmColor?: string,   // default: '#f44336' (accent-red)
 *   }
 *
 * Rules:
 *   - Idempotent: re-arming a still-armed button just resets the timer.
 *   - Stores the original label on .dataset.originalLabel so revert is faithful.
 *   - Outside-click handler auto-registers once the button is armed.
 *   - No dependency on any framework; pure DOM.
 */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;
  var ns = window.SwarmChat || (window.SwarmChat = {});
  if (typeof ns.armToConfirm === 'function') return;

  var ARMED_ATTR = 'data-swarm-armed';

  function revert(btn) {
    if (!btn) return;
    var orig = btn.dataset.swarmOrigLabel;
    var origHtml = btn.dataset.swarmOrigHtml;
    var origBg = btn.dataset.swarmOrigBg;
    var origColor = btn.dataset.swarmOrigColor;
    if (origHtml != null) {
      btn.innerHTML = origHtml;
    } else if (orig != null) {
      btn.textContent = orig;
    }
    if (origBg != null) btn.style.background = origBg;
    if (origColor != null) btn.style.color = origColor;
    btn.removeAttribute(ARMED_ATTR);
    delete btn.dataset.swarmOrigLabel;
    delete btn.dataset.swarmOrigHtml;
    delete btn.dataset.swarmOrigBg;
    delete btn.dataset.swarmOrigColor;
    if (btn._swarmArmTimer) {
      clearTimeout(btn._swarmArmTimer);
      btn._swarmArmTimer = null;
    }
    if (btn._swarmArmOutside) {
      document.removeEventListener('click', btn._swarmArmOutside, true);
      btn._swarmArmOutside = null;
    }
  }

  function armToConfirm(btn, onConfirm, opts) {
    if (!btn || typeof onConfirm !== 'function') return false;
    opts = opts || {};
    var confirmLabel = opts.confirmLabel || 'Confirm';
    var timeoutMs = typeof opts.timeoutMs === 'number' ? opts.timeoutMs : 4000;
    var confirmColor = opts.confirmColor || '#f44336';

    if (btn.getAttribute(ARMED_ATTR) === '1') {
      // Second click → fire and disarm BEFORE callback so the callback
      // can safely DOM-mutate (e.g. remove the button's row).
      revert(btn);
      try { onConfirm(); } catch (e) { /* caller owns error UX */ }
      return true;
    }

    // First click → arm. Preserve innerHTML so icon-only buttons survive revert.
    btn.dataset.swarmOrigLabel = opts.label != null ? String(opts.label) : btn.textContent;
    btn.dataset.swarmOrigHtml = btn.innerHTML;
    btn.dataset.swarmOrigBg = btn.style.background || '';
    btn.dataset.swarmOrigColor = btn.style.color || '';
    btn.textContent = confirmLabel;
    btn.style.background = confirmColor;
    btn.style.color = '#fff';
    btn.setAttribute(ARMED_ATTR, '1');

    btn._swarmArmTimer = setTimeout(function () { revert(btn); }, timeoutMs);

    btn._swarmArmOutside = function (ev) {
      if (ev.target === btn || (btn.contains && btn.contains(ev.target))) return;
      revert(btn);
    };
    // capture=true so we see the click before it bubbles to handlers that
    // might stopPropagation.
    setTimeout(function () {
      document.addEventListener('click', btn._swarmArmOutside, true);
    }, 0);

    return false;
  }

  ns.armToConfirm = armToConfirm;
  ns.disarmConfirm = revert;

  // ── Shared delete icon + helper ───────────────────────────────────────────
  // Session 30.2 Block C1: system-wide trashcan → confirm pattern.
  ns.TRASH_SVG = '<svg viewBox="0 0 16 16" width="13" height="13" fill="none"><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M3 4h10M4.5 4l.5 9a1 1 0 001 1h4a1 1 0 001-1l.5-9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  /**
   * armDelete — convenience wrapper around armToConfirm for delete buttons.
   * Adds the trashcan icon if the button is empty/text-only, then arms.
   *
   *   SwarmChat.armDelete(btn, onConfirm, opts?)
   *     opts.confirmLabel default: 'Delete?'
   *     opts.timeoutMs    default: 4000
   *     opts.confirmColor default: '#f44336'
   */
  function armDelete(btn, onConfirm, opts) {
    if (!btn || typeof onConfirm !== 'function') return false;
    opts = opts || {};
    // If button has no innerHTML or only whitespace, inject the trashcan icon.
    var html = String(btn.innerHTML || '');
    var text = btn.textContent || '';
    if (!html.trim() || (text.trim() && !/<svg/i.test(html))) {
      btn.innerHTML = ns.TRASH_SVG;
    }
    return armToConfirm(btn, onConfirm, {
      confirmLabel: opts.confirmLabel || 'Delete?',
      timeoutMs: typeof opts.timeoutMs === 'number' ? opts.timeoutMs : 4000,
      confirmColor: opts.confirmColor || '#f44336'
    });
  }
  ns.armDelete = armDelete;
})();


/**
 * SwarmChat.actions — unified Phase 4 action-pill pipeline.
 *
 * Workstream J: gives both the main chat window (chat.js) and the home-page
 * tile chat (home-chat.js) the same "Siri-but-better" action pill. The server
 * endpoint /api/chat/action-intent already returns {ok, intent}; this module
 * owns the presentation + dispatch contract so both surfaces stay in sync.
 *
 * Contract:
 *   SwarmChat.fetchActionIntent(message) -> Promise<intent|null>
 *   SwarmChat.executeIntent(intent)      -> void  (UI dispatch, never throws)
 *   SwarmChat.maybeShowActionPill(hostEl, message, opts?) -> void
 *     opts.minConfidence (default 0.7)
 *     opts.compact (default false) — smaller pill for the tile chat
 */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;
  var ns = window.SwarmChat || (window.SwarmChat = {});
  if (typeof ns.maybeShowActionPill === 'function') return;

  function fetchActionIntent(message) {
    var text = String(message == null ? '' : message).trim();
    if (!text) return Promise.resolve(null);
    return fetch('/api/chat/action-intent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok || !data.intent) return null;
        return data.intent;
      })
      .catch(function () { return null; });
  }

  function executeIntent(intent) {
    if (!intent || !intent.id) return;
    var args = intent.args || {};
    try {
      switch (intent.id) {
        case 'open_window':
          if (typeof window.openWindow === 'function' && args.view) {
            window.openWindow(args.view, args.title || args.view, args.template || ('view-' + args.view));
          }
          break;
        case 'spotlight_search':
          if (typeof window.openSpotlight === 'function') {
            window.openSpotlight();
            setTimeout(function () {
              var inp = document.getElementById('spotlight-input');
              if (inp) {
                inp.value = String(args.q || '');
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.focus();
              }
            }, 60);
          }
          break;
        case 'vortex_capture':
          if (typeof window.openWindow === 'function') {
            window.openWindow('time-wizard', 'Vortex', 'view-time-wizard');
          }
          setTimeout(function () {
            if (typeof window.createTwCheckpoint === 'function') window.createTwCheckpoint();
          }, 250);
          break;
        case 'go_home':
          if (typeof window.goHome === 'function') window.goHome();
          break;
        case 'show_shortcuts': {
          var m = document.getElementById('shortcuts-help-modal');
          if (m) m.classList.add('open');
          break;
        }
        default:
          break;
      }
    } catch (_) { /* never let UI dispatch throw into the chat loop */ }
  }

  function maybeShowActionPill(hostEl, message, opts) {
    if (!hostEl) return;
    opts = opts || {};
    var minConf = typeof opts.minConfidence === 'number' ? opts.minConfidence : 0.7;
    var compact = !!opts.compact;
    fetchActionIntent(message).then(function (intent) {
      if (!intent) return;
      if ((Number(intent.confidence) || 0) < minConf) return;
      var pill = document.createElement('div');
      pill.className = 'swarm-action-pill' + (compact ? ' swarm-action-pill-compact' : '');
      var pad = compact ? '6px 10px' : '8px 12px';
      var fontSize = compact ? '10.5px' : '11.5px';
      pill.style.cssText = 'margin:4px 0 6px;padding:' + pad + ';background:color-mix(in srgb,var(--accent) 10%,var(--card));border:1px solid color-mix(in srgb,var(--accent) 45%,var(--border));border-radius:8px;display:flex;align-items:center;gap:10px;font-size:' + fontSize + ';';
      var label = ns.esc(intent.label || 'Run action');
      var rationale = ns.esc(intent.rationale || '');
      pill.innerHTML = ''
        + '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" style="color:var(--accent);flex-shrink:0;"><path d="M4 3l8 5-8 5V3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>'
        + '<div style="flex:1;min-width:0;">'
        +   '<div style="font-weight:600;color:var(--text);">' + label + '</div>'
        +   (compact ? '' : '<div style="font-size:10px;color:var(--text-dim);margin-top:1px;">Detected action · ' + rationale + '</div>')
        + '</div>'
        + '<button class="swarm-action-run" style="padding:4px 10px;background:var(--accent);border:none;border-radius:4px;color:#000;font-size:10.5px;font-weight:700;cursor:pointer;">Execute</button>'
        + '<button class="swarm-action-dismiss" title="Dismiss" style="background:none;border:none;color:var(--text-dim);cursor:pointer;padding:2px 4px;display:flex;align-items:center;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></button>';
      pill.querySelector('.swarm-action-run').addEventListener('click', function () {
        executeIntent(intent);
        pill.style.opacity = '0.55';
        pill.style.pointerEvents = 'none';
        var runBtn = pill.querySelector('.swarm-action-run');
        if (runBtn) runBtn.textContent = '\u2713 Done';
      });
      pill.querySelector('.swarm-action-dismiss').addEventListener('click', function () { pill.remove(); });
      hostEl.appendChild(pill);
      if (hostEl.scrollHeight) hostEl.scrollTop = hostEl.scrollHeight;
    });
  }

  ns.fetchActionIntent = fetchActionIntent;
  ns.executeIntent = executeIntent;
  ns.maybeShowActionPill = maybeShowActionPill;
})();

