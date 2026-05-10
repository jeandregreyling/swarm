/**
 * Y.58 — Show Me The Money hub.
 * Combines the three financial pillars (Financial / Trading / Business)
 * into a single hub with extra Markets and IBank Research tabs.
 *
 * The Financial / Trading / Business panes lazy-clone the existing
 * wishlist pillar templates so we reuse the live loader code path.
 */
'use strict';

let _moneyHubWin = null;
let _moneyHubLoaded = { financial: false, trading: false, business: false, markets: false, ibank: false };

function loadMoneyHubData(win) {
  _moneyHubWin = win;
  _moneyHubLoaded = { financial: false, trading: false, business: false, markets: false, ibank: false };
  const root = win.el || document;
  const tabBar = root.querySelector('.money-hub-tabbar');
  if (tabBar) {
    tabBar.addEventListener('click', (ev) => {
      const btn = ev.target.closest('.money-hub-tab');
      if (!btn) return;
      moneyHubSetTab(btn.dataset.moneyTab, root);
    });
  }
  moneyHubSetTab('financial', root);
}

function moneyHubSetTab(tab, scope) {
  const root = scope || (_moneyHubWin && _moneyHubWin.el) || document;
  root.querySelectorAll('.money-hub-tab').forEach((b) => {
    const on = b.dataset.moneyTab === tab;
    b.classList.toggle('active', on);
    b.style.borderBottomColor = on ? 'var(--accent)' : 'transparent';
    b.style.color = on ? 'var(--text)' : 'var(--text-dim)';
    b.style.fontWeight = on ? '600' : '500';
  });
  root.querySelectorAll('.money-hub-pane').forEach((p) => {
    p.style.display = p.dataset.moneyPane === tab ? 'block' : 'none';
  });
  if (_moneyHubLoaded[tab]) return;
  _moneyHubLoaded[tab] = true;
  _moneyHubLoadPane(tab, root);
}

function _moneyHubLoadPane(tab, root) {
  if (tab === 'financial' || tab === 'trading' || tab === 'business') {
    const pane = root.querySelector(`.money-hub-pane[data-money-pane="${tab}"]`);
    if (!pane) return;
    const slug = tab === 'financial' ? 'financial' : tab === 'trading' ? 'trading' : 'business';
    const tplId = `view-wishlist-${slug === 'financial' ? 'financial' : slug === 'trading' ? 'trading' : 'business'}`;
    const tpl = document.getElementById(tplId);
    if (tpl) {
      pane.innerHTML = '';
      pane.appendChild(tpl.content.cloneNode(true));
      try {
        if (typeof window.loadWishlistPillar === 'function') {
          window.loadWishlistPillar({ el: pane }, slug);
        } else if (typeof window.pillarLiveInit === 'function') {
          window.pillarLiveInit(pane, slug);
        }
      } catch (_) { /* no-op */ }
    } else {
      pane.innerHTML = `<div style="padding:14px;color:var(--text-dim);">${tab} pillar template not loaded.</div>`;
    }
  } else if (tab === 'markets') {
    moneyHubRefreshMarkets();
  } else if (tab === 'ibank') {
    moneyHubLoadResearch();
  }
}

function moneyHubRefreshMarkets() {
  const root = (_moneyHubWin && _moneyHubWin.el) || document;
  const host = root.querySelector('[data-tickers-host]');
  if (!host) return;
  host.innerHTML = '<div style="color:var(--text-dim);">Loading…</div>';
  fetch('/api/wishlist/pillars/financial').then((r) => r.json()).then((d) => {
    const tickers = (d && d.live && d.live.tickers) || [];
    if (!Array.isArray(tickers) || !tickers.length) {
      host.innerHTML = '<div style="color:var(--text-dim);font-size:11px;">No tickers yet — enable the Tasker job below to start scraping NASDAQ + ASX summaries.</div>';
      return;
    }
    host.innerHTML = tickers.slice(0, 24).map((t) => {
      const sym = String(t.symbol || t.ticker || '').toUpperCase();
      const px = (t.price !== undefined) ? Number(t.price).toFixed(2) : '—';
      const ch = (t.change_pct !== undefined) ? Number(t.change_pct).toFixed(2) + '%' : '';
      const dirCol = (t.change_pct >= 0) ? 'var(--ok, #5cb85c)' : 'var(--err, #d9534f)';
      return `<div style="padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);">
        <div style="font-weight:700;">${sym}</div>
        <div style="font-size:11px;color:var(--text-dim);">${px}</div>
        <div style="font-size:10px;color:${dirCol};">${ch}</div>
      </div>`;
    }).join('');
  }).catch(() => {
    host.innerHTML = '<div style="color:var(--text-dim);font-size:11px;">Could not load market snapshot.</div>';
  });
}

function moneyHubEnsureTaskerJob() {
  fetch('/api/tasker/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'money_hub_daily_newsletter',
      schedule: 'daily 07:20',
      action_type: 'PYTHON',
      action_data: 'money_hub_daily_newsletter',
      created_by: 'money-hub',
    }),
  }).then((r) => r.json()).then((d) => {
    alert((d && d.ok) ? 'Tasker job queued.' : 'Tasker accepted but no ok flag — check Tasker tab.');
  }).catch((e) => alert('Tasker call failed: ' + e.message));
}

function moneyHubScanPatterns() {
  fetch('/api/trading/scan-patterns', { method: 'POST' })
    .then((r) => r.json())
    .then((d) => alert((d && d.ok) ? `Pattern scan queued (${d.queued || 0} symbols).` : 'Scan request sent.'))
    .catch(() => alert('Pattern scan endpoint not available yet.'));
}

function moneyHubResearchPropositions() {
  fetch('/api/business/research-propositions', { method: 'POST' })
    .then((r) => r.json())
    .then((d) => alert((d && d.ok) ? 'IBank research queued.' : 'Research request sent.'))
    .catch(() => alert('IBank research endpoint not available yet.'));
}

function moneyHubLoadResearch() {
  const root = (_moneyHubWin && _moneyHubWin.el) || document;
  const host = root.querySelector('[data-ibank-host]');
  if (!host) return;
  host.innerHTML = '<div style="color:var(--text-dim);">Loading…</div>';
  fetch('/api/wishlist/pillars/business').then((r) => r.json()).then((d) => {
    const items = (d && d.live && d.live.research) || (d && d.live && d.live.summary && d.live.summary.research) || [];
    if (!items.length) {
      host.innerHTML = '<div style="color:var(--text-dim);font-size:11px;">No research entries yet. Click "Research propositions/acquisitions" to seed the feed.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 20).map((it) => `
      <div style="padding:8px 10px;border:1px solid var(--border);border-radius:6px;margin-bottom:6px;background:var(--card);">
        <div style="font-weight:700;font-size:12px;">${(it.title || '').replace(/</g, '&lt;')}</div>
        <div style="font-size:10px;color:var(--text-dim);">${(it.summary || '').replace(/</g, '&lt;')}</div>
      </div>`).join('');
  }).catch(() => {
    host.innerHTML = '<div style="color:var(--text-dim);font-size:11px;">Could not load research feed.</div>';
  });
}

window.loadMoneyHubData = loadMoneyHubData;
window.moneyHubSetTab = moneyHubSetTab;
window.moneyHubRefreshMarkets = moneyHubRefreshMarkets;
window.moneyHubEnsureTaskerJob = moneyHubEnsureTaskerJob;
window.moneyHubScanPatterns = moneyHubScanPatterns;
window.moneyHubResearchPropositions = moneyHubResearchPropositions;
