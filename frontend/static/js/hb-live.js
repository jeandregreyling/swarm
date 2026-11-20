/* HB Live L3 (owner 20 Nov 2026: "main chat is the main dashboard ... different windows can open as bubbles on top of the main chat and
   HB keeps track of it all and I can see it happening in real time"; spec docs/spec-hb-live-dashboard.md).

   One strip at the top of main chat: a chip per lane (GPU APEX, CPU Fred, CPU small, Online, HB, Admin, Claude Code), Needs you, the
   task list and the system. Click a chip: a window opens over the chat with that lane's live work and step trail, the task list
   (the clipboard, with Needs you pinned on top) or the system gauges. Windows drag by their title, minimise to a bubble on the right
   edge that keeps pulsing while its lane works, and are remembered per viewer. Everything renders from ONE snapshot:
   GET /api/peer/v1/hb/live, every 2 s while the page is visible and at once on a chat event. */
(function (root) {
  'use strict';

  // ── Pure renderers (no DOM; tested in Node) ──────────────────────────────
  const ICON = { gpu: '⬢', fred: '◆', small: '◇', online: '☁', hb: '✦', admin: '#', 'claude-code': '❯', system: '♨', master: '☰', needs: '⚑' };
  const SHORT = { gpu: 'APEX', fred: 'Fred', small: 'Small', online: 'Online', hb: 'HB', admin: 'Admin', 'claude-code': 'Claude Code', system: 'System' };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function took(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    return s >= 3600 ? Math.floor(s / 3600) + ' h ' + Math.floor((s % 3600) / 60) + ' min'
      : s >= 60 ? Math.floor(s / 60) + ' min ' + (s % 60) + ' s' : s + ' s';
  }
  function clock(epoch) {
    if (!epoch) return '';
    if (typeof epoch === 'string') return epoch;
    const d = new Date(epoch * 1000);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }
  function laneLine(lane) {
    if (!lane.items || !lane.items.length) return lane.note || 'idle';
    const it = lane.items[0];
    const more = lane.items.length > 1 ? ' (+' + (lane.items.length - 1) + ')' : '';
    return (it.last_step || it.title || 'working') + more;
  }

  function renderStrip(snap) {
    const lanes = (snap.lanes || []).filter((l) => l.id !== 'system');
    const needs = (snap.needs_you || []).filter((n) => n.kind !== 'status');
    const master = (snap.master || {}).items || [];
    const now = master.find((i) => i.state === 'now' || i.state === 'needs_you');
    const parked = master.filter((i) => i.parked).length;
    const tele = snap.telemetry || {}, gpu = tele.gpu || {}, cpu = tele.cpu || {};
    const chip = (id, state, label, line, extra) =>
      `<button type="button" class="hbl-chip hbl-${state}" data-win="${esc(id)}" title="${esc(label + ': ' + line)}">` +
      `<span class="hbl-dot"></span><span class="hbl-ico">${ICON[id] || '•'}</span><b>${esc(label)}</b>` +
      `<span class="hbl-line">${esc(line)}</span>${extra || ''}</button>`;
    let html = lanes.map((l) => chip(l.id, l.state, SHORT[l.id] || l.label, laneLine(l))).join('');
    html += chip('needs', needs.length ? 'waiting' : 'idle', 'Needs you', needs.length ? needs.length + ' waiting' : 'nothing',
      needs.length ? `<span class="hbl-count">${needs.length}</span>` : '');
    html += chip('master', now ? 'busy' : (master.length ? 'waiting' : 'idle'), 'Tasks',
      (snap.master && snap.master.on === false ? 'Auto off · ' : '') + (now ? 'now: ' + now.title : master.length + ' open' + (parked ? ', ' + parked + ' parked' : '')));
    const sys = [gpu.busy_pct != null ? 'GPU ' + Math.round(gpu.busy_pct) + '%' : '', gpu.temp_c != null ? Math.round(gpu.temp_c) + '°C' : '',
      cpu.load1 != null ? 'load ' + cpu.load1 : ''].filter(Boolean).join(' · ');
    html += chip('system', (snap.unexplained || []).length ? 'error' : 'idle', 'System', (snap.unexplained || []).length ? '⚠ ' + snap.unexplained[0].evidence : (sys || '—'));
    return html;
  }

  function renderTrail(trail) {
    if (!trail || !trail.length) return '';
    return '<ol class="hbl-trail">' + trail.map((t) =>
      `<li class="hbl-k-${esc(t.kind || 'step')}"><span class="hbl-t">${esc(clock(t.at))}</span> ${esc(t.text)}</li>`).join('') + '</ol>';
  }

  function renderLane(snap, laneId, now) {
    const lane = (snap.lanes || []).find((l) => l.id === laneId) || { items: [] };
    const t = now || snap.at || 0;
    let html = '';
    if (lane.note) html += `<div class="hbl-note">${esc(lane.note)}</div>`;
    if (!lane.items.length) html += '<div class="hbl-empty">Nothing running here right now.</div>';
    lane.items.forEach((it) => {
      html += '<div class="hbl-item"><div class="hbl-item-head">' +
        `<b>${esc(it.actor || SHORT[laneId] || '')}</b>` + (it.model ? ` · ${esc(it.model)}` : '') + (it.device ? ` · ${esc(it.device)}` : '') +
        (it.since ? ` · <span class="hbl-elapsed">${took(t - it.since)}</span>` : '') + (it.purpose ? ` · <i>${esc(it.purpose)}</i>` : '') +
        `</div><div class="hbl-item-title">${esc(it.title)}</div>` + renderTrail(it.trail) + '</div>';
    });
    const done = (snap.history || []).filter((h) => h.lane === laneId).slice(0, 8);
    if (done.length) {
      html += '<div class="hbl-sub">Finished</div><ul class="hbl-hist">' + done.map((h) =>
        `<li class="hbl-${h.outcome === 'ok' ? 'ok' : 'err'}"><span class="hbl-t">${esc(clock(h.at))}</span> ${esc(h.title)} ` +
        `<span class="hbl-dim">· ${took(h.took_s)} · ${h.steps} steps${h.last ? ' · ' + esc(h.last) : ''}</span></li>`).join('') + '</ul>';
    }
    return html;
  }

  const STATE_ORDER = ['needs_you', 'now', 'next', 'waiting', 'blocked'];
  const STATE_WORD = { needs_you: 'Needs you', now: 'Now', next: 'Next', waiting: 'Waiting', blocked: 'Blocked' };

  function renderMaster(snap, controls, needsControls) {
    const m = snap.master || {}, items = m.items || [];
    const needs = (snap.needs_you || []).filter((n) => n.kind !== 'status');
    let html = `<div class="hbl-note">HB is ${m.on === false ? '<b>paused</b> (Auto off)' : 'driving'}` +
      `${m.auto ? ' · auto-approve on' : ''} · ${items.length} open` +
      (controls ? ` <span class="hbl-ctl"><button type="button" data-switch="auto" data-on="${m.on === false ? 1 : 0}">${m.on === false ? 'Start (Auto on)' : 'Stop (Auto off)'}</button></span>` : '') +
      '</div><div class="hbl-said hbl-dim"></div>';
    if (needs.length) {
      html += '<div class="hbl-sub">Needs you</div><ul class="hbl-list">' + needs.map((n) =>
        `<li class="hbl-needs" title="${esc(n.why || n.title || '')}"><span class="hbl-tag">${esc(n.kind || 'review')}</span> ${esc(n.label || n.text || '')}` +
        (n.title && n.title !== n.label ? `<div class="hbl-dim">${esc(n.title)}</div>` : '') + (needsControls ? needsControls(n) : '') + '</li>').join('') + '</ul>';
    }
    STATE_ORDER.forEach((state) => {
      const rows = items.filter((i) => (i.state || 'waiting') === state);
      if (!rows.length) return;
      html += `<div class="hbl-sub">${STATE_WORD[state]}</div><ul class="hbl-list">` + rows.map((i) =>
        `<li data-step="${esc(i.step_id)}" data-task="${esc(i.task_id || '')}" title="${esc(i.why || '')}">` +
        `<span class="hbl-row-title">${esc(i.title)}</span>` +
        `<span class="hbl-tag">${esc(i.doer || 'apex')}</span>` + (i.importance ? `<span class="hbl-tag">imp ${esc(i.importance)}</span>` : '') +
        (i.parked ? '<span class="hbl-tag hbl-amber">parked by HB</span>' : '') +
        (i.live ? `<div class="hbl-live-line">● ${esc(SHORT[i.live.lane] || i.live.lane)}: ${esc(i.live.last_step || 'working')}</div>` : '') +
        (controls ? controls(i) : '') + '</li>').join('') + '</ul>';
    });
    if (!items.length && !needs.length) html += '<div class="hbl-empty">The task list is empty.</div>';
    return html;
  }

  function renderSystem(snap) {
    const t = snap.telemetry || {}, g = t.gpu || {}, c = t.cpu || {}, r = t.ram || {};
    const bar = (label, value, max, unit) => {
      if (value == null) return '';
      const pct = max ? Math.min(100, Math.round((value / max) * 100)) : Math.min(100, Math.round(value));
      return `<div class="hbl-gauge"><span>${esc(label)}</span><div class="hbl-bar"><i style="width:${pct}%"></i></div>` +
        `<span class="hbl-dim">${esc(value)}${unit || ''}${max ? ' / ' + esc(max) + (unit || '') : ''}</span></div>`;
    };
    let html = bar('GPU busy', g.busy_pct, null, '%') + bar('VRAM', g.vram_used_gb, g.vram_total_gb, ' GB') +
      bar('GPU temp', g.temp_c, 100, '°C') + bar('CPU load', c.load1, c.cores, '') + bar('CPU temp', c.temp_c, 100, '°C') +
      bar('RAM', r.used_gb, r.total_gb, ' GB');
    (snap.unexplained || []).forEach((u) => { html += `<div class="hbl-warn">⚠ ${esc(u.evidence)}</div>`; });
    (snap.lanes || []).filter((l) => l.note).forEach((l) => { html += `<div class="hbl-note">${esc(SHORT[l.id] || l.id)}: ${esc(l.note)}</div>`; });
    return html || '<div class="hbl-empty">No readings.</div>';
  }

  const R = { renderStrip, renderLane, renderMaster, renderSystem, renderTrail, took, esc, ICON, SHORT };
  root.HBLiveRender = R;
  if (typeof module !== 'undefined' && module.exports) module.exports = R;
  if (typeof document === 'undefined' || typeof window === 'undefined') return;

  // ── Page layer ───────────────────────────────────────────────────────────
  const KEY = 'hbLive.windows';
  const S = { snap: null, version: null, wins: {}, busy: false, controls: null };
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; } }
  function save() {
    const out = {};
    Object.keys(S.wins).forEach((id) => { const w = S.wins[id]; out[id] = { x: w.x, y: w.y, min: w.min, w: w.w, h: w.h }; });
    try { localStorage.setItem(KEY, JSON.stringify(out)); } catch (e) {}
  }

  function style() {
    if (document.getElementById('hb-live-style')) return;
    const st = document.createElement('style');
    st.id = 'hb-live-style';
    st.textContent = `
#hb-live-strip{display:flex;gap:6px;padding:6px 10px;overflow-x:auto;border-bottom:1px solid var(--border,#333);flex:0 0 auto;scrollbar-width:thin}
.hbl-chip{display:flex;align-items:center;gap:5px;min-width:0;max-width:260px;flex:0 0 auto;padding:4px 9px;border-radius:14px;cursor:pointer;
  border:1px solid var(--border,#333);background:var(--card,#1b1b1b);color:var(--text,#ddd);font-size:11.5px;line-height:1.3}
.hbl-chip b{font-weight:600;white-space:nowrap}.hbl-ico{opacity:.8}
.hbl-line{color:var(--text-dim,#999);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px}
.hbl-dot{width:8px;height:8px;border-radius:50%;background:#777;flex:0 0 8px}
.hbl-busy .hbl-dot{background:#2ecc71;box-shadow:0 0 0 0 rgba(46,204,113,.7);animation:hblPulse 1.4s infinite}
.hbl-waiting .hbl-dot{background:#ffb300}.hbl-error .hbl-dot{background:#ff5252}.hbl-error{border-color:#ff5252}
.hbl-busy{border-color:rgba(46,204,113,.6)}.hbl-waiting{border-color:rgba(255,179,0,.6)}
.hbl-count{background:#ffb300;color:#000;border-radius:9px;padding:0 6px;font-weight:700;font-size:10.5px}
@keyframes hblPulse{0%{box-shadow:0 0 0 0 rgba(46,204,113,.7)}70%{box-shadow:0 0 0 7px rgba(46,204,113,0)}100%{box-shadow:0 0 0 0 rgba(46,204,113,0)}}
.hbl-win{position:fixed;z-index:9000;width:420px;max-width:calc(100vw - 32px);max-height:70vh;display:flex;flex-direction:column;
  background:var(--card,#1b1b1b);color:var(--text,#ddd);border:1px solid var(--border,#333);border-radius:10px;box-shadow:0 10px 32px rgba(0,0,0,.45);
  resize:both;overflow:hidden;font-size:12.5px}
.hbl-win-head{display:flex;align-items:center;gap:6px;padding:7px 10px;cursor:move;border-bottom:1px solid var(--border,#333);user-select:none}
.hbl-win-head b{flex:1}.hbl-win-head button{background:none;border:0;color:var(--text-dim,#999);cursor:pointer;font-size:15px;padding:0 4px}
.hbl-win-body{overflow:auto;padding:8px 10px;flex:1}
.hbl-item{border-left:3px solid var(--accent,#00e08a);padding:4px 8px;margin:6px 0}.hbl-item-head{color:var(--text-dim,#999);font-size:11.5px}
.hbl-item-title{font-weight:600;margin:2px 0}.hbl-trail{margin:4px 0 0 16px;padding:0;line-height:1.45}
.hbl-trail li.hbl-k-check{color:#ffb300}.hbl-trail li.hbl-k-error{color:#ff5252}.hbl-t{opacity:.55;font-variant-numeric:tabular-nums}
.hbl-sub{margin:10px 0 3px;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-dim,#999)}
.hbl-list,.hbl-hist{list-style:none;margin:0;padding:0}.hbl-list li,.hbl-hist li{padding:4px 2px;border-bottom:1px solid var(--border,#2a2a2a)}
.hbl-tag{display:inline-block;margin-left:6px;padding:0 6px;border:1px solid var(--border,#444);border-radius:8px;font-size:10.5px;color:var(--text-dim,#aaa)}
.hbl-amber{border-color:#ffb300;color:#ffb300}.hbl-needs .hbl-tag{border-color:#ffb300;color:#ffb300}
.hbl-live-line{color:#2ecc71;font-size:11.5px;margin-top:2px}.hbl-dim{color:var(--text-dim,#999)}.hbl-err{color:#ff8a80}
.hbl-note{color:var(--text-dim,#999);margin:2px 0 6px}.hbl-empty{color:var(--text-dim,#999);padding:8px 0}.hbl-warn{color:#ff5252;margin:6px 0}
.hbl-gauge{display:grid;grid-template-columns:80px 1fr auto;gap:8px;align-items:center;margin:6px 0}
.hbl-bar{height:8px;border-radius:4px;background:var(--border,#333);overflow:hidden}.hbl-bar i{display:block;height:100%;background:var(--accent,#00e08a)}
.hbl-ctl{display:inline-flex;gap:4px;margin-left:6px}.hbl-ctl button,.hbl-ctl select{font-size:10.5px;padding:1px 6px;border-radius:6px;cursor:pointer;
  border:1px solid var(--border,#444);background:var(--bg,#111);color:var(--text,#ddd)}
#hb-live-dock{position:fixed;right:10px;top:30%;z-index:9001;display:flex;flex-direction:column;gap:8px}
.hbl-bubble{width:40px;height:40px;border-radius:50%;border:1px solid var(--border,#444);background:var(--card,#1b1b1b);color:var(--text,#ddd);
  cursor:pointer;font-size:16px;box-shadow:0 4px 12px rgba(0,0,0,.35)}.hbl-bubble.hbl-busy{border-color:#2ecc71;animation:hblPulse 1.4s infinite}
body.hb-live-on #hb-now,body.hb-live-on #hb-live-activity,body.hb-live-on #hb-clipboard,body.hb-live-on #home-chat-main .hb-needs-you{display:none!important}
@media (max-width:640px){.hbl-win{left:8px!important;right:8px;width:auto}.hbl-line{max-width:90px}}`;
    document.head.appendChild(st);
  }

  function classic() { try { return localStorage.getItem('hbLive.classic') === '1'; } catch (e) { return false; } }
  function strip() {
    if (classic()) { document.body.classList.remove('hb-live-on'); return null; }
    document.body.classList.add('hb-live-on');   // HB Live L5: hides the HB-now pill, live box, HB Driving board and Needs-you bar in main chat
    let el = document.getElementById('hb-live-strip');
    if (el) return el;
    const main = document.getElementById('home-chat-main'), bar = document.getElementById('home-chat-bar');
    if (!main) return null;
    el = document.createElement('div');
    el.id = 'hb-live-strip';
    el.setAttribute('role', 'toolbar');
    el.setAttribute('aria-label', 'What HB and the models are doing');
    if (bar && bar.parentNode === main) bar.insertAdjacentElement('afterend', el); else main.prepend(el);
    el.addEventListener('click', (e) => { const b = e.target.closest('[data-win]'); if (b) toggle(b.dataset.win); });
    return el;
  }
  function dock() {
    let d = document.getElementById('hb-live-dock');
    if (!d) { d = document.createElement('div'); d.id = 'hb-live-dock'; document.body.appendChild(d); }
    return d;
  }

  const TITLE = { needs: 'Needs you', master: 'Tasks (HB clipboard)', system: 'System', gpu: 'GPU · APEX', fred: 'CPU · Fred',
    small: 'CPU · small models', online: 'Online models', hb: 'HB (orchestrator)', admin: 'Admin (sudo in your terminal)', 'claude-code': 'Claude Code' };
  function title(id) { return (ICON[id] || '') + ' ' + (TITLE[id] || id); }

  function open(id, saved) {
    if (S.wins[id]) { S.wins[id].min = false; place(id); render(); save(); return; }
    const n = Object.keys(S.wins).length;
    const w = Object.assign({ x: Math.max(16, window.innerWidth - 460 - n * 26), y: 90 + n * 26, min: false }, saved || {});
    const el = document.createElement('section');
    el.className = 'hbl-win';
    el.dataset.win = id;
    el.innerHTML = `<div class="hbl-win-head"><b>${R.esc(title(id))}</b><button type="button" data-act="min" aria-label="Minimise" title="Minimise to a bubble">–</button>` +
      '<button type="button" data-act="close" aria-label="Close" title="Close">×</button></div><div class="hbl-win-body"></div>';
    document.body.appendChild(el);
    w.el = el;
    S.wins[id] = w;
    el.querySelector('[data-act=min]').onclick = () => { w.min = true; place(id); save(); renderDock(); };
    el.querySelector('[data-act=close]').onclick = () => close(id);
    drag(el, w);
    place(id);
    render();
    save();
  }
  function close(id) { const w = S.wins[id]; if (!w) return; w.el.remove(); delete S.wins[id]; save(); renderDock(); }
  function toggle(id) { const w = S.wins[id]; if (w && !w.min) close(id); else open(id); }
  function place(id) {
    const w = S.wins[id];
    w.x = Math.min(Math.max(0, w.x), Math.max(0, window.innerWidth - 120));
    w.y = Math.min(Math.max(0, w.y), Math.max(0, window.innerHeight - 60));
    w.el.style.left = w.x + 'px'; w.el.style.top = w.y + 'px';
    w.el.style.display = w.min ? 'none' : 'flex';
    if (w.w) w.el.style.width = w.w + 'px';
    if (w.h) w.el.style.height = w.h + 'px';
    renderDock();
  }
  function drag(el, w) {
    const head = el.querySelector('.hbl-win-head');
    head.addEventListener('pointerdown', (e) => {
      if (e.target.closest('button')) return;
      const dx = e.clientX - w.x, dy = e.clientY - w.y;
      head.setPointerCapture(e.pointerId);
      const move = (ev) => { w.x = ev.clientX - dx; w.y = ev.clientY - dy; el.style.left = w.x + 'px'; el.style.top = w.y + 'px'; };
      const up = () => { head.removeEventListener('pointermove', move); head.removeEventListener('pointerup', up); place(w.el.dataset.win); save(); };
      head.addEventListener('pointermove', move);
      head.addEventListener('pointerup', up);
    });
    if (window.ResizeObserver) new ResizeObserver(() => { if (!w.min && w.el.offsetWidth) { w.w = w.el.offsetWidth; w.h = w.el.offsetHeight; } }).observe(el);
  }
  function laneState(id) {
    const s = S.snap || {};
    if (id === 'needs') return (s.needs_you || []).some((n) => n.kind !== 'status') ? 'waiting' : 'idle';
    if (id === 'master') return ((s.master || {}).items || []).some((i) => i.live) ? 'busy' : 'idle';
    if (id === 'system') return (s.unexplained || []).length ? 'error' : 'idle';
    const l = (s.lanes || []).find((x) => x.id === id);
    return l ? l.state : 'idle';
  }
  function renderDock() {
    const d = dock();
    const mins = Object.keys(S.wins).filter((id) => S.wins[id].min);
    d.innerHTML = mins.map((id) => `<button type="button" class="hbl-bubble hbl-${laneState(id)}" data-win="${R.esc(id)}" title="${R.esc(title(id))}">${ICON[id] || '•'}</button>`).join('');
    d.querySelectorAll('[data-win]').forEach((b) => { b.onclick = () => open(b.dataset.win); });
  }

  function body(id) {
    const s = S.snap || {};
    if (id === 'master' || id === 'needs') return R.renderMaster(s, S.controls, S.needsControls);
    if (id === 'system') return R.renderSystem(s);
    return R.renderLane(s, id, Date.now() / 1000);
  }
  function render() {
    if (!S.snap) return;
    style();
    const el = strip();
    if (el) el.innerHTML = R.renderStrip(S.snap);
    Object.keys(S.wins).forEach((id) => {
      const w = S.wins[id], b = w.el.querySelector('.hbl-win-body');
      if (w.min) return;
      const top = b.scrollTop, atEnd = b.scrollHeight - b.scrollTop - b.clientHeight < 30;
      b.innerHTML = body(id);
      b.scrollTop = atEnd && id !== 'master' && id !== 'needs' ? b.scrollHeight : top;
    });
    renderDock();
  }

  // ── HB Live L4a: controls in the Tasks window, through HB's own routes (/hb/queue task, clip, switch) ──
  const DOER_CHOICES = ['apex', 'fred', 'small', 'hb', 'codex', 'gemini', 'claude'];
  function controlsFor(i) {
    const step = R.esc(i.step_id || ''), task = R.esc(i.task_id || '');
    let html = '<div class="hbl-ctl">';
    if (i.state === 'needs_you' && i.step_id) html += `<button type="button" data-q="task" data-a="accept" data-id="${step}">Approve</button>`;
    if (i.task_id) {
      if (i.parked) html += `<button type="button" data-q="task" data-a="continue" data-id="${task}" title="Give it a fresh try">Try again</button>`;
      else if (i.state === 'now') html += `<button type="button" data-q="task" data-a="pause" data-id="${task}">Pause</button>`;
      else html += `<button type="button" data-q="task" data-a="continue" data-id="${task}">Continue</button>`;
      html += `<button type="button" data-q="task" data-a="cancel" data-id="${task}" data-confirm="Cancel this task?">Cancel</button>`;
    }
    if (i.step_id) {
      html += `<button type="button" data-q="clip" data-a="top" data-id="${step}" title="Move to the top">⇈</button>` +
        `<button type="button" data-q="clip" data-a="up" data-id="${step}" title="Move up">↑</button>` +
        `<button type="button" data-q="clip" data-a="down" data-id="${step}" title="Move down">↓</button>` +
        `<select data-q="clip" data-a="importance" data-id="${step}" title="Importance (5 is highest)">` +
        [5, 4, 3, 2, 1].map((n) => `<option value="${n}"${Number(i.importance) === n ? ' selected' : ''}>imp ${n}</option>`).join('') + '</select>' +
        `<select data-q="clip" data-a="doer" data-id="${step}" title="Who does it - HB lines up this model">` +
        DOER_CHOICES.map((d) => `<option value="${d}"${(i.doer || 'apex') === d ? ' selected' : ''}>${d}</option>`).join('') + '</select>';
    }
    return html + '</div>';
  }
  function send(body, win) {
    const note = win && win.querySelector('.hbl-said');
    return fetch('/api/peer/v1/hb/queue', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) }).then((r) => r.json()).then((d) => {
      if (note) note.textContent = (d && (d.said || d.error || d.changed)) || '';
      refresh();
    }).catch(() => { if (note) note.textContent = 'HB did not answer - try again.'; });
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.hbl-win [data-q]');
    if (b && b.tagName === 'BUTTON') {
      if (b.dataset.confirm && !window.confirm(b.dataset.confirm)) return;
      send({ [b.dataset.q]: [b.dataset.a, b.dataset.id] }, b.closest('.hbl-win'));
    }
    const sw = e.target.closest('.hbl-win [data-switch]');
    if (sw) send({ switch: sw.dataset.switch, on: sw.dataset.on === '1' }, sw.closest('.hbl-win'));
  });
  document.addEventListener('change', (e) => {
    const s = e.target.closest('.hbl-win select[data-q]');
    if (s) send({ [s.dataset.q]: [s.dataset.a, s.dataset.id, s.value] }, s.closest('.hbl-win'));
  });
  S.controls = controlsFor;

  // HB Live L5: everything the old Needs-you bar could do, in the Tasks window
  function needsControlsFor(n) {
    let html = '<div class="hbl-ctl">';
    if (n.kind === 'accept' && n.step_id) html += `<button type="button" data-q="task" data-a="accept" data-id="${R.esc(n.step_id)}">Approve</button>`;
    if (n.open && n.open.type === 'message' && n.open.id) html += `<button type="button" data-show="${Number(n.open.id)}">Show in chat</button>`;
    (n.actions || []).forEach((a) => { if (a && a.command) html += `<button type="button" data-cmd="${R.esc(a.command)}">${R.esc(a.label || a.command)}</button>`; });
    if (n.task_id && n.kind !== 'accept') {
      html += `<button type="button" data-q="task" data-a="continue" data-id="${R.esc(n.task_id)}">Continue</button>` +
        `<button type="button" data-q="task" data-a="cancel" data-id="${R.esc(n.task_id)}" data-confirm="Cancel this task?">Cancel</button>`;
    }
    return html + '</div>';
  }
  S.needsControls = needsControlsFor;
  document.addEventListener('click', (e) => {
    const show = e.target.closest('.hbl-win [data-show]');
    if (show) {
      const m = document.querySelector(`#home-chat-messages [data-message-id="${Number(show.dataset.show)}"]`);
      if (m) { m.scrollIntoView({ behavior: 'smooth', block: 'center' }); m.style.outline = '2px solid #ffb300'; setTimeout(() => { m.style.outline = ''; }, 2500); }
    }
    const cmd = e.target.closest('.hbl-win [data-cmd]');
    if (cmd) {
      const input = document.getElementById('home-chat-input');
      if (input) { input.value = cmd.dataset.cmd; input.dispatchEvent(new Event('input', { bubbles: true })); document.getElementById('home-chat-send-btn')?.click(); }
    }
  });

  let pending = null;
  function refresh() {
    if (document.hidden || S.busy || classic()) return;
    S.busy = true;
    fetch('/api/peer/v1/hb/live', { credentials: 'same-origin' }).then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d || !d.ok) return;
      S.snap = d;
      render();
    }).catch(() => {}).finally(() => { S.busy = false; });
  }
  function soon() { clearTimeout(pending); pending = setTimeout(refresh, 300); }

  root.hbLive = { classic: (on) => { try { localStorage.setItem('hbLive.classic', on ? '1' : '0'); } catch (e) {} location.reload(); }, open, close, toggle, refresh, state: S, setControls: (fn) => { S.controls = fn; render(); } };
  document.addEventListener('sse:chat', soon);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(refresh, 2000);
  const restore = () => { const saved = load(); Object.keys(saved).forEach((id) => open(id, saved[id])); refresh(); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', restore); else restore();
})(typeof window !== 'undefined' ? window : globalThis);
