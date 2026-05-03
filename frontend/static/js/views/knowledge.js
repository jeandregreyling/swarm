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
  { id: 'memory',  label: 'Memory',  icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.3"/><path d="M8 5v3l2 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>' },
  { id: 'library', label: 'Library', icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M3 3.5h3v9H3zM7 3.5h3v9H7zM11.5 3.5l2.5 8.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>' },
  { id: 'tasker',  label: 'Tasker',  icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><path d="M8 5v3l2 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>' },
  { id: 'guide',   label: 'Guide',   icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M3 2.5h10v11H3zM5.5 6h5M5.5 8.5h5M5.5 11h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>' },
];

function loadKnowledgeData(win) {
  _knowledgeWin = win;
  _knowledgeLoaded = { files: false, docs: false, memory: false, library: false, tasker: false, guide: false };

  const root = win.el.querySelector('#knowledge-root');
  if (!root) return;

  // Build tab bar
  const tabBar = root.querySelector('#knowledge-tab-bar');
  if (tabBar) {
    const tabsHtml = _KN_TABS.map(t =>
      `<button class="kn-tab${t.id === _knowledgeTab ? ' kn-tab-active' : ''}" data-kn-tab="${t.id}" onclick="knowledgeSetTab('${t.id}')">${t.icon} ${t.label}</button>`
    ).join('');
    // Trailing (i) info button — explains what this panel does
    const infoHtml = `<button class="kn-tab kn-info-btn" type="button" onclick="knowledgeOpenInfo()" title="What is the Knowledge Center?" style="margin-left:auto;border-radius:50%;width:26px;height:26px;padding:0;display:inline-flex;align-items:center;justify-content:center;">
      <svg viewBox="0 0 16 16" width="12" height="12" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><path d="M8 7.2v4M8 5.2h0" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
    </button>`;
    tabBar.style.display = 'flex';
    tabBar.style.alignItems = 'center';
    tabBar.innerHTML = tabsHtml + infoHtml;
  }

  // P4-S37: refresh interests strip whenever Knowledge opens
  knowledgeRefreshInterestStrip();

  // Show initial tab
  knowledgeSetTab(_knowledgeTab);
}

// P4-S37 — populate the interests strip in the Knowledge header
function knowledgeRefreshInterestStrip() {
  const list = document.getElementById('kn-interests-list');
  if (!list) return;
  fetch('/api/interests').then(r => r.json()).then(d => {
    const items = (d && (d.interests || d.topics || d.items)) || [];
    if (!Array.isArray(items) || !items.length) {
      list.textContent = 'no topics yet — click "Edit interests" to add a few.';
      return;
    }
    const labels = items.slice(0, 10).map(it => typeof it === 'string' ? it : (it.topic || it.label || it.name)).filter(Boolean);
    list.innerHTML = labels.map(l =>
      `<span style="display:inline-block;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:1px 8px;margin-right:4px;color:var(--text);font-style:normal;font-size:10.5px;">${_knEsc(l)}</span>`
    ).join('') + (items.length > labels.length ? `<span style="color:var(--text-dim);">+${items.length - labels.length} more</span>` : '');
  }).catch(() => { list.textContent = '(unable to load)'; });
  // STEP-KC-INTERESTS-GENERAL-KNOWLEDGE-SUGGESTIONS-20260430 — render
  // adjacency-based suggestions next to the existing topics so the user can
  // approve/ignore optional general-knowledge additions with a one-click
  // surface. Each suggestion shows *why* it was suggested.
  knowledgeRefreshSuggestions();
}

function knowledgeRefreshSuggestions() {
  const strip = document.getElementById('kn-interests-strip');
  if (!strip) return;
  // Mount/replace a sibling row inside the strip for suggestions.
  let row = document.getElementById('kn-interests-suggestions');
  if (!row) {
    row = document.createElement('div');
    row.id = 'kn-interests-suggestions';
    row.style.cssText = 'flex-basis:100%;display:none;margin-top:6px;padding-top:6px;border-top:1px dashed color-mix(in srgb,var(--accent) 25%,var(--border));font-size:10.5px;color:var(--text-dim);';
    strip.appendChild(row);
  }
  let dismissed;
  try { dismissed = new Set(JSON.parse(localStorage.getItem('swarm_kc_suggestions_dismissed') || '[]')); }
  catch (_) { dismissed = new Set(); }
  fetch('/api/library/topics/suggestions').then(r => r.json()).then(d => {
    const sugs = (d && d.suggestions) || [];
    const active = sugs.filter(s => !dismissed.has((s.topic || '').toLowerCase()));
    if (!active.length) { row.style.display = 'none'; row.innerHTML = ''; return; }
    row.style.display = '';
    row.innerHTML =
      '<span style="color:var(--text);font-weight:600;margin-right:6px;">You might also like</span>' +
      active.map(s => {
        const t = _knEsc(s.topic);
        const why = _knEsc(s.because || '');
        const cat = _knEsc(s.category || 'general');
        return `<span style="display:inline-flex;align-items:center;gap:4px;background:color-mix(in srgb,var(--accent) 7%,var(--card));border:1px solid var(--border);border-radius:999px;padding:2px 4px 2px 10px;margin:2px 4px 2px 0;">
          <span title="${why}" style="color:var(--text);">${t}</span>
          <button onclick="knowledgeApproveSuggestion('${t.replace(/'/g, "\\'")}','${cat}')" title="Add to your topics — ${why}" style="background:var(--accent);color:#000;border:none;border-radius:999px;padding:1px 8px;font-size:9.5px;font-weight:700;cursor:pointer;">+ Add</button>
          <button onclick="knowledgeIgnoreSuggestion('${t.replace(/'/g, "\\'")}')" title="Hide this suggestion" style="background:transparent;border:none;color:var(--text-dim);cursor:pointer;font-size:11px;line-height:1;padding:0 4px;">✕</button>
        </span>`;
      }).join('') +
      '<span style="color:var(--text-dim);margin-left:4px;">— suggestions are based on adjacency to topics you already added, never on chat content.</span>';
  }).catch(() => { row.style.display = 'none'; });
}

function knowledgeApproveSuggestion(topic, category) {
  fetch('/api/library/topics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, category: category || 'general', source: 'suggestion' }),
  }).then(r => r.json()).then(d => {
    if (d && d.ok) {
      if (typeof showToast === 'function') showToast(`Added "${topic}" to your topics`, 'success');
      knowledgeRefreshInterestStrip();
    } else if (typeof showToast === 'function') {
      showToast('Could not add topic: ' + ((d && d.error) || 'unknown'), 'error');
    }
  }).catch(() => {
    if (typeof showToast === 'function') showToast('Network error adding topic', 'error');
  });
}

function knowledgeIgnoreSuggestion(topic) {
  let dismissed;
  try { dismissed = new Set(JSON.parse(localStorage.getItem('swarm_kc_suggestions_dismissed') || '[]')); }
  catch (_) { dismissed = new Set(); }
  dismissed.add(String(topic || '').toLowerCase());
  try { localStorage.setItem('swarm_kc_suggestions_dismissed', JSON.stringify(Array.from(dismissed))); } catch (_) {}
  knowledgeRefreshSuggestions();
}

window.knowledgeRefreshSuggestions = knowledgeRefreshSuggestions;
window.knowledgeApproveSuggestion = knowledgeApproveSuggestion;
window.knowledgeIgnoreSuggestion = knowledgeIgnoreSuggestion;

/* Info popover: describes Knowledge Center + how Ctrl+Space plugs into it */
function knowledgeOpenInfo() {
  let modal = document.getElementById('kn-info-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'kn-info-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.5);backdrop-filter:blur(4px);opacity:0;pointer-events:none;transition:opacity .15s;';
    modal.innerHTML = `
      <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:22px 26px;max-width:540px;width:92%;max-height:86vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,0.4);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="font-size:14px;font-weight:700;color:var(--text);">About the Knowledge Center</div>
          <button onclick="document.getElementById('kn-info-modal').style.opacity=0;document.getElementById('kn-info-modal').style.pointerEvents='none';" style="background:none;border:none;color:var(--text-dim);cursor:pointer;display:flex;align-items:center;padding:4px;">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </button>
        </div>
        <div style="font-size:12px;line-height:1.65;color:var(--text);">
          <p style="margin:0 0 10px;"><strong>Knowledge Center</strong> is the swarm's unified memory — your files, project docs and curated library in one place.</p>
          <div style="display:grid;grid-template-columns:70px 1fr;gap:6px 12px;margin:10px 0 14px;font-size:11.5px;">
            <div style="color:var(--accent);font-weight:700;">Files</div><div>Upload PDFs, notes and attachments. Everything is indexed for later search.</div>
            <div style="color:var(--accent);font-weight:700;">Docs</div><div>Project documentation (<code style="font-size:10.5px;">docs/</code>) — architecture, roadmap, runbooks.</div>
            <div style="color:var(--accent);font-weight:700;">Library</div><div>Curated sources: URLs, books, references the swarm can pull from.</div>
            <div style="color:var(--accent);font-weight:700;">Guide</div><div>Step-by-step user guide — how to use every part of Fridays.</div>
          </div>
          <div style="padding:10px 12px;border:1px solid color-mix(in srgb,var(--accent) 45%,var(--border));border-radius:8px;background:color-mix(in srgb,var(--accent) 9%,var(--card));margin:10px 0 12px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <svg viewBox="0 0 20 20" width="14" height="14" fill="none" style="color:var(--accent);"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" stroke-width="1.6"/><path d="M13 13l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
              <strong>Tip: Spotlight searches all of it</strong>
              <kbd style="margin-left:auto;background:var(--window-header);border:1px solid var(--border);border-radius:3px;padding:1px 6px;font-size:11px;font-family:inherit;">Ctrl+Space</kbd>
            </div>
            <div style="font-size:11px;color:var(--text-dim);">Press Ctrl+Space from anywhere — results include docs, KB, tickets, proposals, conversations and memory.</div>
          </div>
          <p style="margin:6px 0 10px;font-size:11.5px;color:var(--text-dim);">
            <strong style="color:var(--text);">How retrieval works:</strong> documents are split into chunks, embedded, and matched against your query. Chat answers cite the source chunks when they use the knowledge base. Try the <strong style="color:var(--text);">Ask the knowledge base</strong> bar at the top of this panel to see retrieval in action.
          </p>
          <!-- Seed interests: helps the swarm pre-fetch relevant knowledge -->
          <div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-top:12px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
              <svg viewBox="0 0 16 16" width="13" height="13" fill="none" style="color:var(--accent);"><path d="M8 2v12M2 8h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
              <strong style="font-size:12px;">Tell the swarm what you're into</strong>
            </div>
            <div style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">Add topics so Librarian/Scholar/Seeker can surface relevant sources proactively. One per line, or comma-separated.</div>
            <textarea id="kn-seed-input" rows="3" placeholder="e.g. rust, local LLMs, homelab automation"
              style="width:100%;background:var(--window-header);border:1px solid var(--border);border-radius:6px;padding:7px 10px;font-size:11.5px;color:var(--text);font-family:inherit;outline:none;resize:vertical;box-sizing:border-box;"></textarea>
            <div style="display:flex;align-items:center;gap:8px;margin-top:8px;">
              <button onclick="knowledgeSeedInterests()" style="background:var(--accent);color:#000;border:none;border-radius:6px;padding:6px 14px;font-size:11px;font-weight:700;cursor:pointer;">Save interests</button>
              <span id="kn-seed-status" style="font-size:11px;color:var(--text-dim);"></span>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
  modal.style.opacity = '1';
  modal.style.pointerEvents = 'auto';
}

/* Save free-text topics (comma- or newline-separated) via /api/interests/seed */
async function knowledgeSeedInterests() {
  const ta = document.getElementById('kn-seed-input');
  const status = document.getElementById('kn-seed-status');
  if (!ta) return;
  const raw = (ta.value || '').trim();
  if (!raw) { if (status) status.textContent = 'Enter at least one topic.'; return; }
  const topics = raw.split(/[\n,]+/).map(t => t.trim()).filter(Boolean).slice(0, 30);
  if (!topics.length) { if (status) status.textContent = 'Nothing to save.'; return; }
  if (status) status.textContent = 'Saving…';
  try {
    const r = await fetch('/api/interests/seed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topics }),
    });
    const d = await r.json();
    if (d && d.ok) {
      if (status) status.textContent = `Saved ${d.count || 0} topic${d.count === 1 ? '' : 's'}.`;
      ta.value = '';
      if (typeof showToast === 'function') showToast('Interests saved — Librarian will keep an eye out.');
      // P4-S37: refresh the in-page strip immediately
      try { knowledgeRefreshInterestStrip(); } catch (_) {}
    } else {
      if (status) status.textContent = `Error: ${(d && d.error) || 'failed'}`;
    }
  } catch (err) {
    if (status) status.textContent = `Error: ${err}`;
  }
}

/* Run a RAG query against /api/library/search and render the top chunks. */
async function knowledgeRunQuery() {
  const inp = document.getElementById('kn-quick-query-input');
  const out = document.getElementById('kn-quick-query-results');
  const clr = document.getElementById('kn-quick-query-clear');
  if (!inp || !out) return;
  const q = (inp.value || '').trim();
  if (!q) return;
  out.style.display = '';
  out.innerHTML = `<div style="padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card);font-size:11px;color:var(--text-dim);">Retrieving…</div>`;
  if (clr) clr.style.display = '';
  try {
    const r = await fetch('/api/library/search?q=' + encodeURIComponent(q) + '&k=5');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'search failed');
    const results = d.results || [];
    if (!results.length) {
      out.innerHTML = `<div style="padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--card);font-size:11.5px;color:var(--text-dim);">
        <strong style="color:var(--text);">No knowledge matched "${_knEsc(q)}".</strong>
        <div style="margin-top:4px;">Try different keywords, or add sources in the Library tab so the swarm has something to retrieve from.</div>
      </div>`;
      return;
    }
    const header = `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 10px;font-size:10.5px;color:var(--text-dim);">
      <span><strong style="color:var(--text);">${results.length}</strong> chunks retrieved for "${_knEsc(q)}"</span>
      <span>Top result: <strong style="color:var(--text);">${Math.round((results[0].score || 0) * 100)}% match</strong></span>
    </div>`;
    const rows = results.map((r, idx) => {
      const scorePct = Math.round((r.score || 0) * 100);
      const excerpt = _knEsc((r.chunk_text || '').slice(0, 240));
      const title = _knEsc(r.title || 'Untitled');
      const sourceType = _knEsc(r.source_type || 'source');
      const path = _knEsc(r.path || r.source_path || r.url || '');
      // P4-S36: every result is selectable — Open / Send to chat / Copy.
      return `<div data-kn-result-idx="${idx}" style="padding:8px 10px;border:1px solid var(--border);border-radius:8px;background:var(--card);margin-bottom:6px;">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:4px;">
          <div style="font-size:11.5px;font-weight:700;color:var(--text);flex:1;min-width:0;">${title}</div>
          <div style="font-size:10px;color:var(--text-dim);white-space:nowrap;">${sourceType} · ${scorePct}%</div>
        </div>
        <div style="font-size:11px;color:var(--text-dim);line-height:1.55;margin-bottom:6px;">${excerpt}…</div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
          ${path ? `<button onclick="knowledgeOpenResult('${path.replace(/'/g, "\\'")}')" style="background:var(--accent);color:#000;border:none;border-radius:5px;padding:3px 10px;font-size:10px;font-weight:700;cursor:pointer;">Open</button>` : ''}
          <button onclick="knowledgeSendResultToChat('${title.replace(/'/g, "\\'")}', '${path.replace(/'/g, "\\'")}')" style="background:var(--window-header);border:1px solid var(--border);border-radius:5px;padding:3px 10px;font-size:10px;color:var(--text);cursor:pointer;">Send to chat</button>
          ${path ? `<button onclick="knowledgeCopyResultPath('${path.replace(/'/g, "\\'")}')" style="background:transparent;border:1px solid var(--border);border-radius:5px;padding:3px 10px;font-size:10px;color:var(--text-dim);cursor:pointer;">Copy path</button>` : ''}
          ${path ? `<span style="font-size:10px;color:var(--text-dim);font-family:monospace;margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:60%;">${path}</span>` : ''}
        </div>
      </div>`;
    }).join('');
    out.innerHTML = header + rows;
  } catch (err) {
    out.innerHTML = `<div style="padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card);font-size:11px;color:var(--danger);">Retrieval error: ${_knEsc(String(err))}</div>`;
  }
}

function knowledgeClearQuery() {
  const inp = document.getElementById('kn-quick-query-input');
  const out = document.getElementById('kn-quick-query-results');
  const clr = document.getElementById('kn-quick-query-clear');
  if (inp) inp.value = '';
  if (out) { out.style.display = 'none'; out.innerHTML = ''; }
  if (clr) clr.style.display = 'none';
}

function _knEsc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// P4-S36 — actions on selectable RAG results
function knowledgeOpenResult(path) {
  if (!path) return;
  if (/^https?:\/\//i.test(path)) { window.open(path, '_blank', 'noopener'); return; }
  // Open via Files window if available
  if (typeof openWindow === 'function') {
    openWindow('files', 'Files', 'view-files');
    setTimeout(() => {
      if (typeof filesPreviewFileByPath === 'function') filesPreviewFileByPath(path);
      else if (typeof filesNavigateTo === 'function') {
        const dir = path.includes('/') ? path.split('/').slice(0, -1).join('/') : '';
        filesNavigateTo(dir);
      }
    }, 250);
  }
}

function knowledgeSendResultToChat(title, path) {
  const text = path ? `Reference: ${title} — ${path}` : `Reference: ${title}`;
  if (typeof openWindow === 'function') openWindow('chat', 'Chat', 'view-chat');
  setTimeout(() => {
    const inp = document.getElementById('chat-input') || document.querySelector('textarea[id*="chat"]');
    if (inp) {
      inp.value = (inp.value ? inp.value + '\n' : '') + text;
      inp.focus();
      if (typeof showToast === 'function') showToast('Reference dropped into chat input');
    }
  }, 250);
}

function knowledgeCopyResultPath(path) {
  if (!path) return;
  try { navigator.clipboard.writeText(path); if (typeof showToast === 'function') showToast('Path copied'); }
  catch (_) {}
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
  else if (tab === 'memory') {
    const panel = document.getElementById('kn-panel-memory');
    if (!panel) return;
    const tpl = document.getElementById('view-memory');
    if (tpl) {
      const clone = tpl.content.cloneNode(true);
      panel.innerHTML = '';
      panel.appendChild(clone);
    }
    const mockWin = { el: panel };
    if (typeof loadMemoryData === 'function') loadMemoryData(mockWin);
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
  else if (tab === 'tasker') {
    const panel = document.getElementById('kn-panel-tasker');
    if (!panel) return;
    const tpl = document.getElementById('view-tasker');
    if (tpl) {
      const clone = tpl.content.cloneNode(true);
      panel.innerHTML = '';
      panel.appendChild(clone);
    }
    const mockWin = { el: panel };
    if (typeof loadTaskerData === 'function') loadTaskerData(mockWin);
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
