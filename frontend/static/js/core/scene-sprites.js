/* Scene Sprites Engine — v1
 * Spawns animated creatures/effects inside #ambient-scene based on body[data-scene]:
 *   beach   → seagulls, dolphins, crabs, octopus, umbrellas, waves
 *   forest  → falling leaves, birds, fireflies, scampering animals
 *   rain    → clouds, raindrops, lightning, rainbows, sun breaks
 * Respects body[data-scene-ambient="off"] and body[data-scene-effect="off"].
 * Keeps active sprite count bounded; cleans up on scene change.
 */
(function () {
  'use strict';
  if (window.__sceneSpritesBooted) return;
  window.__sceneSpritesBooted = true;

  const HOST_ID = 'scene-sprite-layer';
  const STYLE_ID = 'scene-sprite-styles';
  const MAX_SPRITES = 48;
  let emitters = [];
  let currentScene = null;

  // ─── inject stylesheet once ────────────────────────────────────────
  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const css = `
#${HOST_ID}{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:1;}
.sp{position:absolute;will-change:transform,opacity;user-select:none;pointer-events:none;font-family:"Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji",sans-serif;}
@keyframes sp-fly-lr{from{transform:translate(-10vw, var(--y,30vh)) scale(var(--s,1));opacity:0}
  8%,92%{opacity:var(--o,.85)}to{transform:translate(110vw, calc(var(--y,30vh) + var(--dy,-6vh))) scale(var(--s,1));opacity:0}}
@keyframes sp-fly-rl{from{transform:translate(110vw, var(--y,30vh)) scale(calc(var(--s,1) * -1),var(--s,1));opacity:0}
  8%,92%{opacity:var(--o,.85)}to{transform:translate(-10vw, calc(var(--y,30vh) + var(--dy,-6vh))) scale(calc(var(--s,1) * -1),var(--s,1));opacity:0}}
@keyframes sp-bob{0%,100%{margin-top:0}50%{margin-top:-8px}}
@keyframes sp-fall{from{transform:translate(var(--x,50vw),-10vh) rotate(0) scale(var(--s,1));opacity:0}
  6%,92%{opacity:var(--o,.8)}to{transform:translate(calc(var(--x,50vw) + var(--dx,20vw)),110vh) rotate(var(--rot,540deg)) scale(var(--s,1));opacity:0}}
@keyframes sp-drop{from{transform:translate(var(--x,50vw),-10vh) scaleY(1.2);opacity:0}
  8%{opacity:var(--o,.7)}to{transform:translate(calc(var(--x,50vw) + var(--dx,0)),110vh) scaleY(1.8);opacity:0}}
@keyframes sp-walk{from{transform:translate(-10vw, var(--y,88vh)) scale(var(--s,1));opacity:0}
  10%,90%{opacity:var(--o,.85)}to{transform:translate(110vw, var(--y,88vh)) scale(var(--s,1));opacity:0}}
@keyframes sp-walk-rl{from{transform:translate(110vw, var(--y,88vh)) scale(calc(var(--s,1) * -1),var(--s,1));opacity:0}
  10%,90%{opacity:var(--o,.85)}to{transform:translate(-10vw, var(--y,88vh)) scale(calc(var(--s,1) * -1),var(--s,1));opacity:0}}
@keyframes sp-arc{0%{transform:translate(-5vw, 78vh) scale(var(--s,1));opacity:0}
  8%{opacity:.9}50%{transform:translate(50vw, var(--peak,40vh)) scale(var(--s,1))}92%{opacity:.9}
  100%{transform:translate(105vw, 78vh) scale(var(--s,1));opacity:0}}
@keyframes sp-drift-up{from{transform:translate(var(--x,50vw),110vh) rotate(0);opacity:0}
  10%,90%{opacity:.8}to{transform:translate(calc(var(--x,50vw) + var(--dx,10vw)),-10vh) rotate(var(--rot,180deg));opacity:0}}
@keyframes sp-wave{0%{transform:translateX(-20vw) scaleX(1.1);opacity:0}
  10%,90%{opacity:.55}100%{transform:translateX(120vw) scaleX(1.1);opacity:0}}
@keyframes sp-flicker{0%,100%{opacity:0.25;transform:translate(var(--x,50vw),var(--y,60vh)) scale(0.8)}
  50%{opacity:0.95;transform:translate(calc(var(--x,50vw) + 2vw),calc(var(--y,60vh) - 2vh)) scale(1.1)}}
@keyframes sp-lightning{0%,94%,100%{opacity:0}95%,97%{opacity:0.85}96%{opacity:0.35}}
@keyframes sp-rainbow-in{from{opacity:0;transform:translate(-10vw,40vh) scale(.9)}
  20%,80%{opacity:.65}to{opacity:0;transform:translate(-10vw,40vh) scale(1.15)}}
@keyframes sp-sunshine{0%,100%{opacity:0}40%,60%{opacity:0.75;transform:translate(var(--x,60vw),var(--y,12vh)) scale(1.15)}}

body[data-scene-ambient="off"] #${HOST_ID},
body[data-scene-effect="off"] #${HOST_ID}{display:none}
body[data-scene="off"] #${HOST_ID}{display:none}
`;
    const el = document.createElement('style');
    el.id = STYLE_ID;
    el.textContent = css;
    document.head.appendChild(el);
  }

  // ─── host container ────────────────────────────────────────────────
  function ensureHost() {
    let host = document.getElementById(HOST_ID);
    if (host) return host;
    const ambient = document.getElementById('ambient-scene');
    if (!ambient) return null;
    host = document.createElement('div');
    host.id = HOST_ID;
    ambient.appendChild(host);
    return host;
  }

  function rand(min, max) { return Math.random() * (max - min) + min; }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  // ─── sprite factory ────────────────────────────────────────────────
  function spawn(glyph, opts = {}) {
    const host = ensureHost();
    if (!host) return;
    if (host.childElementCount > MAX_SPRITES) return;
    const el = document.createElement('span');
    el.className = 'sp';
    el.textContent = glyph;
    const dur = opts.duration || rand(8, 16);
    el.style.cssText = [
      `font-size:${opts.size || rand(18, 32)}px`,
      `animation:${opts.animation || 'sp-fly-lr'} ${dur}s ${opts.easing || 'linear'} forwards`,
      opts.filter ? `filter:${opts.filter}` : '',
      opts.extra || ''
    ].filter(Boolean).join(';');
    // CSS custom properties
    Object.entries(opts.vars || {}).forEach(([k, v]) => el.style.setProperty(k, v));
    host.appendChild(el);
    setTimeout(() => { try { el.remove(); } catch (_) {} }, (dur * 1000) + 200);
  }

  // ─── scene emitter sets ────────────────────────────────────────────
  const SCENES = {
    beach: [
      { // seagulls drifting across sky
        every: [2200, 4600], fn: () => {
          const rl = Math.random() < 0.5;
          spawn('🕊️', {
            size: rand(18, 28),
            animation: rl ? 'sp-fly-rl' : 'sp-fly-lr',
            duration: rand(14, 22),
            vars: { '--y': `${rand(6, 32)}vh`, '--dy': `${rand(-6, 6)}vh`, '--s': rand(0.9, 1.3), '--o': rand(0.7, 0.95) }
          });
        }
      },
      { // dolphin leaps
        every: [9000, 18000], fn: () => {
          spawn('🐬', {
            size: rand(26, 38),
            animation: 'sp-arc',
            duration: rand(7, 11),
            vars: { '--peak': `${rand(36, 52)}vh`, '--s': rand(0.9, 1.2) }
          });
        }
      },
      { // crab scuttling along bottom
        every: [7000, 14000], fn: () => {
          const rl = Math.random() < 0.5;
          spawn('🦀', {
            size: rand(18, 26),
            animation: rl ? 'sp-walk-rl' : 'sp-walk',
            duration: rand(10, 16),
            vars: { '--y': `${rand(82, 92)}vh`, '--s': rand(0.8, 1.1) }
          });
        }
      },
      { // octopus drifting up
        every: [18000, 36000], fn: () => {
          spawn('🐙', {
            size: rand(22, 34),
            animation: 'sp-drift-up',
            duration: rand(20, 32),
            vars: { '--x': `${rand(10, 90)}vw`, '--dx': `${rand(-10, 10)}vw`, '--rot': `${rand(-180, 180)}deg` }
          });
        }
      },
      { // static-ish umbrella + palm accents (slow drift-up cameo)
        every: [14000, 28000], fn: () => {
          spawn(pick(['⛱️', '🌴', '🏖️', '🐚', '🐠']), {
            size: rand(22, 34),
            animation: 'sp-drift-up',
            duration: rand(28, 44),
            vars: { '--x': `${rand(0, 100)}vw`, '--dx': `${rand(-5, 5)}vw`, '--rot': '20deg' }
          });
        }
      },
      { // wave fronts
        every: [5000, 9000], fn: () => {
          spawn('〰️', {
            size: rand(40, 80),
            animation: 'sp-wave',
            duration: rand(10, 16),
            extra: `top:${rand(72, 86)}vh;opacity:0.4;color:#7ec7ff;text-shadow:0 0 12px #7ec7ff`,
            vars: {}
          });
        }
      },
    ],
    forest: [
      { // falling leaves
        every: [900, 1800], fn: () => {
          spawn(pick(['🍂', '🍃', '🌿']), {
            size: rand(14, 24),
            animation: 'sp-fall',
            duration: rand(9, 16),
            vars: { '--x': `${rand(0, 100)}vw`, '--dx': `${rand(-18, 18)}vw`, '--rot': `${rand(360, 900)}deg`, '--s': rand(0.8, 1.2), '--o': rand(0.65, 0.9) }
          });
        }
      },
      { // birds
        every: [4200, 8000], fn: () => {
          const rl = Math.random() < 0.5;
          spawn(pick(['🐦', '🦜', '🦋']), {
            size: rand(18, 28),
            animation: rl ? 'sp-fly-rl' : 'sp-fly-lr',
            duration: rand(12, 18),
            vars: { '--y': `${rand(12, 42)}vh`, '--dy': `${rand(-8, 8)}vh`, '--s': rand(0.9, 1.2), '--o': rand(0.75, 0.95) }
          });
        }
      },
      { // scampering critters along bottom
        every: [6500, 13000], fn: () => {
          const rl = Math.random() < 0.5;
          spawn(pick(['🐿️', '🐰', '🦔', '🐍', '🦎']), {
            size: rand(18, 26),
            animation: rl ? 'sp-walk-rl' : 'sp-walk',
            duration: rand(8, 14),
            vars: { '--y': `${rand(80, 92)}vh`, '--s': rand(0.85, 1.1) }
          });
        }
      },
      { // fireflies — flicker in random spots
        every: [500, 1400], fn: () => {
          const x = `${rand(5, 95)}vw`;
          const y = `${rand(15, 75)}vh`;
          spawn('✨', {
            size: rand(10, 18),
            animation: 'sp-flicker',
            duration: rand(2.5, 5),
            extra: 'color:#ffeb7a;text-shadow:0 0 10px #ffd84a',
            vars: { '--x': x, '--y': y }
          });
        }
      },
    ],
    rain: [
      { // drifting clouds
        every: [4000, 9000], fn: () => {
          spawn('☁️', {
            size: rand(44, 80),
            animation: 'sp-fly-lr',
            duration: rand(30, 55),
            extra: 'opacity:0.7;filter:drop-shadow(0 4px 14px rgba(120,130,150,.35))',
            vars: { '--y': `${rand(4, 22)}vh`, '--dy': `${rand(-2, 3)}vh`, '--s': rand(0.9, 1.4), '--o': 0.75 }
          });
        }
      },
      { // big raindrops (front layer)
        every: [180, 360], fn: () => {
          spawn('💧', {
            size: rand(10, 18),
            animation: 'sp-drop',
            duration: rand(0.9, 1.6),
            extra: 'color:#7ac1ff;filter:drop-shadow(0 0 4px rgba(120,200,255,.7))',
            vars: { '--x': `${rand(0, 100)}vw`, '--dx': `${rand(-2, 2)}vw`, '--o': 0.8 }
          });
        }
      },
      { // small raindrops (back layer)
        every: [90, 220], fn: () => {
          spawn('|', {
            size: rand(8, 14),
            animation: 'sp-drop',
            duration: rand(0.6, 1.1),
            extra: 'color:rgba(140,200,255,0.55);letter-spacing:0;font-weight:700',
            vars: { '--x': `${rand(0, 100)}vw`, '--dx': 0, '--o': 0.5 }
          });
        }
      },
      { // lightning flash (screen-edge flicker)
        every: [12000, 26000], fn: () => {
          spawn('⚡', {
            size: rand(80, 160),
            animation: 'sp-lightning',
            duration: rand(3.5, 5),
            extra: `top:${rand(4, 24)}vh;left:${rand(8, 85)}vw;color:#fff9a8;text-shadow:0 0 30px #fff,0 0 60px #b8d0ff`,
            vars: {}
          });
          // global white flash
          const host = ensureHost();
          if (host) {
            const flash = document.createElement('div');
            flash.className = 'sp';
            flash.style.cssText = 'inset:0;background:#fff;opacity:0;animation:sp-lightning 3.5s ease forwards;mix-blend-mode:screen;';
            host.appendChild(flash);
            setTimeout(() => { try { flash.remove(); } catch (_) {} }, 3700);
          }
        }
      },
      { // rainbow (after some rain)
        every: [30000, 60000], fn: () => {
          spawn('🌈', {
            size: rand(140, 220),
            animation: 'sp-rainbow-in',
            duration: rand(14, 22),
            extra: 'top:28vh;opacity:0.6;filter:saturate(1.3) drop-shadow(0 0 20px rgba(255,255,255,.3))',
            vars: {}
          });
        }
      },
      { // sunshine break between storms
        every: [22000, 45000], fn: () => {
          spawn('☀️', {
            size: rand(60, 100),
            animation: 'sp-sunshine',
            duration: rand(8, 14),
            extra: 'color:#ffd84a;text-shadow:0 0 40px #ffd84a,0 0 80px #ffae3a',
            vars: { '--x': `${rand(12, 80)}vw`, '--y': `${rand(6, 20)}vh` }
          });
        }
      },
    ],
    solar: [
      { // drifting planets (big, slow, reds dominate)
        every: [5000, 10000], fn: () => {
          spawn(pick(['🪐', '🌍', '🌎', '🌏', '☄️']), {
            size: rand(36, 72),
            animation: Math.random() < 0.5 ? 'sp-fly-rl' : 'sp-fly-lr',
            duration: rand(40, 70),
            extra: 'filter:drop-shadow(0 0 18px rgba(255,140,90,.55))',
            vars: { '--y': `${rand(10, 70)}vh`, '--dy': `${rand(-6, 6)}vh`, '--s': rand(0.8, 1.2), '--o': 0.9 }
          });
        }
      },
      { // red mars-ish accents
        every: [9000, 18000], fn: () => {
          spawn('🔴', {
            size: rand(28, 48),
            animation: 'sp-drift-up',
            duration: rand(30, 50),
            extra: 'color:#e24b2c;text-shadow:0 0 24px #ff6a3a,0 0 60px #c81f0a',
            vars: { '--x': `${rand(10, 90)}vw`, '--dx': `${rand(-6, 6)}vw`, '--rot': '0deg' }
          });
        }
      },
      { // shooting stars / comets
        every: [2500, 5500], fn: () => {
          spawn('✦', {
            size: rand(10, 22),
            animation: 'sp-fly-lr',
            duration: rand(3, 6),
            extra: 'color:#ffe7a8;text-shadow:0 0 14px #ffb26a,0 0 40px #ff7a3a;letter-spacing:-4px',
            vars: { '--y': `${rand(6, 60)}vh`, '--dy': `${rand(8, 20)}vh`, '--s': rand(0.7, 1.1), '--o': 0.85 }
          });
        }
      },
      { // dim background stars
        every: [120, 300], fn: () => {
          spawn('·', {
            size: rand(8, 18),
            animation: 'sp-flicker',
            duration: rand(3, 6),
            extra: 'color:#fff6c8;text-shadow:0 0 6px #fff6c8',
            vars: { '--x': `${rand(2, 98)}vw`, '--y': `${rand(2, 88)}vh` }
          });
        }
      },
      { // sun halo bursts (red-gold)
        every: [15000, 32000], fn: () => {
          spawn('☀️', {
            size: rand(80, 140),
            animation: 'sp-sunshine',
            duration: rand(10, 16),
            extra: 'color:#ff9a3a;text-shadow:0 0 60px #ff5a2a,0 0 120px #c81f0a',
            vars: { '--x': `${rand(20, 80)}vw`, '--y': `${rand(10, 40)}vh` }
          });
        }
      },
    ],
    underwater: [
      { // fish schools (right-left and left-right)
        every: [1600, 3400], fn: () => {
          const rl = Math.random() < 0.5;
          spawn(pick(['🐟', '🐠', '🐡', '🐳', '🦑']), {
            size: rand(20, 38),
            animation: rl ? 'sp-fly-rl' : 'sp-fly-lr',
            duration: rand(14, 26),
            extra: 'filter:drop-shadow(0 0 10px rgba(120,210,255,.55))',
            vars: { '--y': `${rand(20, 80)}vh`, '--dy': `${rand(-12, 12)}vh`, '--s': rand(0.8, 1.2), '--o': 0.9 }
          });
        }
      },
      { // red coral + crab accents (the reds the user wants)
        every: [9000, 20000], fn: () => {
          spawn(pick(['🦐', '🦀', '🌺']), {
            size: rand(26, 40),
            animation: 'sp-walk',
            duration: rand(14, 22),
            extra: 'color:#e24b2c;filter:drop-shadow(0 0 12px rgba(226,75,44,.6))',
            vars: { '--y': `${rand(82, 94)}vh`, '--s': rand(0.9, 1.2) }
          });
        }
      },
      { // bubble columns rising
        every: [280, 700], fn: () => {
          spawn('●', {
            size: rand(6, 14),
            animation: 'sp-drift-up',
            duration: rand(5, 10),
            extra: 'color:rgba(200,240,255,0.55);text-shadow:0 0 6px rgba(180,230,255,.6)',
            vars: { '--x': `${rand(3, 97)}vw`, '--dx': `${rand(-3, 3)}vw`, '--rot': '0deg' }
          });
        }
      },
      { // jellyfish (slow pulse, drift up)
        every: [12000, 24000], fn: () => {
          spawn('🪼', {
            size: rand(32, 56),
            animation: 'sp-drift-up',
            duration: rand(30, 50),
            extra: 'filter:drop-shadow(0 0 20px rgba(255,140,200,.6))',
            vars: { '--x': `${rand(10, 90)}vw`, '--dx': `${rand(-5, 5)}vw`, '--rot': '15deg' }
          });
        }
      },
      { // shark silhouette cameo
        every: [25000, 55000], fn: () => {
          const rl = Math.random() < 0.5;
          spawn('🦈', {
            size: rand(44, 72),
            animation: rl ? 'sp-fly-rl' : 'sp-fly-lr',
            duration: rand(22, 34),
            extra: 'filter:drop-shadow(0 0 14px rgba(60,90,120,.7))',
            vars: { '--y': `${rand(40, 72)}vh`, '--dy': `${rand(-4, 4)}vh`, '--s': rand(1.0, 1.3), '--o': 0.85 }
          });
        }
      },
      { // sunbeam shimmer (top of water)
        every: [6000, 12000], fn: () => {
          spawn('║', {
            size: rand(80, 160),
            animation: 'sp-wave',
            duration: rand(10, 16),
            extra: `top:0;color:rgba(180,230,255,0.35);letter-spacing:8px`,
            vars: {}
          });
        }
      },
    ],
  };

  function stopEmitters() {
    emitters.forEach(id => clearTimeout(id));
    emitters = [];
  }

  function startEmitters(scene) {
    stopEmitters();
    const set = SCENES[scene];
    if (!set) return;
    set.forEach(emitter => {
      const schedule = () => {
        const [min, max] = emitter.every;
        const delay = rand(min, max);
        const id = setTimeout(() => {
          try { emitter.fn(); } catch (e) { console.warn('[scene-sprites]', e); }
          schedule();
        }, delay);
        emitters.push(id);
      };
      // first spawn immediately (for instant feedback)
      try { emitter.fn(); } catch (_) {}
      schedule();
    });
  }

  function clearSprites() {
    const host = document.getElementById(HOST_ID);
    if (host) host.innerHTML = '';
  }

  function onSceneChange() {
    const body = document.body;
    const scene = body.dataset.scene || 'off';
    const ambient = body.dataset.sceneAmbient !== 'off';
    const master = body.dataset.sceneEffect !== 'off';
    if (scene === currentScene) return;
    currentScene = scene;
    stopEmitters();
    clearSprites();
    if (!ambient || !master) return;
    if (scene === 'off' || !SCENES[scene]) return;
    startEmitters(scene);
  }

  // watch for scene dataset changes
  function boot() {
    injectStyles();
    ensureHost();
    onSceneChange();
    const obs = new MutationObserver(muts => {
      for (const m of muts) {
        if (m.type === 'attributes' && (
          m.attributeName === 'data-scene' ||
          m.attributeName === 'data-scene-ambient' ||
          m.attributeName === 'data-scene-effect'
        )) {
          onSceneChange();
          return;
        }
      }
    });
    obs.observe(document.body, { attributes: true, attributeFilter: ['data-scene', 'data-scene-ambient', 'data-scene-effect'] });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.SceneSprites = { reset: onSceneChange, stop: stopEmitters };
})();
