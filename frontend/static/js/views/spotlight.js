'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   spotlight.js — Global Spotlight Search (Ctrl+Space)
   Searches commands (instant), then debounced (250ms) across:
     docs · knowledge base · tickets · proposals · conversations · memory
   Exposes: openSpotlight(), closeSpotlight()
────────────────────────────────────────────────────────────────────────── */

// Compact SVG icons — matches the Knowledge Center + home tile style.
const _SP_SVG = {
  chat:      '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2.5 4.5h11v7h-6l-3 2.5V11.5H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  knowledge: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M3 3.5h3v9H3zM7 3.5h3v9H7zM11.5 3.5l2.5 8.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  terminal:  '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M4.5 6.5L7 8.5l-2.5 2M8 11h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  files:     '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2.5 5h4l1-1.5h6V12H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  studio:    '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M3 4l10 2M3 8l10 2M3 12l7 1.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  git:       '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><circle cx="4" cy="4" r="1.6" stroke="currentColor" stroke-width="1.3"/><circle cx="12" cy="4" r="1.6" stroke="currentColor" stroke-width="1.3"/><circle cx="4" cy="12" r="1.6" stroke="currentColor" stroke-width="1.3"/><path d="M4 5.5v5M5.5 4h5a2 2 0 0 1 0 4h-2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  tickets:   '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 7h12" stroke="currentColor" stroke-width="1.3"/></svg>',
  monitor:   '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2 12l3-5 3 3 3-7 3 9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  email:     '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="2" y="4" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 6l6 4 6-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  library:   '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M3 3h10v10H3zM6 3v10M3 6h10" stroke="currentColor" stroke-width="1.3"/></svg>',
  media:     '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="2.5" y="4" width="11" height="8" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5 3v10M11 6.2c0 1.6-1.2 3.1-3 3.6V6.2c1.8.5 3 2 3 3.6Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  memory:    '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M5 3.5h6a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2z" stroke="currentColor" stroke-width="1.3"/><path d="M7.5 6.5v3M5.5 8h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  guide:     '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M3 2.5h10v11H3zM5.5 6h5M5.5 8.5h5M5.5 11h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  skills:    '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M8 2l1.5 4H14l-3.5 2.5L12 13l-4-2.5L4 13l1.5-4.5L2 6h4.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  vortex:    '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><circle cx="8" cy="8" r="5" stroke="currentColor" stroke-width="1.3"/><path d="M8 3c2 2 2 8 0 10M8 3c-2 2-2 8 0 10" stroke="currentColor" stroke-width="1.1"/></svg>',
  docs:      '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M4 3.5h7.5v9H4a1.5 1.5 0 0 0 0-3h7.5M4 3.5a1.5 1.5 0 0 0 0 3M4 6.5h7.5" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  home:      '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2 8l6-5 6 5M4 7v6h8V7" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  help:      '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><path d="M6.5 6.5c0-1 .8-1.8 1.8-1.8s1.8.8 1.8 1.8c0 1-1.8 1.2-1.8 2.5M8 11.5h0" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  // Result-row icons (reused for non-command rows)
  doc:          '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M4 2.5h6l3 3v8H4zM10 2.5V5.5h3" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  kbdoc:        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M3 3h10v10H3zM5 5.5h6M5 8h6M5 10.5h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  ticket:       '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="2" y="3.5" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 7h12M8 7v5" stroke="currentColor" stroke-width="1.3"/></svg>',
  proposal:     '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M4 2.5h6l3 3v8H4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 8l1.5 1.5L11 6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  conversation: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2.5 4.5h11v7h-6l-3 2.5V11.5H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5 7.5h6M5 9.5h4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>',
  memoryRow:    '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M5 3.5h6a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2z" stroke="currentColor" stroke-width="1.3"/><path d="M7.5 6.5v3M5.5 8h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  // Seven — sparkle. Used for any row originating from /api/seven/*.
  seven:        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M8 2l1.1 3.4L12.5 6.5 9.1 7.6 8 11 6.9 7.6 3.5 6.5l3.4-1.1L8 2z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M12.5 11l.5 1.4 1.4.5-1.4.5-.5 1.4-.5-1.4-1.4-.5 1.4-.5.5-1.4z" stroke="currentColor" stroke-width="1" stroke-linejoin="round"/></svg>',
  focus:        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><circle cx="8" cy="8" r="5" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="1.6" fill="currentColor"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
};

