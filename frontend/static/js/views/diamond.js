/* ──────────────────────────────────────────────────────────────────────────────
   diamond.js — Sundial Pulse + Attention Dots + Tile Context Menu

   The sundial replaces the old System Pulse section — a radial gauge in the
   header with "Fridays" at its centre, colour-coded by overall health. Each
   gauge node grows / glows based on its metric.
   ────────────────────────────────────────────────────────────────────────── */

/* ── Sundial SVG Icons (16×16, stroke currentColor — theme-aware) ─────────── */

const SUNDIAL_ICONS = {
  cpu:    '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="4.5" y="4.5" width="7" height="7" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M6.5 4.5v-2m3 2v-2m-3 11v-2m3 2v-2M4.5 6.5h-2m2 3h-2m11-3h-2m2 3h-2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  ram:    '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="2" y="5" width="12" height="6" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M5 5V3.5M8 5V3.5M11 5V3.5M4.5 7.5v1m3.5-1v1m3.5-1v1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  swap:   '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3" y="4" width="10" height="3" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="3" y="9" width="10" height="3" rx=".8" stroke="currentColor" stroke-width="1.3"/><path d="M11.5 7l1 1-1 1M4.5 7l-1 1 1 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  gpu:    '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="2.5" y="4" width="11" height="7" rx="1.2" stroke="currentColor" stroke-width="1.3"/><path d="M5 11v1.5m6-1.5v1.5M5.5 7h2m1 0h2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="8" cy="7.5" r=".6" fill="currentColor"/></svg>',
  temp:   '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 2.5v7.2a2.3 2.3 0 1 0 0 3.6V2.5a1.2 1.2 0 0 0-2.4 0" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M10.2 4.5h1.5m-1.5 2h1.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  disk:   '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="2.5" y="4" width="11" height="8" rx="1.2" stroke="currentColor" stroke-width="1.3"/><path d="M2.5 9h11" stroke="currentColor" stroke-width="1.3"/><circle cx="11" cy="6.5" r=".6" fill="currentColor"/><circle cx="11" cy="10.5" r=".6" fill="currentColor"/></svg>',
  agents: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="4" y="5" width="8" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M8 3v2M6 8h0M10 8h0M6.2 10.1h3.6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  gov:    '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 2.5l5 2.5v3c0 3-2.2 5-5 6-2.8-1-5-3-5-6v-3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6.5 8l1 1 2.5-2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/* ── Sundial Configuration ────────────────────────────────────────────────── */

const SUNDIAL_METRICS = [
  { key: 'cpu',    label: 'CPU',     tip: 'Processor load — how busy the CPU is right now' },
  { key: 'ram',    label: 'RAM',     tip: 'Memory usage — allocated system memory' },
  { key: 'swap',   label: 'V-RAM',   tip: 'Virtual RAM — 48 GB SSD swap for bigger models' },
  { key: 'gpu',    label: 'GPU',     tip: 'GPU VRAM — dedicated graphics memory for models' },
  { key: 'temp',   label: 'Temp',    tip: 'CPU temperature — thermal sensor reading' },
  { key: 'disk',   label: 'Disk',    tip: 'Primary disk utilisation — storage capacity' },
  { key: 'agents', label: 'Members', tip: 'Active swarm members — enabled agents in roster' },
  { key: 'gov',    label: 'Gov',     tip: 'Governance — ALM pipeline enforcement via Vortex' },
];

function _escapeDiamondHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _sundialResidencyHtml(metricKey) {
  const system = window.__fridaysDiamondPulse?.system || {};
  const residency = system.agent_residency || {};
  const bucket = metricKey === 'ram' ? 'ram' : metricKey === 'swap' ? 'swap' : metricKey === 'gpu' ? 'gpu' : '';
  if (!bucket) return '';
  const entries = Array.isArray(residency[bucket]) ? residency[bucket] : [];
  const title = bucket === 'ram' ? 'Loaded in RAM' : bucket === 'swap' ? 'Loaded in V-RAM' : 'Loaded on GPU';
  if (!entries.length) {
    return '<div class="stip-section"><div class="stip-section-title">' + title + '</div><div class="stip-empty">No resident agents reported.</div></div>';
  }
  return '<div class="stip-section"><div class="stip-section-title">' + title + '</div><div class="stip-list">' + entries.map(entry => {
    const modelBits = [];
    if (entry.model) modelBits.push(_escapeDiamondHtml(entry.model));
    if (bucket === 'gpu' && entry.size_vram_gb) modelBits.push(_escapeDiamondHtml(entry.size_vram_gb + ' GB VRAM'));
    else if (entry.size_gb) modelBits.push(_escapeDiamondHtml(entry.size_gb + ' GB'));
    // M11: per-loaded-model unload button
    const unloadBtn = entry.model
      ? '<button class="stip-unload-btn" data-model="' + _escapeDiamondHtml(entry.model) + '" title="Unload ' + _escapeDiamondHtml(entry.model) + '" style="margin-left:6px;background:transparent;border:1px solid #f7b84b66;color:#f7b84b;border-radius:3px;padding:1px 6px;cursor:pointer;font-size:9px;">Unload</button>'
      : '';
    return '<div class="stip-list-row"><span class="stip-list-label">' + _escapeDiamondHtml(entry.label || entry.agent || 'Agent') + '</span><span class="stip-list-meta">' + modelBits.join(' · ') + unloadBtn + '</span></div>';
  }).join('') + '</div></div>';
}

/* ── Sundial Initialisation ───────────────────────────────────────────────── */

function _initSundial() {
  const wrap = document.getElementById('sundial');
  if (!wrap) return;
  const svg = document.getElementById('sundial-rays');
  const count = SUNDIAL_METRICS.length;
  // Y.58c — dial bumped to 150x150 so 8 metrics sit on a 58px ring without
  // overlapping each other or the centre title. Keep cx/cy in sync with
  // the CSS #sundial width/height.
  const cx = 75, cy = 75, radius = 58;

  if (svg) {
    // Outer dial ring
    const ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    ring.setAttribute('cx', cx);  ring.setAttribute('cy', cy);  ring.setAttribute('r', radius);
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', 'var(--border)');
    ring.setAttribute('stroke-width', '0.5');
    ring.setAttribute('opacity', '0.25');
    svg.appendChild(ring);

    // Centre backdrop so text is readable
    const bd = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    bd.setAttribute('cx', cx);  bd.setAttribute('cy', cy);  bd.setAttribute('r', '28');
    bd.setAttribute('fill', 'var(--card)');
    bd.setAttribute('opacity', '0.6');
    svg.appendChild(bd);
  }

  SUNDIAL_METRICS.forEach((m, i) => {
    const angle = (-90 + i * (360 / count)) * Math.PI / 180;
    const nx = cx + radius * Math.cos(angle);
    const ny = cy + radius * Math.sin(angle);

    // Ray from centre disc edge to dot edge (Y.58d — was going through both,
    // which made the dial look tangled / 'el-fucked'). Backdrop disc r=28,
    // dot half-width ≈11 ⇒ leave a clean line between them.
    if (svg) {
      const RAY_INNER = 30;                 // just outside centre backdrop
      const RAY_OUTER = radius - 12;        // just inside the dot
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', cx + RAY_INNER * Math.cos(angle));
      line.setAttribute('y1', cy + RAY_INNER * Math.sin(angle));
      line.setAttribute('x2', cx + RAY_OUTER * Math.cos(angle));
      line.setAttribute('y2', cy + RAY_OUTER * Math.sin(angle));
      line.classList.add('sundial-ray');
      line.dataset.metric = m.key;
      svg.appendChild(line);
    }

    // Node element
    const node = document.createElement('div');
    node.className = 'sundial-node';
    node.dataset.metric = m.key;
    node.dataset.health = 'ok';
    node.innerHTML = '<span class="sundial-dot">' + (SUNDIAL_ICONS[m.key] || '') + '</span><span class="sundial-val">\u2014</span>';
    node.style.left = nx + 'px';
    node.style.top  = ny + 'px';
    node.addEventListener('mouseenter', () => _showSundialTip(m, node));
    node.addEventListener('mouseleave', _hideSundialTip);
    wrap.appendChild(node);
  });

  // Click centre to refresh
  const center = document.getElementById('sundial-center');
  if (center) {
    center.style.cursor = 'pointer';
    center.addEventListener('click', () => {
      loadSystemPulse();
      center.classList.add('sundial-refreshing');
      setTimeout(() => center.classList.remove('sundial-refreshing'), 600);
    });
  }
}

/* ── Sundial Tooltip ──────────────────────────────────────────────────────── */

function _showSundialTip(metric, node) {
  let tip = document.getElementById('sundial-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'sundial-tip';
    tip.className = 'sundial-tooltip';
    document.body.appendChild(tip);
    // Y.58d — keep the tip open while the cursor is anywhere inside it OR
    // travelling between node and tip. The previous version used a fixed
    // 180ms hide timer that the buttons (Auto / Boost / Unload) couldn't
    // out-race — the tip vanished before the click registered. Now any
    // mouseenter on the tip cancels the pending hide.
    tip.addEventListener('mouseenter', () => {
      tip._hover = true;
      if (tip._hideTimer) { clearTimeout(tip._hideTimer); tip._hideTimer = null; }
    });
    tip.addEventListener('mouseleave', () => {
      tip._hover = false;
      if (tip._hideTimer) clearTimeout(tip._hideTimer);
      tip._hideTimer = setTimeout(() => {
        tip.style.display = 'none';
        tip._hideTimer = null;
        if (tip._statusPoll) { clearInterval(tip._statusPoll); tip._statusPoll = null; }
      }, 120);
    });
    tip.addEventListener('click', async (e) => {
      const fanBtn = e.target.closest('.stip-fan-btn');
      if (fanBtn) {
        e.preventDefault();
        e.stopPropagation();
        const mode = fanBtn.dataset.mode || 'auto';
        const status = tip.querySelector('.stip-fan-status');
        if (status) status.textContent = (mode === 'boost' ? 'boosting…' : 'auto…');
        try {
          const r = await fetch('/api/fan/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode }),
          });
          const j = await r.json().catch(() => ({}));
          if (status) {
            if (r.ok && j.ok !== false) {
              status.textContent = (mode === 'boost' ? 'boost on' : 'auto on');
              status.style.color = '#5cb85c';
            } else {
              status.textContent = (j.error || 'fanctl not installed');
              status.style.color = '#d9534f';
            }
          }
          // Y.58f-2 — once boost is on, poll real status every 2s so the
          // user sees CPU temp dropping toward the 50°C exit target. The
          // helper auto-reverts to 'auto' once it hits the floor.
          if (tip._statusPoll) { clearInterval(tip._statusPoll); tip._statusPoll = null; }
          if (status && r.ok && j.ok !== false) {
            const exitT = 50;
            const tick = async () => {
              try {
                const sr = await fetch('/api/fan/status');
                const sj = await sr.json().catch(() => ({}));
                const hs = (sj && sj.helper_state) || {};
                const cur = hs.mode || sj.mode;
                const cpuC = (typeof hs.cpu_peak_c === 'number') ? hs.cpu_peak_c
                           : (typeof sj.cpu_c === 'number' ? sj.cpu_c : null);
                if (cur === 'boost') {
                  const cpuTxt = cpuC != null ? `${Math.round(cpuC)}°C → ${exitT}°C` : 'cooling…';
                  status.textContent = `boost · ${cpuTxt}`;
                  status.style.color = '#f7b84b';
                } else {
                  status.textContent = `auto · ${cpuC != null ? Math.round(cpuC)+'°C' : 'on'}`;
                  status.style.color = '#5cb85c';
                  if (tip._statusPoll) { clearInterval(tip._statusPoll); tip._statusPoll = null; }
                }
              } catch (_) { /* keep last text */ }
            };
            tick();
            tip._statusPoll = setInterval(tick, 2000);
          }
        } catch (_) {
          if (status) { status.textContent = 'unreachable'; status.style.color = '#d9534f'; }
        }
        return;
      }
      const btn = e.target.closest('.stip-unload-btn');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      const model = btn.dataset.model;
      if (!model) return;
      btn.textContent = '…';
      btn.disabled = true;
      try {
        const r = await fetch('/api/ollama/unload', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ model }) });
        const j = await r.json();
        btn.textContent = j.ok ? '✓' : '✕';
      } catch (err) {
        btn.textContent = '✕';
      }
    });
  }
  const valEl  = node.querySelector('.sundial-val');
  const health = node.dataset.health;
  const hLabel = health === 'crit' ? 'Critical' : health === 'warn' ? 'Warning' : 'Normal';
  const hClass = 'stip-h-' + health;
  const iconSvg = SUNDIAL_ICONS[metric.key] || '';
  // Y.58 — temperature node: surface fan-boost controls in the tooltip so the
  // user can spin the DELL fan up to bring temps back to ~50°C without
  // hunting for the Monitor tile.
  const fanBoostHtml = (metric.key === 'temp')
    ? '<div class="stip-fanboost" style="margin-top:6px;display:flex;gap:4px;align-items:center;flex-wrap:wrap;">'
      + '<span style="font-size:9px;color:var(--text-dim);">Fan:</span>'
      + '<button class="stip-fan-btn" data-mode="auto" style="font-size:9px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--text-dim);cursor:pointer;">Auto</button>'
      + '<button class="stip-fan-btn" data-mode="boost" style="font-size:9px;padding:2px 8px;border-radius:4px;border:1px solid #f7b84b66;background:rgba(247,184,75,0.08);color:#f7b84b;cursor:pointer;font-weight:700;">Boost · target 50°C</button>'
      + '<span class="stip-fan-status" style="font-size:9px;color:var(--text-dim);margin-left:auto;"></span>'
      + '</div>'
    : '';
  tip.innerHTML =
    '<div class="stip-header"><span class="stip-icon">' + iconSvg + '</span> ' + metric.label + '</div>' +
    '<div class="stip-desc">' + metric.tip + '</div>' +
    '<div class="stip-val">' + (valEl ? valEl.textContent : '\u2014') + '</div>' +
    '<div class="stip-health ' + hClass + '"><span class="stip-dot"></span> ' + hLabel + '</div>' +
    fanBoostHtml +
    _sundialResidencyHtml(metric.key);
  tip.style.display = 'block';

  const rect = node.getBoundingClientRect();
  const tipW = tip.offsetWidth || 160;
  const tipH = tip.offsetHeight || 80;
  let left = Math.max(8, rect.left + rect.width / 2 - tipW / 2);
  // Y.58d — overlap the tip with the node by 4px so the cursor never crosses
  // a dead zone on its way to the Auto / Boost / Unload buttons. Was -8px gap.
  let top  = rect.top - tipH + 4;
  if (top < 8) top = rect.bottom - 4;                       // flip below if off-screen
  if (left + tipW > window.innerWidth - 8) left = window.innerWidth - tipW - 8;
  tip.style.left = left + 'px';
  tip.style.top  = top  + 'px';
}

