/* ──────────────────────────────────────────────────────────────────────────────
   diamond.js — Sundial Pulse + Attention Dots + Tile Context Menu

   The sundial replaces the old System Pulse section — a radial gauge in the
   header with "Fridays" at its centre, colour-coded by overall health. Each
   gauge node grows / glows based on its metric.
   ────────────────────────────────────────────────────────────────────────── */

/* ── Sundial Configuration ────────────────────────────────────────────────── */

const SUNDIAL_METRICS = [
  { key: 'cpu',    icon: '⚡', label: 'CPU',     tip: 'Processor load — how busy the CPU is right now' },
  { key: 'ram',    icon: '🧠', label: 'RAM',     tip: 'Memory usage — allocated system memory' },
  { key: 'temp',   icon: '🌡️', label: 'Temp',    tip: 'CPU temperature — thermal sensor reading' },
  { key: 'queue',  icon: '📥', label: 'Queue',   tip: 'Task queue depth — pending items for members' },
  { key: 'disk',   icon: '💾', label: 'Disk',    tip: 'Primary disk utilisation — storage capacity' },
  { key: 'agents', icon: '🤖', label: 'Members', tip: 'Active swarm members — enabled agents in roster' },
  { key: 'gov',    icon: '🛡️', label: 'Gov',     tip: 'Governance — ALM pipeline enforcement via Vortex' },
];

/* ── Sundial Initialisation ───────────────────────────────────────────────── */

function _initSundial() {
  const wrap = document.getElementById('sundial');
  if (!wrap) return;
  const svg = document.getElementById('sundial-rays');
  const count = SUNDIAL_METRICS.length;
  const cx = 60, cy = 60, radius = 44;

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
    bd.setAttribute('cx', cx);  bd.setAttribute('cy', cy);  bd.setAttribute('r', '22');
    bd.setAttribute('fill', 'var(--card)');
    bd.setAttribute('opacity', '0.6');
    svg.appendChild(bd);
  }

  SUNDIAL_METRICS.forEach((m, i) => {
    const angle = (-90 + i * (360 / count)) * Math.PI / 180;
    const nx = cx + radius * Math.cos(angle);
    const ny = cy + radius * Math.sin(angle);

    // Ray from centre to node
    if (svg) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', cx);  line.setAttribute('y1', cy);
      line.setAttribute('x2', nx);  line.setAttribute('y2', ny);
      line.classList.add('sundial-ray');
      line.dataset.metric = m.key;
      svg.appendChild(line);
    }

    // Node element
    const node = document.createElement('div');
    node.className = 'sundial-node';
    node.dataset.metric = m.key;
    node.dataset.health = 'ok';
    node.innerHTML = '<span class="sundial-dot">' + m.icon + '</span><span class="sundial-val">\u2014</span>';
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
  }
  const valEl  = node.querySelector('.sundial-val');
  const health = node.dataset.health;
  const hLabel = health === 'crit' ? '🔴 Critical' : health === 'warn' ? '🟡 Warning' : '🟢 Normal';
  tip.innerHTML =
    '<div class="stip-header">' + metric.icon + ' ' + metric.label + '</div>' +
    '<div class="stip-desc">' + metric.tip + '</div>' +
    '<div class="stip-val">' + (valEl ? valEl.textContent : '\u2014') + '</div>' +
    '<div class="stip-health">' + hLabel + '</div>';
  tip.style.display = 'block';

  const rect = node.getBoundingClientRect();
  const tipW = tip.offsetWidth || 160;
  const tipH = tip.offsetHeight || 80;
  let left = Math.max(8, rect.left + rect.width / 2 - tipW / 2);
  let top  = rect.top - tipH - 8;
  if (top < 8) top = rect.bottom + 8;                       // flip below if off-screen
  if (left + tipW > window.innerWidth - 8) left = window.innerWidth - tipW - 8;
  tip.style.left = left + 'px';
  tip.style.top  = top  + 'px';
}

function _hideSundialTip() {
  const tip = document.getElementById('sundial-tip');
  if (tip) tip.style.display = 'none';
}

/* ── System Pulse Fetch ──────────────────────────────────────────────────── */

function loadSystemPulse() {
  fetch('/api/diamond/pulse')
    .then(r => r.json())
    .then(d => { if (d.ok) _updateSundial(d); })
    .catch(err => console.warn('[Diamond] pulse fetch:', err));
  loadAttentionDots();
}

/* ── Sundial Update ──────────────────────────────────────────────────────── */

function _updateSundial(d) {
  const s = d.system || {}, q = d.queue || {}, a = d.agents || {}, g = d.governance || {};
  const mainDisk = (s.disks && s.disks.length) ? s.disks[0] : {};

  const metrics = {
    cpu:    { display: s.cpu_percent != null ? s.cpu_percent + '%' : '\u2014',      health: _healthLevel(s.cpu_percent, 60, 80) },
    ram:    { display: s.ram_percent != null ? s.ram_percent + '%' : '\u2014',      health: _healthLevel(s.ram_percent, 70, 85) },
    temp:   { display: s.cpu_temp_c  != null ? s.cpu_temp_c + '°C' : '\u2014',     health: _healthLevel(s.cpu_temp_c, 65, 80) },
    queue:  { display: q.depth       != null ? String(q.depth) : '\u2014',          health: q.depth > 10 ? 'crit' : q.depth > 3 ? 'warn' : 'ok' },
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
    if (typeof openWindow === 'function') openWindow('studio', '🎨 Studio', 'view-studio');
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
    '<div class="ctx-item" data-action="open" data-win-id="' + winId + '">📂 Open <strong>' + title + '</strong></div>' +
    '<div class="ctx-sep"></div>' +
    '<div class="ctx-item ctx-danger" data-action="hide" data-win-id="' + winId + '">🙈 Hide tile</div>';

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

/* ── Hidden Tiles ─────────────────────────────────────────────────────────── */

function _hideTile(winId) {
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
  const hidden = JSON.parse(localStorage.getItem('fridays_hidden_tiles') || '[]');
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
    if (!badge) { badge = document.createElement('span'); badge.className = 'hidden-badge'; sectionTitle.appendChild(badge); }
    badge.textContent = hidden.length + ' hidden — click to restore';
    badge.style.display = '';
    sectionTitle.style.cursor = 'pointer';
  } else {
    if (badge) badge.style.display = 'none';
    sectionTitle.style.cursor = '';
  }
}

function _initHiddenTilesRestore() {
  const sectionTitle = document.querySelector('#quick-cards')?.previousElementSibling;
  if (!sectionTitle) return;
  sectionTitle.addEventListener('click', _toggleHiddenPanel);
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

/* ── Init ─────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  _initSundial();
  _initAddNewTile();
  _initTileContextMenu();
  _applyHiddenTiles();
  _initHiddenTilesRestore();
});
