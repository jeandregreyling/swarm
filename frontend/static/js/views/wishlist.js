/* wishlist.js — populate wishlist pillar views from /api/wishlist/pillars/<slug>.
 *
 * Runs on window-open. Looks up the .wishlist-pillar-view inside the just-
 * opened window, reads its data-pillar-slug, fetches the API, and fills in
 * the description + step list. Failure-tolerant: keeps the placeholder copy
 * if the API isn't reachable so the tile still opens cleanly.
 *
 * Hooked from app.js / window-manager.js by listening for the generic
 * 'window:opened' event if the bus exposes one, otherwise wires a
 * MutationObserver fallback so it works regardless of how the window was
 * opened.
 */
(function () {
  'use strict';

  const STATUS_LABELS = {
    todo: 'todo',
    doing: 'doing',
    done: 'done',
    blocked: 'blocked',
    skip: 'skip',
  };

  function escape(text) {
    if (text == null) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function renderStep(step) {
    const status = STATUS_LABELS[step.status] || step.status || 'todo';
    return (
      '<li class="wishlist-step" style="padding:8px 10px;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;background:var(--card);">'
      + '<div style="display:flex;align-items:center;gap:8px;">'
      + '<code style="font-size:10px;color:var(--text-dim);">' + escape(step.step_id) + '</code>'
      + '<span class="wishlist-step-status" style="font-size:9px;padding:1px 6px;border-radius:8px;background:var(--bg);color:var(--text-dim);text-transform:uppercase;letter-spacing:0.4px;">' + escape(status) + '</span>'
      + '</div>'
      + '<div class="wishlist-step-title" style="font-size:12px;margin-top:4px;font-weight:600;">' + escape(step.title) + '</div>'
      + (step.description
        ? '<div class="wishlist-step-desc" style="font-size:11px;color:var(--text-dim);margin-top:4px;line-height:1.5;white-space:pre-wrap;">' + escape(step.description.slice(0, 600)) + (step.description.length > 600 ? '…' : '') + '</div>'
        : '')
      + '</li>'
    );
  }

  function populate(view) {
    if (!view || view.dataset.wishlistPopulated === '1') return;
    const slug = view.dataset.pillarSlug;
    if (!slug) return;
    view.dataset.wishlistPopulated = '1';

    fetch('/api/wishlist/pillars/' + encodeURIComponent(slug))
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (body) {
        if (!body || body.ok !== true) throw new Error('bad payload');
        const desc = view.querySelector('.wishlist-pillar-description');
        if (desc) desc.textContent = body.description || '';
        const list = view.querySelector('.wishlist-pillar-steps');
        if (list) {
          if (Array.isArray(body.steps) && body.steps.length) {
            list.innerHTML = body.steps.map(renderStep).join('');
          } else {
            list.innerHTML = '<li style="font-size:11px;color:var(--text-dim);">No backing steps captured yet.</li>';
          }
        }
      })
      .catch(function () {
        const list = view.querySelector('.wishlist-pillar-steps');
        if (list && !list.children.length) {
          list.innerHTML = '<li style="font-size:11px;color:var(--text-dim);">(unable to load wishlist details)</li>';
        }
      });
  }

  // Public API: explicit populate of all visible pillar views.
  window.wishlistPopulateAll = function () {
    document.querySelectorAll('.wishlist-pillar-view').forEach(populate);
  };

  // Auto-populate when a pillar view appears in the DOM (any window-manager).
  function scanAndPopulate() {
    document.querySelectorAll('.wishlist-pillar-view').forEach(populate);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scanAndPopulate);
  } else {
    scanAndPopulate();
  }

  const observer = new MutationObserver(function (muts) {
    let needsScan = false;
    for (const m of muts) {
      for (const node of m.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.classList && node.classList.contains('wishlist-pillar-view')) { needsScan = true; break; }
        if (node.querySelector && node.querySelector('.wishlist-pillar-view')) { needsScan = true; break; }
      }
      if (needsScan) break;
    }
    if (needsScan) scanAndPopulate();
  });
  observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
})();