function _hideSundialTip() {
  const tip = document.getElementById('sundial-tip');
  if (!tip) return;
  // Y.58d — track the timer so tip mouseenter can cancel it. Grace bumped
  // to 320ms so a slow cursor traversing the 4px overlap zone between the
  // node and the tip can land on Auto / Boost / Unload buttons without the
  // tip vanishing mid-click.
  if (tip._hideTimer) clearTimeout(tip._hideTimer);
  tip._hideTimer = setTimeout(() => {
    if (!tip._hover) tip.style.display = 'none';
    tip._hideTimer = null;
  }, 320);
}

/* ── System Pulse Fetch ──────────────────────────────────────────────────── */

function loadSystemPulse() {
  fetch('/api/diamond/pulse')
    .then(r => r.json())
    .then(d => { if (d.ok) _updateSundial(d); })
    .catch(err => console.warn('[Diamond] pulse fetch:', err));
  loadAttentionDots();
  loadSevenVitals();
}

/* ── Sundial Update ──────────────────────────────────────────────────────── */

function _updateSundial(d) {
  window.__fridaysDiamondPulse = d || {};
  const s = d.system || {}, q = d.queue || {}, a = d.agents || {}, g = d.governance || {};
  const mainDisk = (s.disks && s.disks.length) ? s.disks[0] : {};

  const metrics = {
    cpu:    { display: s.cpu_percent != null ? s.cpu_percent + '%' : '\u2014',      health: _healthLevel(s.cpu_percent, 60, 80) },
    ram:    { display: s.ram_percent != null ? s.ram_percent + '%' : '\u2014',      health: _healthLevel(s.ram_percent, 70, 85) },
    swap:   { display: s.swap_percent != null ? s.swap_percent + '%' : '\u2014',    health: _healthLevel(s.swap_percent, 60, 85) },
    gpu:    { display: s.gpu_vram_percent != null ? s.gpu_vram_percent + '%' : 'N/A', health: s.gpu_vram_percent != null ? _healthLevel(s.gpu_vram_percent, 70, 90) : 'ok' },
    temp:   { display: s.cpu_temp_c  != null ? s.cpu_temp_c + '°C' : '\u2014',     health: _healthLevel(s.cpu_temp_c, 65, 80) },
    disk:   { display: mainDisk.percent != null ? mainDisk.percent + '%' : '\u2014', health: _healthLevel(mainDisk.percent, 70, 90) },
    agents: { display: a.enabled     != null ? a.enabled + '/' + a.total : '\u2014', health: 'ok' },
    gov:    { display: g.alm_status || '\u2014',                                     health: g.alm_status === 'enforced' ? 'ok' : g.alm_status === 'standby' ? 'ok' : 'warn' },
  };

  for (const [key, m] of Object.entries(metrics)) {
    const node = document.querySelector('.sundial-node[data-metric="' + key + '"]');
    if (!node) continue;
    const valEl = node.querySelector('.sundial-val');
    if (valEl) valEl.textContent = m.display;
    node.dataset.health = m.health;

    const ray = document.querySelector('.sundial-ray[data-metric="' + key + '"]');
    if (ray) { ray.classList.remove('ray-ok','ray-warn','ray-crit'); ray.classList.add('ray-' + m.health); }
  }

  // Centre "Fridays" colour = worst metric
  const healths = Object.values(metrics).map(m => m.health);
  const worst = healths.includes('crit') ? 'crit' : healths.includes('warn') ? 'warn' : 'ok';
  const title = document.getElementById('sundial-title');
  if (title) title.dataset.health = worst;
}