// Record-id pattern Seven understands as a focus query.
const _SP_RECORD_RX = /^(B|S|P|PR|T|TC|TR|D|TH)-[0-9A-F]{4,}$/i;
// Ask-Seven pattern: leading "?" routes to /api/seven/explain + /decide.
const _SP_ASK_RX = /^\?\s*(.*)$/;
// Intent keywords mapped to Seven's decide(intent=...) verbs.
const _SP_INTENT_MAP = [
  { rx: /\b(next|todo|what.*should|do.*now|start)\b/i, intent: 'next' },
  { rx: /\b(remember|recall|remind|told)\b/i,           intent: 'remember' },
  { rx: /\b(status|state|how.*going|vital|pulse)\b/i,   intent: 'status' },
];
function _spPickIntent(q) {
  const trimmed = (q || '').trim();
  if (!trimmed) return 'status';
  for (const m of _SP_INTENT_MAP) if (m.rx.test(trimmed)) return m.intent;
  return 'status';
}

const _SP_COMMANDS = [
  { label: 'Chat',              icon: _SP_SVG.chat,      hint: 'Ctrl+J',     action: () => openWindow('chat','Chat','view-chat') },
  { label: 'Knowledge Center',  icon: _SP_SVG.knowledge, hint: 'Ctrl+B',     action: () => openWindow('knowledge','Knowledge','view-knowledge') },
  { label: 'Terminal',          icon: _SP_SVG.terminal,  hint: '',           action: () => openWindow('terminal','Terminal','view-terminal') },
  { label: 'Files',             icon: _SP_SVG.files,     hint: 'in Knowledge', action: () => { openWindow('knowledge','Knowledge','view-knowledge'); setTimeout(() => { if (typeof knowledgeSetTab === 'function') knowledgeSetTab('files'); }, 150); } },
  { label: 'Studio / Proposals',icon: _SP_SVG.studio,    hint: 'Ctrl+P',     action: () => openWindow('studio','Studio','view-studio') },
  { label: 'Git',               icon: _SP_SVG.git,       hint: 'Ctrl+G',     action: () => { openWindow('studio','Studio','view-studio'); setTimeout(()=>{ if(typeof studioSetTab==='function') studioSetTab('git'); },120); } },
  { label: 'Tickets',           icon: _SP_SVG.tickets,   hint: 'Ctrl+T',     action: () => openWindow('tickets','Tickets','view-tickets') },
  { label: 'Monitor',           icon: _SP_SVG.monitor,   hint: '',           action: () => openWindow('monitor','Monitor','view-monitor') },
  { label: 'Email',             icon: _SP_SVG.email,     hint: 'Ctrl+E',     action: () => openWindow('email','Email','view-email') },
  { label: 'Library',           icon: _SP_SVG.library,   hint: '',           action: () => openWindow('library','Library','view-library') },
  { label: 'Media Center',      icon: _SP_SVG.media,     hint: '',           action: () => openWindow('media-center','Media Center','view-media-center') },
  { label: 'Memory',            icon: _SP_SVG.memory,    hint: '',           action: () => openWindow('memory','Memory','view-memory') },
  { label: 'User Guide',        icon: _SP_SVG.guide,     hint: '',           action: () => openWindow('guide','User Guide','view-guide') },
  { label: 'Skills',            icon: _SP_SVG.skills,    hint: '',           action: () => openWindow('skills','Skills','view-skills') },
  { label: 'Vortex',            icon: _SP_SVG.vortex,    hint: '',           action: () => openWindow('time-wizard','Vortex','view-time-wizard') },
  { label: 'Documents',         icon: _SP_SVG.docs,      hint: '',           action: () => openWindow('docs','Documents','view-docs') },
  { label: 'Go Home',           icon: _SP_SVG.home,      hint: 'Ctrl+H',     action: () => { if(typeof goHome==='function') goHome(); } },
  { label: 'Keyboard Shortcuts',icon: _SP_SVG.help,      hint: '?',          action: () => { const m = document.getElementById('shortcuts-help-modal'); if (m) m.classList.add('open'); } },
];

