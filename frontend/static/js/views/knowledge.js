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
let _knowledgeLoaded = { files: false, docs: false, library: false };

const _KN_TABS = [
  { id: 'files',   label: 'Files',   icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M2.5 5h4l1-1.5h6V12H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>' },
  { id: 'docs',    label: 'Docs',    icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M4 3.5h7.5v9H4a1.5 1.5 0 0 0 0-3h7.5M4 3.5a1.5 1.5 0 0 0 0 3M4 6.5h7.5" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>' },
  { id: 'library', label: 'Library', icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M3 3.5h3v9H3zM7 3.5h3v9H7zM11.5 3.5l2.5 8.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>' },
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
  }
}
