/*
 * home_banner.js — first-run empty-state banner
 *
 * Shows the welcome/seed banner when /api/wishlist/summary reports zero
 * entries across all four pillars AND the user has not dismissed it.
 * Dismissal is persisted in localStorage so it does not nag.
 */
(function () {
  'use strict';

  var DISMISS_KEY = 'swarm_first_run_banner_dismissed_v1';

  function show(banner) {
    if (!banner) return;
    banner.style.display = 'block';
  }

  function hide(banner) {
    if (!banner) return;
    banner.style.display = 'none';
  }

  function bind() {
    var banner = document.getElementById('first-run-banner');
    if (!banner) return;

    var dismissBtn = document.getElementById('first-run-banner-dismiss');
    if (dismissBtn) {
      dismissBtn.addEventListener('click', function () {
        try { localStorage.setItem(DISMISS_KEY, '1'); } catch (_) { /* ignore */ }
        hide(banner);
      });
    }

    var dismissed = false;
    try { dismissed = localStorage.getItem(DISMISS_KEY) === '1'; } catch (_) { /* ignore */ }
    if (dismissed) { hide(banner); return; }

    fetch('/api/wishlist/summary')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var pillars = (data && data.pillars) || {};
        var totalOpen = 0;
        Object.keys(pillars).forEach(function (slug) {
          var p = pillars[slug] || {};
          totalOpen += Number(p.open || p.count || 0);
        });
        if (totalOpen === 0) show(banner); else hide(banner);
      })
      .catch(function () { /* server down — leave banner hidden */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
