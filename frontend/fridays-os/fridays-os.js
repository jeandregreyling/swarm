/**
 * FRIDAYS OS — Spatial Interface Engine
 * Camera-driven infinite canvas. No page loads. Everything lives in 3D space.
 */
(function () {
  'use strict';

  // ── State ─────────────────────────────────────────────────────────────────
  const state = {
    camera: { x: 0, y: 0, z: 0, rx: 0, ry: 0, zoom: 1 },
    drag: { active: false, sx: 0, sy: 0, cx: 0, cy: 0 },
    keys: new Set(),
    orbs: new Map(),
    surfaces: new Map(),
    activeSurface: null,
    dreamMode: false,
    lastTick: performance.now(),
  };

  // ── DOM Refs ──────────────────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const viewport = $('#viewport');
  const cameraEl = $('#camera');
  const universe = $('#universe');
  const hudCoords = $('#hud-coords');
  const loader = $('#loader');
  const dreamOverlay = $('#dream-overlay');

  // ── Camera ────────────────────────────────────────────────────────────────
  function updateCamera() {
    const { x, y, z, rx, ry, zoom } = state.camera;
    cameraEl.style.transform =
      `translate3d(${-x}px, ${-y}px, ${z}px) ` +
      `rotateX(${rx}deg) rotateY(${ry}deg) scale(${zoom})`;
    if (hudCoords) {
      hudCoords.textContent = `X ${Math.round(x)}  Y ${Math.round(y)}  Z ${zoom.toFixed(2)}`;
    }
  }

  function moveCamera(dx, dy, dz = 0) {
    state.camera.x += dx;
    state.camera.y += dy;
    state.camera.z += dz;
    updateCamera();
  }

  function zoomCamera(factor) {
    state.camera.zoom = Math.max(0.3, Math.min(3, state.camera.zoom * factor));
    updateCamera();
  }

  // ── Input ─────────────────────────────────────────────────────────────────
  viewport.addEventListener('mousedown', (e) => {
    if (e.button !== 0 || e.target.closest('.orb, .surface, .nav-orb')) return;
    state.drag.active = true;
    state.drag.sx = e.clientX;
    state.drag.sy = e.clientY;
    state.drag.cx = state.camera.x;
    state.drag.cy = state.camera.y;
    viewport.style.cursor = 'grabbing';
  });

  window.addEventListener('mousemove', (e) => {
    if (!state.drag.active) return;
    const dx = (e.clientX - state.drag.sx) / state.camera.zoom;
    const dy = (e.clientY - state.drag.sy) / state.camera.zoom;
    state.camera.x = state.drag.cx - dx;
    state.camera.y = state.drag.cy - dy;
    updateCamera();
  });

  window.addEventListener('mouseup', () => {
    state.drag.active = false;
    viewport.style.cursor = 'grab';
  });

  viewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.92 : 1.08;
    zoomCamera(factor);
  }, { passive: false });

  window.addEventListener('keydown', (e) => {
    state.keys.add(e.key.toLowerCase());
    if (e.key === ' ') {
      e.preventDefault();
      toggleDreamMode();
    }
    if (e.key === 'Escape' && state.activeSurface) {
      closeSurface(state.activeSurface);
    }
  });

  window.addEventListener('keyup', (e) => state.keys.delete(e.key.toLowerCase()));

  // WASD pan
  function tickInput() {
    const speed = 12 / state.camera.zoom;
    if (state.keys.has('w')) moveCamera(0, -speed);
    if (state.keys.has('s')) moveCamera(0, speed);
    if (state.keys.has('a')) moveCamera(-speed, 0);
    if (state.keys.has('d')) moveCamera(speed, 0);
    requestAnimationFrame(tickInput);
  }
  requestAnimationFrame(tickInput);

  // ── Tooltip ───────────────────────────────────────────────────────────────
  const tooltipEl = $('#orb-tooltip');
  function showTooltip(el, id) {
    if (!tooltipEl) return;
    const orb = state.orbs.get(id);
    const label = orb ? orb.label : id;
    const status = orb ? orb.status : 'idle';
    const rect = el.getBoundingClientRect();
    tooltipEl.innerHTML = `<span class="tt-status ${status}"></span><strong>${label}</strong>`;
    tooltipEl.style.left = `${rect.left + rect.width / 2 - tooltipEl.offsetWidth / 2}px`;
    tooltipEl.style.top = `${rect.top - tooltipEl.offsetHeight - 10}px`;
    tooltipEl.style.opacity = '1';
  }
  function hideTooltip() {
    if (tooltipEl) tooltipEl.style.opacity = '0';
  }

  // ── Orbs ──────────────────────────────────────────────────────────────────
  function createOrb(id, label, x, y, tier = 'local', status = 'idle') {
    const el = document.createElement('div');
    el.className = `orb tier-${tier}`;
    el.dataset.orbId = id;
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.innerHTML = `
      <span class="orb-status ${status}"></span>
      <span class="orb-label">${label}</span>
    `;
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      focusOrb(id);
    });
    el.addEventListener('mouseenter', () => showTooltip(el, id));
    el.addEventListener('mouseleave', hideTooltip);
    universe.appendChild(el);
    state.orbs.set(id, { el, x, y, label, tier, status });
    return el;
  }

  function focusOrb(id) {
    const orb = state.orbs.get(id);
    if (!orb) return;
    const targetX = orb.x - window.innerWidth / 2 + 32;
    const targetY = orb.y - window.innerHeight / 2 + 32;
    animateCameraTo(targetX, targetY, 0, 1.4);
    openSurface(id);
  }

  function animateCameraTo(tx, ty, tz, tzoom) {
    const start = { ...state.camera };
    const startTime = performance.now();
    const duration = 800;
    function step(now) {
      const t = Math.min(1, (now - startTime) / duration);
      const ease = 1 - Math.pow(1 - t, 3);
      state.camera.x = start.x + (tx - start.x) * ease;
      state.camera.y = start.y + (ty - start.y) * ease;
      state.camera.z = start.z + (tz - start.z) * ease;
      state.camera.zoom = start.zoom + (tzoom - start.zoom) * ease;
      updateCamera();
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // ── Surfaces ──────────────────────────────────────────────────────────────
  function createSurface(id, title, contentHtml) {
    const el = document.createElement('div');
    el.className = 'surface closed';
    el.dataset.surfaceId = id;
    el.style.left = '80px';
    el.style.top = '20px';
    el.innerHTML = `
      <div class="surface-header">
        <div class="surface-title">${title}</div>
        <button class="surface-close" onclick="window.FRIDAYS.closeSurface('${id}')">×</button>
      </div>
      <div class="surface-body">${contentHtml}</div>
    `;
    universe.appendChild(el);
    state.surfaces.set(id, { el, title });
  }

  function openSurface(id) {
    if (state.activeSurface && state.activeSurface !== id) {
      closeSurface(state.activeSurface);
    }
    const s = state.surfaces.get(id);
    if (!s) return;
    s.el.classList.remove('closed');
    s.el.classList.add('open');
    state.activeSurface = id;
  }

  function closeSurface(id) {
    const s = state.surfaces.get(id);
    if (!s) return;
    s.el.classList.remove('open');
    s.el.classList.add('closed');
    if (state.activeSurface === id) state.activeSurface = null;
  }

  // ── Constellations ────────────────────────────────────────────────────────
  function drawConstellation(name, orbIds, color = 'rgba(0,229,255,0.15)') {
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.classList.add('constellation');
    const svg = $('#constellation-layer');
    if (!svg) return;

    // Draw connecting lines
    for (let i = 0; i < orbIds.length - 1; i++) {
      const a = state.orbs.get(orbIds[i]);
      const b = state.orbs.get(orbIds[i + 1]);
      if (!a || !b) continue;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', a.x + 32);
      line.setAttribute('y1', a.y + 32);
      line.setAttribute('x2', b.x + 32);
      line.setAttribute('y2', b.y + 32);
      line.setAttribute('stroke', color);
      line.setAttribute('stroke-width', '1');
      line.setAttribute('stroke-dasharray', '4 4');
      group.appendChild(line);
    }

    // Label at centroid
    const cx = orbIds.reduce((sum, id) => sum + (state.orbs.get(id)?.x || 0), 0) / orbIds.length + 32;
    const cy = orbIds.reduce((sum, id) => sum + (state.orbs.get(id)?.y || 0), 0) / orbIds.length - 16;
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', cx);
    text.setAttribute('y', cy);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('fill', 'rgba(255,255,255,0.3)');
    text.setAttribute('font-size', '11');
    text.setAttribute('font-family', 'sans-serif');
    text.setAttribute('letter-spacing', '2');
    text.textContent = name;
    group.appendChild(text);

    svg.appendChild(group);
  }

  // ── Starfield ─────────────────────────────────────────────────────────────
  function seedStars(count = 300) {
    const sf = $('.starfield');
    if (!sf) return;
    for (let i = 0; i < count; i++) {
      const star = document.createElement('div');
      star.className = 'star';
      star.style.left = Math.random() * 100 + '%';
      star.style.top = Math.random() * 100 + '%';
      star.style.animationDelay = Math.random() * 3 + 's';
      star.style.opacity = 0.1 + Math.random() * 0.5;
      sf.appendChild(star);
    }
  }

  // ── Dream Mode ────────────────────────────────────────────────────────────
  function toggleDreamMode() {
    state.dreamMode = !state.dreamMode;
    dreamOverlay.classList.toggle('active', state.dreamMode);
    if (state.dreamMode) {
      document.body.style.filter = 'saturate(0.6) brightness(0.9)';
    } else {
      document.body.style.filter = '';
    }
  }

  // ── Navigation Ring ───────────────────────────────────────────────────────
  function setNavActive(id) {
    document.querySelectorAll('.nav-orb').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.nav === id);
    });
  }

  // ── API ───────────────────────────────────────────────────────────────────
  async function fetchAgents() {
    try {
      const res = await fetch('/api/agents/status');
      if (!res.ok) return [];
      return await res.json();
    } catch (e) {
      console.warn('[FRIDAYS] agent fetch failed:', e);
      return [];
    }
  }

  // Store actual constellation centres after layout so nav ring can jump to them
  const constellationCentres = {};

  function tierToConstellation(tier) {
    // Map DB tier → spatial constellation + colour
    const map = {
      local:    { name: 'Think Tank',   colour: 'rgba(0,255,136,0.12)',  cx: 480,  cy: 320 },
      paid:     { name: 'Forge',        colour: 'rgba(0,229,255,0.12)',  cx: 480,  cy: 860 },
      free:     { name: 'Observatory',  colour: 'rgba(200,180,255,0.12)', cx: 1260, cy: 320 },
      service:  { name: 'Garden',       colour: 'rgba(255,170,0,0.12)',  cx: 1260, cy: 860 },
    };
    return map[tier] || map.local;
  }

  function layoutAgents(agents) {
    // Group by constellation
    const groups = {};
    for (const a of agents) {
      const t = (a.tier || 'local').toLowerCase();
      if (!groups[t]) groups[t] = [];
      groups[t].push(a);
    }

    const constellationOrbIds = {};
    for (const [tier, list] of Object.entries(groups)) {
      const cfg = tierToConstellation(tier);
      if (!constellationOrbIds[cfg.name]) constellationOrbIds[cfg.name] = [];
      // Spiral layout around constellation centre
      const angleStep = (2 * Math.PI) / Math.max(list.length, 1);
      const radius = 180;
      list.forEach((a, i) => {
        const angle = angleStep * i - Math.PI / 2;
        const x = cfg.cx + Math.cos(angle) * radius;
        const y = cfg.cy + Math.sin(angle) * radius;
        const id = a.name.toLowerCase();
        const status = a.status === 'busy' ? 'working' : (a.status === 'down' ? 'error' : (a.enabled === false ? 'disabled' : 'idle'));
        createOrb(id, a.name, x, y, tier, status);
        constellationOrbIds[cfg.name].push(id);
        // Create/update surface with live data
        createSurface(id, a.name, renderAgentSurface(a));
      });
      // Store actual centre for nav ring jumps
      constellationCentres[cfg.name.toLowerCase().replace(/\s+/g, '-')] = { x: cfg.cx, y: cfg.cy };
    }

    // Draw constellation lines
    requestAnimationFrame(() => {
      for (const [name, ids] of Object.entries(constellationOrbIds)) {
        const cfg = Object.values(tierToConstellation).find(c => c.name === name);
        drawConstellation(name, ids, cfg?.colour || 'rgba(255,255,255,0.08)');
      }
      // Bridge constellation — hardcoded system nodes
      createOrb('system-bridge', 'Bridge', 900, 580, 'service', 'active');
      drawConstellation('Bridge', ['system-bridge'], 'rgba(255,255,255,0.08)');
      constellationCentres['center'] = { x: 900, y: 580 };
    });
  }

  function renderAgentSurface(a) {
    const statusColor = a.status === 'busy' ? 'var(--success)' : (a.status === 'down' ? 'var(--error)' : 'var(--text-dim)');
    const cbBadge = a.circuit_breaker && a.circuit_breaker !== 'closed'
      ? `<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:var(--error);color:#fff;font-size:10px;font-weight:700;margin-left:8px;">CB ${a.circuit_breaker}</span>`
      : '';
    const lastSeen = a.last_seen
      ? `<span style="color:var(--text-dim);font-size:11px;">· ${new Date(a.last_seen * 1000).toLocaleTimeString()}</span>`
      : '';
    return `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
        <span style="width:10px;height:10px;border-radius:50%;background:${statusColor};display:inline-block;box-shadow:0 0 8px ${statusColor};"></span>
        <strong style="font-size:14px;">${a.name}</strong>
        <span style="font-size:11px;color:var(--text-dim);text-transform:uppercase;">${a.tier}</span>
        ${cbBadge}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;color:var(--text-dim);margin-bottom:10px;">
        <div>Status: <strong style="color:var(--text);">${a.status}</strong></div>
        <div>Active jobs: <strong style="color:var(--text);">${a.active_jobs || 0}</strong></div>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:12px;">Last seen ${lastSeen || '—'}</div>
      <div style="display:flex;gap:6px;">
        <a href="/legacy-ui#chat" target="_self" style="padding:5px 10px;border-radius:6px;background:var(--accent);color:#000;font-size:11px;font-weight:700;text-decoration:none;">Chat</a>
        <a href="/legacy-ui#agents-config" target="_self" style="padding:5px 10px;border-radius:6px;background:var(--glass-border);color:var(--text);font-size:11px;text-decoration:none;border:1px solid var(--glass-border);">Config</a>
      </div>
    `;
  }

  // ── Live polling ───────────────────────────────────────────────────────────
  async function refreshAgents() {
    const agents = await fetchAgents();
    if (!agents.length) return;
    for (const a of agents) {
      const id = a.name.toLowerCase();
      const orb = state.orbs.get(id);
      if (orb) {
        const newStatus = a.status === 'busy' ? 'working' : (a.status === 'down' ? 'error' : (a.enabled === false ? 'disabled' : 'idle'));
        if (orb.status !== newStatus) {
          orb.status = newStatus;
          const dot = orb.el.querySelector('.orb-status');
          if (dot) dot.className = `orb-status ${newStatus}`;
        }
      }
      // Update surface if it exists
      const s = state.surfaces.get(id);
      if (s) {
        s.el.querySelector('.surface-body').innerHTML = renderAgentSurface(a);
      }
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  async function init() {
    seedStars(250);

    // First-visit welcome
    const welcomeOverlay = $('#welcome-overlay');
    try {
      if (welcomeOverlay && !localStorage.getItem('fridays-os-welcome')) {
        welcomeOverlay.style.display = 'flex';
      }
    } catch (e) {
      /* localStorage may be blocked */ }

    const agents = await fetchAgents();
    if (agents.length) {
      layoutAgents(agents);
    } else {
      // Fallback: hardcoded demo layout when API is unreachable
      createOrb('gemma', 'Gemma', 400, 300, 'local', 'idle');
      createOrb('seven', 'Seven', 860, 600, 'service', 'active');
      drawConstellation('Think Tank', ['gemma'], 'rgba(0,255,136,0.12)');
      drawConstellation('Bridge', ['seven'], 'rgba(255,255,255,0.08)');
      createSurface('gemma', 'Gemma', '<p style="color:var(--text-dim)">Offline — API unreachable</p>');
      createSurface('seven', 'Seven', '<p style="color:var(--text-dim)">Offline — API unreachable</p>');
    }

    // Navigation ring handlers — jump to actual constellation centres
    document.querySelectorAll('.nav-orb').forEach((btn) => {
      btn.addEventListener('click', () => {
        const nav = btn.dataset.nav;
        setNavActive(nav);
        const centre = constellationCentres[nav];
        if (centre) {
          const targetX = centre.x - window.innerWidth / 2 + 32;
          const targetY = centre.y - window.innerHeight / 2 + 32;
          animateCameraTo(targetX, targetY, 0, 1.2);
        }
      });
    });

    // Start live polling (10s)
    setInterval(refreshAgents, 10000);

    // Hide loader
    setTimeout(() => {
      loader.classList.add('hidden');
      animateCameraTo(900, 580, 0, 1);
    }, 600);
  }

  // ── Public API ────────────────────────────────────────────────────────────
  window.FRIDAYS = {
    state,
    moveCamera,
    zoomCamera,
    focusOrb,
    openSurface,
    closeSurface,
    toggleDreamMode,
    setNavActive,
  };

  // Boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