function _healthLevel(val, warnAt, critAt) {
  if (val == null) return 'ok';
  if (val >= critAt) return 'crit';
  if (val >= warnAt) return 'warn';
  return 'ok';
}

/* ── Seven Vitals Overlay ────────────────────────────────────────────────── */
// Renders "S · Nc · Xk ep · Yk bel" beneath the sundial title with a heartbeat
// dot. Failure-quiet: if /api/seven endpoints are unreachable, leaves the
// overlay alone.
function loadSevenVitals() {
  Promise.all([
    fetch('/api/seven/heartbeat').then(r => r.json()).catch(() => null),
    fetch('/api/seven/memory').then(r => r.json()).catch(() => null),
  ]).then(([hb, mem]) => {
    if (!hb && !mem) return;
    let overlay = document.getElementById('sundial-seven-vitals');
    const titleHost = document.getElementById('sundial-title');
    if (!overlay && titleHost) {
      overlay = document.createElement('div');
      overlay.id = 'sundial-seven-vitals';
      overlay.style.cssText =
        'position:absolute;left:50%;transform:translateX(-50%);bottom:-22px;' +
        'font-size:9.5px;color:var(--text-dim);white-space:nowrap;letter-spacing:0.4px;' +
        'display:flex;align-items:center;gap:5px;pointer-events:none;';
      const host = titleHost.parentNode;
      if (host) {
        if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
        host.appendChild(overlay);
      }
    }
    if (!overlay) return;
    const alive = !!(hb && hb.alive);
    // hb.ts is epoch seconds of the last tick.
    const tickTs = hb && typeof hb.ts === 'number' ? hb.ts : null;
    const ageS = tickTs != null ? Math.max(0, (Date.now() / 1000) - tickTs) : null;
    let dotColor = '#888';
    if (alive && ageS != null && ageS < 300)       dotColor = '#3ad17a';
    else if (alive && ageS != null && ageS < 1800) dotColor = '#e8b13e';
    else if (alive)                                 dotColor = '#e88a3e';
    else                                            dotColor = '#e85a5a';
    const concepts = (mem && mem.concepts) || 0;
    const beliefs  = (mem && mem.beliefs)  || 0;
    const eps      = (mem && mem.episodes) || 0;
    const fmt = (n) => {
      if (n == null) return '0';
      if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
      return String(n);
    };
    const tickHint = (ageS != null) ? (' · ' + (ageS < 90 ? 'live' : ageS < 600 ? 'recent' : 'idle')) : '';
    overlay.innerHTML =
      '<span title="Seven heartbeat" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + dotColor + ';box-shadow:0 0 4px ' + dotColor + ';"></span>' +
      '<span title="Seven · concepts · episodes · beliefs">S · ' + concepts + 'c · ' + fmt(eps) + ' ep · ' + fmt(beliefs) + ' bel' + tickHint + '</span>';
  });
}