let _spOpen = false;
let _spDebounce = null;
let _spActiveIdx = -1;
let _spItems = [];   // flat list of rendered action refs for keyboard nav

function openSpotlight() {
  const overlay = document.getElementById('spotlight-overlay');
  const input   = document.getElementById('spotlight-input');
  if (!overlay) return;
  _spOpen = true;
  overlay.classList.add('open');
  input.value = '';
  _spActiveIdx = -1;
  _spRenderCommands('');
  // Seven's empty-state: pull suggestions in the background and prepend them.
  _spLoadSevenSuggestions();
  requestAnimationFrame(() => input.focus());
}

/* Seven empty-state — fetches /api/seven/suggest and prepends a section.
   Failure is silent; spotlight still works without Seven. */
function _spLoadSevenSuggestions() {
  const results = document.getElementById('spotlight-results');
  if (!results) return;
  fetch('/api/seven/suggest').then(r => r.json()).then(data => {
    if (!_spOpen) return;
    // Only render if user hasn't started typing.
    const input = document.getElementById('spotlight-input');
    if (input && input.value.trim()) return;
    const items = (data && data.items) || [];
    if (!items.length) return;
    let html = `<div class="spotlight-section-header">Seven sees</div>`;
    items.slice(0, 6).forEach(it => {
      const idx = _spItems.length;
      const target = it.target ? `${it.target.kind}:${it.target.id}` : '';
      html += `<div class="spotlight-item" data-sp-idx="${idx}" onclick="_spActivate(${idx})">
        <div class="spotlight-item-icon">${_SP_SVG.seven}</div>
        <div class="spotlight-item-text">
          <div class="spotlight-item-title">${(it.label || '').replace(/</g,'&lt;')}</div>
          <div class="spotlight-item-sub">${(it.detail || '').replace(/</g,'&lt;')}</div>
        </div>
        ${target ? `<span class="spotlight-item-hint">${target}</span>` : ''}
      </div>`;
      _spItems.push({ type: 'seven', data: it });
    });
    // Prepend so suggestions appear above the Commands list.
    results.insertAdjacentHTML('afterbegin', html);
  }).catch(() => {});
}

/* Seven focus-mode — when the query is a record id (S-…, B-…, PR-…, P-…)
   call /api/seven/observe and render the related-records section. */
function _spLoadSevenFocus(rid) {
  const results = document.getElementById('spotlight-results');
  if (!results) return;
  fetch(`/api/seven/observe?focus=${encodeURIComponent(rid)}&limit_recent=0&limit_open=0`)
    .then(r => r.json()).then(data => {
      if (!_spOpen) return;
      const input = document.getElementById('spotlight-input');
      if (!input || input.value.trim().toUpperCase() !== rid.toUpperCase()) return;
      const focus = data.focus || {};
      const rel = data.related || {};
      const counts = rel.counts || {};
      let html = `<div class="spotlight-section-header">Seven · ${focus.kind || '?'}:${focus.id || rid}</div>`;
      const idx0 = _spItems.length;
      html += `<div class="spotlight-item" data-sp-idx="${idx0}" onclick="_spActivate(${idx0})">
        <div class="spotlight-item-icon">${_SP_SVG.focus}</div>
        <div class="spotlight-item-text">
          <div class="spotlight-item-title">Open ${focus.kind || 'record'} ${focus.id || rid}</div>
          <div class="spotlight-item-sub">${Object.entries(counts).map(([k,v])=>`${k}×${v}`).join(' · ') || 'no edges'}</div>
        </div>
      </div>`;
      _spItems.push({ type: 'seven_focus', data: { focus } });

      // Flatten outgoing+incoming neighbours into rows.
      const buckets = [
        { dir: 'out', map: rel.outgoing || {} },
        { dir: 'in',  map: rel.incoming || {} },
      ];
      buckets.forEach(b => {
        Object.entries(b.map).forEach(([relName, edges]) => {
          (edges || []).slice(0, 8).forEach(e => {
            const idx = _spItems.length;
            const otherKind = b.dir === 'out' ? e.dst_kind : e.src_kind;
            const otherId   = b.dir === 'out' ? e.dst_id   : e.src_id;
            const arrow = b.dir === 'out' ? '→' : '←';
            html += `<div class="spotlight-item" data-sp-idx="${idx}" onclick="_spActivate(${idx})">
              <div class="spotlight-item-icon">${_SP_SVG.seven}</div>
              <div class="spotlight-item-text">
                <div class="spotlight-item-title">${arrow} ${relName}: ${otherKind}:${otherId}</div>
              </div>
              <span class="spotlight-item-hint">${b.dir}</span>
            </div>`;
            _spItems.push({ type: 'seven_focus', data: { focus: { kind: otherKind, id: otherId } } });
          });
        });
      });
      results.insertAdjacentHTML('beforeend', html);
    }).catch(() => {});
}

