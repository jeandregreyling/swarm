/* ──────────────────────────────────────────────────────────────────────────────
   diamond.js — System Pulse + Attention Dots for the home dashboard.

   Replaces the old "Needs Attention" + "System Status" sections with:
     1. Compact vitals badges  (CPU / RAM / Temp / Queue / Disk / Agents / Gov)
     2. 7-day sparkline graph  (tickets closed + proposals executed)
     3. Attention dots          (coloured circles on tile corners)
   ────────────────────────────────────────────────────────────────────────── */

/* ── System Pulse ─────────────────────────────────────────────────────────── */

function loadSystemPulse() {
  fetch('/api/diamond/pulse')
    .then(r => r.json())
    .then(d => {
      if (!d.ok) return;
      _renderVitals(d);
      _renderPulseChart(d);
      _renderPulseSummary(d);
      _updateMoodRing(d);
    })
    .catch(err => console.warn('[Diamond] pulse fetch:', err));

  // Also load attention dots
  loadAttentionDots();
}

/* ── Vitals badges ────────────────────────────────────────────────────────── */

function _renderVitals(d) {
  const s = d.system || {};
  const q = d.queue || {};
  const a = d.agents || {};
  const g = d.governance || {};

  _setVital('pulse-cpu',    (s.cpu_percent != null ? s.cpu_percent + '%' : '—'),   _healthLevel(s.cpu_percent, 60, 80));
  _setVital('pulse-ram',    (s.ram_percent != null ? s.ram_percent + '%' : '—'),   _healthLevel(s.ram_percent, 70, 85));
  _setVital('pulse-temp',   (s.cpu_temp_c != null  ? s.cpu_temp_c + '°C' : '—'),  _healthLevel(s.cpu_temp_c, 65, 80));
  _setVital('pulse-queue',  (q.depth != null       ? String(q.depth) : '—'),       q.depth > 10 ? 'crit' : q.depth > 3 ? 'warn' : 'ok');
  const mainDisk = (s.disks && s.disks.length) ? s.disks[0] : {};
  _setVital('pulse-disk',   (mainDisk.percent != null ? mainDisk.percent + '%' : '—'), _healthLevel(mainDisk.percent, 70, 90));
  _setVital('pulse-agents', a.enabled != null ? (a.enabled + '/' + a.total) : '—', 'ok');
  _setVital('pulse-gov',    g.alm_status || '—', g.alm_status === 'enforced' ? 'ok' : 'warn');
}

function _setVital(id, value, level) {
  const el = document.getElementById(id);
  if (!el) return;
  const valEl = el.querySelector('.pulse-badge-val');
  if (valEl) valEl.textContent = value;
  el.classList.remove('pulse-ok', 'pulse-warn', 'pulse-crit');
  el.classList.add('pulse-' + (level || 'ok'));
}

function _healthLevel(val, warnAt, critAt) {
  if (val == null) return 'ok';
  if (val >= critAt) return 'crit';
  if (val >= warnAt) return 'warn';
  return 'ok';
}

/* ── 7-Day Sparkline Chart (pure canvas) ──────────────────────────────────── */