/* ── Attention Dots on Tiles ──────────────────────────────────────────────── */

function loadAttentionDots() {
  fetch('/api/diamond/attention')
    .then(r => r.json())
    .then(d => { if (d.ok) _renderAttentionDots(d.flags || {}); })
    .catch(err => console.warn('[Diamond] attention fetch:', err));
}

function _renderAttentionDots(flags) {
  document.querySelectorAll('.attn-dot').forEach(el => el.remove());
  for (const [key, flag] of Object.entries(flags)) {
    if (!flag || flag.level === 'none') continue;
    const card = document.querySelector('.home-card[data-win-id="' + key + '"]');
    if (!card) continue;
    if (getComputedStyle(card).position === 'static') card.style.position = 'relative';
    const dot = document.createElement('span');
    dot.className = 'attn-dot attn-dot-' + flag.level;
    dot.title = flag.label || '';
    if (flag.count > 0) dot.textContent = flag.count > 99 ? '99+' : String(flag.count);
    card.appendChild(dot);
  }
}

/* ── "+" Add New Tile ─────────────────────────────────────────────────────── */

function _initAddNewTile() {
  const tile = document.getElementById('add-new-tile');
  if (!tile) return;
  tile.addEventListener('click', () => {
    if (typeof openWindow === 'function') openWindow('studio', 'Studio', 'view-studio');
    setTimeout(() => {
      const btn = document.querySelector('#view-studio .proposal-new-btn, [onclick*="newProposal"]');
      if (btn) btn.click();
    }, 600);
  });
}

