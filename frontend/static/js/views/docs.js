// Docs view — knowledge base, pinboard, brief, library
// Extracted from terminal_base.html

function loadDocsData(win) {
  const content = win.el.querySelector('#docs-content');
  const gov = win.el.querySelector('#docs-governance');
  if (!content) return;

  if (gov) {
    gov.textContent = 'ALM status: loading...';
    fetch('/api/alm/status')
      .then(r => r.json())
      .then(alm => {
        gov.innerHTML = `ALM: <strong>${alm.status === 'enforced' ? 'enforced' : 'warn'}</strong> · ` +
          `Pending: <strong>${alm.work_proposals?.pending || 0}</strong> · ` +
          `Executed: <strong>${alm.work_proposals?.executed || 0}</strong>`;
      })
      .catch(() => { gov.textContent = 'ALM status: unavailable'; });
  }

  window._docsTab = window._docsTab || 'kb';
  docsSetTab(window._docsTab, content);
}

function docsSetTab(tab, contentEl) {
  window._docsTab = tab;
  ['kb','workspace','brief','pinboard','history'].forEach(t => {
    const btn = document.getElementById('docs-tab-' + t);
    if (btn) btn.classList.toggle('docs-tab-btn-active', tab === t);
  });
  const content = contentEl || document.getElementById('docs-content');
  if (!content) return;
  if (tab === 'history')  return loadDocsALMHistory(content);
  if (tab === 'brief')    return loadDocsGhostBrief(content);
  if (tab === 'workspace') return loadDocsWorkspace(content);
  if (tab === 'pinboard') return loadDocsPinboard(content);
  return loadDocsLibrary(content);
}

function loadDocsWorkspace(content) {
  window._kbSelectedId = null;
  content.innerHTML = `
    <div class="docs-layout docs-workspace-layout">
      <aside class="docs-panel docs-sidebar docs-workspace-sidebar">
        <div class="docs-section-heading">Knowledgebase Documents</div>
        <input id="kb-search" class="knowledge-input docs-input" type="text" placeholder="Search title or tags...">
        <button onclick="createNewKbDoc()" class="knowledge-btn knowledge-btn-primary docs-block-btn">+ New Document</button>
        <div id="kb-doc-list" class="docs-scroll-list docs-doc-list"></div>
      </aside>
      <section class="docs-panel docs-workspace-editor">
        <div class="docs-form-grid">
          <input id="kb-doc-name" class="knowledge-input docs-input" type="text" placeholder="Document title">
          <input id="kb-doc-tags" class="knowledge-input docs-input" type="text" placeholder="tags (comma)">
        </div>
        <textarea id="kb-doc-content" class="docs-textarea" placeholder="Write documentation content here..."></textarea>
        <div class="docs-action-row">
          <button onclick="saveKbDoc()" class="knowledge-btn knowledge-btn-primary">Save</button>
          <button onclick="deleteKbDoc()" class="docs-danger-btn">Delete</button>
          <button onclick="reloadKbDocs()" class="knowledge-btn">Refresh</button>
          <div id="kb-status" class="docs-status">No document selected</div>
        </div>
        <div class="docs-subpanel">
          <div class="docs-section-label">Versions</div>
          <div id="kb-versions" class="docs-scroll-list docs-version-list"></div>
        </div>
      </section>
    </div>`;

  document.getElementById('kb-search')?.addEventListener('input', () => renderKbDocList(window._kbDocs || []));
  reloadKbDocs();
}

// ─────────────────────────────────────────────────────────────────────────────
// PINBOARD  (deferred items / Ghost's personal backlog)
// ─────────────────────────────────────────────────────────────────────────────