function _renderPulseChart(d) {
  const canvas = document.getElementById('pulse-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  // High-DPI scaling
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;

  const ticketTrend  = (d.tickets && d.tickets.trend) || [];
  const proposalTrend = (d.proposals && d.proposals.trend) || [];

  // Merge into 7-day series
  const days = [];
  for (let i = 0; i < 7; i++) {
    days.push({
      label: (ticketTrend[i] && ticketTrend[i].day) ? ticketTrend[i].day.slice(5) : '',
      tickets: (ticketTrend[i] && ticketTrend[i].closed) || 0,
      proposals: (proposalTrend[i] && proposalTrend[i].executed) || 0,
    });
  }

  const maxVal = Math.max(1, ...days.map(d => Math.max(d.tickets, d.proposals)));

  ctx.clearRect(0, 0, w, h);

  const padL = 4, padR = 4, padT = 8, padB = 18;
  const chartW = w - padL - padR;
  const chartH = h - padT - padB;
  const barW = chartW / 7;

  // Get CSS colours
  const cs = getComputedStyle(document.documentElement);
  const accentColor = cs.getPropertyValue('--accent').trim() || '#60a5fa';
  const greenColor = '#4caf50';
  const dimColor = cs.getPropertyValue('--text-dim').trim() || '#666';

  for (let i = 0; i < days.length; i++) {
    const x = padL + i * barW;
    const halfBar = barW * 0.3;

    // Ticket bar (left half)
    const th = (days[i].tickets / maxVal) * chartH;
    ctx.fillStyle = accentColor;
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    _roundRect(ctx, x + barW * 0.1, padT + chartH - th, halfBar, th, 2);
    ctx.fill();

    // Proposal bar (right half)
    const ph = (days[i].proposals / maxVal) * chartH;
    ctx.fillStyle = greenColor;
    ctx.beginPath();
    _roundRect(ctx, x + barW * 0.5, padT + chartH - ph, halfBar, ph, 2);
    ctx.fill();

    ctx.globalAlpha = 1;

    // Day label
    ctx.fillStyle = dimColor;
    ctx.font = '9px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(days[i].label, x + barW / 2, h - 3);
  }
}

function _roundRect(ctx, x, y, w, h, r) {
  if (h <= 0) { ctx.rect(x, y, w, 0); return; }
  r = Math.min(r, h / 2, w / 2);
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h);
  ctx.lineTo(x, y + h);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function _renderPulseSummary(d) {
  const t = d.tickets || {};
  const p = d.proposals || {};
  const q = d.queue || {};
  const el1 = document.getElementById('pulse-tickets-open');
  const el2 = document.getElementById('pulse-proposals-pending');
  const el3 = document.getElementById('pulse-consults');
  if (el1) el1.textContent = (t.open || 0) + ' open tickets';
  if (el2) el2.textContent = (p.pending || 0) + ' pending proposals';
  if (el3) el3.textContent = (q.consults_today || 0) + ' consults today';
}

/* ── Attention Dots on Tiles ──────────────────────────────────────────────── */

function loadAttentionDots() {
  fetch('/api/diamond/attention')
    .then(r => r.json())
    .then(d => {
      if (!d.ok) return;
      _renderAttentionDots(d.flags || {});
    })
    .catch(err => console.warn('[Diamond] attention fetch:', err));
}

function _renderAttentionDots(flags) {
  // Remove existing dots
  document.querySelectorAll('.attn-dot').forEach(el => el.remove());

  // Map flag keys → tile data-win-id
  // flags object keys: tickets, studio, library, chat, monitor
  for (const [key, flag] of Object.entries(flags)) {
    if (!flag || flag.level === 'none') continue;
    const card = document.querySelector(`.home-card[data-win-id="${key}"]`);
    if (!card) continue;

    // Ensure relative positioning for dot placement
    if (getComputedStyle(card).position === 'static') {
      card.style.position = 'relative';
    }

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
    // Open Studio with proposal creation
    if (typeof openWindow === 'function') {
      openWindow('studio', '🎨 Studio', 'view-studio');
    }
    // Auto-trigger new proposal after a beat
    setTimeout(() => {
      const btn = document.querySelector('#view-studio .proposal-new-btn, [onclick*="newProposal"]');
      if (btn) btn.click();
    }, 600);
  });
}

/* ── Mood Ring — ambient health glow ──────────────────────────────────────── */

function _updateMoodRing(d) {
  const scene = document.getElementById('ambient-scene');
  if (!scene) return;

  const s = d.system || {};
  const q = d.queue || {};

  // Compute worst-case health score: 0 = calm, 1 = busy, 2 = critical
  const levels = [
    _healthScore(s.cpu_percent, 60, 80),
    _healthScore(s.ram_percent, 70, 85),
    _healthScore(s.cpu_temp_c,  65, 80),
    _healthScore(q.depth,        3, 10),
  ];
  const worst = Math.max(...levels);

  // Map to colour: green (calm) → amber (busy) → red (attention)
  let color, opacity;
  if (worst >= 2) {
    color = '255, 60, 60';      // red
    opacity = 0.10;
  } else if (worst >= 1) {
    color = '255, 165, 0';      // amber
    opacity = 0.07;
  } else {
    color = '76, 175, 80';      // green
    opacity = 0.05;
  }

  scene.style.background = `radial-gradient(ellipse 120% 80% at 50% 30%, rgba(${color}, ${opacity}) 0%, transparent 70%)`;
  scene.style.opacity = '1';
  scene.style.transition = 'background 2s ease, opacity 1.5s ease';
}

function _healthScore(val, warnAt, critAt) {
  if (val == null) return 0;
  if (val >= critAt) return 2;
  if (val >= warnAt) return 1;
  return 0;
}

// ── Init hook ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  _initAddNewTile();
});
