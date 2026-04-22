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
    var origBg = btn.dataset.swarmOrigBg;
    var origColor = btn.dataset.swarmOrigColor;
    if (orig != null) btn.textContent = orig;
    if (origBg != null) btn.style.background = origBg;
    if (origColor != null) btn.style.color = origColor;
    btn.removeAttribute(ARMED_ATTR);
    delete btn.dataset.swarmOrigLabel;
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

    // First click → arm
    btn.dataset.swarmOrigLabel = opts.label != null ? String(opts.label) : btn.textContent;
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
})();