function loadDocsPinboard(contentEl) {
  contentEl.innerHTML = `
    <div class="docs-center-stage">
      <div class="docs-panel docs-pinboard-shell">
        <div class="docs-toolbar docs-toolbar-spaced">
        <div>
          <div class="docs-title-line">&#128204; Pinboard</div>
          <div class="docs-muted-copy">Things to remember, deferred work, and anything Ghost Brief should surface next.</div>
        </div>
        <button id="pin-show-resolved" onclick="_pinToggleResolved()" class="knowledge-btn">Show Resolved</button>
      </div>
        <div class="docs-toolbar">
          <input id="pin-new-input" class="knowledge-input docs-input" type="text" placeholder="Add a pinned item…"
          onkeydown="if(event.key==='Enter') _pinAdd()">
          <button onclick="_pinAdd()" class="knowledge-btn knowledge-btn-primary">+ Pin</button>
        </div>
        <div id="pin-list" class="docs-stack-list">
          <div class="docs-empty-state">Loading…</div>
        </div>
      </div>
    </div>`;
  _pinLoad();
}

let _pinShowResolved = false;

function _pinLoad() {
  const list = document.getElementById('pin-list');
  if (!list) return;
  // ?resolved=1 returns all items; default returns only unresolved
  const url = `/api/deferred${_pinShowResolved ? '?resolved=1' : ''}`;
  fetch(url).then(r => r.json()).then(data => {
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = `<div class="docs-empty-state">
        ${_pinShowResolved ? 'No items here at all yet.' : 'Nothing pinned. Add something above or use the &#128204; Pin button on tickets and proposals.'}
      </div>`;
      return;
    }
    list.innerHTML = items.map(item => {
      const src = item.source ? `<span class="docs-chip">${item.source}</span>` : '';
      const age = item.created_at ? item.created_at.slice(0, 16) : '';
      return `<div class="docs-pin-card${item.resolved ? ' is-resolved' : ''}">
        <input type="checkbox" ${item.resolved?'checked':''} onchange="_pinResolve(${item.id}, this.checked)"
          class="docs-checkbox">
        <div class="docs-pin-copy">
          <div class="docs-pin-text">${_escHtml(item.content)}</div>
          <div class="docs-meta-row">${src}<span>${age}</span></div>
        </div>
        <button onclick="_pinDelete(${item.id})"
          class="docs-quiet-icon" title="Remove">&#x2715;</button>
      </div>`;
    }).join('');
  }).catch(e => {
    const list = document.getElementById('pin-list');
    if (list) list.innerHTML = `<div class="docs-error-state">Failed: ${_escHtml(e.message)}</div>`;
  });
}

function _pinAdd() {
  const input = document.getElementById('pin-new-input');
  const content = (input?.value || '').trim();
  if (!content) return;
  fetch('/api/deferred', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, source: 'manual', pinned_by: 'ghost' })
  }).then(r => r.json()).then(data => {
    if (!data.ok) { showToast(data.error || 'failed', 'error'); return; }
    input.value = '';
    showToast('Pinned', 'success');
    _pinLoad();
  }).catch(e => showToast('Error: ' + e.message, 'error'));
}