/* Ask-Seven mode — query starts with "?". Hits /api/seven/explain for the
   narrative, /decide for ranked proposals. Renders narrative lines + proposals
   above the (optional) record-focus walk. Failure is silent. */
function _spLoadSevenAsk(rawQuery) {
  const results = document.getElementById('spotlight-results');
  if (!results) return;
  const m = _SP_ASK_RX.exec(rawQuery || '');
  const tail = (m && m[1] || '').trim();
  const intent = _spPickIntent(tail);
  // Detect a focus record id inside the tail so "?status of S-7D7677C6E2"
  // also pivots to that record.
  let focus = null;
  const tokens = tail.split(/\s+/);
  for (const tok of tokens) {
    if (_SP_RECORD_RX.test(tok)) { focus = tok.toUpperCase(); break; }
  }
  const explainUrl = focus
    ? `/api/seven/explain?focus=${encodeURIComponent(focus)}`
    : `/api/seven/explain`;
  const decideUrl = focus
    ? `/api/seven/decide?intent=${encodeURIComponent(intent)}&focus=${encodeURIComponent(focus)}`
    : `/api/seven/decide?intent=${encodeURIComponent(intent)}`;

  const inputAtSend = (document.getElementById('spotlight-input') || {}).value;

  Promise.all([
    fetch(explainUrl).then(r => r.json()).catch(() => ({})),
    fetch(decideUrl).then(r => r.json()).catch(() => ({})),
  ]).then(([explainData, decideData]) => {
    if (!_spOpen) return;
    const inputNow = document.getElementById('spotlight-input');
    if (!inputNow || inputNow.value !== inputAtSend) return; // user kept typing

    const lines = (explainData && explainData.lines) || [];
    const proposals = (decideData && decideData.proposals) || [];
    if (!lines.length && !proposals.length) return;

    let html = `<div class="spotlight-section-header">Seven · ask · intent=${intent}${focus ? ' · '+focus : ''}</div>`;

    // Narrative lines first — rendered as non-actionable info rows.
    if (lines.length) {
      lines.forEach(line => {
        const idx = _spItems.length;
        html += `<div class="spotlight-item spotlight-seven-narr" data-sp-idx="${idx}" onclick="_spActivate(${idx})">
          <div class="spotlight-item-icon">${_SP_SVG.seven}</div>
          <div class="spotlight-item-text">
            <div class="spotlight-item-title">${(line || '').replace(/</g,'&lt;')}</div>
          </div>
        </div>`;
        _spItems.push({ type: 'seven_narr', data: { line } });
      });
    }

    // Proposals — actionable; activating routes to target record (if any).
    if (proposals.length) {
      proposals.slice(0, 8).forEach(p => {
        const idx = _spItems.length;
        const t = p.target || null;
        const tgtLbl = t ? `${t.kind}:${t.id}` : '';
        const conf = (typeof p.confidence === 'number')
          ? `conf ${(p.confidence*100|0)}%` : '';
        const action = (p.action || 'review').toUpperCase();
        const sub = [p.rationale || '', conf].filter(Boolean).join(' · ');
        html += `<div class="spotlight-item" data-sp-idx="${idx}" onclick="_spActivate(${idx})">
          <div class="spotlight-item-icon">${_SP_SVG.seven}</div>
          <div class="spotlight-item-text">
            <div class="spotlight-item-title">[${action}] ${(p.label || '').replace(/</g,'&lt;')}</div>
            <div class="spotlight-item-sub">${sub.replace(/</g,'&lt;')}</div>
          </div>
          ${tgtLbl ? `<span class="spotlight-item-hint">${tgtLbl}</span>` : ''}
        </div>`;
        _spItems.push({ type: 'seven', data: p });
      });
    }

    // Show that Seven is propose-only.
    if (decideData && decideData.refused) {
      const idx = _spItems.length;
      html += `<div class="spotlight-item spotlight-seven-narr" data-sp-idx="${idx}" onclick="_spActivate(${idx})">
        <div class="spotlight-item-icon">${_SP_SVG.seven}</div>
        <div class="spotlight-item-text">
          <div class="spotlight-item-title">${(decideData.refused_reason || 'propose-only').replace(/</g,'&lt;')}</div>
        </div>
      </div>`;
      _spItems.push({ type: 'seven_narr', data: {} });
    }

    results.insertAdjacentHTML('afterbegin', html);
  });
}

