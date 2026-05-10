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

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    seedStars(250);

    // Agent orbs — positioned in constellations
    // Think Tank (top-left)
    createOrb('gemma', 'Gemma', 400, 300, 'local', 'idle');
    createOrb('qwen', 'Qwen', 520, 260, 'local', 'active');
    createOrb('llama', 'Llama', 480, 400, 'local', 'idle');
    createOrb('mistral', 'Mistral', 340, 380, 'local', 'idle');
    createOrb('deepseek', 'DeepSeek', 580, 360, 'local', 'idle');
    createOrb('duck', 'Duck', 620, 300, 'local', 'idle');
    createOrb('sniffles', 'Sniffles', 420, 200, 'local', 'idle');

    // Forge (bottom-left)
    createOrb('nine', 'Nine', 400, 800, 'paid', 'idle');
    createOrb('ten', 'Ten', 520, 840, 'paid', 'idle');
    createOrb('eleven', 'Eleven', 480, 940, 'paid', 'idle');
    createOrb('twelve', 'Twelve', 340, 920, 'paid', 'idle');
    createOrb('thirteen', 'Thirteen', 580, 880, 'paid', 'idle');

    // Observatory (top-right)
    createOrb('scholar', 'Scholar', 1200, 300, 'free', 'idle');
    createOrb('seeker', 'Seeker', 1320, 260, 'free', 'idle');
    createOrb('librarian', 'Librarian', 1280, 400, 'free', 'idle');

    // Garden (bottom-right)
    createOrb('ghost', 'Ghost', 1200, 800, 'service', 'active');
    createOrb('fridays', 'Fridays', 1320, 840, 'service', 'active');
    createOrb('watchdog', 'Watchdog', 1280, 940, 'service', 'working');

    // Bridge (centre)
    createOrb('seven', 'Seven', 860, 600, 'service', 'active');
    createOrb('eight', 'Eight', 980, 560, 'local', 'idle');
    createOrb('vortex', 'Vortex', 940, 680, 'service', 'active');

    // Constellations
    requestAnimationFrame(() => {
      drawConstellation('Think Tank', ['gemma', 'qwen', 'llama', 'mistral', 'deepseek', 'duck', 'sniffles'], 'rgba(0,255,136,0.12)');
      drawConstellation('Forge', ['nine', 'ten', 'eleven', 'twelve', 'thirteen'], 'rgba(0,229,255,0.12)');
      drawConstellation('Observatory', ['scholar', 'seeker', 'librarian'], 'rgba(200,180,255,0.12)');
      drawConstellation('Garden', ['ghost', 'fridays', 'watchdog'], 'rgba(255,170,0,0.12)');
      drawConstellation('Bridge', ['seven', 'eight', 'vortex'], 'rgba(255,255,255,0.08)');
    });

    // Surfaces (placeholder content — API-backed in production)
    createSurface('gemma', 'Gemma', '<p>Local Ollama agent. Model: gemma3:latest</p><p>Status: idle</p>');
    createSurface('qwen', 'Qwen', '<p>Local Ollama agent. Model: qwen2.5:latest</p><p>Status: active</p>');
    createSurface('seven', 'Seven', '<p>System orchestrator. Perception + memory + reasoning.</p><p>Status: online</p>');
    createSurface('watchdog', 'Watchdog', '<p>Self-healing monitor. Circuit breaker active.</p><p>Status: working</p>');

    // Navigation ring handlers
    document.querySelectorAll('.nav-orb').forEach((btn) => {
      btn.addEventListener('click', () => {
        const nav = btn.dataset.nav;
        setNavActive(nav);
        if (nav === 'center') animateCameraTo(800, 500, 0, 1);
        if (nav === 'think-tank') animateCameraTo(480, 320, 0, 1.2);
        if (nav === 'forge') animateCameraTo(480, 860, 0, 1.2);
        if (nav === 'observatory') animateCameraTo(1260, 320, 0, 1.2);
        if (nav === 'garden') animateCameraTo(1260, 860, 0, 1.2);
      });
    });

    // Hide loader
    setTimeout(() => {
      loader.classList.add('hidden');
      // Initial camera position — centre on Bridge
      animateCameraTo(800, 500, 0, 1);
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
