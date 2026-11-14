/* HB clipboard holder and switches in main chat (owner 14 Nov). Always visible right above the chat messages.
 * Header: HB, driving or paused, how many open and done today, now / next, and the background work (homework, counsel, checks).
 * Click it for the full clipboard: each task with its state, doer, importance, Ready (homework card) and check result - updated every 5 s.
 * Switches under the chat box: Auto glows while HB drives; Approve only shows while Auto is on and glows when HB approves by itself.
 * Data and switches: /api/peer/v1/hb/queue (core/hb_queue.status). Colours follow the theme (var(--accent)). */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  const ICON = { now: 'play', next: 'more', waiting: 'dot', needs_you: 'flag', blocked: 'blocked' };
  const ico = n => (window.HBIcons && window.HBIcons.svg) ? window.HBIcons.svg(n) : `<span data-hb-icon="${n}"></span>`;
  const DOER = { hb: 'HB', small: 'small model', apex: 'APEX', fred: 'Fred' };
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const S = { open: false, sig: '' };
  const CSS = '.hb-clip{font-size:12px;margin:0 0 6px;padding:6px 10px;border:1px solid var(--border,#2c3a50);border-radius:10px;background:var(--card,#161f2e)}' +
    '.hb-clip-head{display:flex;gap:8px;align-items:center;cursor:pointer;flex-wrap:wrap}.hb-clip-head b{color:var(--accent,#6aa9ff)}' +
    '.hb-clip-line{color:var(--text-dim,#9aa7b8);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:120px}' +
    '.hb-clip-bg{margin-top:3px;color:var(--accent,#6aa9ff);font-size:11px}' +
    '.hb-clip-list{margin:6px 0 0;padding:0;list-style:none;max-height:240px;overflow-y:auto}' +
    '.hb-clip-list li{display:grid;grid-template-columns:14px 1fr auto auto auto;gap:8px;padding:2px 0;align-items:center}' +
    '.hb-clip-list li[data-state=now]{color:var(--accent,#6aa9ff);font-weight:600}.hb-clip-list li[data-state=needs_you]{color:#e0a030}' +
    '.hb-clip-list li[data-state=blocked]{opacity:.5}.hb-chip{font-size:10px;padding:0 6px;border-radius:8px;border:1px solid var(--border,#2c3a50);white-space:nowrap}' +
    '.hb-chip.ready{border-color:var(--accent,#6aa9ff);color:var(--accent,#6aa9ff)}' +
    '.hb-switch{font:inherit;font-size:10px;padding:0 9px;border-radius:10px;border:1px solid var(--border,#2c3a50);background:transparent;color:var(--text-dim,#9aa7b8);cursor:pointer;margin-left:6px}' +
    '.hb-switch.on{color:#fff;border-color:var(--accent,#6aa9ff);background:color-mix(in srgb,var(--accent,#6aa9ff) 35%,transparent);box-shadow:0 0 6px var(--accent,#6aa9ff)}';

  function style() {
    if (document.getElementById('hb-clip-css')) return;
    const st = document.createElement('style'); st.id = 'hb-clip-css'; st.textContent = CSS; document.head.appendChild(st);
  }

  function holder() {
    let el = document.getElementById('hb-clipboard');
    if (el) return el;
    const messages = document.getElementById('home-chat-messages');
    if (!messages || !messages.parentNode) return null;
    el = document.createElement('section'); el.id = 'hb-clipboard'; el.className = 'hb-clip'; el.setAttribute('aria-label', "HB's clipboard: the open tasks");
    messages.parentNode.insertBefore(el, messages);
    el.onclick = e => { if (e.target.closest('.hb-clip-head')) { S.open = !S.open; S.sig = ''; refresh(); } };
    return el;
  }

  function switches() {
    let box = document.getElementById('hb-switches');
    if (box) return box;
    const meta = document.getElementById('home-chat-meta');
    if (!meta) return null;
    box = document.createElement('span'); box.id = 'hb-switches';
    const after = document.getElementById('home-chat-agent-count');
    (after || meta).insertAdjacentElement(after ? 'afterend' : 'afterbegin', box);
    box.onclick = e => { const b = e.target.closest('[data-switch]'); if (b) flip(b.dataset.switch, b.getAttribute('aria-pressed') !== 'true'); };
    return box;
  }

  async function flip(which, on) {
    try {
      const r = await fetch('/api/peer/v1/hb/queue', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ switch: which, on }) });
      const d = await r.json();
      if (d && d.ok) { S.sig = ''; show(d); }
    } catch (_) { /* HB restarting */ }
  }

  function rowHtml(i) {
    const check = i.check_result && i.check_result !== 'not run yet' ? `<span class="hb-chip">check ${esc(i.check_result)}</span>` : '<span></span>';
    return `<li data-state="${esc(i.state)}" title="${esc(i.step_id + (i.why ? ' - ' + i.why : ''))}"><span>${ico(ICON[i.state] || 'dot')}</span>` +
      `<span>${esc(i.title)}</span><span class="hb-chip">${esc(DOER[i.doer] || i.doer || 'APEX')}${i.importance ? ' · importance ' + Math.min(5, i.importance) : ''}</span>` +
      `<span class="hb-chip${i.ready ? ' ready' : ''}">${i.ready ? 'ready' : 'no card'}</span>${check}</li>`;
  }

  function show(d) {
    const sig = JSON.stringify([d.on, d.auto, d.open, d.done_24h, S.open, d.background, d.items.map(i => [i.step_id, i.state, i.ready, i.check_result])]);
    if (sig === S.sig) return;
    S.sig = sig;
    style();
    const el = holder();
    if (el) {
      const now = d.items.find(i => i.state === 'now' || i.state === 'needs_you');
      const next = d.items.find(i => i.state === 'next');
      const line = (now ? 'now: ' + now.title : '') + (next ? (now ? ' · ' : '') + 'next: ' + next.title : '');
      el.innerHTML = `<div class="hb-clip-head" title="${esc(d.summary)}"><b>HB</b><span>${d.on ? 'driving' : 'paused'} · ${d.open} open · ${d.done_24h} done today</span>` +
        `<span class="hb-clip-line">${esc(line)}</span><span aria-hidden="true">${ico(S.open ? 'less' : 'more')}</span></div>` +
        (d.background || []).map(b => `<div class="hb-clip-bg">${ico('sprout')} ${esc(b.role)} (${esc(b.model)}): ${esc(b.now)}</div>`).join('') +
        (S.open ? `<ul class="hb-clip-list">${d.items.map(rowHtml).join('')}</ul>` : '');
    }
    const box = switches();
    if (box) {
      box.innerHTML = `<button type="button" class="hb-switch${d.on ? ' on' : ''}" data-switch="auto" aria-pressed="${d.on}" ` +
        `title="${d.on ? 'Auto is on: HB works through the open tasks. Click to stop.' : 'Auto is off: nothing new starts. Click to let HB drive.'}">Auto</button>` +
        (d.on ? `<button type="button" class="hb-switch${d.auto ? ' on' : ''}" data-switch="approve" aria-pressed="${d.auto}" ` +
          `title="${d.auto ? 'Auto-approve is on: HB approves plans and finished steps whose checks pass.' : 'Auto-approve is off: they wait for you.'}">Approve</button>` : '');
    }
  }

  async function refresh() {
    if (document.hidden) return;
    try {
      const r = await fetch('/api/peer/v1/hb/queue', { credentials: 'same-origin', signal: AbortSignal.timeout(5000) });
      if (!r.ok) return;
      const d = await r.json();
      if (d && d.ok) show(d);
    } catch (_) { /* HB restarting: keep the last view */ }
  }
  window.hbQueueRefresh = refresh;
  setInterval(refresh, 5000);
  document.addEventListener('visibilitychange', refresh);
  setTimeout(refresh, 600);
})();
