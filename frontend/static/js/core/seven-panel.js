'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   seven-panel.js — Shared "Seven sees" footer panel.
   Single helper used by Studio (proposals/projects/records/testlab) and
   Records detail panes to render a compact, propose-only insight pane:
     * narrative (lines from /api/seven/explain?focus=...)
     * top related neighbours (from /api/seven/observe?focus=...)
     * up to 3 ranked proposals from /api/seven/decide?intent=next&focus=...
   The panel is read-only. Activating any neighbour row re-opens Spotlight
   prefilled with that record id so the user can keep walking the graph.

   Usage:
     SevenPanel.mount(targetEl, { kind: 'proposal', id: 'PR-XXXX' });
     SevenPanel.mount(targetEl, { kind: 'project',  id: 'P-XXXX' });

   Idempotent: repeated calls replace the previous mount in the same target.
   Failure-quiet: if /api/seven/* is unreachable, it renders nothing.
   ────────────────────────────────────────────────────────────────────────── */

(function () {
  if (window.SevenPanel) return; // singleton

  const SPARKLE_SVG = '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">'
    + '<path d="M8 2l1.1 3.4L12.5 6.5 9.1 7.6 8 11 6.9 7.6 3.5 6.5l3.4-1.1L8 2z" '
    + 'stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>'
    + '<path d="M12.5 11l.5 1.4 1.4.5-1.4.5-.5 1.4-.5-1.4-1.4-.5 1.4-.5.5-1.4z" '
    + 'stroke="currentColor" stroke-width="1" stroke-linejoin="round"/></svg>';

  const SAFE = (window.SwarmChat && window.SwarmChat.esc)
    ? window.SwarmChat.esc
    : function (s) {
        return String(s == null ? '' : s)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;')
          .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      };

  function _focusKey(kind, id) {
    if (!id) return '';
    return kind ? `${kind}:${id}` : id;
  }

  function _pivotToRecord(rid) {
    if (!rid) return;
    if (typeof window.openSpotlight === 'function') {
      try {
        window.openSpotlight();
        const inp = document.getElementById('spotlight-input');
        if (inp) {
          inp.value = rid;
          inp.dispatchEvent(new Event('input', { bubbles: true }));
        }
      } catch (e) { /* noop */ }
    }
  }

  function _shellHtml(focusLabel) {
    return '<div class="seven-panel" data-seven-panel="1" '
      + 'style="margin-top:14px;border-top:1px solid var(--border, rgba(255,255,255,0.12));'
      + 'padding-top:10px;font-size:12px;line-height:1.45;">'
      + '<div class="seven-panel-header" '
      + 'style="display:flex;align-items:center;gap:6px;margin-bottom:8px;'
      + 'opacity:0.85;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;font-size:11px;">'
      + SPARKLE_SVG + '<span>Seven sees</span>'
      + (focusLabel ? '<span style="opacity:0.55;font-weight:400;text-transform:none;letter-spacing:0;">'
          + '· ' + SAFE(focusLabel) + '</span>' : '')
      + '<span class="seven-panel-status" style="margin-left:auto;opacity:0.55;font-weight:400;'
      + 'text-transform:none;letter-spacing:0;font-size:11px;">…</span>'
      + '</div>'
      + '<div class="seven-panel-body"></div>'
      + '</div>';
  }

  function _renderBody(bodyEl, statusEl, payload) {
    const lines = (payload.explain && payload.explain.lines) || [];
    const observe = payload.observe || {};
    const decide = payload.decide || {};
    const proposals = decide.proposals || [];
    const related = observe.related || {};
    const counts = related.counts || {};

    let html = '';

    if (lines.length) {
      html += '<div class="seven-panel-narr" style="margin-bottom:10px;">';
      lines.forEach((line) => {
        html += '<div style="padding:3px 0;">' + SAFE(line) + '</div>';
      });
      html += '</div>';
    }

    // Compact relation chip row.
    const cKeys = Object.keys(counts);
    if (cKeys.length) {
      html += '<div class="seven-panel-chips" '
        + 'style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;">';
      cKeys.forEach((k) => {
        html += '<span style="border:1px solid var(--border, rgba(255,255,255,0.18));'
          + 'border-radius:10px;padding:1px 8px;font-size:11px;opacity:0.85;">'
          + SAFE(k) + ' × ' + (counts[k] | 0) + '</span>';
      });
      html += '</div>';
    }

    // Up to 3 ranked proposals — clickable.
    if (proposals.length) {
      html += '<div class="seven-panel-proposals" style="display:flex;flex-direction:column;gap:5px;">';
      proposals.slice(0, 3).forEach((p) => {
        const t = p.target || null;
        const tgtId = t ? t.id : '';
        const tgtKind = t ? t.kind : '';
        const conf = (typeof p.confidence === 'number')
          ? ' · conf ' + ((p.confidence * 100) | 0) + '%' : '';
        const action = (p.action || 'review').toUpperCase();
        html += '<div class="seven-panel-prop" data-rid="' + SAFE(tgtId) + '" '
          + 'style="padding:6px 8px;border:1px solid var(--border, rgba(255,255,255,0.10));'
          + 'border-radius:6px;' + (tgtId ? 'cursor:pointer;' : '') + '">'
          + '<div style="font-weight:500;">[' + SAFE(action) + '] '
          + SAFE(p.label || '') + '</div>'
          + '<div style="opacity:0.65;margin-top:2px;font-size:11px;">'
          + SAFE(p.rationale || '') + conf
          + (tgtKind && tgtId ? ' · ' + SAFE(tgtKind + ':' + tgtId) : '')
          + '</div></div>';
      });
      html += '</div>';
    }

    // Propose-only badge.
    html += '<div class="seven-panel-badge" '
      + 'style="margin-top:10px;font-size:10px;opacity:0.5;letter-spacing:0.04em;'
      + 'text-transform:uppercase;">authority · propose-only</div>';

    bodyEl.innerHTML = html || '<div style="opacity:0.55;">Seven has nothing to add yet.</div>';
    if (statusEl) statusEl.textContent = '';

    // Wire proposal clicks → pivot to that record via Spotlight.
    bodyEl.querySelectorAll('.seven-panel-prop[data-rid]').forEach((el) => {
      const rid = el.getAttribute('data-rid');
      if (!rid) return;
      el.addEventListener('click', () => _pivotToRecord(rid));
    });
  }

  function _fetchAll(kind, id) {
    const focusParam = _focusKey(kind, id);
    const qs = focusParam ? '?focus=' + encodeURIComponent(focusParam) : '';
    const decideQs = focusParam
      ? '?intent=next&focus=' + encodeURIComponent(focusParam)
      : '?intent=next';
    return Promise.all([
      fetch('/api/seven/explain' + qs).then((r) => r.json()).catch(() => ({})),
      fetch('/api/seven/observe' + qs).then((r) => r.json()).catch(() => ({})),
      fetch('/api/seven/decide' + decideQs).then((r) => r.json()).catch(() => ({})),
    ]).then((arr) => ({ explain: arr[0], observe: arr[1], decide: arr[2] }));
  }

  function mount(target, opts) {
    if (!target) return;
    opts = opts || {};
    const kind = opts.kind || '';
    const id = opts.id || '';
    if (!id) return; // Need at least an id.

    // Replace previous panel if present.
    const prev = target.querySelector(':scope > .seven-panel[data-seven-panel="1"]');
    if (prev) prev.remove();

    const focusLabel = kind ? (kind + ':' + id) : id;
    target.insertAdjacentHTML('beforeend', _shellHtml(focusLabel));
    const panelEl = target.querySelector(':scope > .seven-panel[data-seven-panel="1"]');
    if (!panelEl) return;
    const statusEl = panelEl.querySelector('.seven-panel-status');
    const bodyEl = panelEl.querySelector('.seven-panel-body');

    _fetchAll(kind, id).then((payload) => {
      try { _renderBody(bodyEl, statusEl, payload); }
      catch (e) {
        if (statusEl) statusEl.textContent = 'unavailable';
        bodyEl.innerHTML = '';
      }
    }).catch(() => {
      if (statusEl) statusEl.textContent = 'unavailable';
    });
  }

  window.SevenPanel = { mount: mount };
})();
