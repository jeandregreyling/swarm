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

  // ── Practice 194: the board inside main chat (owner 20 Nov: "the top banner becomes the main chat window output and this should be
  // resizable ... visible in main chat ... I don't care about the ones not doing anything ... 'needs you' still pops up ... one list with
  // HB orchestrating ... one-click, one window to rule them all") ─────────────────────────────────────────────────────────────────
  const GROUPS = [['needs_you', 'Needs you'], ['now', 'Now'], ['next', 'Next'], ['claude', 'With Claude Code'], ['waiting', 'Waiting'],
    ['spec', 'Needs a spec'], ['parked', 'Parked by HB'], ['blocked', 'Blocked'], ['roadmap', 'Roadmap']];
  const FOLDED = { roadmap: true, blocked: true };

  function activeItems(snap) {
    const out = [];
    (snap.lanes || []).forEach((l) => { if (l.id !== 'system') (l.items || []).forEach((it) => out.push(Object.assign({ lane: l.id }, it))); });
    return out;
  }

  function renderActive(snap, now) {
    const items = activeItems(snap);
    const needs = (snap.needs_you || []).filter((n) => n.kind !== 'status');
    const chips = items.map((it, n) => `<button type="button" class="hbl-chip hbl-busy" data-card="${n}" title="${esc(it.title)}">` +
      `<span class="hbl-dot"></span><span class="hbl-ico">${ICON[it.lane] || '•'}</span><b>${esc(SHORT[it.lane] || it.lane)}</b>` +
      `<span class="hbl-line">${esc(it.last_step || it.title || 'working')}</span></button>`).join('');
    const alert = (snap.unexplained || []).length ? `<span class="hbl-chip hbl-error"><span class="hbl-dot"></span><b>System</b>` +
      `<span class="hbl-line">⚠ ${esc(snap.unexplained[0].evidence)}</span></span>` : '';
    const needChip = needs.length ? `<button type="button" class="hbl-chip hbl-waiting" data-needs-open="1"><span class="hbl-dot"></span>` +
      `<b>Needs you</b><span class="hbl-count">${needs.length}</span></button>` : '';
    if (!items.length && !needs.length && !alert) {
      const last = (snap.history || [])[0];
      return `<div class="hbl-idle">Everyone is idle${last ? ` · last: ${esc(SHORT[last.lane] || last.lane)} - ${esc(last.title)} (${took(last.took_s)}, ${clock(last.at)})` : ''}</div>`;
    }
    const cards = items.map((it, n) => `<div class="hbl-item" data-card-body="${n}"><div class="hbl-item-head">` +
      `<b>${esc(it.actor || SHORT[it.lane] || '')}</b>` + (it.model ? ` · ${esc(it.model)}` : '') + (it.device ? ` · ${esc(it.device)}` : '') +
      (it.since ? ` · <span class="hbl-elapsed">${took((now || snap.at || 0) - it.since)}</span>` : '') + (it.purpose ? ` · <i>${esc(it.purpose)}</i>` : '') +
      `</div><div class="hbl-item-title">${esc(it.title)}</div>` + renderTrail((it.trail || []).slice(-6)) + '</div>').join('');
    return `<div class="hbl-active">${needChip}${chips}${alert}</div>${cards ? `<div class="hbl-cards">${cards}</div>` : ''}`;
  }

  function primaryFor(i) {
    const step = esc(i.step_id || ''), task = esc(i.task_id || '');
    const g = i.group || i.state;
    if (g === 'needs_you' && i.step_id) return `<button type="button" class="hbl-primary" data-q="task" data-a="accept" data-id="${step}">Approve</button>`;
    if (g === 'now' && i.task_id) return `<button type="button" class="hbl-primary" data-q="task" data-a="pause" data-id="${task}">Pause</button>`;
    if (g === 'parked' && i.task_id) return `<button type="button" class="hbl-primary" data-q="task" data-a="continue" data-id="${task}">Try again</button>`;
    if (g === 'spec' && i.task_id) return `<button type="button" class="hbl-primary" data-fill="/done ${task} ">Say what done means</button>`;
    if (g === 'next' && i.step_id) return `<button type="button" class="hbl-primary" data-cmd="/workflow next ${step}">Start now</button>`;
    if (g === 'waiting' && i.task_id) return `<button type="button" class="hbl-primary" data-q="task" data-a="continue" data-id="${task}">Continue</button>`;
    return '';
  }

  function renderList(snap, controls, needsControls, open) {
    const m = snap.master || {}, items = m.items || [];
    const needs = (snap.needs_you || []).filter((n) => n.kind !== 'status');
    const openNow = open || {};
    let html = `<div class="hbl-list-head">HB is ${m.on === false ? '<b>paused</b>' : 'driving'}${m.auto ? ' · auto-approve on' : ''} · ` +
      `${items.filter((i) => (i.group || i.state) !== 'roadmap').length} open` +
      (controls ? ` <button type="button" class="hbl-mini" data-switch="auto" data-on="${m.on === false ? 1 : 0}">${m.on === false ? 'Let HB drive' : 'Pause all'}</button>` : '') +
      ` <button type="button" class="hbl-mini" data-cmd="/board" title="HB posts the list in chat (also from Telegram)">Post the list</button>` +
      '<span class="hbl-said hbl-dim"></span></div>';
    if (needs.length) {
      html += '<div class="hbl-sub">Needs you</div><ul class="hbl-list">' + needs.map((n) =>
        `<li class="hbl-needs" title="${esc(n.why || n.title || '')}"><span class="hbl-row-title">${esc(n.label || n.text || '')}</span>` +
        (needsControls ? needsControls(n) : '') + '</li>').join('') + '</ul>';
    }
    GROUPS.forEach(([key, word]) => {
      if (key === 'needs_you') return;
      const rows = items.filter((i) => (i.group || i.state || 'waiting') === key);
      if (!rows.length) return;
      const folded = FOLDED[key] && !openNow[key];
      html += `<div class="hbl-sub"><button type="button" class="hbl-fold" data-fold="${key}">${folded ? '▸' : '▾'} ${word} (${rows.length})</button></div>`;
      if (folded) return;
      html += '<ul class="hbl-list">' + rows.map((i) =>
        `<li data-step="${esc(i.step_id)}" data-task="${esc(i.task_id || '')}" title="${esc(i.note || i.why || '')}">` +
        `<span class="hbl-row-title">${esc(i.title)}</span><span class="hbl-tag">${esc(i.doer || 'apex')}</span>` +
        (i.live ? `<div class="hbl-live-line">● ${esc(SHORT[i.live.lane] || i.live.lane)}: ${esc(i.live.last_step || 'working')}</div>` : '') +
        (i.note && key === 'spec' ? `<div class="hbl-dim">${esc(i.note)}</div>` : '') +
        `<div class="hbl-row-ctl">${primaryFor(i)}` + (controls && key !== 'roadmap' ? `<button type="button" class="hbl-more" data-more="${esc(i.step_id)}" title="More">…</button>` +
          `<div class="hbl-more-box" data-more-box="${esc(i.step_id)}" hidden>${controls(i)}</div>` : '') + '</div></li>').join('') + '</ul>';
    });
    if (!items.length && !needs.length) html += '<div class="hbl-empty">Nothing open.</div>';
    return html;
  }

  function renderBoard(snap, opts) {
    const o = opts || {};
    return `<div class="hbl-pane-head"><button type="button" class="hbl-fold" data-pane-fold="1">${o.collapsed ? '▸' : '▾'} HB Live</button>` +
      `<span class="hbl-dim">${esc(systemLine(snap))}</span></div>` +
      (o.collapsed ? renderActive(snap, o.now).replace(/<div class="hbl-cards">[\s\S]*$/, '') :
        renderActive(snap, o.now) + `<div class="hbl-board">${renderList(snap, o.controls, o.needsControls, o.open)}</div>`);
  }

  function systemLine(snap) {
    const t = snap.telemetry || {}, g = t.gpu || {}, c = t.cpu || {};
    const free = g.vram_total_gb != null && g.vram_used_gb != null ? (g.vram_total_gb - g.vram_used_gb).toFixed(1) + ' GB free for you' : '';
    return [g.busy_pct != null ? 'GPU ' + Math.round(g.busy_pct) + '%' : '', free, g.temp_c != null ? Math.round(g.temp_c) + '°C' : '',
      c.load1 != null ? 'CPU load ' + c.load1 : ''].filter(Boolean).join(' · ');
  }

  function renderNeedsPopup(n, needsControls) {
    return `<div class="hbl-pop-head">⚑ Needs you</div><div class="hbl-pop-title">${esc(n.label || '')}</div>` +
      (n.title && n.title !== n.label ? `<div class="hbl-dim">${esc(n.title)}</div>` : '') +
      (n.why ? `<div class="hbl-pop-why">${esc(String(n.why).slice(0, 400))}</div>` : '') +
      (needsControls ? needsControls(n) : '') + '<div class="hbl-ctl"><button type="button" data-later="1">Later</button></div>';
  }

  const R = { renderStrip, renderLane, renderMaster, renderSystem, renderTrail, renderActive, renderList, renderBoard, renderNeedsPopup,
    primaryFor, systemLine, took, esc, ICON, SHORT };
  root.HBLiveRender = R;
  if (typeof module !== 'undefined' && module.exports) module.exports = R;
  if (typeof document === 'undefined' || typeof window === 'undefined') return;

  // ── Page layer ───────────────────────────────────────────────────────────
  const S = { snap: null, busy: false, controls: null, needsControls: null, open: {}, popup: null };
  function ls(key, value) {
    try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; }
    return null;
  }

  function style() {
    if (document.getElementById('hb-live-style')) return;
    const st = document.createElement('style');
    st.id = 'hb-live-style';
    st.textContent = `
#hb-live-pane{flex:0 0 auto;max-height:65vh;min-height:34px;overflow:auto;resize:vertical;padding:4px 10px 6px;border-bottom:2px solid var(--border,#333);
  background:var(--card,#161616);color:var(--text,#ddd);font-size:12.5px}
.hbl-pane-head{display:flex;gap:10px;align-items:center;margin-bottom:4px}.hbl-pane-head .hbl-dim{font-size:11.5px}
.hbl-active{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 4px}
.hbl-chip{display:flex;align-items:center;gap:5px;max-width:320px;padding:3px 9px;border-radius:14px;cursor:pointer;border:1px solid var(--border,#333);
  background:var(--bg,#111);color:var(--text,#ddd);font-size:11.5px}
.hbl-chip b{white-space:nowrap}.hbl-ico{opacity:.8}.hbl-line{color:var(--text-dim,#999);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}
.hbl-dot{width:8px;height:8px;border-radius:50%;background:#777;flex:0 0 8px}
.hbl-busy .hbl-dot{background:#2ecc71;animation:hblPulse 1.4s infinite}.hbl-waiting .hbl-dot{background:#ffb300}.hbl-error .hbl-dot{background:#ff5252}
.hbl-busy{border-color:rgba(46,204,113,.6)}.hbl-waiting{border-color:rgba(255,179,0,.7)}.hbl-error{border-color:#ff5252}
.hbl-count{background:#ffb300;color:#000;border-radius:9px;padding:0 6px;font-weight:700;font-size:10.5px}
@keyframes hblPulse{0%{box-shadow:0 0 0 0 rgba(46,204,113,.7)}70%{box-shadow:0 0 0 7px rgba(46,204,113,0)}100%{box-shadow:0 0 0 0 rgba(46,204,113,0)}}
.hbl-idle{color:var(--text-dim,#999);padding:2px 0 4px}
.hbl-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:6px;margin-bottom:6px}
.hbl-item{border-left:3px solid #2ecc71;padding:4px 8px;background:var(--bg,#111);border-radius:4px}
.hbl-item-head{color:var(--text-dim,#999);font-size:11.5px}.hbl-item-title{font-weight:600;margin:2px 0}
.hbl-trail{margin:2px 0 0 16px;padding:0;line-height:1.4;font-size:11.5px}.hbl-trail li.hbl-k-check{color:#ffb300}.hbl-trail li.hbl-k-error{color:#ff5252}
.hbl-t{opacity:.55;font-variant-numeric:tabular-nums}
.hbl-list-head{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:var(--text-dim,#999);margin:4px 0}
.hbl-sub{margin:6px 0 2px;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-dim,#999)}
.hbl-fold{background:none;border:0;color:inherit;font:inherit;cursor:pointer;padding:0;text-transform:inherit;letter-spacing:inherit}
.hbl-list{list-style:none;margin:0;padding:0}.hbl-list li{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:4px 2px;border-bottom:1px solid var(--border,#262626)}
.hbl-row-title{flex:1 1 260px;min-width:0}.hbl-row-ctl{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
.hbl-tag{padding:0 6px;border:1px solid var(--border,#444);border-radius:8px;font-size:10.5px;color:var(--text-dim,#aaa)}
.hbl-needs .hbl-row-title{color:#ffb300}.hbl-live-line{flex-basis:100%;color:#2ecc71;font-size:11.5px}
.hbl-primary,.hbl-mini,.hbl-more,.hbl-ctl button,.hbl-ctl select{font-size:11px;padding:2px 8px;border-radius:6px;cursor:pointer;border:1px solid var(--border,#444);
  background:var(--bg,#111);color:var(--text,#ddd)}
.hbl-primary{border-color:var(--accent,#00e08a);color:var(--accent,#00e08a);font-weight:600}
.hbl-more-box{flex-basis:100%}.hbl-ctl{display:inline-flex;flex-wrap:wrap;gap:4px;margin-top:3px}
.hbl-dim{color:var(--text-dim,#999)}.hbl-empty{color:var(--text-dim,#999);padding:6px 0}.hbl-said{font-size:11px}
#hb-live-pop{position:fixed;z-index:9500;left:50%;top:18%;transform:translateX(-50%);width:440px;max-width:calc(100vw - 32px);padding:14px 16px;
  background:var(--card,#1b1b1b);color:var(--text,#ddd);border:2px solid #ffb300;border-radius:12px;box-shadow:0 0 0 4px rgba(255,179,0,.15),0 14px 40px rgba(0,0,0,.5)}
.hbl-pop-head{color:#ffb300;font-weight:700;margin-bottom:6px}.hbl-pop-title{font-weight:600;margin-bottom:4px}.hbl-pop-why{margin:6px 0;white-space:pre-wrap;font-size:12px}
.hbl-cmd{display:inline;padding:0 6px;margin:0 1px;border-radius:6px;border:1px solid var(--accent,#00e08a);background:transparent;color:var(--accent,#00e08a);
  font:inherit;font-size:.92em;cursor:pointer}
.hbl-json summary{cursor:pointer;color:var(--text-dim,#999)}
body.hb-live-on #hb-now,body.hb-live-on #hb-live-activity,body.hb-live-on #hb-clipboard,body.hb-live-on #home-chat-main .hb-needs-you{display:none!important}
@media (max-width:640px){.hbl-line{max-width:110px}.hbl-cards{grid-template-columns:1fr}}`;
    document.head.appendChild(st);
  }

  function classic() { try { return localStorage.getItem('hbLive.classic') === '1'; } catch (e) { return false; } }
  function pane() {
    if (classic()) { document.body.classList.remove('hb-live-on'); return null; }
    document.body.classList.add('hb-live-on');   // HB Live: hides the HB-now pill, live box, HB Driving board and Needs-you bar in main chat
    let el = document.getElementById('hb-live-pane');
    if (el) return el;
    const main = document.getElementById('home-chat-main'), bar = document.getElementById('home-chat-bar');
    if (!main) return null;
    el = document.createElement('section');
    el.id = 'hb-live-pane';
    el.setAttribute('aria-label', 'HB Live: who is working, and the list of open tasks');
    const h = Number(ls('hbLive.paneHeight'));
    if (h > 40) el.style.height = h + 'px';
    if (bar && bar.parentNode === main) bar.insertAdjacentElement('afterend', el); else main.prepend(el);
    if (window.ResizeObserver) new ResizeObserver(() => { if (el.offsetHeight > 40 && el.style.height) ls('hbLive.paneHeight', String(el.offsetHeight)); }).observe(el);
    el.addEventListener('mouseup', () => { if (el.style.height) ls('hbLive.paneHeight', String(el.offsetHeight)); });
    return el;
  }

  function render() {
    if (!S.snap) return;
    style();
    const el = pane();
    if (!el) return;
    const top = el.scrollTop;
    const open = Array.from(el.querySelectorAll('[data-more-box]:not([hidden])')).map((b) => b.dataset.moreBox);
    el.innerHTML = R.renderBoard(S.snap, { collapsed: ls('hbLive.collapsed') === '1', now: Date.now() / 1000, controls: S.controls,
      needsControls: S.needsControls, open: S.open });
    open.forEach((id) => { const b = el.querySelector(`[data-more-box="${CSS.escape(id)}"]`); if (b) b.hidden = false; });
    el.scrollTop = top;
    popup();
    decorate();
  }

  // Needs-you is the only pop-up: a new item (not seen in this browser) opens it, with one-click answers
  function seen() { try { return new Set(JSON.parse(ls('hbLive.needsSeen') || '[]')); } catch (e) { return new Set(); } }
  function popup() {
    const needs = ((S.snap || {}).needs_you || []).filter((n) => n.kind !== 'status' && !n.info);
    const known = seen();
    const fresh = needs.find((n) => n.key && !known.has(n.key));
    let box = document.getElementById('hb-live-pop');
    if (!fresh) { if (box && S.popup && !needs.some((n) => n.key === S.popup)) { box.remove(); S.popup = null; } return; }
    if (S.popup === fresh.key && box) return;
    if (!box) { box = document.createElement('div'); box.id = 'hb-live-pop'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Needs you'); document.body.appendChild(box); }
    S.popup = fresh.key;
    box.innerHTML = R.renderNeedsPopup(fresh, S.needsControls);
  }
  function settle(key) {
    const known = seen();
    if (key) known.add(key);
    ls('hbLive.needsSeen', JSON.stringify(Array.from(known).slice(-300)));
    const box = document.getElementById('hb-live-pop');
    if (box) box.remove();
    S.popup = null;
    popup();
  }

  // In chat: /commands in HB's and APEX's messages are one-click buttons; HB's raw JSON hand-offs read as one line
  const CMD = /(^|[\s(])(\/(?:accept|reject|continue|pause|cancel|plan|workflow|drive|done|board|status|tasks|approvals|clip|yes|no|today|channels)\b(?: [A-Z]-[0-9A-F]{6,12}| (?:on|off|next|status|auto)\b| S-[0-9A-F]{10})*)/g;
  function decorate() {
    document.querySelectorAll('#home-chat-messages .hc-bubble:not([data-hbl-done])').forEach((b) => {
      b.dataset.hblDone = '1';
      const body = b.querySelector('.hc-bubble-body') || b;
      const text = (body.textContent || '').trim();
      if (text.startsWith('{"task_type"')) {
        let one = 'HB handed a task back to APEX';
        try { const j = JSON.parse(text); one = `↻ HB resumed ${j.task_id || 'a task'} for APEX: ${String(j.next_task || '').split('\n')[0].slice(0, 160)}`; } catch (e) {}
        body.innerHTML = `<details class="hbl-json"><summary>${R.esc(one)}</summary><pre style="white-space:pre-wrap">${R.esc(text)}</pre></details>`;
        return;
      }
      const sender = String((b._chatMessage || {}).from_agent || (b._chatMessage || {}).sender || '').toLowerCase();
      if (!['hummingbird', 'apex', 'hb'].includes(sender)) return;
      const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) if (CMD.test(walker.currentNode.nodeValue)) nodes.push(walker.currentNode);
      nodes.forEach((node) => {
        if (node.parentNode && node.parentNode.closest('pre, code, button, a')) return;
        const span = document.createElement('span');
        span.innerHTML = R.esc(node.nodeValue).replace(CMD, (m, pre, cmd) => `${pre}<button type="button" class="hbl-cmd" data-cmd="${cmd.trim()}">${cmd.trim()}</button>`);
        node.parentNode.replaceChild(span, node);
      });
    });
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
  S.controls = controlsFor;

  // HB Live L5: everything the old Needs-you bar could do
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

  function runCommand(text, fill) {
    const input = document.getElementById('home-chat-input');
    if (!input) return;
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    if (fill) { input.focus(); return; }
    document.getElementById('home-chat-send-btn')?.click();
  }
  const SCOPE = '#hb-live-pane, #hb-live-pop, #home-chat-messages';
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t.closest || !t.closest(SCOPE)) return;
    const pop = t.closest('#hb-live-pop');
    const q = t.closest('button[data-q]');
    if (q) {
      if (q.dataset.confirm && !window.confirm(q.dataset.confirm)) return;
      send({ [q.dataset.q]: [q.dataset.a, q.dataset.id] }, t.closest('#hb-live-pane') || pop);
      if (pop) settle(S.popup);
      return;
    }
    const sw = t.closest('[data-switch]');
    if (sw) { send({ switch: sw.dataset.switch, on: sw.dataset.on === '1' }, t.closest('#hb-live-pane')); return; }
    const cmd = t.closest('[data-cmd]');
    if (cmd) {
      const c = cmd.dataset.cmd;
      if (/^\/(cancel|reject|stop)\b/.test(c) && !window.confirm(`Run ${c}?`)) return;
      runCommand(c);
      if (pop) settle(S.popup);
      return;
    }
    const fill = t.closest('[data-fill]');
    if (fill) { runCommand(fill.dataset.fill, true); return; }
    const show = t.closest('[data-show]');
    if (show) {
      const m = document.querySelector(`#home-chat-messages [data-message-id="${Number(show.dataset.show)}"]`);
      if (m) { m.scrollIntoView({ behavior: 'smooth', block: 'center' }); m.style.outline = '2px solid #ffb300'; setTimeout(() => { m.style.outline = ''; }, 2500); }
      return;
    }
    if (t.closest('[data-later]')) { settle(S.popup); return; }
    const more = t.closest('[data-more]');
    if (more) { const b = document.querySelector(`[data-more-box="${CSS.escape(more.dataset.more)}"]`); if (b) b.hidden = !b.hidden; return; }
    const fold = t.closest('[data-fold]');
    if (fold) { S.open[fold.dataset.fold] = !S.open[fold.dataset.fold]; render(); return; }
    if (t.closest('[data-pane-fold]')) { ls('hbLive.collapsed', ls('hbLive.collapsed') === '1' ? '0' : '1'); render(); return; }
    if (t.closest('[data-needs-open]')) { ls('hbLive.needsSeen', '[]'); popup(); return; }
    const chip = t.closest('[data-card]');
    if (chip) { const c = document.querySelector(`[data-card-body="${chip.dataset.card}"]`); if (c) c.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });
  document.addEventListener('change', (e) => {
    const s = e.target.closest && e.target.closest('#hb-live-pane select[data-q], #hb-live-pop select[data-q]');
    if (s) send({ [s.dataset.q]: [s.dataset.a, s.dataset.id, s.value] }, e.target.closest('#hb-live-pane'));
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

  root.hbLive = { classic: (on) => { try { localStorage.setItem('hbLive.classic', on ? '1' : '0'); } catch (e) {} location.reload(); }, refresh, state: S };
  document.addEventListener('sse:chat', soon);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(refresh, 2000);
  if (window.MutationObserver) {
    const watch = () => { const list = document.getElementById('home-chat-messages'); if (list) new MutationObserver(decorate).observe(list, { childList: true }); else setTimeout(watch, 1000); };
    watch();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refresh); else refresh();
})(typeof window !== 'undefined' ? window : globalThis);
