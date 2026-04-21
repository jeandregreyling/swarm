/**
 * frontend/static/js/views/knowledge.js
 * Knowledge Constellation — unified Files + Docs + Library view (Tier 1.1)
 *
 * Three sub-views arranged as tabs. Each tab lazy-loads the existing
 * sub-view JS: loadFilesData(), loadDocsData(), libInit().
 * Gold glow on system docs. Auto-classification badges.
 *
 * Exposes: loadKnowledgeData(win), knowledgeSetTab(tab)
 */

'use strict';

let _knowledgeWin = null;
let _knowledgeTab = 'files';
let _knowledgeLoaded = { files: false, docs: false, library: false, guide: false };

/* Constellation styling — injected once */
(function _knInjectStyle() {
  if (document.getElementById('kn-constellation-css')) return;
  const s = document.createElement('style'); s.id = 'kn-constellation-css';
  s.textContent = `
    .kn-tab { display:inline-flex;align-items:center;gap:7px;background:color-mix(in srgb, var(--card) 88%, transparent);border:1px solid var(--border);color:var(--text-dim);border-radius:999px;padding:7px 12px;cursor:pointer;font-size:11px;font-weight:700;transition:all .18s;white-space:nowrap; }
    .kn-tab:hover { color:var(--text);border-color:color-mix(in srgb, var(--accent) 38%, var(--border));transform:translateY(-1px); }
    .kn-tab-active { background:var(--accent);color:#000;border-color:var(--accent);box-shadow:0 10px 26px color-mix(in srgb, var(--accent) 28%, transparent); }
    .kn-tab svg { opacity:.9; }
    .kn-system-doc { border-left:2px solid #f7b84b;box-shadow:0 0 6px rgba(247,184,75,0.15); }
    .kn-badge { display:inline-block;padding:2px 6px;border-radius:999px;font-size:9px;font-weight:700;margin-left:6px;letter-spacing:.03em;text-transform:uppercase; }
    .kn-badge-config { background:#3a6b4e33;color:#5cb85c; }
    .kn-badge-doc { background:#f7b84b22;color:#f7b84b; }
    .kn-badge-code { background:#5bc0de22;color:#5bc0de; }
  `;
  document.head.appendChild(s);
})();

const _KN_TABS = [
  { id: 'files',   label: 'Files',   icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M2.5 5h4l1-1.5h6V12H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>' },
  { id: 'docs',    label: 'Docs',    icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M4 3.5h7.5v9H4a1.5 1.5 0 0 0 0-3h7.5M4 3.5a1.5 1.5 0 0 0 0 3M4 6.5h7.5" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>' },
  { id: 'library', label: 'Library', icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M3 3.5h3v9H3zM7 3.5h3v9H7zM11.5 3.5l2.5 8.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>' },
  { id: 'guide',   label: 'Guide',   icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M3 2.5h10v11H3zM5.5 6h5M5.5 8.5h5M5.5 11h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>' },
];

function loadKnowledgeData(win) {
  _knowledgeWin = win;
  _knowledgeLoaded = { files: false, docs: false, library: false };

  const root = win.el.querySelector('#knowledge-root');
  if (!root) return;

  // Build tab bar
  const tabBar = root.querySelector('#knowledge-tab-bar');
  if (tabBar) {
    tabBar.innerHTML = _KN_TABS.map(t =>
      `<button class="kn-tab${t.id === _knowledgeTab ? ' kn-tab-active' : ''}" data-kn-tab="${t.id}" onclick="knowledgeSetTab('${t.id}')">${t.icon} ${t.label}</button>`
    ).join('');
  }

  // Show initial tab
  knowledgeSetTab(_knowledgeTab);
}

function knowledgeSetTab(tab) {
  _knowledgeTab = tab;

  // Update tab buttons
  document.querySelectorAll('.kn-tab').forEach(btn => {
    btn.classList.toggle('kn-tab-active', btn.dataset.knTab === tab);
  });

  // Show/hide panels
  _KN_TABS.forEach(t => {
    const panel = document.getElementById('kn-panel-' + t.id);
    if (panel) panel.style.display = t.id === tab ? '' : 'none';
  });

  // Lazy-load the sub-view
  if (!_knowledgeLoaded[tab]) {
    _knowledgeLoaded[tab] = true;
    _knLoadSubView(tab);
  }
}

function _knLoadSubView(tab) {
  if (tab === 'files') {
    // Inject files template content and init
    const panel = document.getElementById('kn-panel-files');
    if (!panel) return;
    const tpl = document.getElementById('view-files');
    if (tpl) {
      const clone = tpl.content.cloneNode(true);
      panel.innerHTML = '';
      panel.appendChild(clone);
    }
    // Create a mock win object for files
    const mockWin = { el: panel };
    if (typeof loadFilesData === 'function') loadFilesData(mockWin);
    setTimeout(() => _knClassifyItems(panel), 500);
  }
  else if (tab === 'docs') {
    const panel = document.getElementById('kn-panel-docs');
    if (!panel) return;
    const tpl = document.getElementById('view-docs');
    if (tpl) {
      const clone = tpl.content.cloneNode(true);
      panel.innerHTML = '';
      panel.appendChild(clone);
    }
    const mockWin = { el: panel };
    if (typeof loadDocsData === 'function') loadDocsData(mockWin);
    setTimeout(() => _knClassifyItems(panel), 500);
  }
  else if (tab === 'library') {
    const panel = document.getElementById('kn-panel-library');
    if (!panel) return;
    const tpl = document.getElementById('view-library');
    if (tpl) {
      const clone = tpl.content.cloneNode(true);
      panel.innerHTML = '';
      panel.appendChild(clone);
    }
    if (typeof libInit === 'function') libInit();
    setTimeout(() => _knClassifyItems(panel), 500);
  }
  else if (tab === 'guide') {
    const panel = document.getElementById('kn-panel-guide');
    if (!panel) return;
    const tpl = document.getElementById('view-guide');
    if (tpl) {
      const clone = tpl.content.cloneNode(true);
      panel.innerHTML = '';
      panel.appendChild(clone);
    }
    const mockWin = { el: panel };
    if (typeof loadGuideData === 'function') loadGuideData(mockWin);
  }
}

/* Auto-classify items in docs/library panels with gold glow and badges */
function _knClassifyItems(panel) {
  if (!panel) return;
  panel.querySelectorAll('[data-doc-path], [data-file-path]').forEach(el => {
    const p = (el.dataset.docPath || el.dataset.filePath || '').toLowerCase();
    if (p.startsWith('swarm_docs/') || p.startsWith('docs/') || p.endsWith('.md')) {
      el.classList.add('kn-system-doc');
      if (!el.querySelector('.kn-badge')) {
        const badge = document.createElement('span');
        if (p.endsWith('.py') || p.endsWith('.js')) { badge.className = 'kn-badge kn-badge-code'; badge.textContent = 'code'; }
        else if (p.includes('config') || p.endsWith('.yaml') || p.endsWith('.json') || p.endsWith('.toml')) { badge.className = 'kn-badge kn-badge-config'; badge.textContent = 'config'; }
        else { badge.className = 'kn-badge kn-badge-doc'; badge.textContent = 'doc'; }
        const title = el.querySelector('.card-title, .doc-title, [class*="title"]');
        (title || el).appendChild(badge);
      }
    }
  });
}