function _pinResolve(id, resolved) {
  fetch(`/api/deferred/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolved: resolved ? 1 : 0 })
  }).then(() => _pinLoad()).catch(() => {});
}

function _pinDelete(id) {
  fetch(`/api/deferred/${id}`, { method: 'DELETE' })
    .then(() => { showToast('Removed', 'info'); _pinLoad(); })
    .catch(() => {});
}

function _pinToggleResolved() {
  _pinShowResolved = !_pinShowResolved;
  const btn = document.getElementById('pin-show-resolved');
  if (btn) btn.textContent = _pinShowResolved ? 'Hide Resolved' : 'Show Resolved';
  _pinLoad();
}

// Global helper — called from proposal detail, ticket detail, and chat
function pinItemToDeferred(sourceId, content, source) {
  fetch('/api/deferred', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: content || sourceId, source: source || 'manual', source_id: String(sourceId), pinned_by: 'ghost' })
  }).then(r => r.json()).then(data => {
    if (!data.ok) { showToast(data.error || 'failed', 'error'); return; }
    showToast('Pinned to Brief', 'success');
  }).catch(e => showToast('Pin failed: ' + e.message, 'error'));
}

function reloadKbDocs() {
  fetch('/api/kb')
    .then(r => r.json())
    .then(data => {
      window._kbDocs = Array.isArray(data) ? data : [];
      renderKbDocList(window._kbDocs);
      if (window._kbSelectedId) {
        loadKbDoc(window._kbSelectedId);
      }
    })
    .catch(e => showToast('Failed to load docs: ' + e.message, 'error'));
}

function renderKbDocList(docs) {
  const host = document.getElementById('kb-doc-list');
  if (!host) return;
  const q = (document.getElementById('kb-search')?.value || '').toLowerCase().trim();
  const rows = (docs || []).filter(d => {
    const hay = `${d.doc_name || ''} ${d.tags || ''}`.toLowerCase();
    return !q || hay.includes(q);
  });

  if (!rows.length) {
    host.innerHTML = '<div class="docs-empty-state docs-empty-compact">No docs found.</div>';
    return;
  }

  host.innerHTML = rows.map(d => {
    const active = Number(window._kbSelectedId) === Number(d.id);
    const updated = (d.updated_at || '').slice(0,16) || 'unknown';
    const versions = Number(d.version_count || 0);
    return `<button type="button" onclick="loadKbDoc(${d.id})" class="docs-doc-row${active ? ' is-active' : ''}">
      <div class="docs-doc-row-title">${_escHtml(d.doc_name || '(untitled)')}</div>
      <div class="docs-doc-row-meta">${_escHtml(d.tags || 'all')} · ${updated}</div>
      <div class="docs-doc-row-meta">Versions: ${versions}</div>
    </button>`;
  }).join('');
}

function createNewKbDoc() {
  window._kbSelectedId = null;
  const name = document.getElementById('kb-doc-name');
  const tags = document.getElementById('kb-doc-tags');
  const content = document.getElementById('kb-doc-content');
  const versions = document.getElementById('kb-versions');
  const status = document.getElementById('kb-status');
  if (name) name.value = '';
  if (tags) tags.value = 'all';
  if (content) content.value = '';
  if (versions) versions.innerHTML = '<div class="docs-empty-state docs-empty-compact">No versions yet.</div>';
  if (status) status.textContent = 'Creating a new document';
}

function loadKbDoc(docId) {
  window._kbSelectedId = Number(docId);
  fetch(`/api/kb/${docId}`)
    .then(r => r.json())
    .then(doc => {
      document.getElementById('kb-doc-name').value = doc.doc_name || '';
      document.getElementById('kb-doc-tags').value = doc.tags || 'all';
      document.getElementById('kb-doc-content').value = doc.content || '';
      document.getElementById('kb-status').textContent = `Editing #${doc.id} · updated ${(doc.updated_at || '').slice(0,16)}`;
      renderKbDocList(window._kbDocs || []);
      loadKbVersions(doc.id);
    })
    .catch(e => showToast('Load failed: ' + e.message, 'error'));
}

function saveKbDoc() {
  const doc_name = (document.getElementById('kb-doc-name')?.value || '').trim();
  const tags = (document.getElementById('kb-doc-tags')?.value || 'all').trim() || 'all';
  const content = document.getElementById('kb-doc-content')?.value || '';
  if (!doc_name) return showToast('Document title required', 'error');

  const selected = window._kbSelectedId;
  const url = selected ? `/api/kb/${selected}` : '/api/kb';
  const method = selected ? 'PUT' : 'POST';
  fetch(url, {
    method,
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ doc_name, tags, content })
  })
    .then(r => r.json().then(data => ({status: r.status, data})))
    .then(({status, data}) => {
      if (status >= 400 || data.ok === false) throw new Error(data.error || 'save failed');
      if (!selected && data.id) window._kbSelectedId = data.id;
      showToast(selected ? 'Document updated' : 'Document created', 'success');
      reloadKbDocs();
    })
    .catch(e => showToast('Save failed: ' + e.message, 'error'));
}

