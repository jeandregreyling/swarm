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
      if (slug === 'business') _moneyHubMountPayrollWorkbench(pane);
      if (slug === 'trading') _moneyHubMountPaperTradingLab(pane);
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

function _moneyHubMountPayrollWorkbench(pane) {
  if (!pane || pane.querySelector('#mh-payroll-workbench')) return;
  const box = document.createElement('section');
  box.id = 'mh-payroll-workbench';
  box.style.cssText = 'margin:10px 0 14px;padding:12px 14px;border-radius:12px;border:1px solid rgba(16,232,164,0.32);background:linear-gradient(135deg,rgba(12,24,34,0.82),rgba(16,28,38,0.72));backdrop-filter:blur(12px);font-size:12px;';
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <strong style="color:#6ef7c8;">💼 Payroll Consultant Workbench (AU Stage-3 PAYG · 12% SG Super · STP Phase 2)</strong>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:8px;">
      <label style="display:flex;flex-direction:column;gap:2px;">Employee<input id="mh-pay-emp" value="Staff Member" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);"></label>
      <label style="display:flex;flex-direction:column;gap:2px;">Annual Salary (AUD)<input id="mh-pay-sal" type="number" value="104000" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);"></label>
      <label style="display:flex;flex-direction:column;gap:2px;">Frequency<select id="mh-pay-freq" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);"><option value="fortnightly">Fortnightly</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
      <label style="display:flex;flex-direction:column;gap:2px;">OT 1.5x hrs<input id="mh-pay-ot15" type="number" step="0.5" value="0" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);"></label>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
      <button type="button" onclick="window.moneyHubCalcPayroll(false)" style="padding:5px 12px;border-radius:7px;border:1px solid #10e8a4;background:rgba(16,232,164,0.18);color:#d1fae5;cursor:pointer;font-weight:600;">Calculate Payslip</button>
      <button type="button" onclick="window.moneyHubCalcPayroll(true)" style="padding:5px 12px;border-radius:7px;border:1px solid #38bdf8;background:rgba(56,189,248,0.18);color:#e0f2fe;cursor:pointer;font-weight:600;">Post to Business Ledger</button>
    </div>
    <div id="mh-payroll-result" style="font-family:ui-monospace,monospace;font-size:11px;color:#cbd5e1;">Enter salary or hours and click Calculate Payslip.</div>
  `;
  pane.prepend(box);
}

async function moneyHubCalcPayroll(commit) {
  const out = document.getElementById('mh-payroll-result');
  const payload = {
    employee: document.getElementById('mh-pay-emp')?.value || 'Staff Member',
    annual_salary: Number(document.getElementById('mh-pay-sal')?.value || 0),
    frequency: document.getElementById('mh-pay-freq')?.value || 'fortnightly',
    overtime_15_hours: Number(document.getElementById('mh-pay-ot15')?.value || 0),
  };
  try {
    const url = commit ? '/api/business/payroll/commit' : '/api/business/payroll/calculate';
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'payroll calc failed');
    const s = d.payslip;
    if (out) {
      out.innerHTML = `Gross: <b>$${s.gross_pay.toFixed(2)}</b> · PAYG+Medicare: <b>$${s.total_tax_withheld.toFixed(2)}</b> · Net: <b style="color:#6ef7c8;">$${s.net_pay.toFixed(2)}</b> · SG Super (${(s.super_rate * 100).toFixed(1)}%): <b>$${s.superannuation_sg.toFixed(2)}</b> · Annual Leave: +${s.leave_accruals.annual_leave_hours}h` + (commit ? ` · <span style="color:#38bdf8;">Posted (${(d.ledger_entry_ids || []).join(', ')})</span>` : '');
    }
  } catch (err) {
    if (out) out.textContent = 'Payroll error: ' + (err.message || err);
  }
}

function _moneyHubMountPaperTradingLab(pane) {
  if (!pane || pane.querySelector('#mh-paper-lab')) return;
  const box = document.createElement('section');
  box.id = 'mh-paper-lab';
  box.style.cssText = 'margin:10px 0 14px;padding:12px 14px;border-radius:12px;border:1px solid rgba(56,189,248,0.34);background:linear-gradient(135deg,rgba(12,20,36,0.84),rgba(18,24,42,0.76));backdrop-filter:blur(12px);font-size:12px;';
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:8px;">
      <strong style="color:#7dd3fc;">📊 $500 Paper-Trading Risk Lab & 32 GB GPU Milestone Tracker</strong>
      <span style="font-size:10px;padding:2px 8px;border-radius:999px;background:rgba(255,184,77,0.18);border:1px solid rgba(255,184,77,0.45);color:#fde68a;font-weight:700;">PAPER-ONLY · MAX 2% RISK · $0 LIVE CAPITAL</span>
    </div>
    <div id="mh-paper-scorecard" style="font-family:ui-monospace,monospace;font-size:11px;color:#e2e8f0;margin-bottom:8px;">Loading paper scorecard…</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:6px;margin-bottom:8px;">
      <input id="mh-ppr-sym" placeholder="Symbol (VOO)" value="VOO" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);">
      <input id="mh-ppr-entry" type="number" step="0.01" placeholder="Entry" value="500" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);">
      <input id="mh-ppr-stop" type="number" step="0.01" placeholder="Stop Loss" value="490" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);">
      <input id="mh-ppr-tp" type="number" step="0.01" placeholder="Take Profit" value="525" style="padding:5px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);">
      <button type="button" onclick="window.moneyHubOpenPaperTrade()" style="padding:5px 10px;border-radius:7px;border:1px solid #38bdf8;background:rgba(56,189,248,0.2);color:#e0f2fe;cursor:pointer;font-weight:600;">Open Paper Trade</button>
    </div>
  `;
  pane.prepend(box);
  moneyHubRefreshPaperScorecard();
}

