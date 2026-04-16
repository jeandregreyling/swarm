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
  const active   = 'background:var(--accent);color:#000;border-color:var(--accent);font-weight:600;';
  const inactive = 'background:transparent;color:var(--text-dim);border-color:var(--border);font-weight:600;';
  ['kb','workspace','brief','pinboard','history'].forEach(t => {
    const btn = document.getElementById('docs-tab-' + t);
    if (btn) btn.style.cssText = btn.style.cssText.replace(/background[^;]+;|color[^;]+;|border-color[^;]+;/g,'') + (tab===t ? active : inactive);
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
    <div style="display:flex;gap:14px;height:100%;min-height:460px;">
      <aside style="width:320px;max-width:42%;display:flex;flex-direction:column;gap:8px;border-right:1px solid var(--border);padding-right:12px;">
        <div style="font-size:12px;font-weight:700;">Knowledgebase Documents</div>
        <input id="kb-search" type="text" placeholder="Search title or tags..." style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text);outline:none;">
        <button onclick="createNewKbDoc()" style="padding:8px 10px;background:var(--accent);border:none;border-radius:6px;color:#000;font-size:12px;font-weight:700;cursor:pointer;text-align:left;">+ New Document</button>
        <div id="kb-doc-list" style="flex:1;overflow-y:auto;"></div>
      </aside>
      <section style="flex:1;min-width:0;display:flex;flex-direction:column;gap:10px;">
        <div style="display:grid;grid-template-columns:1fr 180px;gap:8px;">
          <input id="kb-doc-name" type="text" placeholder="Document title" style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text);outline:none;">
          <input id="kb-doc-tags" type="text" placeholder="tags (comma)" style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text);outline:none;">
        </div>
        <textarea id="kb-doc-content" placeholder="Write documentation content here..." style="flex:1;min-height:220px;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:10px;color:var(--text);outline:none;resize:vertical;font-family:ui-monospace, SFMono-Regular, Menlo, monospace;font-size:12px;line-height:1.5;"></textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button onclick="saveKbDoc()" style="padding:7px 12px;background:var(--accent);border:none;border-radius:6px;color:#000;font-size:12px;font-weight:700;cursor:pointer;">Save</button>
          <button onclick="deleteKbDoc()" style="padding:7px 12px;background:#f4433620;border:1px solid #f4433660;border-radius:6px;color:#f44336;font-size:12px;font-weight:700;cursor:pointer;">Delete</button>
          <button onclick="reloadKbDocs()" style="padding:7px 12px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px;cursor:pointer;">Refresh</button>
          <div id="kb-status" style="margin-left:auto;font-size:11px;color:var(--text-dim);display:flex;align-items:center;">No document selected</div>
        </div>
        <div style="border-top:1px solid var(--border);padding-top:10px;">
          <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Versions</div>
          <div id="kb-versions" style="max-height:170px;overflow-y:auto;"></div>
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
    <div style="max-width:680px;margin:0 auto;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:10px;flex-wrap:wrap;">
        <div>
          <div style="font-size:13px;font-weight:700;">&#128204; Pinboard</div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:2px;">Things to remember — fed into Ghost Brief's NEXT 24H section</div>
        </div>
        <button id="pin-show-resolved" onclick="_pinToggleResolved()" style="padding:5px 10px;border:1px solid var(--border);border-radius:4px;background:transparent;color:var(--text-dim);font-size:11px;cursor:pointer;">Show Resolved</button>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:14px;">
        <input id="pin-new-input" type="text" placeholder="Add a pinned item…"
          style="flex:1;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--text);outline:none;font-size:12px;font-family:inherit;"
          onkeydown="if(event.key==='Enter') _pinAdd()">
        <button onclick="_pinAdd()" style="padding:8px 16px;background:var(--accent);border:none;border-radius:6px;color:#000;font-size:12px;font-weight:700;cursor:pointer;">+ Pin</button>
      </div>
      <div id="pin-list" style="display:flex;flex-direction:column;gap:8px;">
        <div style="color:var(--text-dim);font-size:12px;text-align:center;padding:20px;">Loading…</div>
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
      list.innerHTML = `<div style="color:var(--text-dim);font-size:12px;text-align:center;padding:30px;">
        ${_pinShowResolved ? 'No items here at all yet.' : 'Nothing pinned. Add something above or use the &#128204; Pin button on tickets and proposals.'}
      </div>`;
      return;
    }
    list.innerHTML = items.map(item => {
      const src = item.source ? `<span style="font-size:10px;color:var(--text-dim);padding:1px 6px;border:1px solid var(--border);border-radius:8px;">${item.source}</span>` : '';
      const age = item.created_at ? item.created_at.slice(0, 16) : '';
      return `<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 12px;background:var(--card);border:1px solid var(--border);border-radius:6px;${item.resolved?'opacity:0.5;':''}">
        <input type="checkbox" ${item.resolved?'checked':''} onchange="_pinResolve(${item.id}, this.checked)"
          style="margin-top:2px;accent-color:var(--accent);cursor:pointer;flex-shrink:0;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:12px;line-height:1.5;${item.resolved?'text-decoration:line-through;color:var(--text-dim);':''}">${_escHtml(item.content)}</div>
          <div style="display:flex;gap:6px;margin-top:4px;align-items:center;">${src}<span style="font-size:10px;color:var(--text-dim);">${age}</span></div>
        </div>
        <button onclick="_pinDelete(${item.id})"
          style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:14px;flex-shrink:0;opacity:0.6;padding:0 4px;" title="Remove">&#x2715;</button>
      </div>`;
    }).join('');
  }).catch(e => {
    const list = document.getElementById('pin-list');
    if (list) list.innerHTML = `<div style="color:#f77;font-size:12px;">Failed: ${e.message}</div>`;
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
    host.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:12px;">No docs found.</div>';
    return;
  }

  host.innerHTML = rows.map(d => {
    const active = Number(window._kbSelectedId) === Number(d.id);
    const updated = (d.updated_at || '').slice(0,16) || 'unknown';
    const versions = Number(d.version_count || 0);
    return `<div onclick="loadKbDoc(${d.id})" style="padding:10px;border:1px solid ${active ? 'var(--accent)' : 'var(--border)'};border-radius:6px;background:${active ? 'var(--card-hover)' : 'var(--card)'};margin-bottom:8px;cursor:pointer;">
      <div style="font-size:12px;font-weight:700;">${_escHtml(d.doc_name || '(untitled)')}</div>
      <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">${_escHtml(d.tags || 'all')} · ${updated}</div>
      <div style="font-size:10px;color:var(--text-dim);">Versions: ${versions}</div>
    </div>`;
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
  if (versions) versions.innerHTML = '<div style="font-size:11px;color:var(--text-dim);">No versions yet.</div>';
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
        host.innerHTML = '<div style="font-size:11px;color:var(--text-dim);">No versions recorded yet.</div>';
        return;
      }
      host.innerHTML = rows.map(v => {
        const ts = (v.created_at || '').slice(0,16) || 'unknown';
        return `<div style="padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);margin-bottom:7px;">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
            <div style="font-size:11px;font-weight:700;">v${v.version_number} · ${_escHtml(v.action || 'update')}</div>
            <button onclick="restoreKbVersion(${docId}, ${v.id})" style="padding:4px 8px;background:var(--card-hover);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:10px;cursor:pointer;">Restore</button>
          </div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">${_escHtml(ts)} · ${Math.round((v.content_length || 0)/1024)}KB</div>
        </div>`;
      }).join('');
    })
    .catch(e => { host.innerHTML = `<div style="font-size:11px;color:#f77;">${_escHtml(e.message)}</div>`; });
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
        `<button onclick="openDocDetail('${fname}', '${label}')" style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">${label}</button>`
      ).join('');

      content.innerHTML = `
        <div style="display:flex;gap:14px;height:100%;min-height:420px;">
          <div style="flex:1;min-width:0;display:flex;flex-direction:column;">
            <div style="margin-bottom:10px;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:8px;">
              <div style="font-size:15px;font-weight:700;margin-bottom:4px;">Welcome home Doctor Specles, this is where the good reading lives.</div>
              <div style="font-size:12px;color:var(--text-dim);">Choose your weapons wisely. Search, filter, and open any doc with one click.</div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;">
              <input id="docs-search" type="text" placeholder="Search docs, ALM notes, tests..." style="flex:1;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text);outline:none;">
              <select id="docs-kind-filter" style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);">
                <option value="all">All</option>
                <option value="text">Text/Markdown</option>
                <option value="html">HTML</option>
              </select>
            </div>
            <div style="margin-bottom:10px;display:flex;flex-wrap:wrap;gap:8px;">${qButtons}</div>
            <div id="docs-catalogue" style="flex:1;overflow-y:auto;"></div>
          </div>
          <aside style="width:250px;max-width:42%;border-left:1px solid var(--border);padding-left:12px;display:flex;flex-direction:column;gap:10px;">
            <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;">Sections</div>
            <button onclick="docsQuickFilter('all')" style="padding:7px 10px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;cursor:pointer;text-align:left;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><rect x="3" y="1.5" width="8" height="11" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 5h3M5.5 7.5h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><rect x="5" y="3.5" width="8" height="11" rx="1" stroke="currentColor" stroke-width="1.3" fill="var(--card)"/><path d="M7.5 7h3M7.5 9.5h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg> All Documents</button>
            <button onclick="docsQuickFilter('testing')" style="padding:7px 10px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;cursor:pointer;text-align:left;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M5 2h6M6.5 2v3.5L4 12.5a1 1 0 001 1h6a1 1 0 001-1L9.5 5.5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Testing Docs</button>
            <button onclick="docsQuickFilter('root')" style="padding:7px 10px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;cursor:pointer;text-align:left;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M2 4h5l1.5 1.5H14v8H2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg> Core Docs</button>
            <button onclick="docsQuickFilter('html')" style="padding:7px 10px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;cursor:pointer;text-align:left;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><ellipse cx="8" cy="8" rx="3" ry="6" stroke="currentColor" stroke-width="1.1"/><path d="M2.5 6h11M2.5 10h11" stroke="currentColor" stroke-width="1.1"/></svg> HTML Manuals</button>
            <button onclick="docsSetTab('history')" style="padding:7px 10px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;cursor:pointer;text-align:left;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><rect x="3" y="2" width="10" height="12" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 5h5M5.5 7.5h5M5.5 10h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg> ALM History</button>
            <div id="docs-last-change" style="margin-top:auto;padding:10px;background:var(--card);border:1px solid var(--border);border-radius:6px;font-size:11px;color:var(--text-dim);">Select a document to inspect metadata.</div>
          </aside>
        </div>`;

      const search = document.getElementById('docs-search');
      const kind = document.getElementById('docs-kind-filter');
      if (search) search.addEventListener('input', () => renderDocsCatalogue(window._docsCatalogue || []));
      if (kind) kind.addEventListener('change', () => renderDocsCatalogue(window._docsCatalogue || []));
      window._docsSectionFilter = 'all';
      renderDocsCatalogue(window._docsCatalogue || []);
    })
    .catch(e => { content.innerHTML = `<span style="color:#f77;">Failed to load docs: ${e.message}</span>`; });
}

