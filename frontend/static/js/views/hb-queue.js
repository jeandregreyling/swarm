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
    '.hb-clip-list li{display:grid;grid-template-columns:14px 1fr auto auto auto auto;gap:8px;padding:2px 0;align-items:center}' +
    '.hb-clip-edit{display:inline-flex;gap:2px;align-items:center}.hb-clip-edit button,.hb-clip-edit select{font:inherit;font-size:10px;line-height:1.2;padding:0 5px;' +
    'border-radius:6px;border:1px solid var(--border,#2c3a50);background:transparent;color:var(--text-dim,#9aa7b8);cursor:pointer}' +
    '.hb-clip-edit button:hover,.hb-clip-edit select:hover{color:var(--accent,#6aa9ff);border-color:var(--accent,#6aa9ff)}' +
    '.hb-clip-list li[data-state=now]{color:var(--accent,#6aa9ff);font-weight:600}.hb-clip-list li[data-state=needs_you]{color:#e0a030}' +
    '.hb-clip-list li[data-state=blocked]{opacity:.5}.hb-chip{font-size:10px;padding:0 6px;border-radius:8px;border:1px solid var(--border,#2c3a50);white-space:nowrap}' +
    '.hb-chip.ready{border-color:var(--accent,#6aa9ff);color:var(--accent,#6aa9ff)}' +
    '.hb-switch{font:inherit;font-size:10px;padding:0 9px;border-radius:10px;border:1px solid var(--border,#2c3a50);background:transparent;color:var(--text-dim,#9aa7b8);cursor:pointer;margin-left:6px}' +
    '.hb-switch.on{color:#fff;border-color:var(--accent,#6aa9ff);background:color-mix(in srgb,var(--accent,#6aa9ff) 35%,transparent);box-shadow:0 0 6px var(--accent,#6aa9ff)}';

  function style() {
    if (document.getElementById('hb-clip-css')) return;
    const st = document.createElement('style'); st.id = 'hb-clip-css'; st.textContent = CSS; document.head.appendChild(st);
  }

  // Owner 15 Nov ("I don't see a task board at all"): HB has two chat windows - the Home chat panel and the Chat window
  // ("Message APEX..."). The board was only ever put in the first. It now sits above the messages of both.
  const PLACES = [['hb-clipboard', 'home-chat-messages'], ['hb-clipboard-chat', 'chat-messages']];
  function holders() { return PLACES.map(p => holder(p[0], p[1])).filter(Boolean); }

  function holder(id = 'hb-clipboard', anchor = 'home-chat-messages') {
    let el = document.getElementById(id);
    if (el) return el;
    const messages = document.getElementById(anchor);
    if (!messages || !messages.parentNode) return null;
    el = document.createElement('section'); el.id = id; el.className = 'hb-clip'; el.setAttribute('aria-label', "HB's clipboard: the open tasks");
    messages.parentNode.insertBefore(el, messages);
    el.onclick = e => {
      const sw = e.target.closest('[data-switch]');        // the switches inside the Chat window's board header
      if (sw) { e.stopPropagation(); flip(sw.dataset.switch, sw.getAttribute('aria-pressed') !== 'true'); return; }
      const t = e.target.closest('[data-task]');           // owner 15 Nov: pause / continue / approve / cancel a task by clicking
      if (t) {
        e.stopPropagation();
        if (t.dataset.task === 'cancel' && !window.confirm('Cancel this task? Its queued work is dropped and it will not run again.')) return;
        task([t.dataset.task, t.dataset.id]);
        return;
      }
      const b = e.target.closest('[data-clip]');           // owner 15 Nov: move a task by clicking (same as /clip up|down|top)
      if (b) { e.stopPropagation(); clip([b.dataset.clip, b.dataset.step]); return; }
      if (e.target.closest('.hb-clip-head')) { S.open = !S.open; S.sig = ''; refresh(); }
    };
    el.onchange = e => { const s = e.target.closest('select[data-importance]'); if (s && s.value) clip(['importance', s.dataset.importance, s.value]); };
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

  async function clip(args) {
    try {
      const r = await fetch('/api/peer/v1/hb/queue', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clip: args }) });
      const d = await r.json();
      if (d && d.ok) { S.sig = ''; show(d); }
    } catch (_) { /* HB restarting */ }
  }

  async function task(args) {
    try {
      const r = await fetch('/api/peer/v1/hb/queue', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task: args }) });
      const d = await r.json();
      if (d && d.ok) { S.sig = ''; show(d); }
    } catch (_) { /* HB restarting */ }
  }

  function taskHtml(i) {
    if (!i.task_id) return '';
    const id = esc(i.task_id), why = String(i.why || '');
    const held = /held by you|Continue off|paused/i.test(why);
    return (i.state === 'needs_you' && /approval/i.test(why) ? `<button type="button" data-task="accept" data-id="${esc(i.step_id)}" title="Approve this finished step">approve</button>` : '') +
      (held ? `<button type="button" data-task="continue" data-id="${id}" title="Give it a fresh try">continue</button>`
            : `<button type="button" data-task="pause" data-id="${id}" title="Stop it; it keeps its place">pause</button>`) +
      `<button type="button" data-task="cancel" data-id="${id}" title="Drop this task">cancel</button>`;
  }

  function editHtml(i) {
    if (i.state === 'blocked') return '<span></span>';
    if (i.state === 'now') return `<span class="hb-clip-edit">${taskHtml(i)}</span>`;
    const step = esc(i.step_id), now = Math.min(5, i.importance || 3);
    return `<span class="hb-clip-edit">${taskHtml(i)}<button type="button" data-clip="top" data-step="${step}" title="Move to the top: HB does it next">⤒</button>` +
      `<button type="button" data-clip="up" data-step="${step}" title="Move up">▲</button>` +
      `<button type="button" data-clip="down" data-step="${step}" title="Move down">▼</button>` +
      `<select data-importance="${step}" title="Importance (5 is highest)">${[5, 4, 3, 2, 1].map(n => `<option value="${n}"${n === now ? ' selected' : ''}>${n}</option>`).join('')}</select></span>`;
  }

  function rowHtml(i) {
    const check = i.check_result && i.check_result !== 'not run yet' ? `<span class="hb-chip">check ${esc(i.check_result)}</span>` : '<span></span>';
    return `<li data-state="${esc(i.state)}" title="${esc(i.step_id + (i.why ? ' - ' + i.why : ''))}"><span>${ico(ICON[i.state] || 'dot')}</span>` +
      `<span>${esc(i.title)}</span><span class="hb-chip">${esc(DOER[i.doer] || i.doer || 'APEX')}${i.importance ? ' · importance ' + Math.min(5, i.importance) : ''}</span>` +
      `<span class="hb-chip${i.ready ? ' ready' : ''}">${i.ready ? 'ready' : 'no card'}</span>${check}${editHtml(i)}</li>`;
  }

  function show(d) {
    const sig = JSON.stringify([d.on, d.auto, d.open, d.done_24h, S.open, d.background, d.items.map(i => [i.step_id, i.state, i.ready, i.check_result, i.importance, i.doer])]);
    if (sig === S.sig) return;
    S.sig = sig;
    style();
    const all = holders(), el = all[0];
    if (el) {
      const now = d.items.find(i => i.state === 'now' || i.state === 'needs_you');
      const next = d.items.find(i => i.state === 'next');
      const line = (now ? 'now: ' + now.title : '') + (next ? (now ? ' · ' : '') + 'next: ' + next.title : '');
      el.innerHTML = `<div class="hb-clip-head" title="${esc(d.summary)}"><b>HB</b><span>${d.on ? 'driving' : 'paused'} · ${d.open} open · ${d.done_24h} done today</span>` +
        `<span class="hb-clip-line">${esc(line)}</span><span aria-hidden="true">${ico(S.open ? 'less' : 'more')}</span></div>` +
        (d.background || []).map(b => `<div class="hb-clip-bg">${ico('sprout')} ${esc(b.role)} (${esc(b.model)}): ${esc(b.now)}</div>`).join('') +
        (S.open ? `<ul class="hb-clip-list">${d.items.map(rowHtml).join('')}</ul>` : '');
    }
    const swHtml = `<button type="button" class="hb-switch${d.on ? ' on' : ''}" data-switch="auto" aria-pressed="${d.on}" ` +
        `title="${d.on ? 'Auto is on: HB works through the open tasks. Click to stop.' : 'Auto is off: nothing new starts. Click to let HB drive.'}">Auto</button>` +
        (d.on ? `<button type="button" class="hb-switch${d.auto ? ' on' : ''}" data-switch="approve" aria-pressed="${d.auto}" ` +
          `title="${d.auto ? 'Auto-approve is on: HB approves plans and finished steps whose checks pass.' : 'Auto-approve is off: they wait for you.'}">Approve</button>` : '');
    const box = switches();
    if (box) box.innerHTML = swHtml;
    // owner 15 Nov: the Chat window has no switch row of its own - its board carries the switches in its header
    all.slice(1).forEach(other => { other.innerHTML = el ? el.innerHTML.replace('</div>', swHtml + '</div>') : ''; });
  }

  function notOwner() {
    if (S.sig === 'not-owner') return;
    S.sig = 'not-owner';
    style();
    holders().forEach(el => { el.innerHTML = '<div class="hb-clip-head"><b>HB</b><span>Task board is off in this window: it is not signed in as the owner. ' +
      '<a href="/login" style="color:var(--accent,#6aa9ff)">Sign in</a> here to see and change the tasks.</span></div>'; });
  }

  async function refresh() {
    if (document.hidden) return;
    try {
      const r = await fetch('/api/peer/v1/hb/queue', { credentials: 'same-origin', signal: AbortSignal.timeout(5000) });
      if (r.status === 401 || r.status === 403) { notOwner(); return; }   // owner 15 Nov: say it instead of showing nothing
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
