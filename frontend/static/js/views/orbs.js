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
  const ROLE_KEY = { eye: EYE, echo: ECHO, thread: THREAD, pulse: PULSE, voice: VOICE };
  // Voice shapes: each uses a fixed draw function — never shared
  const VOICE_STYLE = [0, 1, 4, 5, 6]; // drawRings, drawMandala, drawLissajous, drawVortex, drawPulsar

  // ── Mouse ─────────────────────────────────────────────────────────────────────
  const mouse = { x: -999, y: -999 };
  let mouseVX = 0, mouseVY = 0, prevMX = 0, prevMY = 0, prevMT = 0;
  let mouseStillPos = null, mouseStillTimer = null;
  const mouseHeat = [];

  // ── Drag ──────────────────────────────────────────────────────────────────────
  let dragOrb = null, dragPX = 0, dragPY = 0, dragHistory = [];

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
    let rx = ROOST_BASE[i][0]*W, ry = ROOST_BASE[i][1]*H;
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
      x: 0, y: 0, vx: 0, vy: 0,
      z: rand(0.5, 0.9), vz: rand(-0.0003, 0.0003),
      baseR: 0, r: 0,
      roostX: 0, roostY: 0,
      settled: 0, watchAngle: rand(0, Math.PI*2),
      state: 'idle', stateTimer: rand(1000, 4000),
      driftAngle: rand(0, Math.PI*2),
      driftPhase: rand(0, Math.PI*2),
      breathPhase: rand(0, Math.PI*2),
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
      if (o.thoughtAlpha >= 1) o.thoughtPhase = 'hold';
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
  //  DRAW STYLES
  // ══════════════════════════════════════════════════════════════════════════════
  function drawRings(o,t){
    const rings=[{s:1.00,spd:1.0,dash:[9,5],lw:1.5,nodes:8,col:ACCENT},{s:0.77,spd:-1.4,dash:[5,9],lw:1.0,nodes:6,col:GLOW_A},{s:0.57,spd:2.0,dash:[14,4],lw:1.8,nodes:10,col:ACCENT},{s:0.37,spd:-2.2,dash:[3,7],lw:1.2,nodes:5,col:GLOW_B},{s:0.18,spd:3.2,dash:[],lw:2.5,nodes:0,col:ACCENT}];
    rings.forEach((ring,i)=>{ctx.save();ctx.translate(o.x,o.y);ctx.rotate(t*ring.spd);ctx.beginPath();ctx.arc(0,0,o.r*ring.s,0,Math.PI*2);ctx.setLineDash(ring.dash);ctx.strokeStyle=ring.col;ctx.lineWidth=ring.lw;ctx.globalAlpha=0.72-i*0.1;ctx.shadowColor=ring.col;ctx.shadowBlur=10;ctx.stroke();for(let j=0;j<ring.nodes;j++){const a=(j/ring.nodes)*Math.PI*2;ctx.beginPath();ctx.arc(Math.cos(a)*o.r*ring.s,Math.sin(a)*o.r*ring.s,2.2,0,Math.PI*2);ctx.fillStyle=ACCENT;ctx.globalAlpha=1;ctx.shadowBlur=18;ctx.setLineDash([]);ctx.fill();}ctx.restore();});
    eyeDot(o,4,ACCENT,32);
  }
  function drawMandala(o,t){
    const N=8;for(let i=0;i<N;i++){ctx.save();ctx.translate(o.x,o.y);ctx.rotate((i/N)*Math.PI*2+t*0.32);ctx.beginPath();ctx.moveTo(0,0);ctx.bezierCurveTo(o.r*0.44,-o.r*0.36,o.r*0.86,0,0,o.r*0.94);ctx.bezierCurveTo(-o.r*0.11,o.r*0.70,0,o.r*0.36,0,0);ctx.setLineDash([]);ctx.strokeStyle=ACCENT;ctx.lineWidth=1;ctx.globalAlpha=0.32;ctx.shadowColor=ACCENT;ctx.shadowBlur=8;ctx.stroke();ctx.restore();}
    ctx.save();ctx.beginPath();ctx.arc(o.x,o.y,o.r*0.97,0,Math.PI*2);ctx.strokeStyle=GLOW_A;ctx.lineWidth=0.8;ctx.setLineDash([2,9]);ctx.globalAlpha=0.32;ctx.stroke();ctx.restore();
    polygon(o.x,o.y,o.r*0.44,6,-t*0.62,ACCENT,1.5,0.76);polygon(o.x,o.y,o.r*0.44,6,-t*0.62+Math.PI/6,GLOW_A,1.0,0.46);polygon(o.x,o.y,o.r*0.22,3,t*0.92,ACCENT,2.0,0.86);
    eyeDot(o,4.5,ACCENT,34);
  }
  function drawHelix(o,t){
    for(let i=0;i<3;i++){const rot=t*0.72+(i/3)*Math.PI*2;ctx.save();ctx.translate(o.x,o.y);ctx.rotate(rot);ctx.beginPath();ctx.ellipse(0,0,o.r*0.90,o.r*0.27,0,0,Math.PI*2);ctx.strokeStyle=i===0?ACCENT:(i===1?GLOW_A:GLOW_B);ctx.lineWidth=1.6;ctx.globalAlpha=0.56;ctx.shadowColor=ACCENT;ctx.shadowBlur=12;ctx.setLineDash([]);ctx.stroke();ctx.restore();const tx=o.x+Math.cos(rot)*o.r*0.90,ty=o.y+Math.sin(rot)*o.r*0.90;dot(tx,ty,4,ACCENT,24);dot(o.x-(tx-o.x),o.y-(ty-o.y),4,ACCENT,24);}
    ctx.save();ctx.beginPath();ctx.arc(o.x,o.y,o.r*0.92,0,Math.PI*2);ctx.strokeStyle=GLOW_A;ctx.lineWidth=0.8;ctx.globalAlpha=0.24;ctx.setLineDash([4,11]);ctx.stroke();ctx.restore();
    eyeDot(o,5.5,ACCENT,38);
  }
  function drawCrystal(o,t){
    polygon(o.x,o.y,o.r*0.96,6,t*0.36,ACCENT,1.5,0.62);polygon(o.x,o.y,o.r*0.68,6,-t*0.54+Math.PI/6,GLOW_A,1.0,0.46);polygon(o.x,o.y,o.r*0.48,3,t*0.86,ACCENT,2.0,0.74);polygon(o.x,o.y,o.r*0.48,3,-t*0.70+Math.PI,GLOW_B,1.5,0.56);
    ctx.save();ctx.beginPath();ctx.arc(o.x,o.y,o.r*0.19,0,Math.PI*2);ctx.strokeStyle=ACCENT;ctx.lineWidth=2.2;ctx.globalAlpha=0.88;ctx.shadowColor=ACCENT;ctx.shadowBlur=24;ctx.setLineDash([]);ctx.stroke();ctx.restore();
    ctx.save();ctx.translate(o.x,o.y);ctx.rotate(t*0.36);ctx.setLineDash([4,9]);ctx.strokeStyle=ACCENT;ctx.lineWidth=0.5;ctx.globalAlpha=0.22;for(let i=0;i<6;i++){const a=(i/6)*Math.PI*2-Math.PI/2;ctx.beginPath();ctx.moveTo(Math.cos(a)*o.r*0.19,Math.sin(a)*o.r*0.19);ctx.lineTo(Math.cos(a)*o.r*0.96,Math.sin(a)*o.r*0.96);ctx.stroke();}ctx.restore();
    eyeDot(o,4,ACCENT,32);
  }
  function drawLissajous(o,t){
    const A=3,B=2,STEPS=420,delta=t*0.36;ctx.save();ctx.beginPath();for(let i=0;i<=STEPS;i++){const p=(i/STEPS)*Math.PI*2,px=o.x+Math.sin(A*p+delta)*o.r*0.88,py=o.y+Math.sin(B*p)*o.r*0.88;i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}ctx.closePath();ctx.strokeStyle=ACCENT;ctx.lineWidth=1.6;ctx.globalAlpha=0.65;ctx.shadowColor=ACCENT;ctx.shadowBlur=14;ctx.setLineDash([]);ctx.stroke();ctx.restore();
    ctx.save();ctx.beginPath();ctx.ellipse(o.x,o.y,o.r*0.90,o.r*0.90,0,0,Math.PI*2);ctx.strokeStyle=GLOW_A;ctx.lineWidth=0.7;ctx.globalAlpha=0.18;ctx.setLineDash([3,11]);ctx.stroke();ctx.restore();
    const np=(t*0.4)%(Math.PI*2);dot(o.x+Math.sin(A*np+delta)*o.r*0.88,o.y+Math.sin(B*np)*o.r*0.88,3.5,GLOW_A,18);
    eyeDot(o,5,ACCENT,30);
  }
  function drawVortex(o,t){
    const ARMS=3,POINTS=160;for(let arm=0;arm<ARMS;arm++){const off=(arm/ARMS)*Math.PI*2;ctx.save();ctx.translate(o.x,o.y);ctx.beginPath();for(let i=0;i<POINTS;i++){const frac=i/POINTS,angle=frac*Math.PI*4.2+off+t*0.52,rad=frac*o.r*0.92;i===0?ctx.moveTo(Math.cos(angle)*rad,Math.sin(angle)*rad):ctx.lineTo(Math.cos(angle)*rad,Math.sin(angle)*rad);}ctx.strokeStyle=arm===0?ACCENT:(arm===1?GLOW_A:GLOW_B);ctx.lineWidth=1.6-arm*0.3;ctx.globalAlpha=0.62-arm*0.14;ctx.shadowColor=ACCENT;ctx.shadowBlur=9;ctx.setLineDash([]);ctx.stroke();ctx.restore();}
    ctx.save();const g=ctx.createRadialGradient(o.x,o.y,0,o.x,o.y,o.r*0.26);g.addColorStop(0,ACCENT+'cc');g.addColorStop(1,ACCENT+'00');ctx.beginPath();ctx.arc(o.x,o.y,o.r*0.26,0,Math.PI*2);ctx.fillStyle=g;ctx.globalAlpha=1;ctx.fill();ctx.restore();
    eyeDot(o,4,ACCENT,28);
  }
  function drawPulsar(o,t){
    for(let i=0;i<4;i++){const phase=((t*0.7+i*0.25)%1);const rr=o.r*(0.2+phase*0.8);ctx.save();ctx.beginPath();ctx.arc(o.x,o.y,rr,0,Math.PI*2);ctx.strokeStyle=i%2===0?ACCENT:GLOW_B;ctx.lineWidth=2.0-phase*1.2;ctx.globalAlpha=(1-phase)*0.55;ctx.shadowColor=ACCENT;ctx.shadowBlur=8;ctx.setLineDash([]);ctx.stroke();ctx.restore();}
    ctx.save();ctx.translate(o.x,o.y);ctx.rotate(t*0.3);ctx.strokeStyle=ACCENT;ctx.lineWidth=1.0;ctx.globalAlpha=0.4;ctx.setLineDash([3,6]);ctx.beginPath();ctx.moveTo(-o.r*0.7,0);ctx.lineTo(o.r*0.7,0);ctx.stroke();ctx.beginPath();ctx.moveTo(0,-o.r*0.7);ctx.lineTo(0,o.r*0.7);ctx.stroke();ctx.restore();
    eyeDot(o,4,ACCENT,28);
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
    const tx = o.roostX + Math.cos(o.driftPhase) * (o.baseR * 0.9);
    const ty = o.roostY + Math.sin(o.driftPhase * 1.3) * (o.baseR * 0.55);
    o.vx += (tx - o.x) * 0.0012;
    o.vy += (ty - o.y) * 0.0012;
    o.vx += Math.cos(o.driftPhase * 2.1) * rhythm;
    o.vy += Math.sin(o.driftPhase * 1.8) * rhythm;
    o.state = Brain.ctx.agentsBusy || Brain.ctx.pendingMessages > 0 ? 'active' : 'steady';
  }

  function behaviorVoice(o,dt){
    _applyFlee(o);
    const anchorX = lerp(o.roostX, W * 0.58, 0.45);
    const anchorY = lerp(o.roostY, H * 0.34, 0.45);
    const drift = o.ideaReady ? 0.0018 : 0.0011;
    o.vx += (anchorX - o.x) * drift;
    o.vy += (anchorY - o.y) * drift;
    if (o.ideaReady) {
      o.state = 'speaking';
      o.vx += Math.cos(o.driftPhase + dt * 0.001) * 0.0042;
      o.vy += Math.sin(o.driftPhase + dt * 0.0014) * 0.0038;
    } else {
      o.state = 'composing';
      if (Math.random() < 0.0012) o.driftAngle += rand(-0.35, 0.35);
      o.vx += Math.cos(o.driftAngle) * 0.0030;
      o.vy += Math.sin(o.driftAngle) * 0.0030;
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
    else if (!sleeping && o.placedTimer <= 0) {
      switch(o.role){
        case EYE:    behaviorEye(o,dt);    break;
        case ECHO:   behaviorEcho(o,dt);   break;
        case THREAD: behaviorThread(o,dt); break;
        case PULSE:  behaviorPulse(o,dt);  break;
        case VOICE:  behaviorVoice(o,dt);  break;
      }
      // Roost pull when drifting slowly
      const spd0=Math.sqrt(o.vx*o.vx+o.vy*o.vy);
      const pull=Math.max(0,0.42-spd0)*0.0015;
      if(pull>0.0001){o.vx+=(o.roostX-o.x)*pull;o.vy+=(o.roostY-o.y)*pull;}
    }
    if (o.placedTimer > 0) { o.placedTimer -= dt; o.vx *= 0.90; o.vy *= 0.90; }

    // Boundary
    const m=Math.min(W,H)*MARGIN;
    if(o.x<m)o.vx+=0.08;if(o.x>W-m)o.vx-=0.08;if(o.y<m)o.vy+=0.08;if(o.y>H-m)o.vy-=0.08;
    if(sleeping){o.vx*=0.92;o.vy*=0.92;}
    o.vx*=FRICTION;o.vy*=FRICTION;
    const spd=Math.sqrt(o.vx*o.vx+o.vy*o.vy);
    if(spd>MAX_SPD){o.vx=o.vx/spd*MAX_SPD;o.vy=o.vy/spd*MAX_SPD;}
    o.x+=o.vx;o.y+=o.vy;

    // Depth
    o.z+=o.vz;
    if(o.z>1.0){o.z=1.0;o.vz=-Math.abs(o.vz)*rand(0.8,1.2);}
    if(o.z<0.25){o.z=0.25;o.vz=Math.abs(o.vz)*rand(0.8,1.2);}
    if(Math.random()<0.002)o.vz+=rand(-0.0002,0.0002);
    o.vz=clamp(o.vz,-0.0013,0.0013);

    // Settled
    o.settled=lerp(o.settled,spd<0.20?1:0,0.007);

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

    ctx.save();

    // 3D tilt transform
    if(Math.abs(o.tiltX)>0.02||Math.abs(o.tiltY)>0.02){
      ctx.translate(o.x,o.y);
      ctx.transform(Math.cos(o.tiltY),Math.sin(o.tiltX)*0.32,-Math.sin(o.tiltY)*0.32,Math.cos(o.tiltX),0,0);
      ctx.translate(-o.x,-o.y);
    }

    ctx.globalAlpha=Math.min(baseAlpha+boost,0.88)*dormFade;
    const animSpeed=o.speed*lerp(1.0,0.24,o.settled)*(1+o.interestLevel*0.28)*(o.ideaReady?1.3:1);
    DRAW_FNS[o.style%DRAW_FNS.length](o,t*animSpeed);

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
    [...orbs].sort((a,b)=>a.z-b.z).forEach(o=>{drawTrail(o);renderOrb(o,t);});
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
  document.addEventListener('mousemove',function(e){
    if(document.body.dataset.sceneEffect==='off')return;
    if(dragOrb)e.preventDefault();
    const now=performance.now();
    const mdt=Math.max(now-prevMT,8);
    mouseVX=lerp(mouseVX,(e.clientX-prevMX)/mdt*16,0.20);
    mouseVY=lerp(mouseVY,(e.clientY-prevMY)/mdt*16,0.20);
    prevMX=mouse.x=e.clientX;prevMY=mouse.y=e.clientY;prevMT=now;
    clearTimeout(mouseStillTimer);
    mouseStillTimer=setTimeout(()=>{mouseStillPos={x:mouse.x,y:mouse.y};},2200);
    if(sleeping)sleeping=false;
    clearTimeout(sleepTimer);sleepTimer=setTimeout(()=>{sleeping=true;},10000);
    if(dragOrb){dragOrb.x=mouse.x;dragOrb.y=mouse.y;dragHistory.push({x:mouse.x,y:mouse.y,ts:now});if(dragHistory.length>6)dragHistory.shift();updateTrail(dragOrb);}
    const hit=orbAt(mouse.x,mouse.y);
    const cur=hit?(dragOrb?'grabbing':'grab'):'';
    if(cur!==document.body._oc){document.body._oc=cur;document.body.style.cursor=cur||'';}
  });

  document.addEventListener('mousedown',function(e){
    if(document.body.dataset.sceneEffect==='off')return;
    const hit=orbAt(e.clientX,e.clientY);
    if(hit){dragOrb=hit;dragPX=e.clientX;dragPY=e.clientY;dragHistory=[{x:e.clientX,y:e.clientY,ts:performance.now()}];hit.placedTimer=0;setOrbDragState(true);e.preventDefault();e.stopPropagation();}
  },true);

  document.addEventListener('mouseup',function(){
    if(!dragOrb)return;
    const dropped=dragOrb;
    // Compute throw velocity
    if(dragHistory.length>=2){
      const n=dragHistory[dragHistory.length-1],o2=dragHistory[0];
      const el=Math.max(n.ts-o2.ts,8),sc=16/el;
      dropped.vx=clamp((n.x-o2.x)*sc,-MAX_SPD*3,MAX_SPD*3);
      dropped.vy=clamp((n.y-o2.y)*sc,-MAX_SPD*3,MAX_SPD*3);
    }
    // Check if dropped onto another orb → attempt merge/fight
    let mergeTarget=null;
    orbs.forEach(other=>{
      if(other===dropped||other.absorbed)return;
      if(dist(dropped.x,dropped.y,other.x,other.y)<(dropped.r+other.r)*0.85)mergeTarget=other;
    });
    if(mergeTarget){
      tryMerge(dropped, mergeTarget);
    } else {
      // Gentle drop = sit still
      const throwSpd=Math.sqrt(dropped.vx**2+dropped.vy**2);
      if(throwSpd<0.8){dropped.placedTimer=rand(12000,22000);dropped.vx=0;dropped.vy=0;}
      else burst(dropped.x,dropped.y,Math.round(clamp(throwSpd * 5, 12, 28)),0.85);
    }
    dropped.settled=0;
    burst(dropped.x,dropped.y,10,0.6);
    dragOrb=null;dragHistory=[];
    setOrbDragState(false);
  });

  document.addEventListener('selectstart', function(e){
    if(!dragOrb) return;
    e.preventDefault();
  });

  document.addEventListener('click',function(e){
    if(document.body.dataset.sceneEffect==='off')return;
    if(dist(e.clientX,e.clientY,dragPX,dragPY)>10)return;
    const hit=orbAt(e.clientX,e.clientY);
    if(!hit)return;
    // Council thought dismissal — if orb is showing a council thought, dismiss it
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
    hit.style=(hit.style+1)%DRAW_FNS.length;
    hit.vx+=rand(-0.5,0.5);hit.vy+=rand(-0.5,0.5);
    hit.z=clamp(hit.z+rand(0.1,0.22),0.25,1.0);
    hit.settled=0;hit.placedTimer=0;
    burst(hit.x,hit.y,14,0.82);
    if(typeof showToast==='function')showToast((hit.mergedName||ROLE_NAMES[hit.role])+' → '+STYLE_NAMES[hit.style],'info');
  },true);

  // Touch
  let lastTouch=null;
  document.addEventListener('touchstart',e=>{
    if(document.body.dataset.sceneEffect==='off')return;
    const t=e.touches[0];lastTouch={x:t.clientX,y:t.clientY};mouse.x=t.clientX;mouse.y=t.clientY;
    const hit=orbAt(t.clientX,t.clientY);
    if(hit){dragOrb=hit;dragPX=t.clientX;dragPY=t.clientY;dragHistory=[{x:t.clientX,y:t.clientY,ts:performance.now()}];setOrbDragState(true);e.preventDefault();}
  },{passive:false});
  document.addEventListener('touchmove',e=>{
    if(document.body.dataset.sceneEffect==='off')return;
    const t=e.touches[0];mouse.x=t.clientX;mouse.y=t.clientY;
    if(dragOrb){dragOrb.x=t.clientX;dragOrb.y=t.clientY;dragHistory.push({x:t.clientX,y:t.clientY,ts:performance.now()});if(dragHistory.length>6)dragHistory.shift();updateTrail(dragOrb);e.preventDefault();}
  },{passive:false});
  document.addEventListener('touchend',e=>{
    if(!dragOrb)return;
    const t=e.changedTouches[0];
    if(lastTouch&&dist(t.clientX,t.clientY,lastTouch.x,lastTouch.y)<12){dragOrb.style=(dragOrb.style+1)%DRAW_FNS.length;burst(dragOrb.x,dragOrb.y,12,0.8);}
    if(dragHistory.length>=2){const n=dragHistory[dragHistory.length-1],o2=dragHistory[0],el=Math.max(n.ts-o2.ts,8),sc=16/el;dragOrb.vx=clamp((n.x-o2.x)*sc,-MAX_SPD*3,MAX_SPD*3);dragOrb.vy=clamp((n.y-o2.y)*sc,-MAX_SPD*3,MAX_SPD*3);}
    const throwSpd=Math.sqrt(dragOrb.vx**2+dragOrb.vy**2);
    if(throwSpd>0.8)burst(dragOrb.x,dragOrb.y,Math.round(clamp(throwSpd * 5, 12, 28)),0.85);
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
  sleepTimer=setTimeout(()=>{sleeping=true;},10000);
  requestAnimationFrame(draw);

})();
