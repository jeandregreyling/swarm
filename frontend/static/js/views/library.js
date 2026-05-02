/**
 * frontend/static/js/views/library.js
 * Knowledge Library — SAP Corner, programming best practices, and consulting pool.
 * Categories, semantic search, dedup, agent context injection.
 *
 * Exposes: libInit(), libSearch(), libToggleAddDrawer(), libSubmitSource(),
 *          libSelectCategory(), libSeedKnowledge()
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let _libSources       = [];
let _libActiveType    = 'text';
let _libSelTags       = new Set();
let _libModelReady    = null;
let _libCategories    = [];
let _libByCat         = {};
let _libActiveCat     = '';
let _libSelectedSource = null;  // currently selected node detail

const _SAP_TAGS = [
  'sap_hcm', 'abap', 'payroll', 'sap_note',
  'ecp', 'btp', 'schema', 'pcr', 'infotype',
  'consulting', 'client', 'legal', 'process', 'project',
];

// SVG icons per source type
const _TYPE_SVG = {
  text: `<svg viewBox="0 0 16 16" width="13" height="13" fill="none"><path d="M3.5 4h9M3.5 7h9M3.5 10h6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  url:  `<svg viewBox="0 0 16 16" width="13" height="13" fill="none"><path d="M6.5 9.5a3 3 0 0 0 4.2 0l1.5-1.5a3 3 0 0 0-4.2-4.2L7 4.8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M9.5 6.5a3 3 0 0 0-4.2 0L3.8 8a3 3 0 0 0 4.2 4.2L9 11.2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  email:`<svg viewBox="0 0 16 16" width="13" height="13" fill="none"><path d="M2.5 4.5h11v8h-11zM2.5 4.5l5.5 4 5.5-4" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`,
  pdf:  `<svg viewBox="0 0 16 16" width="13" height="13" fill="none"><path d="M4 2h6l3 3v9H4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M10 2v3h3M6 8h4M6 10.5h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
};

// ── Init ──────────────────────────────────────────────────────────────────────
function libInit() {
  _libSelTags.clear();
  _libActiveType = 'text';
  _libActiveCat  = '';
  _renderTagGrid();
  _loadCategories();
  _loadSources();
  _checkModel();
  _renderTypeContent();

  const inp = document.getElementById('library-search-input');
  if (inp) {
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') libSearch();
    });
    // Real-time graph highlight as user types
    inp.addEventListener('input', () => {
      if (typeof libGraphHighlight === 'function') libGraphHighlight(inp.value.trim());
      if (!inp.value.trim()) _libHideSearchResults();
    });
  }

  const drop = document.getElementById('library-pdf-drop');
  const fileInput = document.getElementById('library-pdf-input');
  if (drop && fileInput) {
    drop.addEventListener('click', () => fileInput.click());
    drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag-over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('drag-over'));
    drop.addEventListener('drop', e => {
      e.preventDefault();
      drop.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) _setPdfFile(file);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) _setPdfFile(fileInput.files[0]);
    });
  }

  // Category selector change in add drawer
  const catSel = document.getElementById('library-add-category');
  if (catSel) catSel.addEventListener('change', _updateSubcategoryOptions);
}

let _pdfFile = null;

function _setPdfFile(file) {
  _pdfFile = file;
  const drop = document.getElementById('library-pdf-drop');
  if (drop) {
    drop.innerHTML =
      `<div style="display:flex;flex-direction:column;align-items:center;gap:4px;">
        ${_TYPE_SVG.pdf}
        <span style="font-weight:700;color:var(--text);">${_esc(file.name)}</span>
        <span style="font-size:10px;">${(file.size / 1024).toFixed(0)} KB — click to change</span>
      </div>`;
  }
}

// ── Categories ────────────────────────────────────────────────────────────────
async function _loadCategories() {
  try {
    const r = await fetch('/api/library/categories');
    const d = await r.json();
    if (!d.ok) return;
    _libCategories = d.categories || [];
    _libByCat      = d.by_category || {};
    _renderCategoryNav();
    _populateCategorySelect();
  } catch (_) {}
}

function _renderCategoryNav() {
  const nav = document.getElementById('library-category-nav');
  if (!nav) return;
  const total = Object.values(_libByCat).reduce((s, n) => s + n, 0);
  let html = `<button class="lib-cat-btn${_libActiveCat === '' ? ' active' : ''}" data-cat="" onclick="libSelectCategory('', this)">
    <span class="lib-cat-icon"><svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2 3.5h3l1 1h7v8H2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg></span>
    <span class="lib-cat-label">All</span>
    ${total ? `<span class="lib-cat-count">${total}</span>` : ''}
  </button>`;
  for (const cat of _libCategories) {
    const count = _libByCat[cat.id] || 0;
    const active = _libActiveCat === cat.id ? ' active' : '';
    html += `<button class="lib-cat-btn${active}" data-cat="${cat.id}" onclick="libSelectCategory('${cat.id}', this)">
      <span class="lib-cat-icon">${cat.icon}</span>
      <span class="lib-cat-label">${_esc(cat.label)}</span>
      ${count ? `<span class="lib-cat-count">${count}</span>` : ''}
    </button>`;
  }
  nav.innerHTML = html;
}

function libSelectCategory(catId, btn) {
  _libActiveCat = catId;
  document.querySelectorAll('.lib-cat-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  _loadSources();
}

function _populateCategorySelect() {
  const catSel = document.getElementById('library-add-category');
  if (!catSel) return;
  catSel.innerHTML = '';
  for (const cat of _libCategories) {
    const opt = document.createElement('option');
    opt.value = cat.id;
    opt.textContent = `${cat.icon} ${cat.label}`;
    catSel.appendChild(opt);
  }
  _updateSubcategoryOptions();
}

function _updateSubcategoryOptions() {
  const catSel = document.getElementById('library-add-category');
  const subSel = document.getElementById('library-add-subcategory');
  if (!catSel || !subSel) return;
  const catId = catSel.value;
  const cat = _libCategories.find(c => c.id === catId);
  subSel.innerHTML = '<option value="">— None —</option>';
  if (cat && cat.subcategories) {
    for (const sub of cat.subcategories) {
      const opt = document.createElement('option');
      opt.value = sub.id;
      opt.textContent = `${sub.icon} ${sub.label}`;
      subSel.appendChild(opt);
    }
  }
}

// ── Model check / banner ──────────────────────────────────────────────────────
async function _checkModel() {
  try {
    const r = await fetch('/api/library/model-status');
    const d = await r.json();
    _libModelReady = d.ready;
    const banner = document.getElementById('library-model-banner');
    if (banner) {
      banner.classList.toggle('visible', !d.ready);
    }
  } catch (_) {}
}

function libPullModel() {
  const btn = document.getElementById('library-pull-btn');
  if (btn) { btn.textContent = 'Pulling…'; btn.disabled = true; }
  fetch('/api/library/pull-model', { method: 'POST' })
    .then(() => {
      if (btn) btn.textContent = 'Pulling in background — check Ollama logs';
      setTimeout(_checkModel, 15000);
    })
    .catch(() => {
      if (btn) { btn.textContent = 'Pull'; btn.disabled = false; }
    });
}

// ── Sources ───────────────────────────────────────────────────────────────────
async function _loadSources() {
  try {
    let url = '/api/library/sources';
    if (_libActiveCat) url += `?category=${encodeURIComponent(_libActiveCat)}`;
    const r = await fetch(url);
    const d = await r.json();
    if (!d.ok) return;
    _libSources = d.sources || [];
    _renderStats(d.stats || {});
    _renderSourcesList();
    _libInitGraph();
  } catch (_) {}
}

function _libInitGraph() {
  const canvas = document.getElementById('library-graph-canvas');
  const empty  = document.getElementById('library-graph-empty');
  if (!canvas) return;
  if (!_libSources.length) {
    if (empty) empty.classList.add('visible');
    return;
  }
  if (empty) empty.classList.remove('visible');
  // Reset detail panel
  _libHideNodeDetail();
  if (typeof libGraphInit === 'function') {
    libGraphInit(_libSources, canvas, _libNodeClick);
  }
}

function _libNodeClick(source, related) {
  _libSelectedSource = source;
  _libShowNodeDetail(source, related);
}

function _libShowNodeDetail(source, related) {
  const detail  = document.getElementById('library-node-detail');
  const list    = document.getElementById('library-sources-list');
  if (!detail) return;

  const tags = _parseTags(source.domain_tags);
  const cat  = source.category || 'general';
  const catColor = { sap_corner:'#f7b84b', programming:'#5bc0de', fridays:'#5cb85c', general:'#9b9b9b' }[cat] || '#888';

  document.getElementById('library-node-title').textContent = source.title;
  document.getElementById('library-node-meta').innerHTML =
    `<span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:999px;background:${catColor}22;color:${catColor};border:1px solid ${catColor}44;">${cat.replace('_',' ')}</span>` +
    `<span style="font-size:10px;color:var(--text-dim);">${source.source_type}</span>` +
    `<span style="font-size:10px;color:var(--text-dim);">${source.chunk_count || 0} chunks</span>`;

  document.getElementById('library-node-tags').innerHTML = tags.length
    ? tags.map(t => `<span class="lib-node-tag">${_esc(t)}</span>`).join('')
    : '<span style="font-size:11px;color:var(--text-dim);">No tags</span>';

  const relEl = document.getElementById('library-node-related');
  relEl.innerHTML = related.length
    ? related.slice(0, 6).map(r => {
        const rc = { sap_corner:'#f7b84b', programming:'#5bc0de', fridays:'#5cb85c', general:'#9b9b9b' }[r.category] || '#888';
        return `<div class="lib-related-item" onclick="_libNodeClick(${JSON.stringify(r).replace(/"/g,'&quot;')}, [])">
          <span class="lib-related-dot" style="background:${rc};"></span>
          <span>${_esc(r.title)}</span>
        </div>`;
      }).join('')
    : '<span style="font-size:11px;color:var(--text-dim);">No related sources yet</span>';

  const preview = (source.raw_text || source.content || '').slice(0, 500);
  document.getElementById('library-node-preview').textContent = preview || '(No preview available)';

  if (list) list.style.display = 'none';
  detail.style.display = 'flex';
}

function _libHideNodeDetail() {
  const detail = document.getElementById('library-node-detail');
  const list   = document.getElementById('library-sources-list');
  if (detail) detail.style.display = 'none';
  if (list)   list.style.display = '';
  _libSelectedSource = null;
}

function _libHideSearchResults() {
  const sr = document.getElementById('library-search-results');
  const gv = document.getElementById('library-graph-view');
  if (sr) sr.style.display = 'none';
  if (gv) gv.style.display = '';
  if (typeof libGraphReset === 'function') libGraphReset();
}

function libNodeDelete() {
  if (!_libSelectedSource) return;
  libDeleteSource(_libSelectedSource.source_id, null);
  _libHideNodeDetail();
}

function libNodeReprocess() {
  if (!_libSelectedSource) return;
  libReprocess(_libSelectedSource.source_id, null);
}

function _renderStats(stats) {
  const el = document.getElementById('library-stats');
  if (!el) return;
  const total = stats.total_sources || 0;
  const chunks = stats.total_chunks || 0;
  const types  = stats.by_type || {};
  const typeParts = Object.entries(types)
    .map(([k, v]) => `${v} ${k}`)
    .join(' · ');

  el.innerHTML =
    `<span>${total} source${total !== 1 ? 's' : ''}</span>` +
    (chunks ? `<span>·</span><span>${chunks} chunks</span>` : '') +
    (typeParts ? `<span>·</span><span style="color:var(--text-dim);opacity:0.7;">${typeParts}</span>` : '');
}

function _renderSourcesList() {
  const list = document.getElementById('library-sources-list');
  if (!list) return;

  if (!_libSources.length) {
    list.innerHTML =
      `<div style="padding:20px;text-align:center;font-size:11px;color:var(--text-dim);">
        ${_libActiveCat ? 'No sources in this category yet.' : 'No sources yet — add your first document or seed built-in knowledge.'}
      </div>`;
    return;
  }

  list.innerHTML = _libSources.map(s => {
    const tags = _parseTags(s.domain_tags);
    const icon = _TYPE_SVG[s.source_type] || _TYPE_SVG.text;
    const date = _fmtDate(s.created_at);
    const chunks = s.chunk_count || 0;
    return `
      <div class="lib-source-item" data-id="${s.source_id}">
        <div class="lib-source-header">
          <span class="lib-source-icon" style="color:var(--accent);">${icon}</span>
          <span class="lib-source-name">${_esc(s.title)}</span>
        </div>
        <div class="lib-source-meta">
          ${s.category ? `<span class="lib-cat-badge">${_esc(s.category)}${s.subcategory ? '/' + _esc(s.subcategory) : ''}</span>` : ''}
          <span>${s.source_type}</span>
          <span>${date}</span>
          ${chunks ? `<span>${chunks} chunk${chunks !== 1 ? 's' : ''}</span>` : '<span class="lib-source-processing"><span class="lib-spinner"></span> indexing…</span>'}
        </div>
        ${tags.length ? `<div class="lib-source-tags">${tags.map(t => `<span class="lib-tag">${_esc(t)}</span>`).join('')}</div>` : ''}
        <div class="lib-source-actions">
          <button class="lib-source-btn" onclick="libOpenSource(${s.source_id})" title="Open full text">⤢</button>
          <button class="lib-source-btn" onclick="libReclassifyPrompt(${s.source_id}, event)" title="Reclassify / retag">⇄</button>
          <button class="lib-source-btn" onclick="libReprocess(${s.source_id}, this)" title="Re-embed">↻</button>
          <button class="lib-source-btn danger" onclick="libDeleteSource(${s.source_id}, this)" title="Delete"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
        </div>
      </div>`;
  }).join('');
}

async function libDeleteSource(sourceId, btn) {
  // Session 28 Workstream A.3: shared armToConfirm primitive.
  var fire = async function () {
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(`/api/library/sources/${sourceId}`, { method: 'DELETE' });
      const d = await r.json();
      if (d.ok) { _loadSources(); _loadCategories(); }
      else alert('Delete failed: ' + (d.error || 'unknown error'));
    } catch (_) {
      if (btn) btn.disabled = false;
    }
  };
  if (btn && window.SwarmChat && typeof window.SwarmChat.armToConfirm === 'function') {
    window.SwarmChat.armToConfirm(btn, fire, { confirmLabel: '?', timeoutMs: 4000 });
    return;
  }
  if (!confirm('Remove this source and all its chunks?')) return;
  fire();
}

async function libReprocess(sourceId, btn) {
  if (btn) { btn.textContent = '…'; btn.disabled = true; }
  try {
    await fetch(`/api/library/sources/${sourceId}/reprocess`, { method: 'POST' });
    setTimeout(_loadSources, 3000);
  } finally {
    if (btn) { btn.textContent = '↻'; btn.disabled = false; }
  }
}

// ── Search ────────────────────────────────────────────────────────────────────
async function libSearch() {
  const inp = document.getElementById('library-search-input');
  const query = (inp ? inp.value : '').trim();
  if (!query) return;

  const btn = document.getElementById('library-search-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="lib-spinner"></span>'; }

  // Show search results overlay, keep graph in background highlighted
  const gv = document.getElementById('library-graph-view');
  const sr = document.getElementById('library-search-results');
  if (gv) gv.style.display = 'none';
  if (sr) { sr.style.display = ''; sr.innerHTML = `<div style="display:flex;justify-content:center;padding:24px;"><span class="lib-spinner"></span></div>`; }
  if (typeof libGraphHighlight === 'function') libGraphHighlight(query);

  try {
    let url = `/api/library/search?q=${encodeURIComponent(query)}&k=8`;
    if (_libActiveCat) url += `&category=${encodeURIComponent(_libActiveCat)}`;
    const r = await fetch(url);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'search failed');
    _renderResults(d.results || [], query);
  } catch (err) {
    if (sr) sr.innerHTML = `<div class="lib-empty-state"><span style="color:var(--danger);">Search error: ${_esc(String(err))}</span></div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Search'; }
  }
}

function _renderResults(results, query) {
  const panel = document.getElementById('library-search-results');
  if (!panel) return;

  // Back-to-graph button header
  const backBtn = `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 14px;border-bottom:1px solid var(--border);font-size:11px;color:var(--text-dim);">
    <span><strong style="color:var(--text);">${results.length}</strong> results for "${_esc(query)}"</span>
    <button onclick="_libHideSearchResults()" style="background:var(--window-header);border:1px solid var(--border);border-radius:5px;padding:3px 8px;font-size:10px;color:var(--text-dim);cursor:pointer;">← Graph</button>
  </div>`;

  if (!results.length) {
    panel.innerHTML = backBtn +
      `<div class="lib-empty-state">
        <svg viewBox="0 0 24 24" width="40" height="40" fill="none"><circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M16.5 16.5L21 21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <div>No results for <strong>${_esc(query)}</strong>${_libActiveCat ? ` in ${_libActiveCat}` : ''}</div>
        <div style="opacity:0.6;">Try different keywords, change category, or add more sources</div>
      </div>`;
    return;
  }

  const terms = query.toLowerCase().split(/\s+/).filter(t => t.length > 2);

  panel.innerHTML = backBtn + results.map(r => {
    const tags      = _parseTags(r.domain_tags);
    const excerpt   = _highlight(_esc(r.chunk_text.slice(0, 320)), terms);
    const scorePct  = Math.round((r.score || 0) * 100);
    const icon      = _TYPE_SVG[r.source_type] || _TYPE_SVG.text;
    const catLabel  = r.category || 'general';
    const subLabel  = r.subcategory ? `/${r.subcategory}` : '';
    return `
      <div class="lib-result-card" onclick="libExpandResult(${r.source_id}, this)">
        <div class="lib-result-header">
          <div>
            <div class="lib-result-title">${_esc(r.title)}</div>
            <span class="lib-cat-badge">${_esc(catLabel)}${_esc(subLabel)}</span>
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
            <span class="lib-result-type">${icon} ${r.source_type}</span>
            <span class="lib-result-score">${scorePct}% match</span>
          </div>
        </div>
        ${tags.length ? `<div class="lib-result-tags">${tags.map(t => `<span class="lib-tag">${_esc(t)}</span>`).join('')}</div>` : ''}
        <div class="lib-result-excerpt">${excerpt}…</div>
      </div>`;
  }).join('');
}

function libExpandResult(sourceId, card) {
  // Toggle a full-text expansion for the clicked result card
  const existing = card.querySelector('.lib-result-full');
  if (existing) { existing.remove(); return; }

  const excerpt = card.querySelector('.lib-result-excerpt');
  if (!excerpt) return;

  const full = document.createElement('div');
  full.className = 'lib-result-full';
  full.style.cssText = 'margin-top:10px;font-size:11px;color:var(--text);line-height:1.7;white-space:pre-wrap;word-break:break-word;border-top:1px solid var(--border);padding-top:10px;';
  full.textContent = excerpt.textContent; // unhighlighted full text already truncated — good enough
  card.appendChild(full);
}

// ── Add source drawer ─────────────────────────────────────────────────────────
function libToggleAddDrawer() {
  const drawer = document.getElementById('library-add-drawer');
  if (!drawer) return;
  const open = drawer.classList.toggle('open');
  if (open) {
    _pdfFile = null;
    _libSelTags.clear();
    _renderTagGrid();
    _renderTypeContent();
    _populateCategorySelect();
    document.getElementById('library-add-title').value = '';
    ['library-text-content', 'library-url-input', 'library-email-content'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const drop = document.getElementById('library-pdf-drop');
    if (drop) drop.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;gap:6px;">
        ${_TYPE_SVG.pdf}
        <span>Drop PDF here or click to browse</span>
      </div>`;
    // Pre-select category if filter is active
    const catSel = document.getElementById('library-add-category');
    if (catSel && _libActiveCat) {
      catSel.value = _libActiveCat;
      _updateSubcategoryOptions();
    }
  }
}

function libCloseAddDrawer() {
  const drawer = document.getElementById('library-add-drawer');
  if (drawer) drawer.classList.remove('open');
}

function libSetType(type, btn) {
  _libActiveType = type;
  document.querySelectorAll('.lib-type-tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  _renderTypeContent();
}

function _renderTypeContent() {
  ['text', 'url', 'email', 'pdf'].forEach(t => {
    const el = document.getElementById(`library-type-${t}`);
    if (el) el.style.display = t === _libActiveType ? 'flex' : 'none';
  });
}

function _renderTagGrid() {
  const grid = document.getElementById('library-tag-grid');
  if (!grid) return;
  grid.innerHTML = _SAP_TAGS.map(tag =>
    `<button class="lib-tag-toggle${_libSelTags.has(tag) ? ' selected' : ''}"
      onclick="libToggleTag('${tag}', this)">${tag}</button>`
  ).join('');
}

function libToggleTag(tag, btn) {
  if (_libSelTags.has(tag)) {
    _libSelTags.delete(tag);
    btn.classList.remove('selected');
  } else {
    _libSelTags.add(tag);
    btn.classList.add('selected');
  }
}

// ── Submit ────────────────────────────────────────────────────────────────────
async function libSubmitSource() {
  const btn = document.getElementById('library-submit-btn');
  const title       = (document.getElementById('library-add-title')?.value || '').trim();
  const tags        = Array.from(_libSelTags);
  const category    = document.getElementById('library-add-category')?.value || 'general';
  const subcategory = document.getElementById('library-add-subcategory')?.value || '';

  if (btn) { btn.disabled = true; btn.textContent = 'Adding…'; }

  try {
    if (_libActiveType === 'pdf') {
      if (!_pdfFile) { alert('Please select a PDF file first.'); return; }
      const fd = new FormData();
      fd.append('file', _pdfFile);
      if (title) fd.append('title', title);
      fd.append('tags', JSON.stringify(tags));
      fd.append('category', category);
      if (subcategory) fd.append('subcategory', subcategory);
      const r = await fetch('/api/library/ingest-pdf', { method: 'POST', body: fd });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || 'ingest failed');
    } else {
      let content = '';
      if (_libActiveType === 'text') {
        content = document.getElementById('library-text-content')?.value.trim() || '';
      } else if (_libActiveType === 'url') {
        content = document.getElementById('library-url-input')?.value.trim() || '';
      } else if (_libActiveType === 'email') {
        content = document.getElementById('library-email-content')?.value.trim() || '';
      }
      if (!content) { alert('Please enter content to add.'); return; }

      const r = await fetch('/api/library/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: _libActiveType, title, content, tags, category, subcategory }),
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || 'ingest failed');
    }

    libCloseAddDrawer();
    setTimeout(() => { _loadSources(); _loadCategories(); }, 1200);

  } catch (err) {
    alert('Error: ' + String(err));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Add to Library'; }
  }
}

// ── Seed knowledge ────────────────────────────────────────────────────────────
async function libSeedKnowledge() {
  const btn = document.getElementById('library-seed-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Seeding…'; }
  try {
    const r = await fetch('/api/library/seed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection: 'all' }),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'seed failed');
    if (typeof showToast === 'function') {
      showToast(d.message || `Seeded ${d.added} docs`, 'success');
    } else {
      alert(d.message || `Seeded ${d.added} docs (${d.skipped} skipped)`);
    }
    setTimeout(() => { _loadSources(); _loadCategories(); }, 2000);
  } catch (err) {
    alert('Seed error: ' + String(err));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Seed Knowledge'; }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _parseTags(raw) {
  if (!raw) return [];
  try { return JSON.parse(raw); } catch (_) { return []; }
}

function _fmtDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: '2-digit' }); }
  catch (_) { return iso.slice(0, 10); }
}

function _esc(s) {
  if (typeof window !== 'undefined' && window.SwarmChat && typeof window.SwarmChat.esc === 'function') {
    return window.SwarmChat.esc(s);
  }
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _highlight(escaped, terms) {
  let s = escaped;
  terms.forEach(t => {
    const re = new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    s = s.replace(re, '<mark style="background:color-mix(in srgb, var(--accent) 20%, transparent);color:var(--text);border-radius:2px;padding:0 1px;">$1</mark>');
  });
  return s;
}

// ── Open / Reclassify modal (Session — library edit support) ──────────────────
async function libOpenSource(sourceId) {
  try {
    const r = await fetch(`/api/library/sources/${sourceId}`);
    const d = await r.json();
    if (!d.ok) { alert('Open failed: ' + (d.error || 'unknown')); return; }
    _libShowSourceModal(d.source);
  } catch (e) {
    alert('Open failed: ' + String(e));
  }
}

function libReclassifyPrompt(sourceId, ev) {
  if (ev && ev.stopPropagation) ev.stopPropagation();
  libOpenSource(sourceId);
}

function _libShowSourceModal(src) {
  let modal = document.getElementById('lib-source-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'lib-source-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:99990;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.55);backdrop-filter:blur(4px);';
    document.body.appendChild(modal);
  }
  const tags = _parseTags(src.domain_tags);
  const catOpts = (_libCategories || []).map(c =>
    `<option value="${_esc(c.id)}" ${c.id === src.category ? 'selected' : ''}>${_esc(c.label)}</option>`
  ).join('') || `<option value="general">general</option>`;
  const activeCat = (_libCategories || []).find(c => c.id === src.category);
  const subOpts = '<option value="">— None —</option>' +
    ((activeCat && activeCat.subcategories) || []).map(s =>
      `<option value="${_esc(s.id)}" ${s.id === src.subcategory ? 'selected' : ''}>${_esc(s.label)}</option>`
    ).join('');

  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 22px;max-width:820px;width:94%;max-height:88vh;display:flex;flex-direction:column;gap:10px;box-shadow:0 14px 44px rgba(0,0,0,0.45);">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div style="font-size:10px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;">Library Document #${src.source_id}</div>
        <button onclick="_libCloseSourceModal()" title="Close" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--text-dim);cursor:pointer;width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
      </div>

      <input id="lib-modal-title" class="lib-form-input" value="${_esc(src.title || '')}" placeholder="Title"
        style="font-size:14px;font-weight:600;">

      <div style="display:grid;grid-template-columns:1fr 1fr 2fr;gap:8px;">
        <div>
          <div class="lib-form-label">Category</div>
          <select id="lib-modal-cat" class="lib-form-input" onchange="_libModalCatChange()">${catOpts}</select>
        </div>
        <div>
          <div class="lib-form-label">Subcategory</div>
          <select id="lib-modal-sub" class="lib-form-input">${subOpts}</select>
        </div>
        <div>
          <div class="lib-form-label">Tags (comma-separated)</div>
          <input id="lib-modal-tags" class="lib-form-input" value="${_esc(tags.join(', '))}" placeholder="sap_hcm, abap, payroll">
        </div>
      </div>

      <div style="font-size:10px;color:var(--text-dim);">
        ${src.source_type} · ${src.chunk_count || 0} chunks · added by ${_esc(src.added_by || '')} · ${_fmtDate(src.created_at)}
        ${src.source_ref ? ` · <span style="opacity:.7;">${_esc(src.source_ref)}</span>` : ''}
      </div>

      <div style="flex:1;min-height:200px;max-height:50vh;overflow-y:auto;border:1px solid var(--border);border-radius:8px;padding:12px 14px;background:color-mix(in srgb, var(--window-header) 50%, var(--card));font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:var(--text-dim);">
${_esc(src.raw_text || '(No content stored)')}
      </div>

      <div style="display:flex;gap:8px;justify-content:space-between;">
        <button onclick="_libModalDelete(${src.source_id})" class="lib-form-input" style="flex:0 0 auto;color:var(--danger);border-color:color-mix(in srgb,var(--danger) 45%, var(--border));background:transparent;cursor:pointer;">Delete</button>
        <div style="display:flex;gap:8px;">
          <button onclick="_libCloseSourceModal()" class="lib-form-input" style="flex:0 0 auto;background:transparent;cursor:pointer;">Cancel</button>
          <button onclick="_libModalSave(${src.source_id})" class="lib-form-input" style="flex:0 0 auto;background:var(--accent);color:#000;border-color:var(--accent);font-weight:700;cursor:pointer;">Save</button>
        </div>
      </div>
    </div>`;
  modal.style.display = 'flex';
}

function _libCloseSourceModal() {
  const m = document.getElementById('lib-source-modal');
  if (m) m.style.display = 'none';
}

function _libModalCatChange() {
  const catSel = document.getElementById('lib-modal-cat');
  const subSel = document.getElementById('lib-modal-sub');
  if (!catSel || !subSel) return;
  const cat = (_libCategories || []).find(c => c.id === catSel.value);
  subSel.innerHTML = '<option value="">— None —</option>' +
    ((cat && cat.subcategories) || []).map(s => `<option value="${_esc(s.id)}">${_esc(s.label)}</option>`).join('');
}

async function _libModalSave(sourceId) {
  const title = (document.getElementById('lib-modal-title')?.value || '').trim();
  const category = document.getElementById('lib-modal-cat')?.value || 'general';
  const subcategory = document.getElementById('lib-modal-sub')?.value || '';
  const tagsRaw = document.getElementById('lib-modal-tags')?.value || '';
  const tags = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);
  try {
    const r = await fetch(`/api/library/sources/${sourceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, category, subcategory, tags }),
    });
    const d = await r.json();
    if (!d.ok) { alert('Save failed: ' + (d.error || 'unknown')); return; }
    _libCloseSourceModal();
    _loadSources();
    _loadCategories();
  } catch (e) {
    alert('Save failed: ' + String(e));
  }
}

async function _libModalDelete(sourceId) {
  if (!confirm('Delete this document and all its chunks? This cannot be undone.')) return;
  try {
    const r = await fetch(`/api/library/sources/${sourceId}`, { method: 'DELETE' });
    const d = await r.json();
    if (!d.ok) { alert('Delete failed: ' + (d.error || 'auth required — sign in first')); return; }
    _libCloseSourceModal();
    _loadSources();
    _loadCategories();
  } catch (e) {
    alert('Delete failed: ' + String(e));
  }
}

// ── Research Topics (idle-research interest manager) ──────────────────────────
let _libTopicsFilter = 'all';
let _libTopicsEscHandler = null;

function _libCloseTopicsModal() {
  const m = document.getElementById('lib-topics-modal');
  if (m) m.style.display = 'none';
  if (_libTopicsEscHandler) {
    document.removeEventListener('keydown', _libTopicsEscHandler);
    _libTopicsEscHandler = null;
  }
}

async function libOpenTopicsManager() {
  let modal = document.getElementById('lib-topics-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'lib-topics-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:99991;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.55);backdrop-filter:blur(4px);';
    // Click-outside to close
    modal.addEventListener('mousedown', (ev) => {
      if (ev.target === modal) _libCloseTopicsModal();
    });
    document.body.appendChild(modal);
  }
  modal.innerHTML = `
    <div id="lib-topics-panel" style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px 12px;width:min(720px, 94vw);height:min(70vh, 640px);min-width:440px;min-height:360px;max-width:96vw;max-height:92vh;display:flex;flex-direction:column;gap:10px;box-shadow:0 14px 44px rgba(0,0,0,0.45);resize:both;overflow:auto;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex:0 0 auto;">
        <div style="min-width:0;">
          <div style="font-size:13px;font-weight:700;color:var(--text);">Research Topics</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:2px;line-height:1.35;">Scholar &amp; Seeker run idle research on active topics overnight. Paused topics stay in the list but are skipped.</div>
        </div>
        <button onclick="_libCloseTopicsModal()" title="Close (Esc)" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--text-dim);cursor:pointer;width:24px;height:24px;flex:0 0 auto;line-height:1;display:inline-flex;align-items:center;justify-content:center;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
      </div>

      <form onsubmit="event.preventDefault(); libTopicsAdd();" style="display:flex;gap:6px;align-items:center;flex:0 0 auto;">
        <input id="lib-topics-new" class="lib-form-input" placeholder="Add a topic (e.g. SAP Payroll schemas and PCRs)" style="flex:1 1 auto;width:auto;">
        <select id="lib-topics-new-cat" class="lib-form-input" title="Category for the new topic" style="flex:0 0 132px;width:132px;">
          <option value="sap_corner" selected>sap_corner</option>
          <option value="programming">programming</option>
          <option value="fridays">fridays</option>
          <option value="general">general</option>
        </select>
        <button type="submit" title="Add topic" style="flex:0 0 auto;background:var(--window-header);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 12px;font-size:11px;font-weight:600;cursor:pointer;">+ Add</button>
      </form>

      <div style="display:flex;gap:6px;align-items:center;flex:0 0 auto;font-size:11px;color:var(--text-dim);">
        <span>Filter:</span>
        <select id="lib-topics-filter" onchange="libTopicsApplyFilter(this.value)" class="lib-form-input" style="flex:0 0 auto;width:auto;padding:4px 8px;font-size:11px;">
          <option value="all">All</option>
          <option value="active">Active only</option>
          <option value="paused">Paused only</option>
          <option value="sap_corner">Category: sap_corner</option>
          <option value="programming">Category: programming</option>
          <option value="fridays">Category: fridays</option>
          <option value="general">Category: general</option>
          <option value="tech">Category: tech</option>
          <option value="personal">Category: personal</option>
        </select>
        <span id="lib-topics-count" style="margin-left:auto;"></span>
      </div>

      <div id="lib-topics-list" style="flex:1 1 auto;overflow-y:auto;border:1px solid var(--border);border-radius:8px;padding:6px;display:flex;flex-direction:column;gap:4px;min-height:0;">
        <div style="padding:14px;text-align:center;font-size:11px;color:var(--text-dim);">Loading…</div>
      </div>
    </div>`;
  modal.style.display = 'flex';

  // Restore filter selection and wire Esc-to-close
  const filterSel = document.getElementById('lib-topics-filter');
  if (filterSel) filterSel.value = _libTopicsFilter;
  if (_libTopicsEscHandler) document.removeEventListener('keydown', _libTopicsEscHandler);
  _libTopicsEscHandler = (ev) => {
    if (ev.key === 'Escape') { ev.preventDefault(); _libCloseTopicsModal(); }
  };
  document.addEventListener('keydown', _libTopicsEscHandler);

  await libTopicsReload();
}

function libTopicsApplyFilter(val) {
  _libTopicsFilter = String(val || 'all');
  libTopicsReload();
}

async function libTopicsReload() {
  const list = document.getElementById('lib-topics-list');
  const countEl = document.getElementById('lib-topics-count');
  if (!list) return;
  try {
    const r = await fetch('/api/library/topics');
    const d = await r.json();
    if (!d.ok) { list.innerHTML = `<div style="padding:14px;color:var(--danger);font-size:11px;">${_esc(d.error || 'Failed to load')}</div>`; return; }
    const all = d.topics || [];
    const f = _libTopicsFilter;
    const topics = all.filter(t => {
      if (f === 'all') return true;
      if (f === 'active') return !!t.active;
      if (f === 'paused') return !t.active;
      return String(t.category || '').toLowerCase() === f;
    });
    if (countEl) countEl.textContent = `${topics.length} of ${all.length}`;
    if (!topics.length) {
      list.innerHTML = `<div style="padding:14px;text-align:center;font-size:11px;color:var(--text-dim);">No topics match this filter.</div>`;
      return;
    }
    list.innerHTML = topics.map(t => {
      const paused = !t.active;
      return `
        <div style="display:flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid var(--border);border-radius:6px;background:${paused ? 'color-mix(in srgb, var(--window-header) 60%, transparent)' : 'var(--card)'};opacity:${paused ? '0.6' : '1'};">
          <div style="flex:1;min-width:0;">
            <div style="font-size:12px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(t.topic)}</div>
            <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">
              ${_esc(t.category || 'general')} · score ${Number(t.score || 0).toFixed(1)} · ${_esc(t.source || 'user')}${t.source_agent ? '/' + _esc(t.source_agent) : ''}
            </div>
          </div>
          <button onclick="libTopicsRunNow(${t.id})" title="Run now" style="background:none;border:1px solid var(--border);border-radius:5px;padding:4px 8px;font-size:10px;color:var(--accent);cursor:pointer;" ${paused ? 'disabled' : ''}>▶</button>
          <button onclick="libTopicsToggle(${t.id}, ${paused ? 1 : 0})" title="${paused ? 'Resume' : 'Pause'}" style="background:none;border:1px solid var(--border);border-radius:5px;padding:4px 8px;font-size:10px;color:var(--text-dim);cursor:pointer;display:inline-flex;align-items:center;gap:4px;">${paused ? '<svg viewBox="0 0 16 16" width="9" height="9" fill="currentColor" aria-hidden="true"><path d="M4 3l9 5-9 5z"/></svg> Resume' : '<svg viewBox="0 0 16 16" width="9" height="9" fill="currentColor" aria-hidden="true"><rect x="4" y="3" width="3" height="10"/><rect x="9" y="3" width="3" height="10"/></svg> Pause'}</button>
          <button onclick="libTopicsDelete(${t.id})" title="Delete" style="background:none;border:1px solid var(--border);border-radius:5px;padding:4px 8px;font-size:10px;color:var(--danger);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
        </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = `<div style="padding:14px;color:var(--danger);font-size:11px;">${_esc(String(e))}</div>`;
  }
}

async function libTopicsAdd() {
  const topic = (document.getElementById('lib-topics-new')?.value || '').trim();
  const category = document.getElementById('lib-topics-new-cat')?.value || 'sap_corner';
  if (!topic) return;
  try {
    const r = await fetch('/api/library/topics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, category, score: 8.0 }),
    });
    const d = await r.json();
    if (!d.ok) { alert('Add failed: ' + (d.error || 'unknown')); return; }
    const inp = document.getElementById('lib-topics-new');
    if (inp) inp.value = '';
    libTopicsReload();
  } catch (e) {
    alert('Add failed: ' + String(e));
  }
}

async function libTopicsToggle(id, newActive) {
  try {
    await fetch(`/api/library/topics/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: Boolean(newActive) }),
    });
    libTopicsReload();
  } catch (_) {}
}

async function libTopicsDelete(id) {
  if (!confirm('Delete this topic permanently?')) return;
  try {
    await fetch(`/api/library/topics/${id}`, { method: 'DELETE' });
    libTopicsReload();
  } catch (_) {}
}

async function libTopicsRunNow(id) {
  try {
    const r = await fetch(`/api/library/topics/run/${id}`, { method: 'POST' });
    const d = await r.json();
    if (!d.ok) { alert('Run failed: ' + (d.error || 'unknown')); return; }
    alert(`Queued research: "${d.topic}". Check swarm_knowledge in a few minutes.`);
  } catch (e) {
    alert('Run failed: ' + String(e));
  }
}

// ── STEP-KC-TOPICS-HIVE-NAVIGATION-20260430 ─────────────────────────────────
// Deep-link helpers so KC topics, sources, and documents all resolve to the
// same Hive Nodes spine via the `/api/hive/resolve` endpoint. Exposed on
// window so other views (knowledge.js, chat surfaces, top-bar dropdowns)
// can call them without coupling to library.js internals.
async function kcResolveHiveHref(kind, id) {
  try {
    const r = await fetch(`/api/hive/resolve?kind=${encodeURIComponent(kind)}&id=${encodeURIComponent(id)}`);
    const d = await r.json();
    if (d && d.ok && d.href) return d.href;
  } catch (_) {}
  return null;
}

async function kcOpenHive(kind, id) {
  const href = await kcResolveHiveHref(kind, id);
  if (href) {
    if (typeof window.openWindow === 'function') {
      window.openWindow('hive-nodes', 'Hive Nodes', 'view-hive-nodes', { url: href });
    } else {
      window.location.assign(href);
    }
    return true;
  }
  return false;
}

async function kcLoadHiveGraph(recent = 30) {
  try {
    const r = await fetch(`/api/hive/graph?recent=${encodeURIComponent(recent)}`);
    const d = await r.json();
    if (d && d.ok) return d;
  } catch (_) {}
  return { ok: false, nodes: [], edges: [], counts: { topics: 0, sources: 0, edges: 0 } };
}

if (typeof window !== 'undefined') {
  window.kcResolveHiveHref = kcResolveHiveHref;
  window.kcOpenHive = kcOpenHive;
  window.kcLoadHiveGraph = kcLoadHiveGraph;
}