async function moneyHubRefreshPaperScorecard() {
  const host = document.getElementById('mh-paper-scorecard');
  if (!host) return;
  try {
    const r = await fetch('/api/trading/paper/scorecard');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'failed');
    const c = d.scorecard;
    host.innerHTML = `Equity: <b>$${c.current_equity_usd.toFixed(2)}</b> (PnL ${c.total_pnl_usd >= 0 ? '+' : ''}$${c.total_pnl_usd.toFixed(2)} / ${c.return_pct}%) · Closed: <b>${c.closed_trades}</b> · Open: <b>${c.open_trades || 0}</b> · Win Rate: <b>${c.win_rate_pct}%</b> · PF: <b>${c.profit_factor}</b> · Max DD: <b>${c.max_drawdown_pct}%</b> · 32GB GPU Goal: <b>${c.gpu_goal_progress_pct}%</b><br><span style="color:#94a3b8;">Gate: ${c.live_readiness_verdict}</span>`;
  } catch (err) {
    host.textContent = 'Paper scorecard unavailable: ' + (err.message || err);
  }
}

async function moneyHubOpenPaperTrade() {
  try {
    const body = {
      symbol: document.getElementById('mh-ppr-sym')?.value || 'VOO',
      side: 'buy',
      entry_price: Number(document.getElementById('mh-ppr-entry')?.value || 0),
      stop_loss_price: Number(document.getElementById('mh-ppr-stop')?.value || 0),
      take_profit_price: Number(document.getElementById('mh-ppr-tp')?.value || 0) || null,
    };
    const r = await fetch('/api/trading/paper/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'failed');
    if (typeof window.showToast === 'function') window.showToast(`Opened paper trade ${d.trade_id} (max risk $${d.sizing.max_loss_usd})`, 'success');
    moneyHubRefreshPaperScorecard();
  } catch (err) {
    if (typeof window.showToast === 'function') window.showToast('Paper trade rejected: ' + (err.message || err), 'error');
  }
}

window.loadMoneyHubData = loadMoneyHubData;
window.moneyHubSetTab = moneyHubSetTab;
window.moneyHubRefreshMarkets = moneyHubRefreshMarkets;
window.moneyHubEnsureTaskerJob = moneyHubEnsureTaskerJob;
window.moneyHubScanPatterns = moneyHubScanPatterns;
window.moneyHubResearchPropositions = moneyHubResearchPropositions;
window.moneyHubCalcPayroll = moneyHubCalcPayroll;
window.moneyHubRefreshPaperScorecard = moneyHubRefreshPaperScorecard;
window.moneyHubOpenPaperTrade = moneyHubOpenPaperTrade;