/* ── Tile Context Menu ───────────────────────────────────────────────────── */

function _initTileContextMenu() {
  const grid = document.getElementById('quick-cards');
  if (!grid) return;
  grid.addEventListener('contextmenu', (e) => {
    const card = e.target.closest('.home-card');
    if (!card || card.classList.contains('home-card-add')) return;
    e.preventDefault();
    _showTileContextMenu(e, card);
  });
  document.addEventListener('click', _closeTileContextMenu);
}

function _showTileContextMenu(e, card) {
  _closeTileContextMenu();
  const winId = card.dataset.winId;
  const label = card.querySelector('.card-title span:last-child');
  const title = label ? label.textContent : winId;

  const menu = document.createElement('div');
  menu.id = 'tile-context-menu';
  menu.className = 'tile-ctx';
  menu.innerHTML =
    '<div class="ctx-item" data-action="open" data-win-id="' + winId + '"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M2 4.5h12M2 4.5v8a1 1 0 001 1h10a1 1 0 001-1v-8M6 2.5h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Open <strong>' + title + '</strong></div>' +
    '<div class="ctx-sep"></div>' +
    '<div class="ctx-item ctx-danger" data-action="hide" data-win-id="' + winId + '"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M2 8s2.5-4.5 6-4.5S14 8 14 8s-2.5 4.5-6 4.5S2 8 2 8z" stroke="currentColor" stroke-width="1.3"/><line x1="3" y1="13" x2="13" y2="3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Hide tile</div>';

  menu.style.left = e.clientX + 'px';
  menu.style.top  = e.clientY + 'px';
  document.body.appendChild(menu);

  // Keep inside viewport
  requestAnimationFrame(() => {
    const r = menu.getBoundingClientRect();
    if (r.right  > window.innerWidth)  menu.style.left = (window.innerWidth  - r.width  - 8) + 'px';
    if (r.bottom > window.innerHeight) menu.style.top  = (window.innerHeight - r.height - 8) + 'px';
  });

  menu.addEventListener('click', (ev) => {
    const item = ev.target.closest('.ctx-item');
    if (!item) return;
    if (item.dataset.action === 'open') card.click();
    else if (item.dataset.action === 'hide') _hideTile(item.dataset.winId);
    _closeTileContextMenu();
  });
}

