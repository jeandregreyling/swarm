// orbs.js — Five Voices of Seven · Ambient Intelligence System
// The nervous system expressed in geometry: Observer, Memory, Logic, Intuition, Expression.
(function () {
  'use strict';

  const canvas = document.getElementById('orb-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let W = 0, H = 0, DPR = 1;
  let ACCENT = '#27CBFF', GLOW_A = '#CDEEFF', GLOW_B = '#E6F6FF';

  // ── Roles ─────────────────────────────────────────────────────────────────────
  // Five Voices of Seven — the local-algorithm nervous system made visible
  const EYE = 0, ECHO = 1, THREAD = 2, PULSE = 3, VOICE = 4;
  const ROLE_NAMES = ['Eye', 'Echo', 'Thread', 'Pulse', 'Voice'];
  const ROLE_KEYS  = ['eye', 'echo', 'thread', 'pulse', 'voice'];
  const ROLE_KEY = { eye: EYE, echo: ECHO, thread: THREAD, pulse: PULSE, voice: VOICE };

  // ── Per-orb visibility & graphics quality (user-controllable) ────────────────
  // Persisted in localStorage. Each voice can be hidden individually; quality
  // toggles between 'high' (3D wireframes, rotation, depth, trails) and 'low'
  // (flat 2D rings, cheap glow — best for low-power machines).
  const ORB_VIS_KEY = 'fridays_orb_visible';
  const ORB_QUALITY_KEY = 'fridays_orb_quality';
  let _orbVisible = { eye:true, echo:true, thread:true, pulse:true, voice:true };
  let _orbQuality = 'high';
  try {
    const stored = JSON.parse(localStorage.getItem(ORB_VIS_KEY) || 'null');
    if (stored && typeof stored === 'object') {
      ROLE_KEYS.forEach(k => { if (typeof stored[k] === 'boolean') _orbVisible[k] = stored[k]; });
    }
  } catch (e) {}
  try {
    const q = String(localStorage.getItem(ORB_QUALITY_KEY) || 'high').toLowerCase();
    _orbQuality = (q === 'low') ? 'low' : 'high';
  } catch (e) {}
  function isOrbVisible(role) {
    const key = ROLE_KEYS[role];
    return _orbVisible[key] !== false;
  }
  function setOrbVisible(roleKey, on) {
    const k = String(roleKey || '').toLowerCase();
    if (!(k in _orbVisible)) return;
    _orbVisible[k] = !!on;
    try { localStorage.setItem(ORB_VIS_KEY, JSON.stringify(_orbVisible)); } catch (e) {}
    _syncOrbControls();
  }
  function setOrbQuality(mode) {
    _orbQuality = (String(mode || 'high').toLowerCase() === 'low') ? 'low' : 'high';
    try { localStorage.setItem(ORB_QUALITY_KEY, _orbQuality); } catch (e) {}
    document.body.dataset.orbQuality = _orbQuality;
    _syncOrbControls();
  }
  function _syncOrbControls() {
    ROLE_KEYS.forEach(k => {
      const el = document.getElementById('orb-vis-' + k);
      if (el) el.checked = _orbVisible[k] !== false;
    });
    const lo = document.getElementById('orb-quality-low');
    const hi = document.getElementById('orb-quality-high');
    [lo, hi].forEach(el => {
      if (!el) return;
      el.style.background = 'var(--card)';
      el.style.color = 'var(--text-dim)';
      el.style.borderColor = 'var(--border)';
    });
    const active = (_orbQuality === 'low') ? lo : hi;
    if (active) {
      active.style.background = 'var(--accent, #27CBFF)';
      active.style.color = '#0a0f14';
      active.style.borderColor = 'var(--accent, #27CBFF)';
    }
  }
  // Expose for inline onchange handlers in the settings panel
  window.setOrbVisible = setOrbVisible;
  window.setOrbQuality = setOrbQuality;
  window.syncOrbControls = _syncOrbControls;
  // Initial body dataset so CSS / other code can react if it wants to
  try { document.body.dataset.orbQuality = _orbQuality; } catch (e) {}

  // Voice shapes: each uses a fixed draw function — never shared
  const VOICE_STYLE = [0, 1, 4, 5, 6]; // drawRings, drawMandala, drawLissajous, drawVortex, drawPulsar
  // 2026-04-23 — Personalities. Each orb has a "home" shape (above) and an
  // "alt" shape it morphs into when its mood/state peaks. Cross-faded over
  // ~700ms. Keeps each voice geometrically distinct AND gives them a
  // visible reaction to what the system is doing.
  //   Eye   (Rings)     → Crystal  when alert       — sharper, focused
  //   Echo  (Mandala)   → Helix    when recalling   — deeper, twisted
  //   Thread(Lissajous) → Vortex   when reasoning   — pulling threads in
  //   Pulse (Vortex)    → Pulsar   when active      — stronger beat
  //   Voice (Pulsar)    → Rings    when speaking    — broadcasting out
  const ALT_STYLE = [3, 2, 5, 6, 0]; // index into DRAW_FNS

  // ── Mouse ─────────────────────────────────────────────────────────────────────
  const mouse = { x: -999, y: -999 };
  let mouseVX = 0, mouseVY = 0, prevMX = 0, prevMY = 0, prevMT = 0;
  let mouseStillPos = null, mouseStillTimer = null;
  const mouseHeat = [];

  // ── Drag / Carry ──────────────────────────────────────────────────────────────
  // dragOrb  — pressed mouse-down on orb, drag while held, release = throw.
  // carriedOrb — picked up via double-click, follows cursor with no button,
  //              next click anywhere drops it and sets that spot as its new
  //              home/anchor (overrides the hardcoded ROOST_BASE).
  let dragOrb = null, dragPX = 0, dragPY = 0, dragHistory = [];
  let carriedOrb = null;
  let lastClickTS = 0, lastClickOrb = null;

  function setOrbDragState(active) {
    document.body.classList.toggle('orb-dragging', !!active);
    document.body.style.cursor = active ? 'grabbing' : '';
    if (!active) document.body._oc = '';
  }

  // ── Sleep ─────────────────────────────────────────────────────────────────────
  let sleeping = false, sleepTimer = null;

  // ── Helpers ───────────────────────────────────────────────────────────────────
  const rand  = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const lerp  = (a, b, t) => a + (b - a) * t;
  const dist  = (ax, ay, bx, by) => Math.sqrt((bx-ax)**2+(by-ay)**2);

  function readColors() {
    const s = getComputedStyle(document.documentElement);
    ACCENT = (s.getPropertyValue('--accent')  || '#27CBFF').trim();
    GLOW_A = (s.getPropertyValue('--glow-a')  || '#CDEEFF').trim();
    GLOW_B = (s.getPropertyValue('--glow-b')  || '#E6F6FF').trim();
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  ORB BRAIN — lightweight DOM context scanner
  // ══════════════════════════════════════════════════════════════════════════════
  const Brain = {
    ctx: {
      openWindows: 0, chatActive: false, hasErrors: false,
      agentsBusy: false, pendingMessages: 0, onHome: true,
      activeViewName: '', idleSeconds: 0, sessionMinutes: 0,
      userBusy: false,
    },
    sessionStart: Date.now(),
    scanTimer: 0,

    scan() {
      const c = this.ctx;
      c.openWindows    = document.querySelectorAll('.window-wrap').length;
      c.chatActive     = !!document.querySelector('#chat-output, .chat-output, [id*="chat"]');
      c.hasErrors      = document.querySelectorAll('[id*="glitch-badge"]:not([style*="display:none"])').length > 0;
      c.agentsBusy     = document.querySelectorAll('[class*="agent"][class*="active"], [data-status="running"]').length > 0;
      c.pendingMessages= document.querySelectorAll('[class*="badge"]:not(:empty), [class*="notification"]').length;
      c.onHome         = !document.querySelector('.window-wrap');
      c.sessionMinutes = Math.floor((Date.now() - this.sessionStart) / 60000);
      c.idleSeconds    = sleeping ? 10 : 0;
      // Name of most recently focused window
      const active = document.querySelector('.window-wrap[style*="z-index: 9"], .window-wrap');
      c.activeViewName = active ? (active.dataset.view || active.querySelector('.window-title')?.textContent?.trim() || '') : '';
      // userBusy: roost when there's clearly user-driven work happening on screen.
      // Otherwise the orbs are free to wander/explore. Mouse motion alone is
      // weak signal — require either DOM busy-ness or recent typing.
      const recentInput = (performance.now() - (window._lastUserInputTs || 0)) < 6000;
      c.userBusy = (
        c.agentsBusy ||
        c.hasErrors ||
        c.pendingMessages > 0 ||
        c.openWindows >= 2 ||
        recentInput
      );
    },

    update(dt) {
      this.scanTimer += dt;
      if (this.scanTimer > 5000) { this.scanTimer = 0; this.scan(); }
    },

    // What's under this orb? returns category string or null
    elementUnder(x, y) {
      const el = document.elementFromPoint(x, y);
      if (!el) return null;
      if (el.closest('.home-tile, [data-tile], .tile')) return 'tile';
      if (el.closest('[id*="chat"], .chat-message, .msg')) return 'chat';
      if (el.closest('.fri-card, .modal-content')) return 'card';
      if (el.closest('button, .btn, [role="button"]')) return 'button';
      if (el.closest('.window-wrap')) return 'window';
      return null;
    },

    // Signal tokens fed to Voice
    popSignals(orbRole) {
      const c = this.ctx;
      const signals = [];
      if (orbRole === EYE    && c.hasErrors)          signals.push({ type: 'error',   weight: 3 });
      if (orbRole === EYE    && c.agentsBusy)         signals.push({ type: 'agents',  weight: 2 });
      if (orbRole === ECHO   && c.chatActive)         signals.push({ type: 'chat',    weight: 2 });
      if (orbRole === THREAD && c.openWindows > 3)    signals.push({ type: 'busy',    weight: 2 });
      if (orbRole === PULSE  && c.pendingMessages > 0)signals.push({ type: 'pending', weight: 2 });
      if (orbRole === VOICE  && c.agentsBusy)         signals.push({ type: 'action',  weight: 2 });
      if (orbRole === VOICE  && c.sessionMinutes > 15)signals.push({ type: 'user',    weight: 2 });
      if (c.sessionMinutes > 30)                      signals.push({ type: 'long',    weight: 1 });
      return signals;
    },
  };

  // ══════════════════════════════════════════════════════════════════════════════
  //  COUNCIL LINK — fetches Agent 20 thoughts from the backend
  // ══════════════════════════════════════════════════════════════════════════════
  const CouncilLink = {
    thoughts: {},          // keyed by role constant → council row object
    enabled: false,        // true once first successful fetch
    fetchTimer: 0,
    INTERVAL: 30000,       // poll every 30 s

    async fetch() {
      try {
        const res = await fetch('/api/council/latest');
        if (!res.ok) return;
        const data = await res.json();
        if (Array.isArray(data)) {
          const next = {};
          data.forEach(t => {
            const role = ROLE_KEY[t.orb_role];
            if (role !== undefined && !next[role]) next[role] = t;
          });
          this.thoughts = next;
          this.enabled = true;
        }
      } catch (_) { /* silent */ }
    },

    update(dt) {
      this.fetchTimer += dt;
      if (this.fetchTimer >= this.INTERVAL) {
        this.fetchTimer = 0;
        this.fetch();
      }
    },

    async dismiss(id) {
      try {
        await fetch('/api/council/dismiss/' + id, { method: 'POST' });
        for (const k in this.thoughts) {
          if (this.thoughts[k] && this.thoughts[k].id === id) delete this.thoughts[k];
        }
      } catch (_) { /* silent */ }
    },

    thoughtFor(role) { return this.thoughts[role] || null; },
  };

  // ══════════════════════════════════════════════════════════════════════════════
  //  SEVEN LINK — pulls Seven's live beliefs / attention / curiosity and routes
  //  one item per orb role so each orb's bubble reflects what Seven is
  //  currently thinking about.
  // ══════════════════════════════════════════════════════════════════════════════
  const SevenLink = {
    thoughts: {},          // role → { id, thought, kind }
    enabled: false,
    fetchTimer: 0,
    INTERVAL: 25000,

    _truncate(s, n=120) {
      s = String(s || '').trim().replace(/\s+/g,' ');
      return s.length > n ? s.slice(0, n-1) + '…' : s;
    },

    async fetch() {
      // Pull a small bundle of Seven's current state. All endpoints are
      // read-only and cheap. Failures are silently tolerated — orbs fall
      // back to council/dialogue thoughts.
      try {
        const [bRes, aRes, cRes] = await Promise.all([
          fetch('/api/seven/beliefs?limit=8').catch(() => null),
          fetch('/api/seven/attention?limit=8').catch(() => null),
          fetch('/api/curiosity/open?limit=8').catch(() => null),
        ]);
        const beliefs   = (bRes && bRes.ok) ? ((await bRes.json()).items || []) : [];
        const attention = (aRes && aRes.ok) ? ((await aRes.json()).items || []) : [];
        const curiosity = (cRes && cRes.ok) ? ((await cRes.json()).items || []) : [];
        const next = {};
        // THREAD = reasoning → top belief
        if (beliefs[0]) {
          const b = beliefs[0];
          const txt = b.predicate ? `${b.subject} ${b.predicate} ${b.object || ''}`.trim()
                                  : (b.statement || b.text || '');
          next[THREAD] = { id: 'b'+(b.id||0), thought: this._truncate(txt), kind:'belief' };
        }
        // EYE = watching → attention/hot record
        if (attention[0]) {
          const a = attention[0];
          const txt = a.title || a.summary || a.text || a.kind || '';
          next[EYE] = { id: 'a'+(a.id||a.ref_id||0), thought: this._truncate(txt), kind:'attention' };
        }
        // PULSE = stirring → open curiosity question
        if (curiosity[0]) {
          const q = curiosity[0];
          next[PULSE] = { id: 'q'+(q.id||0), thought: this._truncate(q.question || q.text || ''), kind:'question' };
        }
        // ECHO = recall → second belief or attention echo
        if (beliefs[1]) {
          const b = beliefs[1];
          const txt = b.predicate ? `${b.subject} ${b.predicate} ${b.object || ''}`.trim()
                                  : (b.statement || b.text || '');
          next[ECHO] = { id: 'b'+(b.id||0), thought: this._truncate(txt), kind:'belief' };
        } else if (attention[1]) {
          const a = attention[1];
          next[ECHO] = { id: 'a'+(a.id||a.ref_id||0), thought: this._truncate(a.title || a.summary || ''), kind:'attention' };
        }
        // VOICE = speaking → another curiosity or third belief
        if (curiosity[1]) {
          const q = curiosity[1];
          next[VOICE] = { id: 'q'+(q.id||0), thought: this._truncate(q.question || ''), kind:'question' };
        } else if (beliefs[2]) {
          const b = beliefs[2];
          const txt = b.predicate ? `${b.subject} ${b.predicate} ${b.object || ''}`.trim()
                                  : (b.statement || b.text || '');
          next[VOICE] = { id: 'b'+(b.id||0), thought: this._truncate(txt), kind:'belief' };
        }
        this.thoughts = next;
        this.enabled = Object.keys(next).length > 0;
      } catch (_) { /* silent */ }
    },

    update(dt) {
      this.fetchTimer += dt;
      if (this.fetchTimer >= this.INTERVAL) {
        this.fetchTimer = 0;
        this.fetch();
      }
    },

    thoughtFor(role) { return this.thoughts[role] || null; },
  };

  // Track recent input so Brain.scan() can flip userBusy on/off.
  ['keydown','wheel','touchstart'].forEach(ev => {
    window.addEventListener(ev, () => { window._lastUserInputTs = performance.now(); }, {passive:true, capture:true});
  });

  // ══════════════════════════════════════════════════════════════════════════════
  //  DIALOGUE — Five Voices speak to each other
  // ══════════════════════════════════════════════════════════════════════════════
  const VP = {
    [EYE]:    {
      idle:   ['...watching', 'all clear', 'quiet', 'tracking', 'still here', 'on watch'],
      alert:  ['activity', 'something moved', 'heads up', 'alert', 'eyes open'],
      agents: ['agents active', 'busy out there', 'things running', 'motion detected'],
      chat:   ['signal arriving', 'words incoming', 'reading...', 'new message'],
      reply:  ['I see it', 'confirmed', 'observed', 'noted', 'watching that too', 'logged'],
    },
    [ECHO]:   {
      idle:   ['...', 'remembering', 'filing this', 'in memory', 'stored'],
      context:['I recall this', 'pattern match', 'seen before', 'cross-reference found'],
      memory: ['building context', 'long thread', 'deep archive'],
      reply:  ['...matches a pattern', 'I recall that', 'this rhymes with', 'familiar', 'filed'],
    },
    [THREAD]: {
      idle:   ['hmm', 'connecting...', 'if A then B', 'follows from', 'the thread holds'],
      reason: ['analysing', 'running logic', 'computing...', 'cross-referencing'],
      problem:['error implies...', 'root cause?', 'following the thread', 'diagnosis pending'],
      reply:  ['therefore', 'follows logically', 'connects to', 'if so then', 'the pattern holds'],
    },
    [PULSE]:  {
      idle:   ['...', '~', 'quiet signal', 'sensing', 'feels steady'],
      active: ['activity detected', 'something stirs', 'energy rising', 'pulse quickens'],
      signal: ['incoming', 'new signal', 'feels significant', 'sensing a shift'],
      reply:  ['feels right', '...something stirs', 'instinct says yes', 'I sense it', 'resonating'],
    },
    [VOICE]:  {
      idle:   ['worth noting', 'let me add', 'I would suggest', 'yes, and—', 'to be said'],
      ideas:  ['try a different angle?', 'worth pausing on', 'what if...?', 'follow that thread', 'almost there'],
      long:   ['still going strong', "you're committed", 'long session'],
      reply:  ['noted, and—', 'worth saying', 'yes, and', "I'd add", 'to summarise'],
    },
  };

  const Dialogue = {
    thread: [],
    pending: [],

    _rnd(arr) { return arr[Math.floor(Math.random() * arr.length)]; },

    _pick(role, cat) {
      const p = VP[role];
      return this._rnd((p && p[cat]) || p.idle || ['...']);
    },

    _responder(speaker) {
      const others = [EYE, ECHO, THREAD, PULSE, VOICE].filter(r => r !== speaker);
      return others[Math.floor(Math.random() * others.length)];
    },

    record(role, text) {
      this.thread.push({ role, text, time: performance.now() });
      if (this.thread.length > 5) this.thread.shift();
      const responder = this._responder(role);
      this.pending.push({
        role: responder,
        text: this._pick(responder, 'reply'),
        delay: 4000 + Math.random() * 7000,
        at: performance.now(),
      });
      if (this.pending.length > 6) this.pending.shift();
    },

    dequeue(role) {
      const now = performance.now();
      const idx = this.pending.findIndex(p => p.role === role && now - p.at >= p.delay);
      if (idx >= 0) return this.pending.splice(idx, 1)[0].text;
      return null;
    },

    generate(o) {
      // Prefer Seven's live thoughts (beliefs / attention / curiosity).
      const seven = SevenLink.thoughtFor(o.role);
      if (seven && seven.thought) { o._councilThoughtId = null; o._sevenThoughtId = seven.id; return seven.thought; }
      o._sevenThoughtId = null;
      const council = CouncilLink.thoughtFor(o.role);
      if (council) { o._councilThoughtId = council.id; return council.thought; }
      o._councilThoughtId = null;

      const pending = this.dequeue(o.role);
      if (pending) { this.record(o.role, pending); return pending; }

      const c = Brain.ctx;
      let text;
      switch (o.role) {
        case EYE:
          if (c.hasErrors)  text = this._pick(EYE, 'alert');
          else if (c.agentsBusy) text = this._pick(EYE, 'agents');
          else if (o.interestTarget === 'chat') text = this._pick(EYE, 'chat');
          else text = this._pick(EYE, 'idle');
          break;
        case ECHO:
          if (o.interestTarget === 'chat') text = this._pick(ECHO, 'context');
          else if (c.sessionMinutes > 20) text = this._pick(ECHO, 'memory');
          else text = this._pick(ECHO, 'idle');
          break;
        case THREAD:
          if (c.agentsBusy) text = this._pick(THREAD, 'reason');
          else if (c.hasErrors) text = this._pick(THREAD, 'problem');
          else text = this._pick(THREAD, 'idle');
          break;
        case PULSE:
          if (c.agentsBusy || c.pendingMessages > 0) text = this._pick(PULSE, 'active');
          else text = this._pick(PULSE, 'idle');
          break;
        case VOICE:
          if (o.ideaReady) text = this._pick(VOICE, 'ideas');
          else if (c.sessionMinutes > 30) text = this._pick(VOICE, 'long');
          else text = this._pick(VOICE, 'idle');
          break;
        default: text = '...';
      }
      this.record(o.role, text);
      return text;
    },
  };

  const Thoughts = { generate: (o) => Dialogue.generate(o) };

  // ══════════════════════════════════════════════════════════════════════════════
  //  MERGE COMPATIBILITY
  // ══════════════════════════════════════════════════════════════════════════════
  //  'love'    → they merge, grow, gain each other's thoughts
  //  'fight'   → they orbit, 3D spin, then separate smaller
  //  'neutral' → friendly bump, no major reaction
  const COMPAT = {
    [EYE]:    { [ECHO]:'love',   [THREAD]:'love',   [PULSE]:'love',    [VOICE]:'love',   [EYE]:'fight'    },
    [ECHO]:   { [EYE]:'love',    [THREAD]:'love',   [PULSE]:'neutral', [VOICE]:'love',   [ECHO]:'fight'   },
    [THREAD]: { [EYE]:'love',    [ECHO]:'love',     [PULSE]:'fight',   [VOICE]:'love',   [THREAD]:'fight' },
    [PULSE]:  { [EYE]:'love',    [ECHO]:'neutral',  [THREAD]:'fight',  [VOICE]:'love',   [PULSE]:'fight'  },
    [VOICE]:  { [EYE]:'love',    [ECHO]:'love',     [THREAD]:'love',   [PULSE]:'love',   [VOICE]:'fight'  },
  };

  const MERGED_NAMES = {
    [`${EYE}-${ECHO}`]:    'Witness',
    [`${EYE}-${THREAD}`]:  'Analyst',
    [`${EYE}-${PULSE}`]:   'Sense',
    [`${EYE}-${VOICE}`]:   'Signal',
    [`${ECHO}-${THREAD}`]: 'Synthesis',
    [`${ECHO}-${VOICE}`]:  'Narrator',
    [`${THREAD}-${VOICE}`]:'Argument',
    [`${PULSE}-${VOICE}`]: 'Impulse',
  };

  function getCompat(a, b) { return (COMPAT[a.role] || {})[b.role] || 'neutral'; }
  function getMergedName(a, b) {
    const k = `${Math.min(a.role,b.role)}-${Math.max(a.role,b.role)}`;
    return MERGED_NAMES[k] || ROLE_NAMES[a.role]+'+'+ROLE_NAMES[b.role];
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  ROOST ZONES — pre-assigned, heat-nudged
  // ══════════════════════════════════════════════════════════════════════════════
  const ROOST_BASE = [
    [0.09, 0.14],  // EYE    - top-left, watchful corner
    [0.12, 0.82],  // ECHO   - bottom-left, deep archive
    [0.50, 0.90],  // THREAD - bottom-centre, reasoning bridge
    [0.88, 0.72],  // PULSE  - bottom-right, sensing periphery
    [0.88, 0.20],  // VOICE  - top-right, outward broadcast
  ];

  function updateRoost(o, i) {
    // User-assigned anchor (from double-click drop) overrides hardcoded base.
    let rx, ry;
    if (o.customHomeX != null && o.customHomeY != null) {
      rx = o.customHomeX; ry = o.customHomeY;
    } else {
      rx = ROOST_BASE[i][0]*W; ry = ROOST_BASE[i][1]*H;
    }
    mouseHeat.forEach(p => {
      const dx=rx-p.x, dy=ry-p.y, d=Math.sqrt(dx*dx+dy*dy)||1;
      if (d < 260) { rx += (dx/d)*(260-d)*0.22; ry += (dy/d)*(260-d)*0.22; }
    });
    const mg = Math.min(W,H)*0.08;
    o.roostX = clamp(rx, mg, W-mg);
    o.roostY = clamp(ry, mg, H-mg);
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  ORB FACTORY
  // ══════════════════════════════════════════════════════════════════════════════
  function mkOrb(role, styleIdx, baseRF, spd) {
    return {
      role, style: styleIdx, baseRF, speed: spd,
      // Personality morph (2026-04-23): each orb can cross-fade between its
      // home `style` and an `altStyle` based on its current mood/state.
      altStyle: ALT_STYLE[role] != null ? ALT_STYLE[role] : styleIdx,
      morphPhase: 0,      // 0 = fully home, 1 = fully alt
      morphTarget: 0,     // 0 or 1 — eased toward by tickMorph()
      x: 0, y: 0, vx: 0, vy: 0,
      z: rand(0.5, 0.9), vz: rand(-0.0003, 0.0003),
      baseR: 0, r: 0,
      roostX: 0, roostY: 0,
      customHomeX: null, customHomeY: null,  // user-set anchor (double-click drop)
      settled: 0, watchAngle: rand(0, Math.PI*2),
      state: 'idle', stateTimer: rand(1000, 4000),
      driftAngle: rand(0, Math.PI*2),
      driftPhase: rand(0, Math.PI*2),
      breathPhase: rand(0, Math.PI*2),
      // 3D rotation (yaw around Y, pitch around X). Each orb spins at its own
      // rate so the wireframe shapes read as genuine 3D bodies.
      yaw: rand(0, Math.PI*2),
      pitch: rand(-0.4, 0.4),
      yawSpd:   rand(0.25, 0.55) * (Math.random()<0.5?-1:1),  // rad/sec
      pitchSpd: rand(0.08, 0.22) * (Math.random()<0.5?-1:1),
      flash: 0, trail: [],
      tiltX: 0, tiltY: 0,           // 3D tilt angles (radians)
      // Thought bubble
      thought: null, thoughtAlpha: 0, thoughtPhase: 'hidden',
      thoughtHoldTimer: 0, thoughtCooldown: rand(20000, 40000),
      // DOM awareness
      interestTarget: null, interestLevel: 0,
      // Merge/fight
      absorbed: false,               // true = this orb is inside another
      absorber: null,                // ref to absorber orb when absorbed
      mergedFrom: null,              // ref to absorbed orb (when this is absorber)
      mergedName: null,              // display name of merge result
      sizeBonus: 0,                  // +/- baseR multiplier from merges
      fighting: false,               // currently in fight
      fightPartner: null,
      fightTimer: 0,
      fightAngle: rand(0, Math.PI*2),
      // Voice idea state
      ideaTokens: 0, ideaReady: false,
      // Role-specific
      snoopTarget: null,
      patrolAngle: rand(0, Math.PI*2),
      patrolTarget: null,
      placedTimer: 0,
      // Reserved fields kept for compatibility; all five voices stay awake
      dormant: false,
      dormantAlpha: 0,          // 0 = fully dormant, 1 = fully awake
      _councilThoughtId: null,  // tracks active council thought for dismissal
    };
  }

  const orbs = [
    mkOrb(EYE,    VOICE_STYLE[EYE],    0.124, 0.80),
    mkOrb(ECHO,   VOICE_STYLE[ECHO],   0.098, 0.90),
    mkOrb(THREAD, VOICE_STYLE[THREAD], 0.090, 0.70),
    mkOrb(PULSE,  VOICE_STYLE[PULSE],  0.076, 1.00),
    mkOrb(VOICE,  VOICE_STYLE[VOICE],  0.084, 0.60),
  ];

  // ── Thought-bubble persistence (slice 5c) ─────────────────────────────────
  // Save the most recent thought per orb to localStorage so reload keeps the
  // bubble visible briefly instead of going blank for the full cooldown
  // window. Keyed by role; expires after 5 minutes.
  const _THOUGHT_KEY = 'fridays-orb-thoughts-v1';
  const _THOUGHT_TTL = 5 * 60 * 1000;
  function _persistThought(o) {
    if (!o || !o.thought) return;
    let store = {};
    try { store = JSON.parse(localStorage.getItem(_THOUGHT_KEY) || '{}') || {}; } catch(_) {}
    store[o.role] = { text: String(o.thought).slice(0, 240), ts: Date.now() };
    try { localStorage.setItem(_THOUGHT_KEY, JSON.stringify(store)); } catch(_) {}
  }
  function _hydrateThoughts() {
    let store = {};
    try { store = JSON.parse(localStorage.getItem(_THOUGHT_KEY) || '{}') || {}; } catch(_) { return; }
    const now = Date.now();
    orbs.forEach(o => {
      const rec = store[o.role];
      if (!rec || !rec.text) return;
      const age = now - (rec.ts || 0);
      if (age > _THOUGHT_TTL) return;
      o.thought = rec.text;
      o.thoughtAlpha = 1;
      o.thoughtPhase = 'hold';
      // Show for a few seconds after hydration, then fade out.
      o.thoughtHoldTimer = Math.max(1500, 4000 - Math.floor(age / 8));
      // Push the next natural thought a touch later so we don't double-flash.
      o.thoughtCooldown = rand(8000, 18000);
    });
  }
  // Run hydration after orbs settle into their initial roost positions.
  setTimeout(() => { try { _hydrateThoughts(); } catch(_) {} }, 700);

  // ── Resize ────────────────────────────────────────────────────────────────────
  function resize() {
    DPR = Math.min(window.devicePixelRatio||1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = Math.round(W*DPR); canvas.height = Math.round(H*DPR);
    canvas.style.width = W+'px'; canvas.style.height = H+'px';
    const base = Math.min(W,H);
    orbs.forEach((o,i) => {
      o.baseR = base * o.baseRF;
      if (o.x === 0) { o.x = ROOST_BASE[i][0]*W+rand(-50,50); o.y = ROOST_BASE[i][1]*H+rand(-50,50); }
      updateRoost(o, i);
    });
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  PARTICLES
  // ══════════════════════════════════════════════════════════════════════════════
  const sparks = [], impacts = [];

  function burst(x, y, count, power, col) {
    count = count||14; power = power||0.65;
    const c = col || ACCENT;
    for (let i = 0; i < count; i++) {
      const a=Math.random()*Math.PI*2, spd=power*(1.5+Math.random()*2.8);
      sparks.push({x,y,vx:Math.cos(a)*spd,vy:Math.sin(a)*spd-0.6,life:1,decay:0.019+Math.random()*0.02,sz:1.8+Math.random()*2.4,col:c});
    }
  }

  function ringBurst(x, y) { impacts.push({x,y,r:0,life:1}); burst(x,y,20,1.0); }

  function drawParticles(ts) {
    for (let i=impacts.length-1;i>=0;i--) {
      const p=impacts[i]; p.r+=2.2; p.life-=0.04;
      if (p.life<=0){impacts.splice(i,1);continue;}
      ctx.save(); ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.strokeStyle=ACCENT; ctx.lineWidth=1.8; ctx.globalAlpha=p.life*0.38;
      ctx.shadowColor=ACCENT; ctx.shadowBlur=12; ctx.setLineDash([]); ctx.stroke(); ctx.restore();
    }
    for (let i=sparks.length-1;i>=0;i--) {
      const s=sparks[i];
      s.x+=s.vx; s.y+=s.vy; s.vx*=0.973; s.vy=s.vy*0.973+0.055; s.life-=s.decay;
      if (s.life<=0){sparks.splice(i,1);continue;}
      const sz=s.sz*s.life;
      ctx.save(); ctx.translate(s.x,s.y); ctx.rotate(ts*0.003+i*0.44);
      ctx.globalAlpha=s.life*0.75; ctx.fillStyle=s.col||ACCENT; ctx.shadowColor=s.col||ACCENT; ctx.shadowBlur=10;
      ctx.beginPath();
      ctx.moveTo(0,-sz);ctx.lineTo(sz*0.28,-sz*0.28);ctx.lineTo(sz,0);ctx.lineTo(sz*0.28,sz*0.28);
      ctx.lineTo(0,sz);ctx.lineTo(-sz*0.28,sz*0.28);ctx.lineTo(-sz,0);ctx.lineTo(-sz*0.28,-sz*0.28);
      ctx.closePath(); ctx.fill(); ctx.restore();
    }
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  THOUGHT BUBBLE RENDERER
  // ══════════════════════════════════════════════════════════════════════════════
  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y); ctx.quadraticCurveTo(x+w,y,x+w,y+r);
    ctx.lineTo(x+w,y+h-r); ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);
    ctx.lineTo(x+r,y+h); ctx.quadraticCurveTo(x,y+h,x,y+h-r);
    ctx.lineTo(x,y+r); ctx.quadraticCurveTo(x,y,x+r,y); ctx.closePath();
  }

  function drawThought(o) {
    if (!o.thought || o.thoughtAlpha <= 0.01) return;
    const text = o.thought;
    const fontSize = 11;
    const pad = 7;
    ctx.font = `500 ${fontSize}px "SF Mono", "Fira Code", monospace`;
    const tw = ctx.measureText(text).width;
    const bw = tw + pad*2 + 2;
    const bh = fontSize + pad*2;

    // Position above orb, clamp to screen
    let bx = o.x - bw/2;
    let by = o.y - o.r*1.3 - bh - 10;
    bx = clamp(bx, 8, W - bw - 8);
    by = clamp(by, 8, H - bh - 8);
    const alpha = o.thoughtAlpha;

    ctx.save();
    ctx.globalAlpha = alpha;

    // Bubble background
    ctx.shadowColor = ACCENT; ctx.shadowBlur = 14;
    ctx.fillStyle = 'rgba(8, 12, 22, 0.82)';
    roundRect(bx, by, bw, bh, 6); ctx.fill();

    // Subtle border
    ctx.strokeStyle = ACCENT; ctx.lineWidth = 0.7; ctx.globalAlpha = alpha * 0.5;
    ctx.setLineDash([]); roundRect(bx, by, bw, bh, 6); ctx.stroke();

    // Stem — tiny triangle pointing down toward orb
    const stemX = clamp(o.x, bx+10, bx+bw-10);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = 'rgba(8, 12, 22, 0.82)';
    ctx.beginPath();
    ctx.moveTo(stemX-5, by+bh);
    ctx.lineTo(stemX+5, by+bh);
    ctx.lineTo(stemX, by+bh+7);
    ctx.closePath(); ctx.fill();

    // Text
    ctx.globalAlpha = alpha * 0.95;
    ctx.fillStyle = ACCENT;
    ctx.shadowColor = ACCENT; ctx.shadowBlur = 6;
    ctx.font = `500 ${fontSize}px "SF Mono", "Fira Code", monospace`;
    ctx.fillText(text, bx+pad+1, by+pad+fontSize*0.85);

    // Voice orb: sparkle dots around bubble when an idea is ready
    if (o.role === VOICE && o.ideaReady) {
      for (let i = 0; i < 6; i++) {
        const a = (i/6)*Math.PI*2 + Date.now()*0.001;
        const sx = bx + bw/2 + Math.cos(a)*(bw*0.65);
        const sy = by + bh/2 + Math.sin(a)*(bh*1.1);
        ctx.globalAlpha = alpha * (0.4 + 0.3 * Math.sin(Date.now()*0.003 + i));
        ctx.fillStyle = '#fff';
        ctx.shadowColor = ACCENT; ctx.shadowBlur = 8;
        ctx.beginPath(); ctx.arc(sx, sy, 1.5, 0, Math.PI*2); ctx.fill();
      }
    }
    // Council thought indicator — small pulsing dot top-right of bubble
    if (o._councilThoughtId) {
      const ix = bx + bw - 4, iy = by + 4;
      ctx.globalAlpha = alpha * (0.5 + 0.4 * Math.sin(Date.now() * 0.004));
      ctx.fillStyle = '#5EF29D'; ctx.shadowColor = '#5EF29D'; ctx.shadowBlur = 6;
      ctx.beginPath(); ctx.arc(ix, iy, 2.5, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  THOUGHT TICK — manages bubble lifecycle per orb
  // ══════════════════════════════════════════════════════════════════════════════
  function tickThought(o, dt) {
    if (o.thoughtPhase === 'hidden') {
      o.thoughtCooldown -= dt;
      if (o.thoughtCooldown <= 0 && o.settled > 0.45 && !o.fighting && !o.absorbed && !o.dormant) {
        o.thought = Thoughts.generate(o);
        o.thoughtAlpha = 0;
        o.thoughtPhase = 'fadein';
        o.thoughtHoldTimer = 2500 + o.thought.length * 80;
        o.thoughtCooldown = rand(25000, 50000);
        // Voice gets longer display when it has an idea to express
        if (o.role === VOICE && o.ideaReady) o.thoughtHoldTimer = 5000;
      }
    } else if (o.thoughtPhase === 'fadein') {
      o.thoughtAlpha = Math.min(1, o.thoughtAlpha + dt/400);
      if (o.thoughtAlpha >= 1) {
        o.thoughtPhase = 'hold';
        try { _persistThought(o); } catch(_) {}
      }
    } else if (o.thoughtPhase === 'hold') {
      o.thoughtHoldTimer -= dt;
      if (o.thoughtHoldTimer <= 0) {
        o.thoughtPhase = 'fadeout';
        if (o.role === VOICE && o.ideaReady) {
          o.ideaReady = false; o.ideaTokens = 0; // idea expressed, reset
        }
      }
    } else if (o.thoughtPhase === 'fadeout') {
      o.thoughtAlpha = Math.max(0, o.thoughtAlpha - dt/600);
      if (o.thoughtAlpha <= 0) { o.thoughtPhase = 'hidden'; o.thought = null; }
    }
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  DOM INTEREST SCAN
  // ══════════════════════════════════════════════════════════════════════════════
  let domTimer = 0;
  function scanDOMInterest(dt) {
    domTimer += dt;
    if (domTimer < 1800) return;
    domTimer = 0;
    orbs.forEach(o => {
      if (o === dragOrb || o.x <= 0 || o.absorbed) return;
      const label = Brain.elementUnder(o.x, o.y);
      o.interestTarget = label;
      o.interestLevel = lerp(o.interestLevel, label ? 1 : 0, 0.25);
      // Feed contextual signals into Voice so it can surface ideas
      const signals = Brain.popSignals(o.role);
      const voice = orbs[VOICE];
      signals.forEach(s => {
        voice.ideaTokens += s.weight;
        if (voice.ideaTokens >= 10 && !voice.ideaReady) {
          voice.ideaReady = true;
          voice.thoughtCooldown = rand(3000, 6000); // show thought soon
        }
      });
    });
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  CONNECTIONS
  // ══════════════════════════════════════════════════════════════════════════════
  function drawConnections() {
    const MAX = Math.min(W,H)*0.36;
    for (let i=0;i<orbs.length;i++) for (let j=i+1;j<orbs.length;j++) {
      const a=orbs[i], b=orbs[j];
      if (a.absorbed || b.absorbed) continue;
      const d=dist(a.x,a.y,b.x,b.y);
      if (d>=MAX) continue;
      const alpha=(1-d/MAX)*0.08*((a.z+b.z)*0.5);
      ctx.save();
      const g=ctx.createLinearGradient(a.x,a.y,b.x,b.y);
      g.addColorStop(0,ACCENT); g.addColorStop(1,GLOW_A);
      ctx.strokeStyle=g; ctx.lineWidth=0.5; ctx.globalAlpha=alpha;
      ctx.shadowColor=ACCENT; ctx.shadowBlur=3; ctx.setLineDash([3,8]);
      ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke(); ctx.restore();
    }
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  TRAILS
  // ══════════════════════════════════════════════════════════════════════════════
  function updateTrail(o) {
    const spd=Math.sqrt(o.vx*o.vx+o.vy*o.vy);
    if (spd>0.7){o.trail.push({x:o.x,y:o.y,spd});if(o.trail.length>16)o.trail.shift();}
    else if (o.trail.length>0) o.trail.shift();
  }
  function drawTrail(o) {
    if (o.absorbed) return;
    for (let i=0;i<o.trail.length;i++){
      const p=o.trail[i], frac=i/o.trail.length;
      const speedScale = clamp((Number(p.spd || 0) / (MAX_SPD * 2.2 || 1)), 0.35, 1.4);
      const radius = Math.max(0.9, o.r * frac * 0.2 * speedScale);
      ctx.save();
      ctx.beginPath();
      ctx.arc(p.x,p.y,radius,0,Math.PI*2);
      ctx.fillStyle = i === o.trail.length - 1 ? '#fff' : ACCENT;
      ctx.globalAlpha = frac * 0.16 * o.z * speedScale;
      ctx.shadowColor = ACCENT;
      ctx.shadowBlur = 6 + speedScale * 8;
      ctx.setLineDash([]);
      ctx.fill();
      if (speedScale > 0.7) {
        ctx.beginPath();
        ctx.arc(p.x + rand(-1.8, 1.8), p.y + rand(-1.8, 1.8), Math.max(0.55, radius * 0.5), 0, Math.PI * 2);
        ctx.globalAlpha = frac * 0.11 * o.z;
        ctx.fillStyle = '#fff';
        ctx.fill();
      }
      ctx.restore();
    }
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  PRIMITIVES
  // ══════════════════════════════════════════════════════════════════════════════
  function dot(x,y,r,color,blur){
    ctx.save();ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);
    ctx.fillStyle=color;ctx.shadowColor=color;ctx.shadowBlur=blur;
    ctx.globalAlpha=1;ctx.setLineDash([]);ctx.fill();ctx.restore();
  }
  function polygon(cx,cy,r,n,rot,color,lw,alpha){
    ctx.save();ctx.translate(cx,cy);ctx.rotate(rot);ctx.beginPath();
    for(let i=0;i<n;i++){const a=(i/n)*Math.PI*2-Math.PI/2;i===0?ctx.moveTo(Math.cos(a)*r,Math.sin(a)*r):ctx.lineTo(Math.cos(a)*r,Math.sin(a)*r);}
    ctx.closePath();ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.globalAlpha=alpha;
    ctx.shadowColor=color;ctx.shadowBlur=14;ctx.setLineDash([]);ctx.stroke();ctx.restore();
  }

  // ── 3D wireframe helpers ─────────────────────────────────────────────────────
  // Unit-sphere point rotated by yaw (Y-axis, left/right) then pitch (X-axis, up/down).
  // Returns projected screen {x,y} plus normalized z in [-1..1] for depth cues.
  function proj3(o, ux, uy, uz, yaw, pitch, R){
    const cy=Math.cos(yaw),  sy=Math.sin(yaw);
    const cp=Math.cos(pitch),sp=Math.sin(pitch);
    // Yaw around Y: (x,z)
    let x1 = ux*cy + uz*sy;
    let z1 = -ux*sy + uz*cy;
    const y1 = uy;
    // Pitch around X: (y,z)
    const y2 = y1*cp - z1*sp;
    const z2 = y1*sp + z1*cp;
    // Orthographic projection with a tiny perspective squash (front bigger)
    const persp = 1 + z2*0.18;
    return { x: o.x + x1*R*persp, y: o.y + y2*R*persp, z: z2 };
  }
  // Depth-based alpha: front faces bright, back faces dim (never fully hidden).
  function zAlpha(z, front, back){ const k=(z+1)*0.5; return back + (front-back)*k; }
  function zLW(z, front, back){ const k=(z+1)*0.5; return back + (front-back)*k; }

  // Stroke a 3D-polyline on the unit sphere (points in [-1..1] cube, projected).
  function strokePath3(o, pts, yaw, pitch, R, color, baseLW, baseAlpha, closed){
    if (pts.length < 2) return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 6;
    ctx.setLineDash([]);
    // Sample 2 projected points to compute avg depth per segment
    let prev = proj3(o, pts[0][0], pts[0][1], pts[0][2], yaw, pitch, R);
    for (let i=1;i<pts.length;i++){
      const p = proj3(o, pts[i][0], pts[i][1], pts[i][2], yaw, pitch, R);
      const avgZ = (prev.z + p.z) * 0.5;
      ctx.globalAlpha = baseAlpha * zAlpha(avgZ, 1.0, 0.22);
      ctx.lineWidth = baseLW * zLW(avgZ, 1.0, 0.55);
      ctx.beginPath();
      ctx.moveTo(prev.x, prev.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      prev = p;
    }
    if (closed){
      const p0 = proj3(o, pts[0][0], pts[0][1], pts[0][2], yaw, pitch, R);
      const avgZ = (prev.z + p0.z)*0.5;
      ctx.globalAlpha = baseAlpha * zAlpha(avgZ, 1.0, 0.22);
      ctx.lineWidth = baseLW * zLW(avgZ, 1.0, 0.55);
      ctx.beginPath(); ctx.moveTo(prev.x, prev.y); ctx.lineTo(p0.x, p0.y); ctx.stroke();
    }
    ctx.restore();
  }

  // Latitude ring at given polar angle φ (0 = equator, ±π/2 = poles).
  function latitudePts(phi, samples){
    const pts = new Array(samples);
    const y = Math.sin(phi);
    const rr = Math.cos(phi);
    for (let i=0;i<samples;i++){
      const th = (i/samples)*Math.PI*2;
      pts[i] = [Math.cos(th)*rr, y, Math.sin(th)*rr];
    }
    return pts;
  }
  // Longitude meridian at given azimuth θ.
  function longitudePts(theta, samples){
    const pts = new Array(samples);
    const ct = Math.cos(theta), st = Math.sin(theta);
    for (let i=0;i<samples;i++){
      const phi = -Math.PI/2 + (i/(samples-1))*Math.PI;
      const y = Math.sin(phi), rr = Math.cos(phi);
      pts[i] = [ct*rr, y, st*rr];
    }
    return pts;
  }

  function eyeDot(o, r, color, blur) {
    dot(o.x, o.y, r, color, blur);
    if (o.settled < 0.1) return;
    const offset = o.r * 0.24 * o.settled;
    const ex = o.x + Math.cos(o.watchAngle)*offset;
    const ey = o.y + Math.sin(o.watchAngle)*offset;
    ctx.save(); ctx.beginPath(); ctx.arc(ex,ey,r*0.52,0,Math.PI*2);
    ctx.fillStyle='#fff'; ctx.globalAlpha=0.88*o.settled; ctx.shadowColor=color; ctx.shadowBlur=8; ctx.fill(); ctx.restore();
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  DRAW STYLES — all render as rotating 3D wireframes (yaw around Y,
  //  pitch around X). Depth fades back-facing strokes so the sphere reads true.
  // ══════════════════════════════════════════════════════════════════════════════
  function drawRings(o,t){
    // Globe: 5 latitude rings + 8 longitude meridians
    const R = o.r, yaw = o.yaw, pitch = o.pitch;
    const lats = [-Math.PI/3, -Math.PI/6, 0, Math.PI/6, Math.PI/3];
    lats.forEach((phi,i)=>{
      const col = i===2 ? ACCENT : GLOW_A;
      strokePath3(o, latitudePts(phi, 48), yaw, pitch, R*0.96, col, 1.2, 0.65, true);
    });
    const MERIDIANS = 8;
    for (let i=0;i<MERIDIANS;i++){
      const th = (i/MERIDIANS)*Math.PI*2;
      strokePath3(o, longitudePts(th, 28), yaw, pitch, R*0.96, ACCENT, 1.0, 0.55, false);
    }
    // Core bead
    dot(o.x, o.y, 3.2, ACCENT, 22);
    eyeDot(o, 4, ACCENT, 28);
  }

  function drawMandala(o,t){
    // Four great-circles tilted at 45° intervals, plus a slow equator ring.
    const R = o.r, yaw = o.yaw, pitch = o.pitch;
    const rings = [0, Math.PI/4, Math.PI/2, 3*Math.PI/4];
    rings.forEach((roll,i)=>{
      // Build a great circle with an in-plane roll applied before yaw/pitch.
      const pts = [];
      const samples = 56;
      const cr = Math.cos(roll), sr = Math.sin(roll);
      for (let j=0;j<samples;j++){
        const a = (j/samples)*Math.PI*2;
        const x0 = Math.cos(a), y0 = Math.sin(a)*cr, z0 = Math.sin(a)*sr;
        pts.push([x0,y0,z0]);
      }
      const col = i%2===0 ? ACCENT : GLOW_A;
      strokePath3(o, pts, yaw, pitch, R*0.96, col, 1.1, 0.55, true);
    });
    // Inner small polygon billboarded to face viewer
    polygon(o.x,o.y,R*0.22,6,t*0.8,ACCENT,1.6,0.8);
    eyeDot(o, 4, ACCENT, 28);
  }

  function drawHelix(o,t){
    // Double helix wrapped around the sphere axis.
    const R = o.r, yaw = o.yaw, pitch = o.pitch;
    const TURNS = 3, SAMPLES = 140;
    for (let strand=0; strand<2; strand++){
      const pts = [];
      const offset = strand * Math.PI;
      for (let i=0;i<SAMPLES;i++){
        const u = i/(SAMPLES-1);           // 0..1 along axis
        const y = -1 + 2*u;                // -1..1
        const rr = Math.sqrt(Math.max(0, 1 - y*y)); // sphere radius at height
        const ang = u*TURNS*Math.PI*2 + offset + t*1.2;
        pts.push([Math.cos(ang)*rr, y, Math.sin(ang)*rr]);
      }
      strokePath3(o, pts, yaw, pitch, R*0.94, strand===0?ACCENT:GLOW_A, 1.4, 0.7, false);
    }
    // Equator ring for reference
    strokePath3(o, latitudePts(0, 48), yaw, pitch, R*0.96, GLOW_B, 0.8, 0.35, true);
    eyeDot(o, 4.5, ACCENT, 30);
  }

  function drawCrystal(o,t){
    // Icosahedron-like wireframe: 12 vertices of an icosahedron with edges.
    const R = o.r, yaw = o.yaw, pitch = o.pitch;
    const phi = (1 + Math.sqrt(5))/2;
    const s = 1/Math.sqrt(1 + phi*phi);   // normalize
    const a = s, b = s*phi;
    const V = [
      [ 0,  a,  b], [ 0,  a, -b], [ 0, -a,  b], [ 0, -a, -b],
      [ a,  b,  0], [ a, -b,  0], [-a,  b,  0], [-a, -b,  0],
      [ b,  0,  a], [ b,  0, -a], [-b,  0,  a], [-b,  0, -a],
    ];
    // Edges: pairs of vertex indices (30 edges of icosahedron)
    const E = [
      [0,4],[0,6],[0,8],[0,10],[0,2],
      [1,4],[1,6],[1,9],[1,11],[1,3],
      [2,8],[2,10],[2,5],[2,7],
      [3,9],[3,11],[3,5],[3,7],
      [4,8],[4,9],[4,6],
      [5,8],[5,9],[5,7],
      [6,10],[6,11],
      [7,10],[7,11],
      [8,9],[10,11],
    ];
    // Pre-project all vertices
    const P = V.map(v => proj3(o, v[0], v[1], v[2], yaw, pitch, R*0.95));
    ctx.save();
    ctx.strokeStyle = ACCENT;
    ctx.shadowColor = ACCENT;
    ctx.shadowBlur = 8;
    ctx.setLineDash([]);
    E.forEach(ed => {
      const p1 = P[ed[0]], p2 = P[ed[1]];
      const avgZ = (p1.z + p2.z) * 0.5;
      ctx.globalAlpha = 0.7 * zAlpha(avgZ, 1.0, 0.18);
      ctx.lineWidth = 1.2 * zLW(avgZ, 1.0, 0.45);
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    });
    // Vertex dots scaled by depth
    P.forEach(p => {
      const a2 = zAlpha(p.z, 1.0, 0.25);
      ctx.globalAlpha = a2;
      ctx.beginPath(); ctx.arc(p.x, p.y, 1.8*zLW(p.z,1.2,0.5), 0, Math.PI*2);
      ctx.fillStyle = p.z > 0 ? '#fff' : ACCENT;
      ctx.shadowBlur = 10; ctx.fill();
    });
    ctx.restore();
    eyeDot(o, 3.6, ACCENT, 24);
  }

  function drawLissajous(o,t){
    // 3D Lissajous on the sphere surface — parametric (θ,φ) traced as a knot.
    const R = o.r, yaw = o.yaw, pitch = o.pitch;
    const A=3, B=2, C=2, delta=t*0.36;
    const SAMPLES=260;
    const pts = [];
    for (let i=0;i<=SAMPLES;i++){
      const u = (i/SAMPLES)*Math.PI*2;
      const theta = A*u + delta;          // azimuth
      const phi   = Math.sin(B*u)*0.8;    // polar
      const rr = Math.cos(phi);
      pts.push([Math.cos(theta)*rr, Math.sin(phi), Math.sin(theta)*rr]);
    }
    strokePath3(o, pts, yaw, pitch, R*0.92, ACCENT, 1.5, 0.7, true);
    // Second inverted curve
    const pts2 = [];
    for (let i=0;i<=SAMPLES;i++){
      const u = (i/SAMPLES)*Math.PI*2;
      const theta = C*u - delta;
      const phi   = Math.cos(B*u)*0.6;
      const rr = Math.cos(phi);
      pts2.push([Math.cos(theta)*rr, Math.sin(phi), Math.sin(theta)*rr]);
    }
    strokePath3(o, pts2, yaw, pitch, R*0.92, GLOW_A, 1.0, 0.45, true);
    eyeDot(o, 4, ACCENT, 28);
  }

  function drawVortex(o,t){
    // Fibonacci / phyllotaxis sphere: N points spiral-distributed, drawn as dots
    // with depth cues; a faint spiral arm connects them.
    const R = o.r, yaw = o.yaw, pitch = o.pitch;
    const N = 120;
    const GOLDEN = Math.PI * (3 - Math.sqrt(5));
    const pts = [];
    for (let i=0;i<N;i++){
      const y = 1 - (i/(N-1))*2;
      const rr = Math.sqrt(Math.max(0, 1 - y*y));
      const theta = i*GOLDEN + t*0.5;
      pts.push([Math.cos(theta)*rr, y, Math.sin(theta)*rr]);
    }
    // Spiral arm (thin, connects consecutive points)
    strokePath3(o, pts, yaw, pitch, R*0.94, ACCENT, 0.7, 0.35, false);
    // Dots
    ctx.save(); ctx.shadowColor = ACCENT; ctx.setLineDash([]);
    pts.forEach(pp => {
      const p = proj3(o, pp[0], pp[1], pp[2], yaw, pitch, R*0.94);
      const a2 = zAlpha(p.z, 1.0, 0.20);
      const sz = 1.3 * zLW(p.z, 1.4, 0.55);
      ctx.globalAlpha = a2 * 0.9;
      ctx.fillStyle = p.z > 0.2 ? '#fff' : ACCENT;
      ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(p.x, p.y, sz, 0, Math.PI*2); ctx.fill();
    });
    ctx.restore();
    eyeDot(o, 3.4, ACCENT, 22);
  }

  function drawPulsar(o,t){
    // Three pulsing great-circles (X/Y/Z planes) + axial beam aligned with pole.
    const R = o.r, yaw = o.yaw, pitch = o.pitch;
    const pulse = 0.85 + Math.sin(t*2.2)*0.15;
    // Great circle in XY plane (equator)
    strokePath3(o, latitudePts(0, 56), yaw, pitch, R*0.96*pulse, ACCENT, 1.6, 0.7, true);
    // XZ circle (90° roll)
    {
      const pts=[]; for(let i=0;i<56;i++){const a=(i/56)*Math.PI*2;pts.push([Math.cos(a),0,Math.sin(a)]);}
      // That's the same as equator — use a rolled variant instead:
      const pts2=[]; for(let i=0;i<56;i++){const a=(i/56)*Math.PI*2;pts2.push([Math.cos(a),Math.sin(a),0]);}
      strokePath3(o, pts2, yaw, pitch, R*0.96*pulse, GLOW_A, 1.2, 0.55, true);
    }
    // YZ circle
    {
      const pts=[]; for(let i=0;i<56;i++){const a=(i/56)*Math.PI*2;pts.push([0,Math.cos(a),Math.sin(a)]);}
      strokePath3(o, pts, yaw, pitch, R*0.96*pulse, GLOW_B, 1.2, 0.55, true);
    }
    // Axial beam through poles (north/south)
    const north = proj3(o, 0,  1.25, 0, yaw, pitch, R);
    const south = proj3(o, 0, -1.25, 0, yaw, pitch, R);
    ctx.save();
    ctx.strokeStyle = ACCENT; ctx.shadowColor = ACCENT; ctx.shadowBlur = 12;
    ctx.globalAlpha = 0.75 * pulse; ctx.lineWidth = 1.4;
    ctx.setLineDash([4,5]);
    ctx.beginPath(); ctx.moveTo(north.x,north.y); ctx.lineTo(south.x,south.y); ctx.stroke();
    ctx.restore();
    eyeDot(o, 3.8, ACCENT, 26);
  }

  const DRAW_FNS    = [drawRings, drawMandala, drawHelix, drawCrystal, drawLissajous, drawVortex, drawPulsar];
  const STYLE_NAMES = ['Rings','Mandala','Helix','Crystal','Lissajous','Vortex','Pulsar'];

  // ══════════════════════════════════════════════════════════════════════════════
  //  PHYSICS
  // ══════════════════════════════════════════════════════════════════════════════
  const FRICTION=0.976, MAX_SPD=1.6, MARGIN=0.08;

  function _applyFlee(o){
    const md = dist(o.x, o.y, mouse.x, mouse.y);
    const FLEE_R = 220;
    if (md < FLEE_R && md > 0) {
      const dx = (o.x - mouse.x) / md;
      const dy = (o.y - mouse.y) / md;
      const proximity = 1 - md / FLEE_R;
      const force = 0.28 * proximity * proximity;
      const toOrbX = o.x - mouse.x;
      const toOrbY = o.y - mouse.y;
      const chase = (mouseVX * toOrbX + mouseVY * toOrbY) / md;
      const chaseBoost = chase > 3 ? chase * 0.12 : 0;
      o.vx += dx * (force + chaseBoost);
      o.vy += dy * (force + chaseBoost);
      o.settled = 0;
    }
    if (mouseStillPos && md > FLEE_R) {
      // Only tug back to roost while the user is busy on screen. When idle,
      // orbs are free to wander and explore.
      if (!Brain.ctx.userBusy) return;
      const rd = dist(o.x, o.y, o.roostX, o.roostY);
      if (rd > 30) {
        const pull = Math.min(rd * 0.0006, 0.03);
        o.vx += (o.roostX - o.x) * pull;
        o.vy += (o.roostY - o.y) * pull;
      }
    }
  }

  function behaviorEye(o,dt){
    _applyFlee(o);
    const mouseSpeed = Math.hypot(mouseVX, mouseVY);
    if (mouseSpeed > 8.5) {
      o.state = 'alert';
      o.stateTimer = 1400;
    } else if (o.state === 'alert') {
      o.stateTimer -= dt;
      if (o.stateTimer <= 0) o.state = 'idle';
    }
    if (Math.random() < 0.002) o.driftAngle += rand(-0.45, 0.45);
    o.vx += Math.cos(o.driftAngle) * 0.0035;
    o.vy += Math.sin(o.driftAngle) * 0.0035;
    const scanX = W * 0.22 + Math.cos(o.watchAngle + dt * 0.0003) * 36;
    const scanY = H * 0.20 + Math.sin(o.watchAngle + dt * 0.0005) * 28;
    o.vx += (scanX - o.x) * 0.0008;
    o.vy += (scanY - o.y) * 0.0008;
  }

  function behaviorEcho(o,dt){
    _applyFlee(o);
    const mouseSpeed = Math.hypot(mouseVX, mouseVY);
    if (o.state === 'investigating' && o.snoopTarget) {
      const dx = o.snoopTarget.x - o.x;
      const dy = o.snoopTarget.y - o.y;
      const d = Math.hypot(dx, dy) || 1;
      if (d > 24) {
        o.vx += (dx / d) * 0.010;
        o.vy += (dy / d) * 0.010;
      }
      o.stateTimer -= dt;
      if (o.stateTimer <= 0 || d < 24) {
        o.state = 'recalling';
        o.snoopTarget = null;
        o.stateTimer = rand(1800, 3200);
      }
      return;
    }
    if (mouseStillPos && mouseSpeed < 1.2 && o.stateTimer <= 0) {
      o.state = 'investigating';
      o.snoopTarget = {
        x: mouseStillPos.x + rand(-38, 38),
        y: mouseStillPos.y + rand(-38, 38),
      };
      o.stateTimer = rand(2400, 5600);
      return;
    }
    if (Math.random() < 0.003) o.driftAngle += rand(-0.7, 0.7);
    const prowl = o.interestTarget === 'chat' ? 0.0055 : 0.0040;
    o.vx += Math.cos(o.driftAngle) * prowl;
    o.vy += Math.sin(o.driftAngle) * prowl;
    o.state = 'recalling';
    o.stateTimer -= dt;
    if (o.stateTimer <= 0) o.stateTimer = rand(1400, 2600);
  }

  function behaviorThread(o,dt){
    _applyFlee(o);
    o.patrolAngle += 0.00022 * dt;
    const orbitR = Math.min(W, H) * 0.17;
    const tx = W * 0.5 + Math.cos(o.patrolAngle) * orbitR;
    const ty = H * 0.54 + Math.sin(o.patrolAngle * 1.4) * orbitR * 0.42;
    o.vx += (tx - o.x) * 0.0010;
    o.vy += (ty - o.y) * 0.0010;
    if (Brain.ctx.openWindows > 3 || Brain.ctx.hasErrors) {
      o.state = 'reasoning';
      o.vx += (W * 0.5 - o.x) * 0.0007;
      o.vy += (H * 0.52 - o.y) * 0.0007;
    } else {
      o.state = 'weaving';
    }
  }

  function behaviorPulse(o,dt){
    _applyFlee(o);
    o.driftPhase += dt * 0.0024;
    const rhythm = 0.0035 + (Brain.ctx.agentsBusy ? 0.0022 : 0);
    if (Brain.ctx.userBusy) {
      const tx = o.roostX + Math.cos(o.driftPhase) * (o.baseR * 0.9);
      const ty = o.roostY + Math.sin(o.driftPhase * 1.3) * (o.baseR * 0.55);
      o.vx += (tx - o.x) * 0.0012;
      o.vy += (ty - o.y) * 0.0012;
    } else {
      // Idle: roam in larger arcs across the screen instead of orbiting roost.
      const rx = W * (0.5 + Math.cos(o.driftPhase * 0.7) * 0.32);
      const ry = H * (0.5 + Math.sin(o.driftPhase * 0.5) * 0.32);
      o.vx += (rx - o.x) * 0.0006;
      o.vy += (ry - o.y) * 0.0006;
    }
    o.vx += Math.cos(o.driftPhase * 2.1) * rhythm;
    o.vy += Math.sin(o.driftPhase * 1.8) * rhythm;
    o.state = Brain.ctx.agentsBusy || Brain.ctx.pendingMessages > 0 ? 'active' : 'steady';
  }

  function behaviorVoice(o,dt){
    _applyFlee(o);
    const drift = o.ideaReady ? 0.0018 : 0.0011;
    if (Brain.ctx.userBusy) {
      const anchorX = lerp(o.roostX, W * 0.58, 0.45);
      const anchorY = lerp(o.roostY, H * 0.34, 0.45);
      o.vx += (anchorX - o.x) * drift;
      o.vy += (anchorY - o.y) * drift;
    }
    if (o.ideaReady) {
      o.state = 'speaking';
      o.vx += Math.cos(o.driftPhase + dt * 0.001) * 0.0042;
      o.vy += Math.sin(o.driftPhase + dt * 0.0014) * 0.0038;
    } else {
      o.state = 'composing';
      if (Math.random() < 0.0012) o.driftAngle += rand(-0.35, 0.35);
      // Wider wander when idle so VOICE drifts across the screen.
      const wander = Brain.ctx.userBusy ? 0.0030 : 0.0050;
      o.vx += Math.cos(o.driftAngle) * wander;
      o.vy += Math.sin(o.driftAngle) * wander;
    }
  }

  function applyVoicePull(){
    const voice = orbs[VOICE];
    if (!voice || voice.absorbed || voice.fighting || voice.settled < 0.2) return;
    for (let i = 0; i < orbs.length; i++) {
      if (i === VOICE) continue;
      const o = orbs[i];
      if (o.absorbed || o.fighting) continue;
      const pull = Math.max(voice.settled - 0.25, 0) * 0.0008;
      if (pull < 0.0001) continue;
      const dx = voice.x - o.x;
      const dy = voice.y - o.y;
      const d = Math.hypot(dx, dy) || 1;
      if (d > 90) {
        o.vx += (dx / d) * pull;
        o.vy += (dy / d) * pull;
      }
    }
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  MERGE / FIGHT
  // ══════════════════════════════════════════════════════════════════════════════
  function tryMerge(a, b) {
    if (a.absorbed || b.absorbed || a.fighting || b.fighting) return;
    const compat = getCompat(a, b);
    if (compat === 'love') {
      // Merge: a absorbs b (a is the one being dropped onto b, b is target)
      const absorber = a.baseR >= b.baseR ? a : b;
      const absorbed = absorber === a ? b : a;
      absorbed.absorbed = true;
      absorbed.absorber = absorber;
      absorber.mergedFrom = absorbed;
      absorber.mergedName = getMergedName(a, b);
      // Absorber grows
      absorber.sizeBonus = Math.min(absorber.sizeBonus + 0.28, 0.6);
      absorber.ideaTokens += 4; // absorbing gives ideas
      // Merge animation: burst + the absorbed orb flies to absorber
      ringBurst((a.x+b.x)/2, (a.y+b.y)/2);
      burst((a.x+b.x)/2, (a.y+b.y)/2, 28, 1.3);
      absorbed.vx = (absorber.x - absorbed.x) * 0.15;
      absorbed.vy = (absorber.y - absorbed.y) * 0.15;
      absorber.settled = 0;
      if (typeof showToast === 'function')
        showToast(absorber.mergedName + ' formed!', 'info');
    } else if (compat === 'fight') {
      // Fight: they orbit each other then push apart
      a.fighting = true; b.fighting = true;
      a.fightPartner = b; b.fightPartner = a;
      a.fightTimer = rand(3000, 5000); b.fightTimer = a.fightTimer;
      a.fightAngle = rand(0,Math.PI*2); b.fightAngle = a.fightAngle + Math.PI;
      a.settled = 0; b.settled = 0;
      burst((a.x+b.x)/2,(a.y+b.y)/2,14,0.9);
    } else {
      // Neutral: friendly bump
      const dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||1;
      a.vx-=(dx/d)*0.8; a.vy-=(dy/d)*0.8;
      b.vx+=(dx/d)*0.8; b.vy+=(dy/d)*0.8;
      burst((a.x+b.x)/2,(a.y+b.y)/2,8,0.5);
    }
  }

  function tickFight(o, dt) {
    if (!o.fighting || !o.fightPartner) return;
    const p = o.fightPartner;
    o.fightTimer -= dt;
    // Orbit partner
    o.fightAngle += 0.05;
    const center = { x:(o.x+p.x)/2, y:(o.y+p.y)/2 };
    const orbitR = (o.baseR + p.baseR) * 0.7;
    const tx = center.x + Math.cos(o.fightAngle)*orbitR;
    const ty = center.y + Math.sin(o.fightAngle)*orbitR;
    o.vx += (tx-o.x)*0.06; o.vy += (ty-o.y)*0.06;
    // 3D spin
    o.tiltX = Math.sin(o.fightAngle*2) * 0.55;
    o.tiltY = Math.cos(o.fightAngle*1.5) * 0.55;
    // Occasional impact flash
    if (Math.random() < 0.015) {
      burst(o.x, o.y, 5, 0.6);
      o.flash = 0.6; p.flash = 0.6;
    }
    if (o.fightTimer <= 0) {
      // Fight over — shrink slightly, push apart
      o.sizeBonus = Math.max(o.sizeBonus - 0.12, -0.2);
      const dx=o.x-p.x, dy=o.y-p.y, d=Math.sqrt(dx*dx+dy*dy)||1;
      o.vx += (dx/d)*1.5; o.vy += (dy/d)*1.5;
      o.fighting = false; o.fightPartner = null;
      o.tiltX = 0; o.tiltY = 0;
    }
  }

  function tickAbsorbed(o) {
    if (!o.absorbed || !o.absorber) return;
    // Fly toward absorber centre
    const absorber = o.absorber;
    const dx = absorber.x - o.x, dy = absorber.y - o.y;
    const d = Math.sqrt(dx*dx+dy*dy)||1;
    if (d > 3) {
      o.x += (dx/d) * Math.min(d*0.18, 4);
      o.y += (dy/d) * Math.min(d*0.18, 4);
    }
    o.vx = 0; o.vy = 0;
    // Match absorber z
    o.z = absorber.z;
  }

  // Split a merged orb (click to eject absorbed)
  function splitOrb(absorber) {
    const absorbed = absorber.mergedFrom;
    if (!absorbed) return;
    absorbed.absorbed = false; absorbed.absorber = null;
    absorber.mergedFrom = null; absorber.mergedName = null;
    absorber.sizeBonus = Math.max(0, absorber.sizeBonus - 0.28);
    // Eject with velocity
    const angle = rand(0, Math.PI*2);
    absorbed.vx = Math.cos(angle) * 2; absorbed.vy = Math.sin(angle) * 2;
    absorbed.x = absorber.x + Math.cos(angle) * (absorber.r + absorbed.baseR + 10);
    absorbed.y = absorber.y + Math.sin(angle) * (absorber.r + absorbed.baseR + 10);
    absorbed.settled = 0; absorber.settled = 0;
    burst(absorber.x, absorber.y, 18, 1.1);
    if (typeof showToast === 'function') showToast('Orbs split!', 'info');
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  PER-ORB UPDATE
  // ══════════════════════════════════════════════════════════════════════════════
  function updateOrb(o, i, dt) {
    // Absorbed orbs just track their absorber
    if (o.absorbed) { tickAbsorbed(o); tickThought(o, dt); return; }
    if (o === dragOrb) {
      o.breathPhase += 0.011;
      o.r = (o.baseR*(1+o.sizeBonus)) * (0.4+o.z*0.85) * (1+0.055*Math.sin(o.breathPhase));
      if(o.flash>0)o.flash-=0.038;
      return;
    }

    // Fight tick (overrides normal behavior)
    if (o.fighting) { tickFight(o, dt); }
    // Skip the behavior tick (and its roost spring force) for ~thrownTimer ms
    // after a release flick — otherwise the per-frame pull toward the roost
    // out-muscles the throw velocity and the orb plops back next to its base.
    else if (!sleeping && o.placedTimer <= 0 && !(o.thrownTimer > 0)) {
      switch(o.role){
        case EYE:    behaviorEye(o,dt);    break;
        case ECHO:   behaviorEcho(o,dt);   break;
        case THREAD: behaviorThread(o,dt); break;
        case PULSE:  behaviorPulse(o,dt);  break;
        case VOICE:  behaviorVoice(o,dt);  break;
      }
      // Personality morph target — tied to behavioral state per role
      const wantsAlt = (
        (o.role === EYE    && o.state === 'alert') ||
        (o.role === ECHO   && (o.state === 'recalling' || o.state === 'investigating')) ||
        (o.role === THREAD && (o.state === 'reasoning' || o.state === 'weaving')) ||
        (o.role === PULSE  && o.state === 'active') ||
        (o.role === VOICE  && (o.state === 'speaking' || o.ideaReady))
      );
      o.morphTarget = wantsAlt ? 1 : 0;
      // Roost pull when drifting slowly \u2014 only while user is busy.
      // When idle, orbs explore freely instead of being yanked back to base.
      if (Brain.ctx.userBusy) {
        const spd0=Math.sqrt(o.vx*o.vx+o.vy*o.vy);
        const pull=Math.max(0,0.42-spd0)*0.0015;
        if(pull>0.0001){o.vx+=(o.roostX-o.x)*pull;o.vy+=(o.roostY-o.y)*pull;}
      }
    }
    if (o.placedTimer > 0) { o.placedTimer -= dt; o.vx *= 0.90; o.vy *= 0.90; }

    // Boundary
    const m=Math.min(W,H)*MARGIN;
    if(o.x<m)o.vx+=0.08;if(o.x>W-m)o.vx-=0.08;if(o.y<m)o.vy+=0.08;if(o.y>H-m)o.vy-=0.08;
    if(sleeping){o.vx*=0.92;o.vy*=0.92;}
    o.vx*=FRICTION;o.vy*=FRICTION;
    const spd=Math.sqrt(o.vx*o.vx+o.vy*o.vy);
    // Recently-thrown orbs may exceed MAX_SPD until friction brings them back.
    // Without this allowance, a release flick is clamped to 1.6 px/frame and
    // friction kills it inside half a second — the orb "plops" instead of flying.
    if (o.thrownTimer && o.thrownTimer > 0) { o.thrownTimer -= dt; }
    const cap = (o.thrownTimer && o.thrownTimer > 0) ? MAX_SPD * 4 : MAX_SPD;
    if(spd>cap){o.vx=o.vx/spd*cap;o.vy=o.vy/spd*cap;}
    o.x+=o.vx;o.y+=o.vy;

    // Depth
    o.z+=o.vz;
    if(o.z>1.0){o.z=1.0;o.vz=-Math.abs(o.vz)*rand(0.8,1.2);}
    if(o.z<0.25){o.z=0.25;o.vz=Math.abs(o.vz)*rand(0.8,1.2);}
    if(Math.random()<0.002)o.vz+=rand(-0.0002,0.0002);
    o.vz=clamp(o.vz,-0.0013,0.0013);

    // Settled
    o.settled=lerp(o.settled,spd<0.20?1:0,0.007);

    // Morph ease (~1400ms full transit for a softer mood cross-fade;
    // the render layer additionally applies a smoothstep curve).
    const morphStep = Math.min(1, dt * 0.0007);
    o.morphPhase = lerp(o.morphPhase, o.morphTarget, morphStep);

    // 3D rotation integration — yaw (left/right) and pitch (up/down).
    // Rates scale slightly with motion so active orbs visibly spin more.
    const rotBoost = 1 + Math.min(spd/MAX_SPD, 1.0)*0.6 + (o.interestLevel*0.3);
    o.yaw   = (o.yaw   + o.yawSpd   * (dt*0.001) * rotBoost) % (Math.PI*2);
    o.pitch = o.pitch + o.pitchSpd * (dt*0.001) * rotBoost;
    // Gentle pitch re-centering so it wobbles rather than flips
    o.pitch += (0 - o.pitch) * 0.0015;

    // Tilt recovery
    if(!o.fighting){o.tiltX=lerp(o.tiltX,0,0.05);o.tiltY=lerp(o.tiltY,0,0.05);}

    // Breathing
    const breathRate=lerp(0.011,0.004,o.settled);
    const breathAmp=lerp(0.05,0.09,o.settled);
    o.breathPhase+=breathRate;
    const sizeScale=(1+o.interestLevel*0.07)*(sleeping?0.84:1);
    o.r=(o.baseR*(1+o.sizeBonus))*(0.4+o.z*0.85)*(1+breathAmp*Math.sin(o.breathPhase))*sizeScale;

    // Watch angle
    const targetWatch=Math.atan2(mouse.y-o.y,mouse.x-o.x);
    let diff=targetWatch-o.watchAngle;
    while(diff>Math.PI)diff-=Math.PI*2;while(diff<-Math.PI)diff+=Math.PI*2;
    o.watchAngle+=diff*lerp(0.007,0.0015,o.settled);

    if(o.flash>0)o.flash-=0.036;
    updateTrail(o);
    tickThought(o, dt);
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  RENDER
  // ══════════════════════════════════════════════════════════════════════════════
  function renderOrb(o, t) {
    // Dormant orbs: nearly invisible, skip when fully dormant
    if (o.dormant && o.dormantAlpha < 0.02) return;

    if (o.absorbed) {
      // Draw at reduced opacity as it spirals in
      const d=dist(o.x,o.y,o.absorber.x,o.absorber.y);
      const fade=Math.min(1,d/(o.absorber.r*2));
      if(fade<0.05)return;
      ctx.save(); ctx.globalAlpha=fade*0.3;
      const animSpeed=o.speed*0.5;
      DRAW_FNS[o.style%DRAW_FNS.length](o,t*animSpeed);
      ctx.restore();
      return;
    }

    const dormFade = 1.0;

    const baseAlpha=sleeping?(0.12+o.z*0.18):(0.30+o.z*0.42);
    const boost=o.interestLevel*0.10+(o.role===EYE&&o.state==='alert'?0.14:0)+(o.ideaReady?0.12:0);

    // ── Low-graphics mode ─────────────────────────────────────────────────────
    // Skip 3D wireframes, tilt, morph cross-fade, and trails. Render each orb
    // as a flat ringed disc with a soft glow. Cheap, readable, and friendly
    // to integrated graphics / CPU-only rendering.
    if (_orbQuality === 'low') {
      // 2D versions of the same 7 shapes — cheaper than 3D wireframes,
      // but each voice still has a recognizable silhouette.
      ctx.save();
      ctx.globalAlpha = Math.min(baseAlpha + boost, 0.88);
      ctx.shadowColor = ACCENT;
      ctx.shadowBlur = 14;
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 1.3;
      ctx.setLineDash([]);
      const r = o.r * 0.92;
      const styleIdx = ((o.style|0) % 7 + 7) % 7;
      const phase = (t * o.speed) % (Math.PI * 2);
      switch (styleIdx) {
        case 0: { // Rings -> concentric arcs
          ctx.beginPath(); ctx.arc(o.x, o.y, r,        0, Math.PI*2); ctx.stroke();
          ctx.globalAlpha *= 0.7;
          ctx.beginPath(); ctx.arc(o.x, o.y, r * 0.65, 0, Math.PI*2); ctx.stroke();
          ctx.beginPath(); ctx.arc(o.x, o.y, r * 0.32, 0, Math.PI*2); ctx.stroke();
          break;
        }
        case 1: { // Mandala -> 4-petal rose
          ctx.beginPath();
          for (let a = 0; a <= Math.PI*2 + 0.01; a += 0.08) {
            const rad = r * (0.55 + 0.45 * Math.abs(Math.cos(2 * (a + phase * 0.3))));
            const px = o.x + Math.cos(a) * rad;
            const py = o.y + Math.sin(a) * rad;
            if (a === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.stroke();
          break;
        }
        case 2: { // Helix -> sine wave across a circle
          ctx.beginPath(); ctx.arc(o.x, o.y, r, 0, Math.PI*2); ctx.stroke();
          ctx.beginPath();
          for (let i = 0; i <= 40; i++) {
            const tt = i / 40;
            const px = o.x - r + tt * 2 * r;
            const py = o.y + Math.sin(tt * Math.PI * 4 + phase) * r * 0.45;
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.stroke();
          break;
        }
        case 3: { // Crystal -> rotating hexagon
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const a = (i / 6) * Math.PI * 2 + phase * 0.3;
            const px = o.x + Math.cos(a) * r;
            const py = o.y + Math.sin(a) * r;
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.closePath(); ctx.stroke();
          break;
        }
        case 4: { // Lissajous -> 3:2 figure
          ctx.beginPath();
          for (let i = 0; i <= 80; i++) {
            const tt = (i / 80) * Math.PI * 2;
            const px = o.x + Math.sin(tt * 3 + phase) * r;
            const py = o.y + Math.sin(tt * 2) * r * 0.78;
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.stroke();
          break;
        }
        case 5: { // Vortex -> spiral
          ctx.beginPath();
          for (let i = 0; i <= 60; i++) {
            const tt = i / 60;
            const a = tt * Math.PI * 6 + phase * 0.4;
            const rad = r * tt;
            const px = o.x + Math.cos(a) * rad;
            const py = o.y + Math.sin(a) * rad;
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.stroke();
          break;
        }
        case 6: { // Pulsar -> ring + cross + pulsing core
          const pulse = 0.85 + Math.sin(phase * 2.2) * 0.15;
          ctx.beginPath(); ctx.arc(o.x, o.y, r * pulse, 0, Math.PI*2); ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(o.x - r, o.y); ctx.lineTo(o.x + r, o.y);
          ctx.moveTo(o.x, o.y - r); ctx.lineTo(o.x, o.y + r);
          ctx.stroke();
          ctx.fillStyle = ACCENT;
          ctx.beginPath(); ctx.arc(o.x, o.y, 3 * pulse, 0, Math.PI*2); ctx.fill();
          break;
        }
      }
      ctx.restore();
      return;
    }

    ctx.save();

    // 3D tilt transform
    if(Math.abs(o.tiltX)>0.02||Math.abs(o.tiltY)>0.02){
      ctx.translate(o.x,o.y);
      ctx.transform(Math.cos(o.tiltY),Math.sin(o.tiltX)*0.32,-Math.sin(o.tiltY)*0.32,Math.cos(o.tiltX),0,0);
      ctx.translate(-o.x,-o.y);
    }

    ctx.globalAlpha=Math.min(baseAlpha+boost,0.88)*dormFade;
    const animSpeed=o.speed*lerp(1.0,0.24,o.settled)*(1+o.interestLevel*0.28)*(o.ideaReady?1.3:1);
    const baseG = ctx.globalAlpha;

    // Morph: cross-fade home shape ↔ alt shape based on mood (smoothstep curve).
    const mpRaw = o.morphPhase || 0;
    const mp = mpRaw*mpRaw*(3 - 2*mpRaw);  // ease-in-out smoothstep
    if (mp < 0.995) {
      ctx.globalAlpha = baseG * (1 - mp);
      DRAW_FNS[o.style % DRAW_FNS.length](o, t * animSpeed);
    }
    if (mp > 0.005 && o.altStyle !== o.style) {
      ctx.globalAlpha = baseG * mp;
      DRAW_FNS[o.altStyle % DRAW_FNS.length](o, t * animSpeed);
    }
    ctx.globalAlpha = baseG;

    // IDEAS sparkle halo
    if(o.ideaReady){
      ctx.save(); ctx.filter='none';
      for(let i=0;i<8;i++){
        const a=(i/8)*Math.PI*2+t*0.8;
        const sx=o.x+Math.cos(a)*(o.r*1.35),sy=o.y+Math.sin(a)*(o.r*1.35);
        ctx.beginPath();ctx.arc(sx,sy,1.8,0,Math.PI*2);
        ctx.fillStyle='#fff';ctx.globalAlpha=(0.5+0.35*Math.sin(t*3+i))*Math.min(baseAlpha+boost,0.88)*2;
        ctx.shadowColor=ACCENT;ctx.shadowBlur=10;ctx.fill();
      }
      ctx.restore();
    }

    // Interest halo
    if(o.interestLevel>0.2){
      ctx.save();ctx.filter='none';ctx.beginPath();ctx.arc(o.x,o.y,o.r*1.2,0,Math.PI*2);
      ctx.strokeStyle=ACCENT;ctx.lineWidth=0.9;ctx.globalAlpha=o.interestLevel*0.18;
      ctx.shadowColor=ACCENT;ctx.shadowBlur=14;ctx.setLineDash([4,6]);ctx.stroke();ctx.restore();
    }

    // Merge name label (subtle, small, above orb)
    if(o.mergedName&&o.settled>0.3){
      ctx.save();ctx.filter='none';
      ctx.font='500 9px "SF Mono",monospace';ctx.fillStyle=ACCENT;
      ctx.globalAlpha=0.35*o.settled;ctx.shadowColor=ACCENT;ctx.shadowBlur=6;
      const tw=ctx.measureText(o.mergedName).width;
      ctx.fillText(o.mergedName,o.x-tw/2,o.y-o.r-8);
      ctx.restore();
    }

    // Flash
    if(o.flash>0){
      ctx.save();ctx.filter='none';ctx.beginPath();ctx.arc(o.x,o.y,o.r*1.14,0,Math.PI*2);
      ctx.strokeStyle='#fff';ctx.lineWidth=2*o.flash;ctx.globalAlpha=o.flash*0.68;
      ctx.shadowColor='#fff';ctx.shadowBlur=20;ctx.setLineDash([]);ctx.stroke();ctx.restore();
    }

    ctx.restore();

    // Thought bubble rendered outside the 3D transform
    drawThought(o);
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  MAIN LOOP
  // ══════════════════════════════════════════════════════════════════════════════
  let lastTs=0, heatTimer=0;

  function draw(ts) {
    requestAnimationFrame(draw);
    ctx.setTransform(DPR,0,0,DPR,0,0);
    ctx.clearRect(0,0,W,H);
    if(document.body.dataset.sceneEffect==='off')return;

    readColors();
    const dt=Math.min(ts-lastTs,64); lastTs=ts; const t=ts/1000;

    Brain.update(dt);
    CouncilLink.update(dt);
    SevenLink.update(dt);
    heatTimer+=dt;
    if(heatTimer>4500){heatTimer=0;if(mouse.x>0){mouseHeat.push({x:mouse.x,y:mouse.y});if(mouseHeat.length>10)mouseHeat.shift();orbs.forEach((o,i)=>updateRoost(o,i));}}

    scanDOMInterest(dt);
    orbs.forEach((o,i)=>updateOrb(o,i,dt));
    applyVoicePull();

    // Check for merge-by-proximity (non-drag)
    for(let i=0;i<orbs.length;i++)for(let j=i+1;j<orbs.length;j++){
      const a=orbs[i],b=orbs[j];if(a.absorbed||b.absorbed||a.fighting||b.fighting)continue;
      if(dist(a.x,a.y,b.x,b.y)<(a.baseR+b.baseR)*0.35){
        // Very close — but only trigger from drag-drop (handled in mouseup)
        // Passive collisions: elastic bounce
        const dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1;
        const ov=((a.baseR+b.baseR)*0.38-d);
        if(ov>0){a.x-=(dx/d)*ov*0.5;a.y-=(dy/d)*ov*0.5;b.x+=(dx/d)*ov*0.5;b.y+=(dy/d)*ov*0.5;}
      }
    }

    drawParticles(ts);
    drawConnections();
    [...orbs].sort((a,b)=>a.z-b.z).forEach(o=>{
      if (!isOrbVisible(o.role)) return;       // hidden by user toggle
      if (_orbQuality !== 'low') drawTrail(o);  // trails are pricey on low-spec
      renderOrb(o,t);
    });
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  HIT TEST
  // ══════════════════════════════════════════════════════════════════════════════
  function orbAt(mx,my){
    return [...orbs].filter(o=>!o.absorbed).sort((a,b)=>b.z-a.z)
      .find(o=>dist(mx,my,o.x,o.y)<o.r*1.35)||null;
  }

  // ══════════════════════════════════════════════════════════════════════════════
  //  EVENTS
  // ══════════════════════════════════════════════════════════════════════════════
  // Interaction model:
  //   • mousedown on orb → drag while held → mouseup throws with release velocity
  //   • double-click on orb → carry mode: orb follows cursor with no button held
  //   • next click anywhere while carrying → drops orb there, sets it as new home
  //   • single click on orb (no drag, not carrying) → cycle shape style
  const CARRY_STYLE_SENTINEL = '__orbCarry';

  function computeThrowVelocity(history){
    // Use only the last ~140ms of drag motion for the release flick,
    // so early slow dragging doesn't dilute a fast final throw.
    if (!history || history.length < 2) return {vx:0, vy:0};
    const newest = history[history.length-1];
    const cutoff = newest.ts - 140;
    let start = history[0];
    for (let i = history.length - 2; i >= 0; i--) {
      if (history[i].ts <= cutoff) { start = history[i]; break; }
      start = history[i];
    }
    const el = Math.max(newest.ts - start.ts, 8);
    const sc = 16 / el;  // px per 16ms frame
    return {
      vx: clamp((newest.x - start.x) * sc, -MAX_SPD*3, MAX_SPD*3),
      vy: clamp((newest.y - start.y) * sc, -MAX_SPD*3, MAX_SPD*3),
    };
  }

  function setCustomHome(o, x, y){
    const mg = Math.min(W,H)*0.08;
    o.customHomeX = clamp(x, mg, W-mg);
    o.customHomeY = clamp(y, mg, H-mg);
    const i = orbs.indexOf(o);
    if (i >= 0) updateRoost(o, i);
  }

  function startCarry(orb){
    carriedOrb = orb;
    orb.placedTimer = 0;
    orb.vx = 0; orb.vy = 0;
    setOrbDragState(true);
    document.body.style.cursor = 'grabbing';
    if (typeof showToast === 'function') showToast(ROLE_NAMES[orb.role]+' picked up — click to place anchor', 'info');
  }
  function endCarry(x, y){
    if (!carriedOrb) return;
    const o = carriedOrb;
    o.x = x; o.y = y;
    o.vx = 0; o.vy = 0;
    setCustomHome(o, x, y);
    o.placedTimer = 900;  // brief settle
    burst(x, y, 12, 0.7);
    if (typeof showToast === 'function') showToast(ROLE_NAMES[o.role]+' anchored here', 'info');
    carriedOrb = null;
    setOrbDragState(false);
  }

  document.addEventListener('mousemove',function(e){
    if(document.body.dataset.sceneEffect==='off')return;
    if(dragOrb||carriedOrb)e.preventDefault();
    const now=performance.now();
    const mdt=Math.max(now-prevMT,8);
    mouseVX=lerp(mouseVX,(e.clientX-prevMX)/mdt*16,0.20);
    mouseVY=lerp(mouseVY,(e.clientY-prevMY)/mdt*16,0.20);
    prevMX=mouse.x=e.clientX;prevMY=mouse.y=e.clientY;prevMT=now;
    clearTimeout(mouseStillTimer);
    mouseStillTimer=setTimeout(()=>{mouseStillPos={x:mouse.x,y:mouse.y};},2200);
    if(sleeping)sleeping=false;
    clearTimeout(sleepTimer);sleepTimer=setTimeout(()=>{sleeping=true;},10000);
    if(dragOrb){dragOrb.x=mouse.x;dragOrb.y=mouse.y;dragHistory.push({x:mouse.x,y:mouse.y,ts:now});if(dragHistory.length>10)dragHistory.shift();updateTrail(dragOrb);}
    if(carriedOrb){carriedOrb.x=mouse.x;carriedOrb.y=mouse.y;carriedOrb.vx=0;carriedOrb.vy=0;updateTrail(carriedOrb);}
    const hit=orbAt(mouse.x,mouse.y);
    const cur=carriedOrb?'grabbing':(hit?(dragOrb?'grabbing':'grab'):'');
    if(cur!==document.body._oc){document.body._oc=cur;document.body.style.cursor=cur||'';}
  });

  document.addEventListener('mousedown',function(e){
    if(document.body.dataset.sceneEffect==='off')return;
    // If carrying, a mousedown drops the orb at this spot (single click = place).
    if(carriedOrb){
      // Don't start a drag on another orb while carrying; always drop.
      endCarry(e.clientX, e.clientY);
      e.preventDefault(); e.stopPropagation();
      return;
    }
    const hit=orbAt(e.clientX,e.clientY);
    if(hit){dragOrb=hit;dragPX=e.clientX;dragPY=e.clientY;dragHistory=[{x:e.clientX,y:e.clientY,ts:performance.now()}];hit.placedTimer=0;setOrbDragState(true);e.preventDefault();e.stopPropagation();}
  },true);

  document.addEventListener('mouseup',function(e){
    if(!dragOrb)return;
    const dropped=dragOrb;
    // Throw velocity from the final flick (last ~140ms only)
    const v = computeThrowVelocity(dragHistory);
    dropped.vx = v.vx; dropped.vy = v.vy;
    // Check if dropped onto another orb → attempt merge/fight
    let mergeTarget=null;
    orbs.forEach(other=>{
      if(other===dropped||other.absorbed)return;
      if(dist(dropped.x,dropped.y,other.x,other.y)<(dropped.r+other.r)*0.85)mergeTarget=other;
    });
    if(mergeTarget){
      tryMerge(dropped, mergeTarget);
    } else {
      const throwSpd=Math.sqrt(dropped.vx**2+dropped.vy**2);
      // Only a truly motionless release (<0.25) counts as a placement.
      // Anything above that keeps its release velocity — no more "plop".
      if(throwSpd<0.25){
        dropped.vx=0; dropped.vy=0;
        dropped.placedTimer=rand(1200,2200);
      } else {
        // Mark as recently-thrown so the per-tick velocity cap stays loose
        // for ~1.4s — friction will bring it back to MAX_SPD naturally.
        dropped.thrownTimer = 1400;
        burst(dropped.x,dropped.y,Math.round(clamp(throwSpd * 5, 10, 28)),0.85);
      }
    }
    dropped.settled=0;
    burst(dropped.x,dropped.y,10,0.6);
    dragOrb=null;dragHistory=[];
    setOrbDragState(false);
  });

  document.addEventListener('selectstart', function(e){
    if(!dragOrb && !carriedOrb) return;
    e.preventDefault();
  });

  document.addEventListener('click',function(e){
    if(document.body.dataset.sceneEffect==='off')return;
    // If a throw drag just happened, the click event still fires — ignore it when
    // the pointer moved meaningfully between mousedown and click.
    if(dist(e.clientX,e.clientY,dragPX,dragPY)>10)return;
    const hit=orbAt(e.clientX,e.clientY);
    if(!hit) { lastClickOrb = null; lastClickTS = 0; return; }

    // Double-click detection: two quick taps on the same orb.
    //   • If the orb has a custom home (was placed before) → rebase: clear
    //     custom home so it roosts at its natural base again.
    //   • Otherwise → start carry mode so the next click sets a new home.
    const now = performance.now();
    if (lastClickOrb === hit && (now - lastClickTS) < 320) {
      lastClickOrb = null; lastClickTS = 0;
      if (hit.customHomeX != null || hit.customHomeY != null) {
        hit.customHomeX = null;
        hit.customHomeY = null;
        const idx = orbs.indexOf(hit);
        if (idx >= 0) updateRoost(hit, idx);
        hit.placedTimer = 0;
        hit.settled = 0;
        burst(hit.x, hit.y, 10, 0.55);
        if (typeof showToast === 'function') showToast(ROLE_NAMES[hit.role] + ' returning home', 'info');
      } else {
        startCarry(hit);
      }
      e.preventDefault(); e.stopPropagation();
      return;
    }
    lastClickOrb = hit; lastClickTS = now;

    // Council thought dismissal
    if(hit._councilThoughtId && hit.thoughtPhase !== 'hidden'){
      CouncilLink.dismiss(hit._councilThoughtId);
      hit._councilThoughtId = null;
      hit.thoughtPhase = 'fadeout';
      hit.flash = 0.4;
      burst(hit.x, hit.y, 8, 0.5);
      if(typeof showToast==='function')showToast(ROLE_NAMES[hit.role]+' dismissed','info');
      return;
    }
    if(hit.mergedFrom){splitOrb(hit);return;}
    // Single click: cycle shape style (briefly deferred so a double-click
    // can cancel it if the user intends to pick up the orb instead).
    const targetOrb = hit;
    setTimeout(() => {
      if (lastClickOrb !== targetOrb) return; // consumed by dblclick
      targetOrb.style=(targetOrb.style+1)%DRAW_FNS.length;
      targetOrb.vx+=rand(-0.5,0.5);targetOrb.vy+=rand(-0.5,0.5);
      targetOrb.z=clamp(targetOrb.z+rand(0.1,0.22),0.25,1.0);
      targetOrb.settled=0;targetOrb.placedTimer=0;
      burst(targetOrb.x,targetOrb.y,14,0.82);
      if(typeof showToast==='function')showToast((targetOrb.mergedName||ROLE_NAMES[targetOrb.role])+' → '+STYLE_NAMES[targetOrb.style],'info');
      lastClickOrb = null; lastClickTS = 0;
    }, 330);
  },true);

  // Touch
  let lastTouch=null, lastTouchTS=0, lastTouchOrb=null;
  document.addEventListener('touchstart',e=>{
    if(document.body.dataset.sceneEffect==='off')return;
    const t=e.touches[0];lastTouch={x:t.clientX,y:t.clientY};mouse.x=t.clientX;mouse.y=t.clientY;
    if(carriedOrb){ endCarry(t.clientX, t.clientY); e.preventDefault(); return; }
    const hit=orbAt(t.clientX,t.clientY);
    if(hit){
      // Double-tap → carry mode
      const now = performance.now();
      if (lastTouchOrb === hit && (now - lastTouchTS) < 320) {
        lastTouchOrb = null; lastTouchTS = 0;
        startCarry(hit);
        e.preventDefault();
        return;
      }
      lastTouchOrb = hit; lastTouchTS = now;
      dragOrb=hit;dragPX=t.clientX;dragPY=t.clientY;dragHistory=[{x:t.clientX,y:t.clientY,ts:performance.now()}];setOrbDragState(true);e.preventDefault();
    }
  },{passive:false});
  document.addEventListener('touchmove',e=>{
    if(document.body.dataset.sceneEffect==='off')return;
    const t=e.touches[0];mouse.x=t.clientX;mouse.y=t.clientY;
    if(carriedOrb){carriedOrb.x=t.clientX;carriedOrb.y=t.clientY;carriedOrb.vx=0;carriedOrb.vy=0;updateTrail(carriedOrb);e.preventDefault();return;}
    if(dragOrb){dragOrb.x=t.clientX;dragOrb.y=t.clientY;dragHistory.push({x:t.clientX,y:t.clientY,ts:performance.now()});if(dragHistory.length>10)dragHistory.shift();updateTrail(dragOrb);e.preventDefault();}
  },{passive:false});
  document.addEventListener('touchend',e=>{
    if(!dragOrb)return;
    const v = computeThrowVelocity(dragHistory);
    dragOrb.vx = v.vx; dragOrb.vy = v.vy;
    const throwSpd=Math.sqrt(dragOrb.vx**2+dragOrb.vy**2);
    if(throwSpd<0.25){dragOrb.vx=0;dragOrb.vy=0;dragOrb.placedTimer=rand(1200,2200);}
    else burst(dragOrb.x,dragOrb.y,Math.round(clamp(throwSpd * 5, 10, 28)),0.85);
    dragOrb=null;dragHistory=[];
    setOrbDragState(false);
    e.preventDefault();
  },{passive:false});

  // ══════════════════════════════════════════════════════════════════════════════
  //  INIT
  // ══════════════════════════════════════════════════════════════════════════════
  resize();
  window.addEventListener('resize',resize);
  Brain.scan();
  CouncilLink.fetch();  // Initial council fetch
  SevenLink.fetch();    // Initial Seven beliefs/attention/curiosity fetch
  sleepTimer=setTimeout(()=>{sleeping=true;},10000);
  // Sync orb visibility / quality controls once the settings panel exists.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _syncOrbControls);
  } else {
    _syncOrbControls();
  }

  // ── MD-FEATURE-39B9FF065023 — Orbs behaviour overhaul ────────────────────
  // 1. Respect prefers-reduced-motion: auto-snap to 'low' quality on first
  //    load when no user preference has been recorded yet.
  // 2. Expose orbsPause()/orbsResume()/orbsSetQuality() globally so other
  //    surfaces (Tasker, Settings panel, focus-mode) can quiet the orbs
  //    without unmounting them.
  // 3. Pause when the document is hidden — saves battery on laptops that
  //    background the tab.
  let _orbsPaused = false;
  try {
    if (!localStorage.getItem(ORB_QUALITY_KEY)) {
      const mq = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
      if (mq && mq.matches) {
        setOrbQuality('low');
      }
    }
  } catch (_) {}
  document.addEventListener('visibilitychange', () => {
    _orbsPaused = document.hidden;
  });
  window.orbsPause = function () { _orbsPaused = true; };
  window.orbsResume = function () { _orbsPaused = false; requestAnimationFrame(draw); };
  window.orbsSetQuality = setOrbQuality;
  window.orbsIsPaused = function () { return !!_orbsPaused; };
  // Wrap draw with a paused-frame guard. We rebind the rAF callback so the
  // existing draw() function stays untouched.
  const _origDraw = draw;
  draw = function (t) {
    if (_orbsPaused) {
      requestAnimationFrame(draw);
      return;
    }
    _origDraw(t);
  };

  requestAnimationFrame(draw);

})();