function closeSpotlight() {
  const overlay = document.getElementById('spotlight-overlay');
  if (!overlay) return;
  _spOpen = false;
  overlay.classList.remove('open');
  _spItems = [];
  _spActiveIdx = -1;
}

function _spRenderCommands(q) {
  const ql = q.toLowerCase();
  const filtered = ql
    ? _SP_COMMANDS.filter(c => c.label.toLowerCase().includes(ql))
    : _SP_COMMANDS;

  _spItems = [];
  const results = document.getElementById('spotlight-results');
  if (!results) return;

  let html = '';
  if (filtered.length) {
    html += `<div class="spotlight-section-header">Commands</div>`;
    filtered.forEach((c, i) => {
      html += `<div class="spotlight-item" data-sp-idx="${_spItems.length}" onclick="_spActivate(${_spItems.length})">
        <div class="spotlight-item-icon">${c.icon}</div>
        <div class="spotlight-item-text">
          <div class="spotlight-item-title">${c.label}</div>
        </div>
        ${c.hint ? `<span class="spotlight-item-hint">${c.hint}</span>` : ''}
      </div>`;
      _spItems.push({ type: 'command', data: c });
    });
  }
  results.innerHTML = html;
}

function _spAppendDocResults(data) {
  const results = document.getElementById('spotlight-results');
  if (!results || !data.results || !data.results.length) return;

  const groups = [
    { key: 'doc',          header: 'Docs',          icon: _SP_SVG.doc },
    { key: 'kb',           header: 'Workspace',     icon: _SP_SVG.kbdoc },
    { key: 'ticket',       header: 'Tickets',       icon: _SP_SVG.ticket },
    { key: 'proposal',     header: 'Proposals',     icon: _SP_SVG.proposal },
    { key: 'conversation', header: 'Conversations', icon: _SP_SVG.conversation },
    { key: 'memory',       header: 'Memory',        icon: _SP_SVG.memoryRow },
  ];

  let html = '';
  groups.forEach(g => {
    const rows = data.results.filter(r => r.type === g.key);
    if (!rows.length) return;
    html += `<div class="spotlight-section-header">${g.header}</div>`;
    rows.forEach(r => {
      const snippet = r.snippet ? r.snippet.replace(/</g,'&lt;').replace(/>/g,'&gt;') : '';
      const hint = r.section ? r.section : '';
      html += `<div class="spotlight-item" data-sp-idx="${_spItems.length}" onclick="_spActivate(${_spItems.length})">
        <div class="spotlight-item-icon">${g.icon}</div>
        <div class="spotlight-item-text">
          <div class="spotlight-item-title">${(r.title || '').replace(/</g,'&lt;')}</div>
          <div class="spotlight-item-sub">${snippet}</div>
        </div>
        ${hint ? `<span class="spotlight-item-hint">${hint}</span>` : ''}
      </div>`;
      _spItems.push({ type: g.key, data: r });
    });
  });
  results.insertAdjacentHTML('beforeend', html);
}

