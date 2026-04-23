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
};

const _SP_COMMANDS = [
  { label: 'Chat',              icon: _SP_SVG.chat,      hint: 'Ctrl+J',     action: () => openWindow('chat','Chat','view-chat') },
  { label: 'Knowledge Center',  icon: _SP_SVG.knowledge, hint: 'Ctrl+B',     action: () => openWindow('knowledge','Knowledge','view-knowledge') },
  { label: 'Terminal',          icon: _SP_SVG.terminal,  hint: '',           action: () => openWindow('terminal','Terminal','view-terminal') },
  { label: 'Files',             icon: _SP_SVG.files,     hint: '',           action: () => openWindow('files','Files','view-files') },
  { label: 'Studio / Proposals',icon: _SP_SVG.studio,    hint: 'Ctrl+P',     action: () => openWindow('studio','Studio','view-studio') },
  { label: 'Git',               icon: _SP_SVG.git,       hint: 'Ctrl+G',     action: () => { openWindow('studio','Studio','view-studio'); setTimeout(()=>{ if(typeof studioSetTab==='function') studioSetTab('git'); },120); } },
  { label: 'Tickets',           icon: _SP_SVG.tickets,   hint: 'Ctrl+T',     action: () => openWindow('tickets','Tickets','view-tickets') },
  { label: 'Monitor',           icon: _SP_SVG.monitor,   hint: '',           action: () => openWindow('monitor','Monitor','view-monitor') },
  { label: 'Email',             icon: _SP_SVG.email,     hint: 'Ctrl+E',     action: () => openWindow('email','Email','view-email') },
  { label: 'Library',           icon: _SP_SVG.library,   hint: '',           action: () => openWindow('library','Library','view-library') },
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
  requestAnimationFrame(() => input.focus());
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

  // Input: instant command filter + debounced doc search
  input.addEventListener('input', () => {
    const q = input.value.trim();
    _spRenderCommands(q);
    clearTimeout(_spDebounce);
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