function deleteKbDoc() {
  const selected = window._kbSelectedId;
  if (!selected) return showToast('Select a document first', 'error');
  if (!confirm('Delete this document? You can still restore from Versions.')) return;

  fetch(`/api/kb/${selected}`, { method: 'DELETE' })
    .then(r => r.json().then(data => ({status: r.status, data})))
    .then(({status, data}) => {
      if (status >= 400 || data.ok === false) throw new Error(data.error || 'delete failed');
      showToast('Document deleted', 'info');
      createNewKbDoc();
      reloadKbDocs();
    })
    .catch(e => showToast('Delete failed: ' + e.message, 'error'));
}

function loadKbVersions(docId) {
  const host = document.getElementById('kb-versions');
  if (!host) return;
  fetch(`/api/kb/${docId}/versions`)
    .then(r => r.json().then(data => ({status: r.status, data})))
    .then(({status, data}) => {
      if (status >= 400 || data.ok === false) throw new Error(data.error || 'versions unavailable');
      const rows = data.versions || [];
      if (!rows.length) {
        host.innerHTML = '<div class="docs-empty-state docs-empty-compact">No versions recorded yet.</div>';
        return;
      }
      host.innerHTML = rows.map(v => {
        const ts = (v.created_at || '').slice(0,16) || 'unknown';
        return `<div class="docs-version-card">
          <div class="docs-version-header">
            <div class="docs-version-title">v${v.version_number} · ${_escHtml(v.action || 'update')}</div>
            <button onclick="restoreKbVersion(${docId}, ${v.id})" class="knowledge-btn docs-inline-btn">Restore</button>
          </div>
          <div class="docs-doc-row-meta">${_escHtml(ts)} · ${Math.round((v.content_length || 0)/1024)}KB</div>
        </div>`;
      }).join('');
    })
    .catch(e => { host.innerHTML = `<div class="docs-error-state">${_escHtml(e.message)}</div>`; });
}

function restoreKbVersion(docId, versionId) {
  fetch(`/api/kb/${docId}/restore`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ version_id: versionId })
  })
    .then(r => r.json().then(data => ({status: r.status, data})))
    .then(({status, data}) => {
      if (status >= 400 || data.ok === false) throw new Error(data.error || 'restore failed');
      showToast('Version restored', 'success');
      window._kbSelectedId = docId;
      reloadKbDocs();
    })
    .catch(e => showToast('Restore failed: ' + e.message, 'error'));
}