function docsQuickFilter(section) {
  window._docsSectionFilter = section || 'all';
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
    list.innerHTML = '<div style="padding:20px;color:var(--text-dim);font-size:12px;text-align:center;">No matching documents.</div>';
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
    return `<div style="margin-bottom:10px;padding:11px 12px;background:var(--card);border-radius:6px;border:1px solid var(--border);cursor:pointer;" onclick="openDocDetail(${JSON.stringify(fname)},${JSON.stringify(title)}); updateDocsLastChange(${JSON.stringify(title)},${JSON.stringify(mod)},${JSON.stringify(size)},${JSON.stringify(kindTag)})" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
        <strong style="font-size:12px;"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;margin-right:2px;"><path d="M4.5 1.5h4.59L12.5 5v9.5h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M9 1.5v4h3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> ${titleH}</strong>
        <span style="font-size:10px;color:var(--text-dim);">${kindH}</span>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">${descH}</div>
      <div style="font-size:10px;color:var(--text-dim);margin-top:5px;">Last changed: ${modH} · ${sizeH}</div>
    </div>`;
  }).join('');
}

function updateDocsLastChange(title, modified, size, kind) {
  const el = document.getElementById('docs-last-change');
  if (!el) return;
  el.innerHTML = `
    <div style="font-size:11px;font-weight:700;color:var(--text);margin-bottom:4px;">Selected</div>
    <div style="font-size:11px;color:var(--text);">${_escHtml(title || '(unknown)')}</div>
    <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">Type: ${_escHtml(kind || 'DOC')}</div>
    <div style="font-size:10px;color:var(--text-dim);">Last changed: ${_escHtml(modified || 'unknown')}</div>
    <div style="font-size:10px;color:var(--text-dim);">Size: ${_escHtml(size || '—')}</div>`;
}