function _closeTileContextMenu() {
  const m = document.getElementById('tile-context-menu');
  if (m) m.remove();
}

function _showTileHoverTip(card) {
  if (!card || card.classList.contains('home-card-add')) return;
  let tip = document.getElementById('tile-hover-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'tile-hover-tip';
    tip.className = 'tile-hover-tip';
    document.body.appendChild(tip);
  }
  const title = card.dataset.winTitle || card.querySelector('.card-title span:last-child')?.textContent || 'Tile';
  const desc = card.querySelector('.card-desc')?.textContent || '';
  const shortcut = card.dataset.shortcut || '';
  tip.innerHTML =
    '<div class="tile-hover-tip-title">' + _escapeDiamondHtml(title) + '</div>' +
    (desc ? '<div class="tile-hover-tip-desc">' + _escapeDiamondHtml(desc) + '</div>' : '') +
    (shortcut ? '<div class="tile-hover-tip-shortcut">Shortcut · ' + _escapeDiamondHtml(shortcut) + '</div>' : '');
  tip.style.display = 'block';

  const rect = card.getBoundingClientRect();
  const tipW = tip.offsetWidth || 220;
  const tipH = tip.offsetHeight || 90;
  let left = rect.left + (rect.width / 2) - (tipW / 2);
  left = Math.max(8, Math.min(left, window.innerWidth - tipW - 8));
  let top = rect.top - tipH - 12;
  if (top < 8) top = rect.bottom + 12;
  tip.style.left = left + 'px';
  tip.style.top = top + 'px';
}

function _hideTileHoverTip() {
  const tip = document.getElementById('tile-hover-tip');
  if (tip) tip.style.display = 'none';
}

function _initTileHoverTips() {
  document.querySelectorAll('.home-card').forEach(card => {
    if (card.classList.contains('home-card-add')) return;
    card.addEventListener('mouseenter', () => _showTileHoverTip(card));
    card.addEventListener('focusin', () => _showTileHoverTip(card));
    card.addEventListener('mouseleave', _hideTileHoverTip);
    card.addEventListener('focusout', _hideTileHoverTip);
  });
}

/* ── Hidden Tiles ─────────────────────────────────────────────────────────── */

function _hideTile(winId) {
  // Keep core runtime tiles discoverable; users rely on these to reach
  // essential local tooling even when old localStorage state is present.
  if (winId === 'localai' || winId === 'media-center') {
    if (typeof showToast === 'function') showToast((winId === 'media-center' ? 'Media Center' : 'Local AI') + ' tile cannot be hidden.', 'info');
    return;
  }
  const card = document.querySelector('.home-card[data-win-id="' + winId + '"]');
  if (card) {
    card.style.transition = 'opacity 0.25s, transform 0.25s';
    card.style.opacity = '0';
    card.style.transform = 'scale(0.9)';
    setTimeout(() => { card.style.display = 'none'; }, 260);
  }
  const hidden = JSON.parse(localStorage.getItem('fridays_hidden_tiles') || '[]');
  if (!hidden.includes(winId)) hidden.push(winId);
  localStorage.setItem('fridays_hidden_tiles', JSON.stringify(hidden));
  _updateHiddenBadge();
}