function loadDocsLibrary(content) {
  fetch('/api/docs')
    .then(r => r.json())
    .then(data => {
      const docs = Array.isArray(data) ? data : (data.docs || []);
      window._docsCatalogue = docs;

      const quick = [
        ['ALM_DRIVER.md', 'ALM Driver'],
        ['UAT_TEST_SCRIPTS.md', 'UAT Test Scripts'],
        ['testing/ALM_TEST_SPECIFICATION.md', 'ALM Test Specification'],
        ['testing/TIME_WIZARD_TESTS.md', 'Vortex Test Suite'],
        ['CHANGELOG.md', 'Change Log'],
        ['TASK_TRACKER_LIVE.md', 'Task Tracker Live']
      ];

      const qButtons = quick.map(([fname, label]) =>
        `<button onclick="openDocDetail('${fname}', '${label}')" class="knowledge-btn docs-inline-btn">${label}</button>`
      ).join('');

      content.innerHTML = `
        <div class="docs-layout docs-library-layout">
          <div class="docs-library-main">
            <div class="docs-panel docs-hero-card">
              <div class="docs-hero-title">Knowledge reads better when the signal is obvious.</div>
              <div class="docs-muted-copy">Search, filter, jump to the highest-value docs, and keep one metadata rail visible while you browse.</div>
            </div>
            <div class="docs-toolbar">
              <input id="docs-search" class="knowledge-input docs-input" type="text" placeholder="Search docs, ALM notes, tests...">
              <select id="docs-kind-filter" class="knowledge-select docs-select">
                <option value="all">All</option>
                <option value="text">Text/Markdown</option>
                <option value="html">HTML</option>
              </select>
            </div>
            <div class="docs-quick-actions">${qButtons}</div>
            <div id="docs-catalogue" class="docs-catalogue"></div>
          </div>
          <aside class="docs-panel docs-library-rail">
            <div class="docs-section-label">Sections</div>
            <button onclick="docsQuickFilter('all')" class="docs-filter-btn" data-docs-section="all"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><rect x="3" y="1.5" width="8" height="11" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 5h3M5.5 7.5h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><rect x="5" y="3.5" width="8" height="11" rx="1" stroke="currentColor" stroke-width="1.3" fill="var(--card)"/><path d="M7.5 7h3M7.5 9.5h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg> All Documents</button>
            <button onclick="docsQuickFilter('testing')" class="docs-filter-btn" data-docs-section="testing"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><path d="M5 2h6M6.5 2v3.5L4 12.5a1 1 0 001 1h6a1 1 0 001-1L9.5 5.5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Testing Docs</button>
            <button onclick="docsQuickFilter('root')" class="docs-filter-btn" data-docs-section="root"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><path d="M2 4h5l1.5 1.5H14v8H2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg> Core Docs</button>
            <button onclick="docsQuickFilter('html')" class="docs-filter-btn" data-docs-section="html"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><ellipse cx="8" cy="8" rx="3" ry="6" stroke="currentColor" stroke-width="1.1"/><path d="M2.5 6h11M2.5 10h11" stroke="currentColor" stroke-width="1.1"/></svg> HTML Manuals</button>
            <button onclick="docsSetTab('history')" class="docs-filter-btn"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><rect x="3" y="2" width="10" height="12" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 5h5M5.5 7.5h5M5.5 10h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg> ALM History</button>
            <div id="docs-last-change" class="docs-metadata-card">Select a document to inspect metadata.</div>
          </aside>
        </div>`;

      const search = document.getElementById('docs-search');
      const kind = document.getElementById('docs-kind-filter');
      if (search) search.addEventListener('input', () => renderDocsCatalogue(window._docsCatalogue || []));
      if (kind) kind.addEventListener('change', () => renderDocsCatalogue(window._docsCatalogue || []));
      window._docsSectionFilter = 'all';
      docsQuickFilter('all');
    })
    .catch(e => { content.innerHTML = `<div class="docs-error-state">Failed to load docs: ${_escHtml(e.message)}</div>`; });
}

function docsQuickFilter(section) {
  window._docsSectionFilter = section || 'all';
  document.querySelectorAll('[data-docs-section]').forEach(btn => {
    btn.classList.toggle('docs-filter-btn-active', btn.dataset.docsSection === window._docsSectionFilter);
  });
  renderDocsCatalogue(window._docsCatalogue || []);
}

function renderDocsCatalogue(docs) {
  const list = document.getElementById('docs-catalogue');
  if (!list) return;
  const q = (document.getElementById('docs-search')?.value || '').toLowerCase().trim();
  const kind = document.getElementById('docs-kind-filter')?.value || 'all';
  const section = window._docsSectionFilter || 'all';

  const filtered = (docs || []).filter(d => {
    const t = `${d.title || ''} ${d.filename || ''} ${d.description || ''}`.toLowerCase();
    const qOk = !q || t.includes(q);
    const kindOk = kind === 'all' || (d.kind || '').toLowerCase() === kind;
    const sec = (d.section || '').toLowerCase();
    const secOk = section === 'all' || sec === section;
    return qOk && kindOk && secOk;
  });

  if (!filtered.length) {
    list.innerHTML = '<div class="docs-empty-state">No matching documents.</div>';
    return;
  }

  list.innerHTML = filtered.map(d => {
    const title = d.title || d.filename || '(unknown)';
    const fname = d.filename || d.title || '';
    const desc = d.description || '';
    const size = d.size ? `${Math.round(d.size / 1024)}KB` : '—';
    const mod = d.modified_at || 'unknown';
    const kindTag = (d.kind || 'doc').toUpperCase();
    const titleH = _escHtml(title);
    const descH  = _escHtml(desc || (d.section ? `Section: ${d.section}` : ''));
    const modH   = _escHtml(mod);
    const sizeH  = _escHtml(size);
    const kindH  = _escHtml(kindTag);
    return `<button type="button" class="docs-catalogue-card" onclick="openDocDetail(${JSON.stringify(fname)},${JSON.stringify(title)}); updateDocsLastChange(${JSON.stringify(title)},${JSON.stringify(mod)},${JSON.stringify(size)},${JSON.stringify(kindTag)})">
      <div class="docs-catalogue-head">
        <strong class="docs-catalogue-title"><svg viewBox="0 0 16 16" width="12" height="12" fill="none"><path d="M4.5 1.5h4.59L12.5 5v9.5h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M9 1.5v4h3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> ${titleH}</strong>
        <span class="docs-chip">${kindH}</span>
      </div>
      <div class="docs-catalogue-desc">${descH}</div>
      <div class="docs-doc-row-meta">Last changed: ${modH} · ${sizeH}</div>
    </button>`;
  }).join('');
}