function _spActivate(idx) {
  const item = _spItems[idx];
  if (!item) return;
  closeSpotlight();
  const t = item.type;
  const d = item.data || {};
  if (t === 'command') {
    d.action();
  } else if (t === 'doc' || t === 'kb') {
    openWindow('docs', 'Documents', 'view-docs');
    setTimeout(() => {
      if (typeof docsSetTab === 'function') docsSetTab(t === 'doc' ? 'kb' : 'workspace');
    }, 200);
  } else if (t === 'ticket') {
    openWindow('tickets', 'Tickets', 'view-tickets');
  } else if (t === 'proposal') {
    openWindow('studio', 'Studio', 'view-studio');
    setTimeout(() => {
      if (typeof studioSetTab === 'function') studioSetTab('proposals');
    }, 200);
  } else if (t === 'conversation') {
    openWindow('chat', 'Chat', 'view-chat');
    if (d.conversation_id && typeof loadConversation === 'function') {
      setTimeout(() => { try { loadConversation(d.conversation_id); } catch(e){} }, 300);
    }
  } else if (t === 'memory') {
    openWindow('memory', 'Memory', 'view-memory');
  } else if (t === 'seven_narr') {
    // Narrative line — just close, no navigation.
    return;
  } else if (t === 'seven') {
    // Seven suggestion: route to its target if any; else open focus.
    const tgt = d.target;
    if (tgt && tgt.id) {
      // Reopen spotlight pre-filled with the record id so user can dig deeper.
      setTimeout(() => {
        openSpotlight();
        const inp = document.getElementById('spotlight-input');
        if (inp) {
          inp.value = tgt.id;
          inp.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }, 60);
    }
  } else if (t === 'seven_focus') {
    const f = d.focus || {};
    if (!f.id) return;
    // Re-pivot spotlight onto this neighbour.
    setTimeout(() => {
      openSpotlight();
      const inp = document.getElementById('spotlight-input');
      if (inp) {
        inp.value = f.id;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }, 60);
  }
}

function _spSetActive(idx) {
  const all = document.querySelectorAll('#spotlight-results .spotlight-item');
  all.forEach(el => el.classList.remove('sp-active'));
  _spActiveIdx = Math.max(0, Math.min(idx, _spItems.length - 1));
  const target = document.querySelector(`[data-sp-idx="${_spActiveIdx}"]`);
  if (target) {
    target.classList.add('sp-active');
    target.scrollIntoView({ block: 'nearest' });
  }
}

// Wire up input events once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const overlay = document.getElementById('spotlight-overlay');
  const input   = document.getElementById('spotlight-input');
  if (!overlay || !input) return;

  // Click outside box closes
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeSpotlight();
  });

  // Input: instant command filter + debounced doc search + Seven focus mode
  input.addEventListener('input', () => {
    const q = input.value.trim();
    _spRenderCommands(q);
    clearTimeout(_spDebounce);
    if (!q) {
      // empty → repopulate Seven's empty-state suggestions.
      _spLoadSevenSuggestions();
      return;
    }
    // Record-id query → ask Seven directly (no debounce — cheap call).
    if (_SP_RECORD_RX.test(q)) {
      _spLoadSevenFocus(q);
      return;
    }
    // Ask-Seven query: leading "?" routes to /explain + /decide.
    if (_SP_ASK_RX.test(q)) {
      _spLoadSevenAsk(q);
      return;
    }
    if (q.length >= 2) {
      _spDebounce = setTimeout(() => {
        fetch(`/api/search/global?q=${encodeURIComponent(q)}`)
          .then(r => r.json())
          .then(data => _spAppendDocResults(data))
          .catch(() => {});
      }, 250);
    }
  });

  // Keyboard nav inside spotlight
  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeSpotlight(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); _spSetActive(_spActiveIdx + 1); return; }
    if (e.key === 'ArrowUp')   { e.preventDefault(); _spSetActive(_spActiveIdx - 1); return; }
    if (e.key === 'Enter') {
      e.preventDefault();
      const idx = _spActiveIdx >= 0 ? _spActiveIdx : 0;
      _spActivate(idx);
    }
  });
});