function _showTile(winId) {
  const card = document.querySelector('.home-card[data-win-id="' + winId + '"]');
  if (card) {
    card.style.display = '';
    card.style.opacity = '0';
    card.style.transform = 'scale(0.9)';
    requestAnimationFrame(() => {
      card.style.transition = 'opacity 0.25s, transform 0.25s';
      card.style.opacity = '1';
      card.style.transform = 'scale(1)';
    });
  }
  const hidden = JSON.parse(localStorage.getItem('fridays_hidden_tiles') || '[]');
  const idx = hidden.indexOf(winId);
  if (idx > -1) hidden.splice(idx, 1);
  localStorage.setItem('fridays_hidden_tiles', JSON.stringify(hidden));
  _updateHiddenBadge();
  // Refresh hidden panel
  const panel = document.getElementById('hidden-tiles-panel');
  if (panel) { panel.remove(); if (hidden.length > 1) _toggleHiddenPanel(); }
}

function _applyHiddenTiles() {
  let hidden = JSON.parse(localStorage.getItem('fridays_hidden_tiles') || '[]');
  if (!Array.isArray(hidden)) hidden = [];

  // Backward compatibility + safety cleanup for stale values.
  hidden = hidden
    .map(id => id === 'ollama' ? 'localai' : id)
    .filter((id, idx, arr) => !!id && arr.indexOf(id) === idx)
    .filter(id => id !== 'localai' && id !== 'media-center');

  localStorage.setItem('fridays_hidden_tiles', JSON.stringify(hidden));

  hidden.forEach(winId => {
    const card = document.querySelector('.home-card[data-win-id="' + winId + '"]');
    if (card) card.style.display = 'none';
  });
  _updateHiddenBadge();
}

function _updateHiddenBadge() {
  const hidden = JSON.parse(localStorage.getItem('fridays_hidden_tiles') || '[]');
  const sectionTitle = document.querySelector('#quick-cards')?.previousElementSibling;
  if (!sectionTitle) return;
  let badge = sectionTitle.querySelector('.hidden-badge');
  if (hidden.length > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'hidden-badge';
      badge.title = 'Restore hidden tiles';
      badge.style.cssText = 'cursor:pointer;font-size:9px;font-weight:600;letter-spacing:0.03em;'
        + 'color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,transparent);'
        + 'border:1px solid color-mix(in srgb,var(--accent) 25%,transparent);'
        + 'border-radius:999px;padding:1px 8px;margin-left:6px;transition:background 0.15s;';
      sectionTitle.appendChild(badge);
    }
    badge.textContent = hidden.length + ' hidden ↩';
    badge.style.display = '';
  } else {
    if (badge) badge.style.display = 'none';
  }
}

function _initHiddenTilesRestore() {
  const sectionTitle = document.querySelector('#quick-cards')?.previousElementSibling;
  if (!sectionTitle) return;
  // Attach only to the badge so it doesn't conflict with the section collapse click
  sectionTitle.addEventListener('click', (e) => {
    if (e.target.closest('.hidden-badge')) {
      e.stopPropagation();
      _toggleHiddenPanel();
    }
  });
}

function _addTileHideButtons() {
  document.querySelectorAll('#quick-cards .home-card:not(.home-card-add)').forEach(card => {
    if (card.querySelector('.tile-hide-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'tile-hide-btn';
    btn.title = 'Hide tile';
    btn.innerHTML = '<svg viewBox="0 0 16 16" width="10" height="10" fill="none"><line x1="3" y1="13" x2="13" y2="3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><line x1="3" y1="3" x2="13" y2="13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
    btn.style.cssText = 'position:absolute;top:5px;right:5px;width:18px;height:18px;'
      + 'background:color-mix(in srgb,var(--border) 60%,transparent);border:none;border-radius:4px;'
      + 'cursor:pointer;display:flex;align-items:center;justify-content:center;'
      + 'opacity:0;transition:opacity 0.15s,background 0.15s;color:var(--text-dim);padding:0;z-index:2;';
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      _hideTile(card.dataset.winId);
    });
    card.style.position = 'relative';
    card.appendChild(btn);
    card.addEventListener('mouseenter', () => { btn.style.opacity = '1'; });
    card.addEventListener('mouseleave', () => { btn.style.opacity = '0'; });
  });
}

function _toggleHiddenPanel() {
  let panel = document.getElementById('hidden-tiles-panel');
  if (panel) { panel.remove(); return; }
  const hidden = JSON.parse(localStorage.getItem('fridays_hidden_tiles') || '[]');
  if (hidden.length === 0) return;

  panel = document.createElement('div');
  panel.id = 'hidden-tiles-panel';
  panel.className = 'hidden-panel';
  let html = '<div class="hidden-panel-title">Hidden Tiles</div>';
  hidden.forEach(winId => {
    const card = document.querySelector('.home-card[data-win-id="' + winId + '"]');
    const name = card ? (card.querySelector('.card-title span:last-child')?.textContent || winId) : winId;
    html += '<div class="hidden-panel-item"><span>' + name + '</span><button class="hidden-restore-btn" data-win-id="' + winId + '">Show</button></div>';
  });
  panel.innerHTML = html;
  panel.addEventListener('click', (e) => { const btn = e.target.closest('.hidden-restore-btn'); if (btn) _showTile(btn.dataset.winId); });

  const grid = document.getElementById('quick-cards');
  if (grid) grid.before(panel);
}