function updateDocsLastChange(title, modified, size, kind) {
  const el = document.getElementById('docs-last-change');
  if (!el) return;
  el.innerHTML = `
    <div class="docs-section-heading">Selected</div>
    <div class="docs-metadata-title">${_escHtml(title || '(unknown)')}</div>
    <div class="docs-doc-row-meta">Type: ${_escHtml(kind || 'DOC')}</div>
    <div class="docs-doc-row-meta">Last changed: ${_escHtml(modified || 'unknown')}</div>
    <div class="docs-doc-row-meta">Size: ${_escHtml(size || '—')}</div>`;
}

function loadDocsALMHistory(content) {
  fetch('/api/work-proposals?limit=200')
    .then(r => r.json())
    .then(data => {
      const items = data.proposals || [];
      window._proposals = items;
      if (!items.length) {
        content.innerHTML = '<div class="docs-empty-state">No ALM history yet.</div>';
        return;
      }
      const statusMeta = {
        pending:  { color: '#ffa500', bg: '#ffa50022', border: '#ffa50044' },
        approved: { color: '#4caf50', bg: '#4caf5020', border: '#4caf5060' },
        executed: { color: '#2196f3', bg: '#2196f320', border: '#2196f360' },
        rejected: { color: '#f44336', bg: '#f4433620', border: '#f4433660' },
      };
      content.innerHTML = `
        <div class="docs-history-wrap">
        <div class="docs-section-label">
          ${items.length} Proposal${items.length !== 1 ? 's' : ''} (ALM Documentation History)
        </div>
        ${items.map(p => {
          const st = (p.status || 'pending').toLowerCase();
          const m = statusMeta[st] || statusMeta.pending;
          const created = (p.created_at || '').slice(0,16);
          const updated = (p.updated_at || '').slice(0,16);
          const title = _escHtml(p.title || p.proposal_id || 'Untitled Proposal');
          const pid = p.proposal_id || '';
          const pidSafe = _escHtml(pid);
          return `<div class="docs-history-card" style="border-left-color:${m.color};">
            <div class="docs-history-head">
              <div class="docs-history-main" onclick="openProposalDetail(${JSON.stringify(pid)})">
                <div class="docs-history-title">${title}</div>
                <div class="docs-doc-row-meta">${_escHtml(p.agent || 'agent')} · ${created}${updated && updated !== created ? ' → ' + updated : ''} · <span class="docs-mono">${pidSafe}</span></div>
              </div>
              <span class="docs-chip" style="background:${m.bg};color:${m.color};border-color:${m.border};">${st}</span>
            </div>
            <div class="docs-quick-actions">
              <button onclick="openDocDetail('CHANGELOG.md','Change Log')" class="knowledge-btn docs-inline-btn">Change Log</button>
              <button onclick="openDocDetail('ALM_DRIVER.md','ALM Driver')" class="knowledge-btn docs-inline-btn">ALM Driver</button>
              <button onclick="openDocDetail('UAT_TEST_SCRIPTS.md','UAT Test Scripts')" class="knowledge-btn docs-inline-btn">UAT Tests</button>
            </div>
          </div>`;
        }).join('')}
        </div>`;
    })
    .catch(e => { content.innerHTML = `<div class="docs-error-state">Error loading ALM history: ${_escHtml(e.message)}</div>`; });
}