function loadDocsALMHistory(content) {
  fetch('/api/work-proposals?limit=200')
    .then(r => r.json())
    .then(data => {
      const items = data.proposals || [];
      window._proposals = items;
      if (!items.length) {
        content.innerHTML = '<div style="color:var(--text-dim);font-size:12px;text-align:center;padding:30px;">No ALM history yet.</div>';
        return;
      }
      const statusMeta = {
        pending:  { color: '#ffa500', bg: '#ffa50022', border: '#ffa50044' },
        approved: { color: '#4caf50', bg: '#4caf5020', border: '#4caf5060' },
        executed: { color: '#2196f3', bg: '#2196f320', border: '#2196f360' },
        rejected: { color: '#f44336', bg: '#f4433620', border: '#f4433660' },
      };
      content.innerHTML = `
        <div style="padding:0 0 8px;font-size:11px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
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
          return `<div style="background:var(--card);border:1px solid var(--border);border-left:3px solid ${m.color};border-radius:6px;padding:12px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
              <div style="flex:1;cursor:pointer;" onclick="openProposalDetail(${JSON.stringify(pid)})">
                <div style="font-weight:700;font-size:13px;margin-bottom:4px;">${title}</div>
                <div style="font-size:10px;color:var(--text-dim);">${_escHtml(p.agent || 'agent')} · ${created}${updated && updated !== created ? ' → ' + updated : ''} · <span style="font-family:monospace;">${pidSafe}</span></div>
              </div>
              <span style="padding:2px 8px;border-radius:10px;background:${m.bg};color:${m.color};font-size:10px;font-weight:700;border:1px solid ${m.border};">${st}</span>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">
              <button onclick="openDocDetail('CHANGELOG.md','Change Log')" style="padding:5px 9px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">Change Log</button>
              <button onclick="openDocDetail('ALM_DRIVER.md','ALM Driver')" style="padding:5px 9px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">ALM Driver</button>
              <button onclick="openDocDetail('UAT_TEST_SCRIPTS.md','UAT Test Scripts')" style="padding:5px 9px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">UAT Tests</button>
            </div>
          </div>`;
        }).join('')}`;
    })
    .catch(e => { content.innerHTML = `<div style="color:#f77;padding:20px;font-size:12px;">Error loading ALM history: ${e.message}</div>`; });
}

