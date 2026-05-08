/*
 * orientation_card.js — Y.49 first-run orientation card.
 *
 * STEP-DOCS-UX-BC3D33C260. User feedback: "The Help tile is hard to find on
 * first launch" + "confused about the search bar". This card stays visible
 * on the home tile until the user dismisses it (or until the server-side
 * orientation version is bumped — see frontend/blueprints/orientation.py).
 *
 * Source of truth for the version + content is the server, which means we
 * can re-show the card after a release that adds new orientation messaging
 * without depending on every browser's localStorage.
 */
(function () {
  'use strict';

  function show(card) { if (card) card.style.display = 'block'; }
  function hide(card) { if (card) card.style.display = 'none'; }

  function dismissAndHide(card) {
    fetch('/api/orientation/dismiss', { method: 'POST' })
      .catch(function () { /* offline — still hide for this session */ })
      .finally(function () { hide(card); });
  }

  function openManualEntry() {
    // Prefer the existing window-help modal if present; fall back to a
    // dedicated full-screen Manual tile open with a hash anchor.
    if (typeof window.openWindowHelp === 'function') {
      try { window.openWindowHelp('orientation'); return; } catch (_) { /* fall through */ }
    }
    if (typeof window.openWindow === 'function') {
      window.openWindow('manual', 'Manual', 'view-manual');
      return;
    }
    window.location.hash = '#manual/orientation';
  }

  function bind() {
    var card = document.getElementById('orientation-card');
    if (!card) return;

    var dismissBtn = document.getElementById('orientation-card-dismiss');
    if (dismissBtn) {
      dismissBtn.addEventListener('click', function () { dismissAndHide(card); });
    }
    var openLink = document.getElementById('orientation-card-open-manual');
    if (openLink) {
      openLink.addEventListener('click', function (e) {
        e.preventDefault();
        openManualEntry();
      });
    }

    fetch('/api/orientation/seen')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.ok && data.seen === false) show(card); else hide(card);
      })
      .catch(function () { /* server down — leave hidden */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
