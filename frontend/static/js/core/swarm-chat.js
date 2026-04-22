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
