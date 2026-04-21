'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   spotlight.js — Global Spotlight Search (Ctrl+Space)
   Searches commands (instant), docs + KB (debounced 250ms).
   Exposes: openSpotlight(), closeSpotlight()
────────────────────────────────────────────────────────────────────────── */

const _SP_COMMANDS = [
  { label: 'Chat',              icon: '💬', hint: 'Ctrl+J',     action: () => openWindow('chat','Chat','view-chat') },
  { label: 'Knowledge Center',  icon: '📚', hint: 'Ctrl+B',     action: () => openWindow('knowledge','Knowledge','view-knowledge') },
  { label: 'Terminal',          icon: '⌨️', hint: '',            action: () => openWindow('terminal','Terminal','view-terminal') },
  { label: 'Files',             icon: '📁', hint: '',            action: () => openWindow('files','Files','view-files') },
  { label: 'Studio / Proposals',icon: '🎛', hint: 'Ctrl+P',     action: () => openWindow('studio','Studio','view-studio') },
  { label: 'Git',               icon: '🌿', hint: 'Ctrl+G',     action: () => { openWindow('studio','Studio','view-studio'); setTimeout(()=>{ if(typeof studioSetTab==='function') studioSetTab('git'); },120); } },
  { label: 'Tickets',           icon: '🎫', hint: 'Ctrl+T',     action: () => openWindow('tickets','Tickets','view-tickets') },
  { label: 'Monitor',           icon: '📊', hint: '',            action: () => openWindow('monitor','Monitor','view-monitor') },
  { label: 'Email',             icon: '✉️', hint: 'Ctrl+E',     action: () => openWindow('email','Email','view-email') },
  { label: 'Library',           icon: '🔖', hint: '',            action: () => openWindow('library','Library','view-library') },
  { label: 'Memory',            icon: '🧠', hint: '',            action: () => openWindow('memory','Memory','view-memory') },
  { label: 'User Guide',        icon: '📖', hint: '',            action: () => openWindow('guide','User Guide','view-guide') },
  { label: 'Skills',            icon: '⚡', hint: '',            action: () => openWindow('skills','Skills','view-skills') },
  { label: 'Vortex',            icon: '🌀', hint: '',            action: () => openWindow('time-wizard','Vortex','view-time-wizard') },
  { label: 'Documents',         icon: '📄', hint: '',            action: () => openWindow('docs','Documents','view-docs') },
  { label: 'Go Home',           icon: '🏠', hint: 'Ctrl+H',     action: () => { if(typeof goHome==='function') goHome(); } },
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

  const docs = data.results.filter(r => r.type === 'doc');
  const kbs  = data.results.filter(r => r.type === 'kb');

  let html = '';
  if (docs.length) {
    html += `<div class="spotlight-section-header">Docs</div>`;
    docs.forEach(r => {
      const snippet = r.snippet ? r.snippet.replace(/</g,'&lt;').replace(/>/g,'&gt;') : '';
      html += `<div class="spotlight-item" data-sp-idx="${_spItems.length}" onclick="_spActivate(${_spItems.length})">
        <div class="spotlight-item-icon">📄</div>
        <div class="spotlight-item-text">
          <div class="spotlight-item-title">${r.title}</div>
          <div class="spotlight-item-sub">${snippet}</div>
        </div>
        <span class="spotlight-item-hint">${r.section}</span>
      </div>`;
      _spItems.push({ type: 'doc', data: r });
    });
  }
  if (kbs.length) {
    html += `<div class="spotlight-section-header">Workspace</div>`;
    kbs.forEach(r => {
      const snippet = r.snippet ? r.snippet.replace(/</g,'&lt;').replace(/>/g,'&gt;') : '';
      html += `<div class="spotlight-item" data-sp-idx="${_spItems.length}" onclick="_spActivate(${_spItems.length})">
        <div class="spotlight-item-icon">🗒</div>
        <div class="spotlight-item-text">
          <div class="spotlight-item-title">${r.title}</div>
          <div class="spotlight-item-sub">${snippet}</div>
        </div>
      </div>`;
      _spItems.push({ type: 'kb', data: r });
    });
  }
  results.insertAdjacentHTML('beforeend', html);
}

function _spActivate(idx) {
  const item = _spItems[idx];
  if (!item) return;
  closeSpotlight();
  if (item.type === 'command') {
    item.data.action();
  } else if (item.type === 'doc') {
    // Open Documents window and navigate to the file
    openWindow('docs', 'Documents', 'view-docs');
    if (item.data.filename) {
      setTimeout(() => {
        if (typeof docsSetTab === 'function') docsSetTab('kb');
      }, 200);
    }
  } else if (item.type === 'kb') {
    openWindow('docs', 'Documents', 'view-docs');
    setTimeout(() => {
      if (typeof docsSetTab === 'function') docsSetTab('workspace');
    }, 200);
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