/* ── Home chat vertical resize ──────────────────────────────────────────────
   Y.59 — the chat section now exposes two direct edge handles
   (.home-chat-edge-top / .home-chat-edge-bottom) anchored to its outer
   edges. The legacy standalone #home-chat-resizer is still bound for
   back-compat but hidden in CSS. Both edges write to the same storage
   key so the size sticks regardless of which edge the user dragged.
   Top-edge drag DOWN shrinks the chat; bottom-edge drag DOWN grows it. */

function _initHomeChatResize() {
  const chat = document.querySelector('.home-chat-section');
  if (!chat) return;

  const STORAGE_KEY = 'fridays-home-chat-height';
  const MIN_H = 200;
  const maxH = () => Math.max(MIN_H, window.innerHeight - 140);

  const apply = (h) => {
    if (!h) {
      chat.style.minHeight = '';
      chat.style.maxHeight = '';
      return;
    }
    const clamped = Math.max(MIN_H, Math.min(maxH(), h));
    chat.style.minHeight = clamped + 'px';
    chat.style.maxHeight = clamped + 'px';
  };

  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    const h = parseInt(saved, 10);
    if (h >= MIN_H) apply(h);
  }

  const bindHandle = (handle, edge) => {
    if (!handle) return;
    // edge: 'top' | 'bottom'. Top edge: dragging up grows (delta inverted).
    const handleAbove = edge === 'top';

    const beginDrag = (clientY) => {
      const startY = clientY;
      const startH = chat.getBoundingClientRect().height;
      handle.classList.add('home-chat-edge-active');
      handle.classList.add('home-chat-resizer-active'); // legacy class

      const move = (y) => {
        const delta = y - startY;
        const targetH = handleAbove ? startH - delta : startH + delta;
        apply(targetH);
      };
      const end = () => {
        try {
          localStorage.setItem(STORAGE_KEY,
            String(chat.getBoundingClientRect().height));
        } catch (e) {}
        handle.classList.remove('home-chat-edge-active');
        handle.classList.remove('home-chat-resizer-active');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.removeEventListener('touchmove', onTouchMove);
        document.removeEventListener('touchend', onTouchEnd);
        document.body.style.userSelect = '';
      };
      const onMouseMove = (ev) => move(ev.clientY);
      const onMouseUp = () => end();
      const onTouchMove = (ev) => { if (ev.touches[0]) move(ev.touches[0].clientY); };
      const onTouchEnd = () => end();

      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
      document.addEventListener('touchmove', onTouchMove, { passive: true });
      document.addEventListener('touchend', onTouchEnd);
    };

    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      beginDrag(e.clientY);
    });
    handle.addEventListener('touchstart', (e) => {
      if (!e.touches[0]) return;
      beginDrag(e.touches[0].clientY);
    }, { passive: true });

    handle.addEventListener('dblclick', () => {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      apply(0);
    });

    handle.addEventListener('keydown', (e) => {
      const cur = chat.getBoundingClientRect().height;
      let next = cur;
      if (e.key === 'ArrowUp')        next = handleAbove ? cur + 24 : cur - 24;
      else if (e.key === 'ArrowDown') next = handleAbove ? cur - 24 : cur + 24;
      else if (e.key === 'PageUp')    next = handleAbove ? cur + 96 : cur - 96;
      else if (e.key === 'PageDown')  next = handleAbove ? cur - 96 : cur + 96;
      else if (e.key === 'Home') {
        e.preventDefault();
        try { localStorage.removeItem(STORAGE_KEY); } catch(_){}
        apply(0);
        return;
      } else return;
      e.preventDefault();
      apply(next);
      try {
        localStorage.setItem(STORAGE_KEY,
          String(chat.getBoundingClientRect().height));
      } catch (e) {}
    });
  };

  bindHandle(chat.querySelector('.home-chat-edge-top'), 'top');
  bindHandle(chat.querySelector('.home-chat-edge-bottom'), 'bottom');

  // Legacy standalone handle — hidden in CSS but bound for back-compat.
  // Treated as a 'bottom' handle (drag down = grow).
  const legacy = document.getElementById('home-chat-resizer');
  if (legacy && !legacy.classList.contains('home-chat-resizer-legacy-bound')) {
    legacy.classList.add('home-chat-resizer-legacy-bound');
    bindHandle(legacy, 'bottom');
  }
}

/* ── Init ─────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  _initSundial();
  _initAddNewTile();
  _initTileContextMenu();
  _initTileHoverTips();
  _applyHiddenTiles();
  _initHiddenTilesRestore();
  _addTileHideButtons();
  _initHomeChatResize();
});
