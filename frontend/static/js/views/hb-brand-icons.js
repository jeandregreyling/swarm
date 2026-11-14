/* HB brand icons (owner 14 Nov): SVG is the standard - no coloured emoji in HB's interface. Every marker HB writes is shown as an HB line
 * icon (16 grid, stroke 1.3, round caps, currentColor - like core/icons.js) in the theme's highlight colour (var(--accent)), with small
 * living animations. Applies to HB's own messages (anywhere in the text), the live activity, the clipboard and the Needs-you bar.
 * The maintenance screen shows a sleeping hummingbird (recharging) instead of a spanner. Brand guide: core/capability_packs/hb.brand.v1.json */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  const st = 'stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"';
  const S = (body, cls) => `<svg class="${cls || ''}" viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden="true">${body}</svg>`;
  const P = d => `<path d="${d}" ${st}/>`;
  const C = (x, y, r) => `<circle cx="${x}" cy="${y}" r="${r}" ${st}/>`;
  const BIRD = P('M3.5 10.5c0-2.2 1.7-4 3.9-4 1 0 1.9.4 2.6 1L14.5 6l-4 2.3c-.2 2-1.9 3.6-4 3.6H5L3 14l.6-2.6') +
               `<path class="hb-wing" d="M7.6 7.4 5.4 2.5c2 .2 3.4 1.7 3.8 3.7" ${st}/><circle cx="9.6" cy="8.4" r=".6" fill="currentColor"/>`;
  const FLOWER = C(8, 6, 1.2) + P('M8 3.2a1.4 1.4 0 0 1 0 1.6M10.8 6a1.4 1.4 0 0 1-1.6 0M8 8.8a1.4 1.4 0 0 1 0-1.6M5.2 6a1.4 1.4 0 0 1 1.6 0' +
                 'M6.2 4.2a1.5 1.5 0 1 1 1.2-1M9.8 4.2a1.5 1.5 0 1 0-1.2-1M6.2 7.8a1.5 1.5 0 1 0 1.2 1M9.8 7.8a1.5 1.5 0 1 1-1.2 1') +
                 P('M8 9v5M8 12.2c1.3-.1 2.2-.9 2.5-2.2');
  const ICONS = {
    flower: S(FLOWER, 'hb-flower'),
    bird: S(BIRD, 'hb-bird'),
    visit: `<svg class="hb-visit" viewBox="0 0 28 16" width="28" height="16" fill="none" aria-hidden="true"><g class="hb-visit-bird">${BIRD}</g>` +
           `<g transform="translate(13 1) scale(.9)">${FLOWER}</g></svg>`,
    sleeping: S(P('M3.5 11c0-2.2 1.7-3.8 3.9-3.8 1.2 0 2.2.5 2.8 1.3l3.3 1.8-3.4.6c-.4 1.6-1.9 2.8-3.7 2.8H5L3 15l.6-2.6') +
                P('M8.9 9.3q.6.5 1.2 0M5.6 8.4c.8-.7 1.9-1 3-.9') + `<path class="hb-z" d="M11 2.5h2.2L11 4.8h2.2M13.6 5.5h1.4L13.6 7h1.4" ${st}/>`, 'hb-sleeping'),
    clipboard: S(P('M6 3h4v1.8H6zM5.5 3.8H3.8v10h8.4v-10h-1.7M5.8 8h4.4M5.8 10.6h3')),
    check: S(P('M3.5 8.5l3 3 6-7')),
    done: S(C(8, 8, 5.8) + P('M5.4 8.2l1.9 1.9 3.5-4')),
    cross: S(P('M4.5 4.5l7 7M11.5 4.5l-7 7')),
    warn: S(P('M8 2.5l6 11H2zM8 6.5v3.2M8 11.8v.01')),
    pause: S(P('M6 4v8M10 4v8')),
    play: S(P('M5.5 3.5l7 4.5-7 4.5z')),
    search: S(C(7, 7, 4) + P('M10 10l3.5 3.5')),
    flask: S(P('M6.5 2.5h3M7 2.5v4L3.5 12.8a1 1 0 0 0 .9 1.5h7.2a1 1 0 0 0 .9-1.5L9 6.5v-4M5 10h6')),
    sprout: S(P('M8 14V8M8 8C8 5.5 6 4 3.5 4c0 2.5 2 4 4.5 4ZM8 9.5c0-2.5 2-4 4.5-4 0 2.5-2 4-4.5 4Z'), 'hb-sprout'),
    note: S(P('M3.5 12.5l.5-2.5 6.5-6.5 2 2-6.5 6.5zM9.5 4.5l2 2')),
    scroll: S(P('M5 3.5h7.5v8a1.5 1.5 0 0 1-1.5 1.5H4.5A1.5 1.5 0 0 1 3 11.5V10h7.5v1.5M5 3.5A1.5 1.5 0 0 0 3.5 5v5M6.5 6.5h4M6.5 8.5h3')),
    retry: S(P('M12.5 8a4.5 4.5 0 1 1-1.3-3.2M12.5 3v2.5H10')),
    plan: S(P('M5.5 4.5h7M5.5 8h7M5.5 11.5h7M3 4.5h.01M3 8h.01M3 11.5h.01')),
    question: S(C(8, 8, 5.8) + P('M6.5 6.5a1.5 1.5 0 1 1 2 1.4c-.4.2-.5.5-.5.9v.4M8 11v.01')),
    download: S(P('M8 2.5v7M5 6.5l3 3 3-3M3 12.5h10')),
    gear: S(C(8, 8, 2) + P('M8 2v1.5M8 12.5V14M2 8h1.5M12.5 8H14M3.8 3.8l1 1M11.2 11.2l1 1M3.8 12.2l1-1M11.2 4.8l1-1'), 'hb-gear'),
    blocked: S(C(8, 8, 5.8) + P('M4 12l8-8')),
    flag: S(P('M4 14V2.5M4 3h7.5l-1.5 2.5 1.5 2.5H4')),
    more: S(P('M6 4l4 4-4 4')),
    less: S(P('M4 6l4 4 4-4')),
    dot: S(C(8, 8, 1.6)),
  };
  const MARKERS = {
    '🌺': 'flower', '👏': 'flower', '🏅': 'flower', '🤔': 'visit', '🛠': 'visit', '📋': 'clipboard', '✅': 'done', '✔': 'check', '✘': 'cross',
    '❌': 'cross', '⚠': 'warn', '⏸': 'pause', '▶': 'play', '🔎': 'search', '🔍': 'search', '🧪': 'flask', '🌱': 'sprout', '📝': 'note',
    '📜': 'scroll', '↺': 'retry', '☰': 'plan', '❓': 'question', '⬇': 'download', '⚙': 'gear', '⊘': 'blocked',
  };
  const RE = new RegExp('(' + Object.keys(MARKERS).map(m => m.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')️?', 'gu');
  const CSS = '.hb-ico{display:inline-flex;align-items:center;color:var(--accent,#6aa9ff);margin-right:4px;vertical-align:-3px}' +
    '.hb-ico svg{height:1.2em;width:auto}.hb-visit-bird{animation:hb-hover 1.6s ease-in-out infinite}' +
    '.hb-wing{transform-origin:7.6px 7.4px;animation:hb-flap .18s ease-in-out infinite alternate}' +
    '.hb-flower{animation:hb-bloom 2.4s ease-in-out infinite}.hb-sleeping{animation:hb-breathe 3.2s ease-in-out infinite}' +
    '.hb-z{animation:hb-z 3.2s ease-in-out infinite}.hb-sprout{animation:hb-bloom 3s ease-in-out infinite}.hb-gear{animation:hb-spin 6s linear infinite}' +
    '@keyframes hb-hover{0%,100%{transform:translateX(0)}50%{transform:translateX(3px)}}@keyframes hb-flap{to{transform:rotate(-14deg)}}' +
    '@keyframes hb-bloom{50%{transform:scale(1.06)}}@keyframes hb-breathe{50%{transform:translateY(1px)}}@keyframes hb-z{0%,100%{opacity:.25}50%{opacity:1}}' +
    '@keyframes hb-spin{to{transform:rotate(360deg)}}' +
    '#hb-maintenance .hb-ico{margin:0 auto 6px;display:flex;justify-content:center}#hb-maintenance .hb-ico svg{height:44px}' +
    '@media (prefers-reduced-motion: reduce){.hb-ico *{animation:none!important}}';

  /** Text -> parts: strings and {icon} for every HB marker in it. */
  function split(text) {
    const parts = [];
    let last = 0;
    String(text || '').replace(RE, (m, mark, at) => {
      if (at > last) parts.push(text.slice(last, at));
      parts.push({ icon: MARKERS[mark] });
      last = at + m.length;
      return m;
    });
    if (last < String(text || '').length) parts.push(String(text).slice(last));
    return parts;
  }
  /** Older helper: a leading marker only. */
  function marker(text) {
    const parts = split(String(text || '').replace(/^\s+/, ''));
    return parts.length && typeof parts[0] === 'object' ? { icon: parts[0].icon, rest: parts.slice(1).join('') } : null;
  }

  function style() {
    if (document.getElementById('hb-brand-css')) return;
    const s = document.createElement('style'); s.id = 'hb-brand-css'; s.textContent = CSS; document.head.appendChild(s);
  }
  function icon(name) { const span = document.createElement('span'); span.className = 'hb-ico'; span.innerHTML = ICONS[name]; return span; }
  const HB = el => /^(hummingbird|hb)$/i.test(String(el._chatMessage?.sender || el._chatMessage?.from_agent || el.dataset.sender || ''));

  function swap(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) { RE.lastIndex = 0; if (RE.test(n.nodeValue)) nodes.push(n); }
    nodes.forEach(n => {
      if (n.parentNode && n.parentNode.closest && n.parentNode.closest('textarea,input,code,pre,.hb-ico')) return;
      const frag = document.createDocumentFragment();
      split(n.nodeValue).forEach(p => frag.appendChild(typeof p === 'string' ? document.createTextNode(p) : icon(p.icon)));
      n.parentNode.replaceChild(frag, n);
    });
  }

  /** HB's messages, the live activity, the clipboard and the Needs-you bar: every marker becomes its SVG icon. */
  function decorate(root) {
    style();
    const scope = root || document;
    scope.querySelectorAll('[data-message-id]').forEach(b => {     // only when the bubble's text changed since the last pass
      const sig = String(b.textContent.length);
      if (b.dataset.hbIconed === sig || !HB(b)) return;
      swap(b); b.dataset.hbIconed = String(b.textContent.length);
    });
    scope.querySelectorAll('.hb-act, #hb-activity, #hb-clipboard, .hb-needs-you, #hb-approval-popup').forEach(swap);
    scope.querySelectorAll('[data-hb-icon]:not([data-hb-filled])').forEach(el => {   // components ask for an icon by name
      if (ICONS[el.dataset.hbIcon]) { el.innerHTML = ICONS[el.dataset.hbIcon]; el.classList.add('hb-ico'); el.dataset.hbFilled = '1'; }
    });
  }

  /** The one place icons come from: HBIcons.svg('sleeping') - never an emoji or a glyph typed into a component. */
  const svg = name => `<span class="hb-ico" data-hb-icon="${name}" data-hb-filled="1">${ICONS[name] || ''}</span>`;
  window.HBIcons = { ICONS, MARKERS, split, marker, decorate, svg };
  setInterval(() => decorate(document), 1500);
  setTimeout(() => decorate(document), 300);
})();
