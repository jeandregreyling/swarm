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
    return itemLine(it) + more;
  }

  function itemLine(it) {
    const title = String(it.title || '').trim(), stage = String(it.last_step || '').trim();
    return title && stage && title !== stage ? title + ' · ' + stage : (title || stage || 'working');
  }

  function chunkLine(chunks) {
    if (!chunks || !chunks.total || !chunks.doing || typeof chunks.doing !== 'object') return '';
    return 'chunk ' + chunks.doing.n + '/' + chunks.total + ': ' + chunks.doing.text;
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
        `</div><div class="hbl-item-title">${esc(it.title)}</div>` + renderLights(it.lights) + renderTrail(it.trail) + '</div>';
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
    const reading = (label, value, unit) => value == null ? '' :
      `<div class="hbl-note">${esc(label)}: ${esc(value)}${esc(unit || '')}</div>`;
    html += reading('GPU clock', g.clock_mhz, ' MHz') + reading('GPU clock limit', g.clock_limit_mhz, ' MHz') +
      reading('GPU hotspot', g.junction_temp_c, '°C') + reading('GPU fan', g.fan_rpm, ' RPM') +
      reading('GPU power', g.power_w, ' W') + reading('GPU power cap', g.power_cap_w, ' W') +
      reading('GPU mode', g.performance_mode) + reading('CPU0 clock', c.clock_mhz, ' MHz') +
      reading('CPU0 governor', c.governor);
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
      `<span class="hbl-line">${esc(itemLine(it))}</span></button>` +
      (it.task_id ? `<button type="button" class="hbl-mini" data-q="task" data-a="pause" data-id="${esc(it.task_id)}" title="Pause ${esc(it.title || 'this task')}">Pause</button>` : '')).join('');
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
      `</div><div class="hbl-item-title">${esc(it.title)}</div>` + renderLights(it.lights) +
      (chunkLine(it.chunks) ? `<div class="hbl-live-line">${esc(chunkLine(it.chunks))}</div>` : '') +
      (it.last_step ? `<div class="hbl-dim">${esc(it.last_step)}</div>` : '') + renderTrail((it.trail || []).slice(-6)) + '</div>').join('');
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
    // Practice 208 (JD: "the clipboard which I still can't manage"): a step with no HB task yet starts with one click too
    if ((g === 'waiting' || g === 'claude') && i.step_id && !i.task_id) return `<button type="button" class="hbl-primary" data-cmd="/workflow next ${step}">Start now</button>`;
    return '';
  }

  function renderList(snap, controls, needsControls, open) {
    const m = snap.master || {}, items = m.items || [];
    const needs = (snap.needs_you || []).filter((n) => n.kind !== 'status');
    const openNow = open || {};
    let html = `<div class="hbl-list-head">📋 <b>Clipboard</b> · HB is ${m.on === false ? '<b>paused</b>' : 'driving'}${m.auto ? ' · auto-approve on' : ''} · ` +
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
        `<span class="hbl-row-title">${esc(i.title)}${i.chunks && i.chunks.doing ? ' · ' + esc(i.chunks.doing.n) + '/' + esc(i.chunks.total) : ''}</span><span class="hbl-tag">${esc(i.doer || 'apex')}</span>` +
        (chunkLine(i.chunks) ? `<div class="hbl-live-line">${esc(chunkLine(i.chunks))}</div>` : '') +
        (i.live ? `<div class="hbl-live-line">● ${esc(SHORT[i.live.lane] || i.live.lane)}: ${esc(i.live.last_step || 'working')}</div>` : '') +
        (i.note && key === 'spec' ? `<div class="hbl-dim">${esc(i.note)}</div>` : '') +
        `<div class="hbl-row-ctl">${primaryFor(i)}` + (controls && key !== 'roadmap' ? `<button type="button" class="hbl-more" data-more="${esc(i.step_id)}" title="More">…</button>` +
          `<div class="hbl-more-box" data-more-box="${esc(i.step_id)}" hidden>${controls(i)}</div>` : '') + '</div></li>').join('') + '</ul>';
    });
    if (!items.length && !needs.length) html += '<div class="hbl-empty">Nothing open.</div>';
    return html;
  }

  // Practice 272 (JD 22 Nov: "I want those three icons you just lit up built into HB ... 'queue started' 'Inference and Continuity' ...
  // so I can see the system actually using DREAM to do its work"): DOES and DREAM lights, lit only from the turn's own records
  // (core/hb_lights.py; Practice 274: every DOES/DREAM icon carries the meaning every agent's prompt gives it). Green = happened, pulsing = happening now, amber = HB had to step in or only part done, red = failed,
  // dim = not used this turn. Hover a light for its evidence.
  function renderLights(lights, label) {      // Practice 274: TURN (Claude Code's three), DOES and DREAM, each with its meaning on hover
    if (!lights || !lights.turn || !lights.does || !lights.dream) return '';
    const tip = (l) => (l.law || l.word) + ' · now: ' + l.why;
    const one = (l, text) => `<span class="hbl-light hbl-l-${esc(l.state)}" title="${esc(tip(l))}">${esc(text)}</span>`;
    return `<div class="hbl-lights">${label ? `<span class="hbl-dim">${esc(label)}</span>` : ''}` +
      lights.turn.map((l) => one(l, l.icon + ' ' + l.word)).join('') +
      '<span class="hbl-lg">DOES</span>' + lights.does.map((l) => one(l, l.word)).join('') +
      '<span class="hbl-lg">DREAM</span>' + lights.dream.map((l) => one(l, l.letter)).join('') + '</div>';
  }

  // Practice 200: the APEX meter - always on top of main chat (owner: "let me see the actual token count and what APEX is doing")
  function renderMeter(a, rate, lit) {
    if (!a || !a.up) return '<div class="hbl-meter hbl-meter-down">⬢ APEX\'s model server is not answering' + (lit || '') + '</div>';
    const n = (x) => Number(x || 0).toLocaleString('en-AU');
    const who = `⬢ <b>APEX</b> <span class="hbl-dim">${esc(a.model || '')}${a.device ? ' · ' + esc(a.device) : ''}</span>`;
    let what;
    if (!a.busy) what = `<span class="hbl-dim">idle · last prompt ${n(a.prompt_tokens)} tokens</span>`;
    else if (a.prompt_tokens && a.prompt_done + a.prompt_cached < a.prompt_tokens && !a.generated) {
      const pct = Math.min(100, Math.round(((a.prompt_done + a.prompt_cached) / a.prompt_tokens) * 100));
      what = `<b>reading</b> ${n(a.prompt_done + a.prompt_cached)} / ${n(a.prompt_tokens)} tokens <span class="hbl-bar hbl-bar-in"><i style="width:${pct}%"></i></span>` +
        (rate ? ` <span class="hbl-dim">${n(Math.round(rate))} tok/s</span>` : '');
    } else what = `<b>writing</b> ${n(a.generated)} tokens` + (rate ? ` <span class="hbl-dim">· ${rate.toFixed(1)} tok/s</span>` : '');
    const ctx = a.ctx ? ` <span class="hbl-dim">· context ${n(a.prompt_tokens + a.generated)} / ${n(a.ctx)}</span>` : '';
    return `<div class="hbl-meter${a.busy ? ' hbl-meter-busy' : ''}">${who} · ${what}${ctx}${lit || ''}</div>`;
  }

  function renderBoard(snap, opts) {
    const o = opts || {};
    const lit = snap.apex_lights ? renderLights(snap.apex_lights, snap.apex_lights.running ? 'this turn' : 'last turn') : '';
    return renderMeter(snap.apex_live, o.rate, lit) + `<div class="hbl-pane-head"><button type="button" class="hbl-fold" data-pane-fold="1">${o.collapsed ? '▸' : '▾'} HB Live</button>` +
      `<span class="hbl-dim" title="CPU mode: the energy preference of the amd-pstate driver (the CPU still boosts on demand; 'powersave' is only the governor's name)">${esc(systemLine(snap))}</span>${renderPower(snap)}</div>` +
      // Practice 208 (JD 21 Nov: "the clipboard ... there's nothing in there"): the list sat under the worker cards and vanished when the
      // box was short or folded. Now: who is busy (one row) -> the clipboard -> the worker cards; folded still shows the clipboard's count.
      (() => {
        const active = renderActive(snap, o.now), cut = active.indexOf('<div class="hbl-cards">');
        const chips = cut < 0 ? active : active.slice(0, cut), cards = cut < 0 ? '' : active.slice(cut);
        const open = ((snap.master || {}).items || []).filter((i) => (i.group || i.state) !== 'roadmap').length;
        if (o.drawer) {    // Practice 285: the list lives in the drawer; the banner keeps who is working and one Tasks chip
          const needs = (snap.needs_you || []).filter((n) => n.kind !== 'status').length;
          const tasks = `<button type="button" class="hbl-tasks-chip${needs ? ' hbl-tasks-needs' : ''}" data-drawer="1" title="Open the task list">📋 Tasks · ${open} open${needs ? ' · ' + needs + ' need' + (needs === 1 ? 's' : '') + ' you' : ''}</button>`;
          const status = '<button type="button" class="hbl-tasks-chip hbl-status-chip" data-drawer="status" title="APEX, its window, GPU/CPU mode and the model switches">⚙ Status</button>';   // Practice 287
          return `<div class="hbl-row">${tasks.replace('data-drawer="1"', 'data-drawer="tasks"')}${status}${renderTalk()}</div>` + chips + (o.collapsed ? '' : cards);
        }
        return o.collapsed ? chips + `<button type="button" class="hbl-clip-open" data-pane-fold="1">📋 Clipboard · ${open} open - show</button>`
          : chips + `<div class="hbl-board">${renderList(snap, o.controls, o.needsControls, o.open)}</div>` + cards;
      })();
  }

  // Practice 285 (JD 22 Nov: "the clipboard just sort of dangling below HB live ... modernise it" and the team bar "seems a bit out of
  // place ... make it more functional"): the task list is a drawer on the right; the team bar is one row of talk-to buttons.
  function renderDrawer(snap, opts) {
    const o = opts || {};
    return '<div class="hbl-drawer-head"><b>📋 Tasks</b><button type="button" class="hbl-mini" data-drawer="1" title="Close">✕</button></div>' +
      renderList(snap, o.controls, o.needsControls, o.open);
  }
  // Practice 287 (JD 22 Nov: "the live status dropdown is hideously designed and completely unusable ... the context of that section is also
  // quite fucked"): a clean Status drawer - APEX, its window, GPU/CPU mode and the model switches (chat.js handles [data-hb-models] clicks).
  // Practice 290 (JD 22 Nov): downloads and background work, and which network is in use, in the Status drawer
  function renderExtra(x) {
    const e = x || {}, net = e.network || [], dl = e.downloads || [], bg = e.background || [];
    let html = '<div class="hbl-sub">Downloads &amp; background</div>';
    if (!dl.length && !bg.length) html += '<div class="hbl-note hbl-dim">Nothing downloading or running in the background.</div>';
    dl.forEach((d) => { html += `<div class="hbl-note">⇩ <b>${esc(d.what)}</b> · ${esc(d.state)}${d.now ? '<div class="hbl-dim">' + esc(d.now) + '</div>' : ''}` +
      (d.error ? `<div class="hbl-warn">${esc(d.error)}</div>` : '') + '</div>'; });
    bg.forEach((b) => { html += `<div class="hbl-note">⚙ <b>${esc(b.who)}</b>${b.model ? ' · ' + esc(b.model) : ''} · ${esc(b.task)}${b.now ? '<div class="hbl-dim">' + esc(b.now) + '</div>' : ''}</div>`; });
    html += '<div class="hbl-sub">Network</div>';
    if (!net.length) html += '<div class="hbl-note hbl-dim">No connection is up.</div>';
    net.forEach((n) => { html += `<div class="hbl-note">${n.in_use ? '<b style="color:#2ecc71">● in use</b>' : n.backup ? '<span class="hbl-dim">○ backup</span>' : '<span class="hbl-dim">○</span>'} ` +
      `<b>${esc(n.name)}</b> <span class="hbl-dim">· ${esc(n.kind || '')}${n.mobile ? ' · mobile data' : ''} · ${esc(n.device)}</span></div>`; });
    return html;
  }
  function renderStatus(snap, modelsHtml) {
    const a = snap.apex_live || {}, c = (snap.telemetry || {}).cpu || {};
    const n = (x) => Number(x || 0).toLocaleString('en-AU');
    return '<div class="hbl-drawer-head"><b>⚙ Status</b><button type="button" class="hbl-mini" data-drawer="status" title="Close">✕</button></div>' +
      '<div class="hbl-sub">APEX</div>' +
      `<div class="hbl-note">${a.up ? '' : '⚠ model server not answering · '}<b>${esc(a.model || 'unknown model')}</b>${a.device ? ' · ' + esc(a.device) : ''}` +
      `${a.ctx ? ' · window ' + n(a.ctx) + ' tokens' : ''}${a.busy ? ' · working' : ' · idle'}</div>` +
      '<div class="hbl-sub">Power</div>' + `<div class="hbl-note">${renderPower(snap)}${c.governor ? ' <span class="hbl-dim">CPU ' + esc(cpuMode(c)) + '</span>' : ''}</div>` +
      renderExtra(snap.status_extra) +
      '<div class="hbl-sub">Models (Auto = HB decides · On = preferred · Off = never)</div>' +
      `<div class="chat-live-stack hb-models" data-hb-models>${modelsHtml || '<small>Loading the models…</small>'}</div>`;
  }
  const TALK = [['apex', 'APEX'], ['fred', 'Fred'], ['claude', 'Claude'], ['codex', 'Codex'], ['git', 'Copilot'], ['gemini', 'Gemini']];
  function renderTalk() {
    return '<span class="hbl-talk"><span class="hbl-dim">Talk to</span>' + TALK.map(([at, name]) =>
      `<button type="button" class="hbl-doer" data-at="${at}" title="Start your message with @${at}">${name}</button>`).join('') + '</span>';
  }

  // Practice 280 (JD 22 Nov: "a tag at the end that says 'powersave' and doesn't tell me anything"): 'powersave' is the CPU governor's
  // name; with the amd-pstate-epp driver the CPU still boosts on demand and the energy preference says how eagerly. Shown in words.
  const EPP = { performance: 'full speed', balance_performance: 'balanced', default: 'balanced', balance_power: 'saving power', power: 'saving power' };
  function cpuMode(c) { return c.epp ? (EPP[c.epp] || c.epp.replace(/_/g, ' ')) : c.governor; }
  function renderPower(snap) {
    const g = (snap.telemetry || {}).gpu || {};
    if (g.clock_limit_mhz == null && !g.gpu_mode) return '';
    const now = g.gpu_mode || 'stock';
    const b = (id, label, tip, risky) => now === id ? `<b class="hbl-doer hbl-doer-on" title="${esc(tip)}">${label}</b>`
      : `<button type="button" class="hbl-doer" data-q="gpu" data-a="${id}" data-id="gpu"${risky ? ' data-confirm="1"' : ''} title="${esc(tip)}">${label}</button>`;
    return '<span class="hbl-doers">GPU: ' + b('stock', 'Auto (stock)', 'Driver defaults: the card picks its own clocks, stock power limit, fans auto') + ' ' +
      b('jd_tested', 'Overclock', "Your tested profile: 2600 MHz core, 1075 MHz memory, 249 W. HB reverts it by itself if the card runs too hot. Click twice to confirm.", true) + '</span>';
  }

  function systemLine(snap) {
    const t = snap.telemetry || {}, g = t.gpu || {}, c = t.cpu || {};
    const free = g.vram_total_gb != null && g.vram_used_gb != null ? (g.vram_total_gb - g.vram_used_gb).toFixed(1) + ' GB free for you' : '';
    return [g.busy_pct != null ? 'GPU ' + Math.round(g.busy_pct) + '%' : '', free, g.temp_c != null ? Math.round(g.temp_c) + '°C' : '',
      g.clock_mhz != null ? g.clock_mhz + ' MHz' : '',
      g.clock_limit_mhz != null ? 'limit ' + g.clock_limit_mhz + ' MHz' : '',
      c.load1 != null ? 'CPU load ' + c.load1 : '',
      c.clock_mhz != null ? 'CPU0 ' + Math.round(c.clock_mhz) + ' MHz' : '',
      c.governor ? 'CPU ' + cpuMode(c) : ''].filter(Boolean).join(' · ');
  }

  function renderNeedsPopup(n, needsControls) {
    return `<div class="hbl-pop-head">⚑ Needs you</div><div class="hbl-pop-title">${esc(n.label || '')}</div>` +
      (n.title && n.title !== n.label ? `<div class="hbl-dim">${esc(n.title)}</div>` : '') +
      (n.why ? `<div class="hbl-pop-why">${esc(String(n.why).slice(0, 400))}</div>` : '') +
      (needsControls ? needsControls(n) : '') + '<div class="hbl-said hbl-dim" role="status"></div><div class="hbl-ctl"><button type="button" data-later="1">Later</button></div>';
  }

  // Practice 276 (JD 22 Nov: "in the task list, I can't reassign tasks to different actors, it shows a really ugly dropdown with some
  // names in it, not sure why it's showing actors that aren't even available, and also does nothing when I click on any of them"): one
  // button per doer HB can really run now (snapshot.doers: APEX, and Fred unless he is switched off); the current one is lit. A doer set
  // earlier that HB cannot run (e.g. Claude Code's plan rows) shows as a plain tag. Buttons, so the 2 s redraw cannot swallow the click.
  const DOER_NAMES = { apex: 'APEX', fred: 'Fred', claude: 'Claude Code', codex: 'Codex', copilot: 'Copilot', gemini: 'Gemini', hb: 'HB', small: 'small model' };
  function renderDoers(i, doers) {
    if (!i || !i.step_id) return '';
    const now = i.doer || 'apex', ok = (doers || [{ id: 'apex', name: 'APEX', ok: true }]).filter((d) => d.ok);
    let html = '<span class="hbl-doers">Doer:';
    if (!ok.some((d) => d.id === now)) html += ` <span class="hbl-tag" title="Set earlier; HB cannot run this doer from the list">${esc(DOER_NAMES[now] || now)}</span>`;
    html += ok.map((d) => d.id === now
      ? ` <b class="hbl-doer hbl-doer-on" title="${esc(d.why || '')}">${esc(d.name)}</b>`
      : ` <button type="button" class="hbl-doer" data-q="clip" data-a="doer" data-id="${esc(i.step_id)}" data-v="${esc(d.id)}" title="${esc(d.why || '')}">${esc(d.name)}${d.note ? ' (' + esc(d.note) + ')' : (d.off ? ' (off)' : '')}</button>`).join('');   // Practice 278
    // Practice 277: a doer that cannot work right now is not offered, but the list says why (e.g. Fred is switched Off in Live status)
    html += (doers || []).filter((d) => !d.ok && d.why).map((d) => ` <span class="hbl-dim">· ${esc(d.why)}</span>`).join('');
    return html + '</span>';
  }

  // Practice 275: a risky button (Cancel, /cancel, /reject, /stop) arms on the first click and acts on the second within ARM_MS.
  const ARM_MS = 4000;
  function arm(state, key, now) {
    if (state && state.key === key && now <= state.until) return { act: true, armed: null };
    return { act: false, armed: { key, until: now + ARM_MS } };
  }

  const R = { renderStrip, renderLane, renderMaster, renderSystem, renderTrail, renderActive, renderList, renderBoard, renderNeedsPopup,
    primaryFor, systemLine, renderPower, renderDrawer, renderStatus, renderExtra, renderTalk, renderMeter, renderLights, renderDoers, arm, took, esc, ICON, SHORT };
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
.hbl-clip-open{display:block;margin:4px 0;padding:4px 10px;background:none;border:1px solid #2ecc71;border-radius:4px;color:inherit;font:inherit;cursor:pointer}
#hb-live-pane{flex:0 0 auto;max-height:60vh;min-height:34px;overflow:auto;padding:4px 10px 6px;border-bottom:2px solid var(--border,#333);
  background:var(--card,#161616);color:var(--text,#ddd);font-size:12.5px}
.hbl-meter{position:sticky;top:-4px;z-index:2;margin:-4px -10px 4px;padding:5px 10px;background:var(--bg,#111);border-bottom:1px solid var(--border,#333);font-size:12.5px}
.hbl-meter-busy{border-bottom:2px solid #2ecc71}.hbl-meter-down{color:#ff5252}
.hbl-bar-in{display:inline-block;width:90px;height:7px;vertical-align:middle;border-radius:4px;background:var(--border,#333);overflow:hidden}.hbl-bar-in i{display:block;height:100%;background:#2ecc71}
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
.hbl-lights{display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin:3px 0;font-size:11px}
.hbl-lg{font-weight:700;font-size:10px;letter-spacing:.06em;color:var(--text-dim,#999);margin:0 1px 0 6px}
.hbl-light{display:inline-flex;align-items:center;gap:3px;min-width:16px;justify-content:center;padding:0 6px;border-radius:9px;
  border:1px solid var(--border,#444);color:var(--text-dim,#777);opacity:.5;cursor:help}
.hbl-light small{font-size:10px}
.hbl-l-on{opacity:1;color:#2ecc71;border-color:rgba(46,204,113,.7);background:rgba(46,204,113,.12)}
.hbl-l-live{opacity:1;color:#2ecc71;border-color:#2ecc71;animation:hblPulse 1.4s infinite}
.hbl-l-wait{opacity:1;color:#ffb300;border-color:#ffb300;animation:hblPulse 1.4s infinite}
.hbl-l-warn{opacity:1;color:#ffb300;border-color:rgba(255,179,0,.8);background:rgba(255,179,0,.12)}
.hbl-l-bad{opacity:1;color:#ff5252;border-color:#ff5252;background:rgba(255,82,82,.12)}
.hbl-meter .hbl-lights{margin:3px 0 0}
.hbl-armed{background:#c62828 !important;border-color:#ff5252 !important;color:#fff !important;font-weight:700;animation:hblPulse 1.4s infinite}
#hb-scroll-bottom{position:fixed;z-index:9100;width:44px;height:44px;border-radius:50%;border:1px solid var(--border,#444);cursor:pointer;
  background:var(--card,#1b1b1b);color:var(--text,#ddd);font-size:20px;line-height:1;box-shadow:0 6px 18px rgba(0,0,0,.45);opacity:.92}
#hb-scroll-bottom:hover{border-color:var(--accent,#00e08a);color:var(--accent,#00e08a)}
#hb-scroll-bottom.hb-follow{border-color:#2ecc71;color:#2ecc71;animation:hblPulse 1.4s infinite}
#hb-scroll-bottom[hidden]{display:none}
#hb-live-drawer .hb-models{max-height:none;overflow:visible;resize:none}
.hbl-drawer-grip{position:sticky;float:left;top:0;margin:-6px 0 0 -12px;width:6px;height:100%;min-height:100vh;cursor:ew-resize;border-radius:3px}
.hbl-drawer-grip:hover{background:rgba(46,204,113,.35)}
#hb-live-drawer{scrollbar-width:thin;scrollbar-color:var(--border,#444) transparent}
#hb-live-drawer{position:fixed;right:14px;top:70px;bottom:96px;width:min(460px,94vw);overflow:auto;z-index:9000;padding:6px 12px 10px;
  background:var(--card,#161616);color:var(--text,#ddd);border:1px solid var(--border,#333);border-radius:12px;box-shadow:0 14px 40px rgba(0,0,0,.55);font-size:12.5px}
.hbl-drawer-head{display:flex;justify-content:space-between;align-items:center;position:sticky;top:-6px;z-index:1;padding:6px 0;background:var(--card,#161616)}
.hbl-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:2px 0 4px}
.hbl-tasks-chip{font-size:12px;padding:3px 12px;border-radius:14px;border:1px solid var(--accent,#00e08a);background:transparent;color:var(--accent,#00e08a);cursor:pointer;font-weight:600}
.hbl-tasks-needs{border-color:#ffb300;color:#ffb300}
.hbl-talk{display:inline-flex;flex-wrap:wrap;align-items:center;gap:4px;margin-left:auto;font-size:11px}
body.hb-live-on .chat-team>.chat-team-people,body.hb-live-on .chat-team>.chat-support-team,body.hb-live-on .chat-team>.chat-live-board{display:none!important}
body.hb-live-on .chat-team{display:flex;justify-content:flex-end;padding:0 10px;margin:0;min-height:0;border:0;background:none;font-size:11px;opacity:.7}
.hbl-doers{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--text-dim,#999)}
.hbl-doer{font-size:11px;padding:2px 9px;border-radius:10px;border:1px solid var(--border,#444);background:var(--bg,#111);color:var(--text,#ddd);cursor:pointer}
.hbl-doer:hover{border-color:var(--accent,#00e08a)}.hbl-doer-on{border-color:#2ecc71;color:#2ecc71;background:rgba(46,204,113,.12);cursor:default}
body.hb-live-on #hb-now,body.hb-live-on #hb-live-activity,body.hb-live-on #hb-clipboard,body.hb-live-on #home-chat-main .hb-needs-you{display:none!important}
@media (max-width:640px){.hbl-line{max-width:110px}.hbl-cards{grid-template-columns:1fr}}`;
    document.head.appendChild(st);
  }

  function classic() { try { return localStorage.getItem('hbLive.classic') === '1'; } catch (e) { return false; } }
  function drawerEl() {         // Practice 285: the task list drawer on the right, over the chat
    let d = document.getElementById('hb-live-drawer');
    if (d) return d;
    try { d = document.createElement('aside'); d.id = 'hb-live-drawer'; d.hidden = true; d.setAttribute('aria-label', 'HB task list'); document.body.appendChild(d); return d; }
    catch (e) { return { hidden: true, innerHTML: '', scrollTop: 0, contains: () => false, querySelector: () => null, querySelectorAll: () => [] }; }
  }
  // Practice 290 (JD 22 Nov: "the new settings window is not resizable"): drag the drawer's left edge, like the main chat's grip
  if (typeof document !== 'undefined' && document.addEventListener) document.addEventListener('mousedown', (e) => {
    const grip = e.target && e.target.closest && e.target.closest('.hbl-drawer-grip');
    if (!grip) return;
    e.preventDefault();
    const dr = drawerEl(), startX = e.clientX, startW = dr.getBoundingClientRect().width;
    const move = (m) => { const w = Math.max(300, Math.min((root.innerWidth || 1600) - 40, startW + (startX - m.clientX))); dr.style.width = w + 'px'; ls('hbLive.drawerW', String(Math.round(w))); };
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });
  function insertAt(at) {        // Practice 285: talk-to buttons start the message with @name
    const input = document.getElementById('home-chat-input');
    if (!input) return;
    const rest = input.value.replace(/^@[\w-]+\s*/, '');
    input.value = '@' + at + ' ' + rest;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  }
  // Practice 287 (JD 22 Nov: "the round button that hovers in the main chat window at the bottom right corner when I scroll up to let me
  // instantly scroll back to the bottom ... if I double click it, it automatically stays tracking the bottom"): click = jump to the latest
  // message; double click = follow mode on/off (the button glows and the chat keeps to the bottom until you scroll up).
  function scrollButton() {
    const list = document.getElementById('home-chat-messages');
    if (!list || !document.body || !document.createElement || document.getElementById('hb-scroll-bottom')) return;
    const b = document.createElement('button');
    b.id = 'hb-scroll-bottom'; b.type = 'button'; b.textContent = '↓';
    b.title = 'Jump to the latest message · double-click: keep following the newest message';
    document.body.appendChild(b);
    S.follow = ls('hbLive.follow') === '1';
    const atBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 40;
    const toBottom = (smooth) => list.scrollTo({ top: list.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    const update = () => {
      const r = list.getBoundingClientRect();
      b.style.left = Math.round(r.right - 64) + 'px'; b.style.top = Math.round(r.bottom - 64) + 'px';
      b.hidden = !list.offsetParent || (atBottom() && !S.follow);
      b.classList.toggle('hb-follow', !!S.follow);
    };
    b.addEventListener('click', () => { toBottom(true); setTimeout(update, 400); });
    b.addEventListener('dblclick', () => { S.follow = !S.follow; ls('hbLive.follow', S.follow ? '1' : '0'); toBottom(false); update(); });
    list.addEventListener('scroll', update, { passive: true });
    list.addEventListener('wheel', (e) => { if (e.deltaY < 0 && S.follow) { S.follow = false; ls('hbLive.follow', '0'); update(); } }, { passive: true });
    if (root.MutationObserver) new MutationObserver(() => { if (S.follow) toBottom(false); update(); }).observe(list, { childList: true, subtree: true });
    root.addEventListener('resize', update);
    setInterval(update, 1000);
    update();
  }

  function pane() {
    try { scrollButton(); } catch (e) { /* no main chat on this page */ }
    if (classic()) { document.body.classList.remove('hb-live-on'); return null; }
    document.body.classList.add('hb-live-on');   // HB Live: hides the HB-now pill, live box, HB Driving board and Needs-you bar in main chat
    let el = document.getElementById('hb-live-pane');
    if (el) return el;
    const main = document.getElementById('home-chat-main'), bar = document.getElementById('home-chat-bar');
    if (!main) return null;
    el = document.createElement('section');
    el.id = 'hb-live-pane';
    el.setAttribute('aria-label', 'HB Live: who is working, and the list of open tasks');
    // Practice 209 (JD 21 Nov: "I hate that the ribbon needs me to manually grip and drag to open, it should be dynamic"): the pane sizes
    // itself to what is in it (up to 60% of the screen, then it scrolls); a height dragged earlier is forgotten.
    ls('hbLive.paneHeight', '');
    if (bar && bar.parentNode === main) bar.insertAdjacentElement('afterend', el); else main.prepend(el);
    // Chunk A: drag divider between Live pane and chat log
    const div = document.createElement('div');
    div.className = 'hb-live-divider';
    div.setAttribute('role', 'separator');
    div.setAttribute('aria-orientation', 'horizontal');
    div.addEventListener('mousedown', (e) => { e.preventDefault(); dragDivider(div, e); });
    div.addEventListener('touchstart', (e) => { dragDivider(div, e.touches[0]); });
    el.insertAdjacentElement('afterend', div);
    return el;
  }

  function render() {
    if (!S.snap) return;
    style();
    const el = pane();
    if (!el) return;
    const focus = document.activeElement;
    const dr = drawerEl();
    if (focus && focus.tagName === 'SELECT' && (el.contains(focus) || dr.contains(focus))) return;   // Practice 276: never redraw away an open dropdown
    const top = el.scrollTop, dtop = dr.scrollTop;
    const pick = (root) => (root && root.querySelectorAll ? Array.from(root.querySelectorAll('[data-more-box]:not([hidden])')) : []);
    const open = pick(el).concat(pick(dr)).map((b) => b.dataset.moreBox);
    const opts = { rate: S.rate, collapsed: ls('hbLive.collapsed') === '1', now: Date.now() / 1000, controls: S.controls,
      needsControls: S.needsControls, open: S.open, drawer: true };   // Practice 285: the list is in the drawer
    el.innerHTML = R.renderBoard(S.snap, opts);
    const mode = ls('hbLive.drawer') === '1' ? 'tasks' : ls('hbLive.drawer');   // Practice 287: 'tasks' or 'status'
    dr.hidden = mode !== 'tasks' && mode !== 'status';
    if (mode === 'status' && (!S.modelsAt || Date.now() - S.modelsAt > 20000) && typeof root.hbModelsLoad === 'function') {
      S.modelsAt = Date.now(); setTimeout(() => root.hbModelsLoad(dr), 0);
    }
    dr.innerHTML = dr.hidden ? '' : '<div class="hbl-drawer-grip" title="Drag to resize"></div>' +
      (mode === 'status' ? R.renderStatus(S.snap, root.hbModelsHtml) : R.renderDrawer(S.snap, opts));   // Practice 290: resizable
    const w = Number(ls('hbLive.drawerW'));
    if (dr.style && w >= 300) dr.style.width = Math.min(w, (root.innerWidth || 1600) - 40) + 'px';
    open.forEach((id) => { const sel = '[data-more-box="' + CSS.escape(id) + '"]'; const b = (el.querySelector && el.querySelector(sel)) || (dr.querySelector && dr.querySelector(sel)); if (b) b.hidden = false; });
    el.scrollTop = top; dr.scrollTop = dtop;
    popup();
    decorate();
    showArmed();                                         // Practice 275: an armed Cancel survives the redraw
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
        [5, 4, 3, 2, 1].map((n) => `<option value="${n}"${Number(i.importance) === n ? ' selected' : ''}>imp ${n}</option>`).join('') + '</select>' + R.renderDoers(i, (S.snap || {}).doers);   // Practice 276
    }
    return html + '</div>';
  }
  // Bound headers AND JSON, including stalled transports that do not reject on abort.
  function boundedRequest(start) {
    const controller = new AbortController();
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        const error = new Error('HB did not confirm within 15 seconds. Check current status before trying again.');
        error.name = 'TimeoutError';
        reject(error);
        controller.abort();
      }, 15000);
    });
    let response;
    try { response = start(controller.signal); } catch (error) { response = Promise.reject(error); }
    const result = Promise.resolve(response).then(async (r) => ({ ok: r.ok, data: await r.json() }));
    return Promise.race([result, deadline]).finally(() => clearTimeout(timer));
  }

  function send(body, win, url) {
    const note = win && win.querySelector('.hbl-said');
    const options = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    return boundedRequest((signal) => {
      const requestOptions = { ...options, signal };
      return url ? fetch(url, requestOptions) : fetch('/api/peer/v1/hb/queue', requestOptions);
    }).then(({ ok, data: d }) => {
      const said = d && (d.said || d.error || d.changed || d.response);
      if (note) note.textContent = said || (!ok || !d || !d.ok ? 'HB could not do that - try again.' : '');
      if (!ok || !d || d.ok !== true) return false;
      refresh();
      return true;
    }).catch((error) => {
      if (note) note.textContent = error.name === 'TimeoutError' ? error.message : 'HB did not answer - try again.';
      return false;
    });
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

  function runCommand(text, fill, win) {
    if (win && !fill) {
      const conversation = Number(ls('fridays-home-chat-active-thread'));
      if (!Number.isSafeInteger(conversation) || conversation <= 0) {
        const note = win.querySelector('.hbl-said');
        if (note) note.textContent = 'Open the main chat first, then try again.';
        return Promise.resolve(false);
      }
      // Owner commands are recorded and published by the same route as main chat.
      // The next snapshot closes the popup only once this pending item is resolved.
      return send({ message: text, conversation_id: conversation, local_only: true, new_thread: false, auto_relay: false }, win, '/api/chat');
    }
    const input = document.getElementById('home-chat-input');
    if (!input) return;
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    if (fill) { input.focus(); return; }
    document.getElementById('home-chat-send-btn')?.click();
  }
  // Practice 275 (JD 22 Nov: "when I open the task list and click on cancel it pops up a really fucked up confirmation box, the cancel
  // button itself should turn into a confirm button so I basically just have to double click on cancel"): no browser dialog. The first
  // click turns the button red - "Confirm cancel" - and the second within 4 s acts. The 2 s redraw keeps it armed (S.armed).
  function risky(b) { return !!(b.dataset.confirm || (b.dataset.cmd && /^\/(cancel|reject|stop)\b/.test(b.dataset.cmd))); }
  function armKey(b) { return b.dataset.q ? b.dataset.q + ':' + b.dataset.a + ':' + b.dataset.id : 'cmd:' + b.dataset.cmd; }
  function showArmed() {
    document.querySelectorAll('.hbl-armed').forEach((b) => {
      if (!S.armed || armKey(b) !== S.armed.key) { b.classList.remove('hbl-armed'); if (b.dataset.armText) b.textContent = b.dataset.armText; }
    });
    if (!S.armed || Date.now() > S.armed.until) { S.armed = null; return; }
    document.querySelectorAll(SCOPE.split(', ').map((s) => s + ' button[data-q], ' + s + ' button[data-cmd]').join(', ')).forEach((b) => {
      if (!risky(b) || armKey(b) !== S.armed.key || b.classList.contains('hbl-armed')) return;
      const text = b.textContent.trim();
      b.dataset.armText = b.textContent;
      b.textContent = 'Confirm ' + (text.startsWith('/') ? text : text.toLowerCase());
      b.classList.add('hbl-armed');
    });
  }
  function armedClick(b) {
    if (!risky(b)) return true;
    const step = R.arm(S.armed, armKey(b), Date.now());
    S.armed = step.armed;
    showArmed();
    clearTimeout(S.armTimer);
    if (S.armed) S.armTimer = setTimeout(() => { S.armed = null; showArmed(); }, ARM_MS + 50);
    return step.act;
  }
  const SCOPE = '#hb-live-pane, #hb-live-pop, #hb-live-drawer, #home-chat-messages';
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t.closest || !t.closest(SCOPE)) return;
    const pop = t.closest('#hb-live-pop');
    const q = t.closest('button[data-q]');
    if (q) {
      if (!armedClick(q)) return;                        // Practice 275: first click arms, second acts
      if (q.disabled) return;
      q.disabled = true;
      // A 200 response can still be a refusal; the snapshot decides whether this item is resolved.
      send({ [q.dataset.q]: q.dataset.v ? [q.dataset.a, q.dataset.id, q.dataset.v] : [q.dataset.a, q.dataset.id] },   // Practice 276: doer value
        t.closest('#hb-live-pane') || t.closest('#hb-live-drawer') || pop).finally(() => { q.disabled = false; });
      return;
    }
    const sw = t.closest('[data-switch]');
    if (sw) { send({ switch: sw.dataset.switch, on: sw.dataset.on === '1' }, t.closest('#hb-live-pane')); return; }
    const cmd = t.closest('[data-cmd]');
    if (cmd) {
      const c = cmd.dataset.cmd;
      if (!armedClick(cmd)) return;                      // Practice 275
      if (cmd.disabled) return;
      if (pop) {
        cmd.disabled = true;
        runCommand(c, false, pop).finally(() => { cmd.disabled = false; });
      } else runCommand(c);
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
    // Practice 209: the Tasks chip in the top bar opens the clipboard (unfolds the pane and scrolls to the list)
    if (t.closest('[data-win="master"]')) {
      ls('hbLive.drawer', 'tasks');   // Practice 285: the Tasks chip opens the drawer
      ls('hbLive.collapsed', '0'); render();
      const list = document.querySelector('#hb-live-pane .hbl-board');
      if (list) list.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const fold = t.closest('[data-fold]');
    if (fold) { S.open[fold.dataset.fold] = !S.open[fold.dataset.fold]; render(); return; }
    const drw = t.closest('[data-drawer]');   // Practice 285/287: one drawer, Tasks or Status
    if (t.closest('.hbl-drawer-grip')) return;   // Practice 290: the grip drags, it does not close
    if (drw) { const want = drw.dataset.drawer === 'status' ? 'status' : 'tasks', now = ls('hbLive.drawer') === '1' ? 'tasks' : ls('hbLive.drawer');
      ls('hbLive.drawer', now === want ? '0' : want); render(); return; }
    const at = t.closest('[data-at]');
    if (at) { insertAt(at.dataset.at); return; }
    if (t.closest('[data-pane-fold]')) { ls('hbLive.collapsed', ls('hbLive.collapsed') === '1' ? '0' : '1'); render(); return; }
    if (t.closest('[data-needs-open]')) { ls('hbLive.needsSeen', '[]'); popup(); return; }
    const chip = t.closest('[data-card]');
    if (chip) { const c = document.querySelector(`[data-card-body="${chip.dataset.card}"]`); if (c) c.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });
  document.addEventListener('change', (e) => {
    const s = e.target.closest && e.target.closest('#hb-live-pane select[data-q], #hb-live-pop select[data-q], #hb-live-drawer select[data-q]');
    if (s) send({ [s.dataset.q]: [s.dataset.a, s.dataset.id, s.value] }, e.target.closest('#hb-live-pane') || e.target.closest('#hb-live-drawer'));
  });

  let pending = null;
  function refresh() {
    if (document.hidden || S.busy || classic()) return;
    S.busy = true;
    boundedRequest((signal) => fetch('/api/peer/v1/hb/live', { credentials: 'same-origin', signal })).then(({ ok, data: d }) => {
      if (!ok || !d || !d.ok) return;
      // Practice 200: HB restarted (new code) - reload this page once, unless JD is typing
      if (S.started && d.started && d.started !== S.started) {
        const input = document.getElementById('home-chat-input');
        if (!input || !input.value.trim()) { location.reload(); return; }
      }
      S.started = d.started || S.started;
      const a = d.apex_live || {}, p = (S.snap || {}).apex_live || {}, dt = (d.at || 0) - ((S.snap || {}).at || 0);
      S.rate = a.busy && p.busy && a.task === p.task && dt > 0 ? (a.generated > p.generated ? (a.generated - p.generated) / dt
        : (a.prompt_done > p.prompt_done ? (a.prompt_done - p.prompt_done) / dt : S.rate)) : 0;
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
