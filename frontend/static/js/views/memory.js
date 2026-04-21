// Memory view — browse, edit, attach, assign, delete
function renderMemoryAgentTabs() {
  const tabsEl = document.getElementById('memory-agent-tabs');
  if (!tabsEl) return;
  fetch('/api/agents/config')
    .then(r => r.ok ? r.json() : null)
    .catch(() => null)
    .then(agents => {
      if (!Array.isArray(agents)) return;
      let html = `<button class=\"mem-tab active\" data-agent=\"\" onclick=\"_memTab(this,'')\">All</button>`;
      agents.filter(a => a.enabled).forEach(a => {
        html += `<button class="mem-tab" data-agent="${_escHtml(a.name)}" onclick="_memTab(this, this.dataset.agent)">${a.number != null ? a.number + ' · ' : ''}${_escHtml(a.label || a.name)}</button>`;
      });
      tabsEl.innerHTML = html;
    });
}
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('memory-agent-tabs')) renderMemoryAgentTabs();
});
// Extracted from terminal_base.html

function _memoryState() {
  if (!window.__memoryState) {
    window.__memoryState = {
      selected: {},
      bulkEditOpen: false,
      bulkDeleteArmed: false,
    };
  }
  return window.__memoryState;
}

function _memoryEntryKey(id, table) {
  return `${table || 'memory'}:${id}`;
}

function _memoryGetSelectedEntries() {
  const state = _memoryState();
  const values = Object.values(state.selected || {});
  return values.filter(item => item && item.id && item.table && item.table !== 'local_file');
}

function _memoryEnsureBulkBar(activeWin) {
  if (!activeWin || !activeWin.el) return null;
  let bar = activeWin.el.querySelector('#memory-bulk-selection-bar');
  if (bar) return bar;

  const host = activeWin.el.querySelector('#memory-bulk-toolbar') || activeWin.el.querySelector('#memory-source-tabs');
  if (!host || !host.parentNode) return null;

  bar = document.createElement('div');
  bar.id = 'memory-bulk-selection-bar';
  bar.style.display = 'none';
  bar.style.alignItems = 'center';
  bar.style.gap = '8px';
  bar.style.flexWrap = 'wrap';
  bar.style.padding = '0 0 10px';

  bar.innerHTML = `
    <button id="memory-mass-delete-btn" onclick="memoryBulkDelete()" style="background:transparent;border:1px solid #f4433660;color:#f44336;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:11px;">Bulk Delete</button>
    <span id="memory-mass-delete-count" style="font-size:10px;color:var(--text-dim);white-space:nowrap;">0 selected</span>
  `;

  if (host.id === 'memory-bulk-toolbar') {
    host.parentNode.insertBefore(bar, host.nextSibling);
  } else {
    host.parentNode.appendChild(bar);
  }
  return bar;
}

function _memorySyncSelectionUi(win) {
  const activeWin = win || window.__memoryWin;
  if (!activeWin || !activeWin.el) return;
  const state = _memoryState();
  const selected = _memoryGetSelectedEntries();
  const countEl = activeWin.el.querySelector('#memory-selection-count');
  if (countEl) countEl.textContent = `${selected.length} selected`;

  const bulkEditBtn = activeWin.el.querySelector('#memory-bulk-edit-btn');
  const bulkDeleteBtn = activeWin.el.querySelector('#memory-bulk-delete-btn');
  const clearBtn = activeWin.el.querySelector('#memory-clear-selection-btn');
  const massBar = _memoryEnsureBulkBar(activeWin);
  const massDeleteBtn = activeWin.el.querySelector('#memory-mass-delete-btn');
  const massDeleteCount = activeWin.el.querySelector('#memory-mass-delete-count');

  [bulkEditBtn, bulkDeleteBtn, clearBtn].forEach((btn) => {
    if (!btn) return;
    const enabled = selected.length > 0;
    btn.disabled = !enabled;
    btn.style.opacity = enabled ? '1' : '0.55';
    btn.style.cursor = enabled ? 'pointer' : 'not-allowed';
  });

  if (bulkDeleteBtn) {
    const armed = !!state.bulkDeleteArmed && selected.length > 0;
    bulkDeleteBtn.textContent = armed ? `Confirm Delete (${selected.length})` : `Bulk Delete (${selected.length})`;
    bulkDeleteBtn.style.background = armed ? '#f4433620' : 'transparent';
    bulkDeleteBtn.style.borderColor = '#f4433660';
    bulkDeleteBtn.style.color = '#f44336';
  }

  if (massBar) {
    massBar.style.display = selected.length > 1 ? 'flex' : 'none';
  }
  if (massDeleteCount) {
    massDeleteCount.textContent = `${selected.length} selected`;
  }
  if (massDeleteBtn) {
    const armed = !!state.bulkDeleteArmed && selected.length > 0;
    massDeleteBtn.textContent = armed ? `Confirm Delete (${selected.length})` : `Mass Delete (${selected.length})`;
    massDeleteBtn.style.background = armed ? '#f4433620' : 'transparent';
    massDeleteBtn.style.borderColor = '#f4433660';
    massDeleteBtn.style.color = '#f44336';
    massDeleteBtn.disabled = selected.length <= 1;
    massDeleteBtn.style.opacity = selected.length > 1 ? '1' : '0.55';
    massDeleteBtn.style.cursor = selected.length > 1 ? 'pointer' : 'not-allowed';
  }

  activeWin.el.querySelectorAll('.memory-select-checkbox').forEach((box) => {
    const key = box.dataset.key || '';
    box.checked = !!(key && _memoryState().selected[key]);
  });
}

function _memoryToggleSelected(entry, checked) {
  if (!entry || !entry.id || !entry.table || entry.table === 'local_file') return;
  const state = _memoryState();
  const key = _memoryEntryKey(entry.id, entry.table);
  if (checked) {
    state.selected[key] = entry;
  } else {
    delete state.selected[key];
  }
  _memoryState().bulkDeleteArmed = false;
  _memorySyncSelectionUi();
}

function memoryToggleSelected(id, table) {
  const key = _memoryEntryKey(id, table);
  const checked = !!document.querySelector(`.memory-select-checkbox[data-key="${key}"]`)?.checked;
  const m = (window.__memoryCache || []).find(x => String(x.id) === String(id) && String(x.source_table || 'memory') === String(table));
  if (!m || String(table) === 'local_file') return;
  _memoryToggleSelected({
    id,
    table,
    agent: m._agent || m.agent || '',
    subject: m.subject || '',
  }, checked);
}

function memorySelectVisible() {
  const visible = Array.isArray(window.__memoryVisibleRows) ? window.__memoryVisibleRows : [];
  visible.forEach((m) => {
    const table = String(m.source_table || 'memory');
    if (table === 'local_file') return;
    _memoryToggleSelected({
      id: m.id,
      table,
      agent: m._agent || m.agent || '',
      subject: m.subject || '',
    }, true);
  });
  _memorySyncSelectionUi();
  showToast('Visible memory entries selected', 'success');
}

function memoryClearSelection() {
  _memoryState().selected = {};
  _memoryState().bulkDeleteArmed = false;
  _memorySyncSelectionUi();
  const area = document.getElementById('mem-det-action-area');
  if (area) area.innerHTML = '';
}

function memoryOpenBulkEdit() {
  const selected = _memoryGetSelectedEntries();
  if (!selected.length) {
    showToast('Select at least one memory entry first', 'error');
    return;
  }
  const area = document.getElementById('mem-det-action-area');
  const detail = document.getElementById('mem-detail');
  if (!area || !detail) return;

  detail.style.display = 'block';
  area.innerHTML = `
    <div style="border:1px solid var(--border);border-radius:6px;padding:10px;background:var(--card);display:flex;flex-direction:column;gap:8px;">
      <div style="font-size:11px;color:var(--text-dim);">Bulk edit ${selected.length} selected memory entr${selected.length === 1 ? 'y' : 'ies'}</div>
      <input id="mem-bulk-subject" placeholder="Replace subject (leave blank to keep unchanged)" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <textarea id="mem-bulk-append" rows="4" placeholder="Append text to all selected entries" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:8px;resize:vertical;"></textarea>
      <input id="mem-bulk-tags" placeholder="Replace tags (optional)" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <input id="mem-bulk-importance" type="number" min="1" max="10" placeholder="Importance 1-10 (optional)" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <div style="font-size:10px;color:var(--text-dim);">Only the fields you fill in will be applied in bulk.</div>
      <div style="display:flex;gap:6px;justify-content:flex-end;">
        <button class="chat-action-btn" onclick="document.getElementById('mem-det-action-area').innerHTML=''">Cancel</button>
        <button class="chat-action-btn" onclick="memoryBulkEdit()">Apply Bulk Edit</button>
      </div>
    </div>
  `;
}

function memoryBulkEdit() {
  const selected = _memoryGetSelectedEntries();
  if (!selected.length) {
    showToast('No selected memory entries', 'error');
    return;
  }

  const subject = document.getElementById('mem-bulk-subject')?.value ?? '';
  const append = document.getElementById('mem-bulk-append')?.value ?? '';
  const tags = document.getElementById('mem-bulk-tags')?.value ?? '';
  const importanceRaw = document.getElementById('mem-bulk-importance')?.value ?? '';

  const updates = {};
  if (subject.trim()) updates.subject = subject;
  if (append.trim()) updates.append = append;
  if (tags.trim()) updates.tags = tags;
  if (importanceRaw !== '') updates.importance = Number(importanceRaw);

  if (!Object.keys(updates).length) {
    showToast('Fill at least one bulk edit field', 'error');
    return;
  }

  fetch('/api/memory/bulk', {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ entries: selected, updates, ..._authPayload() })
  })
    .then(_memoryParseApiResponse)
    .then(data => {
      if (!data.ok) throw new Error(data.error || 'bulk edit failed');
      showToast(`Bulk updated ${Array.isArray(data.updated) ? data.updated.length : 0} memories`, 'success');
      memoryClearSelection();
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
    })
    .catch(e => showToast('Bulk edit failed: ' + e.message, 'error'));
}

function memoryBulkDelete() {
  const selected = _memoryGetSelectedEntries();
  const state = _memoryState();
  if (!selected.length) {
    state.bulkDeleteArmed = false;
    _memorySyncSelectionUi();
    showToast('No selected memory entries', 'error');
    return;
  }

  if (!state.bulkDeleteArmed) {
    state.bulkDeleteArmed = true;
    _memorySyncSelectionUi();
    showToast(`Click Confirm Delete to remove ${selected.length} selected ${selected.length === 1 ? 'memory' : 'memories'}`, 'error');
    return;
  }

  fetch('/api/memory/bulk', {
    method: 'DELETE',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ entries: selected, ..._authPayload() })
  })
    .then(_memoryParseApiResponse)
    .then(data => {
      if (!data.ok) throw new Error(data.error || 'bulk delete failed');
      showToast(`Deleted ${Array.isArray(data.deleted) ? data.deleted.length : 0} memories`, 'success');
      state.bulkDeleteArmed = false;
      memoryClearSelection();
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
    })
    .catch(e => {
      state.bulkDeleteArmed = false;
      _memorySyncSelectionUi();
      showToast('Bulk delete failed: ' + e.message, 'error');
    });
}

function _memoryParseApiResponse(response) {
  return response.text().then((text) => {
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        const snippet = text.replace(/\s+/g, ' ').trim().slice(0, 160);
        throw new Error(snippet || `Request failed with status ${response.status}`);
      }
    }

    if (!response.ok) {
      const message = data && data.error
        ? data.error
        : (text.replace(/\s+/g, ' ').trim().slice(0, 160) || `Request failed with status ${response.status}`);
      throw new Error(message);
    }

    return data || {};
  });
}

function loadMemoryData(win) {
  const list = win.el.querySelector('#memory-list');
  if (!list) return;
  window.__memoryWin = win;
  window.__memoryCache = [];
  window.__memoryVisibleRows = [];
  window.__memoryAgent = window.__memoryAgent || '';
  window.__memorySource = window.__memorySource || 'all';

  const _renderList = (flat, agentFilter) => {
    const sourceMode = window.__memorySource || 'all';
    let shown = agentFilter ? flat.filter(m => (m._agent || m.agent || '') === agentFilter) : flat;
    if (sourceMode === 'db') {
      shown = shown.filter(m => String(m.source_table || '') !== 'local_file');
    } else if (sourceMode === 'local') {
      shown = shown.filter(m => String(m.source_table || '') === 'local_file');
    }

    window.__memoryVisibleRows = shown.slice(0, 200);

    const countEl = win.el.querySelector('#memory-count');
    if (countEl) countEl.textContent = `${shown.length} of ${flat.length} entries`;

    if (!shown.length) {
      list.innerHTML = `<div style="padding:30px;color:var(--text-dim);font-size:12px;text-align:center;">No memories${agentFilter ? ' for ' + agentFilter : ''}.</div>`;
      _memorySyncSelectionUi(win);
      return;
    }

    list.innerHTML = shown.slice(0, 200).map(m => {
      const title = _escHtml(m.subject || (m.content || '').slice(0, 100) || '(no subject)');
      const agent = m._agent || m.agent || '?';
      const imp = m.importance ? `<span style="color:var(--accent);font-size:9px;padding:1px 5px;border:1px solid var(--border);border-radius:8px;margin-left:4px;">i${m.importance}</span>` : '';
      const tags = m.tags ? `<span style="color:var(--text-dim);font-size:9px;margin-left:4px;">${_escHtml(String(m.tags).slice(0,60))}</span>` : '';
      const ts = (m.created_at || '').slice(0, 16);
      const safeTable = String(m.source_table || 'memory').replace(/[^a-z_]/g, '');
      const key = _memoryEntryKey(m.id || 0, safeTable);
      const isLocalFile = safeTable === 'local_file';
      const checkbox = isLocalFile
        ? `<span style="width:18px;display:inline-flex;justify-content:center;color:var(--text-dim);" title="Local files are read-only">•</span>`
        : `<input type="checkbox" class="memory-select-checkbox" data-key="${key}" onclick="event.stopPropagation(); memoryToggleSelected(${m.id || 0}, '${safeTable}')" style="margin:0;">`;

      const actionButtons = isLocalFile
        ? ''
        : `<div style="display:flex;gap:6px;align-items:center;margin-left:8px;padding-top:1px;" onclick="event.stopPropagation()">
            <button class="chat-action-btn" style="padding:3px 8px;font-size:10px;" onclick="memoryQuickEdit(${m.id || 0}, '${safeTable}')">Edit</button>
            <button class="chat-action-btn" style="padding:3px 8px;font-size:10px;border-color:#f44336;color:#f44336;" onclick="memoryDelete(${m.id || 0}, '${safeTable}')">Delete</button>
          </div>`;
      return `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 14px;border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.1s;" onmouseenter="this.style.background='rgba(255,255,255,0.03)'" onmouseleave="this.style.background=''" onclick="_memExpand(${m.id || 0},'${safeTable}')">
        <div style="padding-top:2px;">${checkbox}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${title}</div>
          <div style="display:flex;align-items:center;gap:4px;margin-top:3px;">
            <span style="font-size:9px;padding:1px 6px;background:var(--card);border:1px solid var(--border);border-radius:8px;color:var(--text-dim);">${agent}</span>
            ${imp}${tags}
            <span style="font-size:9px;color:var(--text-dim);margin-left:auto;">${ts}</span>
          </div>
        </div>
        ${actionButtons}
      </div>`;
    }).join('');

    _memorySyncSelectionUi(win);
  };

  const doMemSearch = (q) => {
    const agentFilter = window.__memoryAgent || '';
    const sourceMode = window.__memorySource || 'all';
    const includeLocal = sourceMode === 'db' ? '0' : '1';
    const agentParam = agentFilter ? `&agent=${encodeURIComponent(agentFilter)}` : '';
    const url = `/api/memory?min=1&limit=400&include_local=${includeLocal}${agentParam}${q ? '&q=' + encodeURIComponent(q) : ''}`;
    list.innerHTML = '<div style="padding:20px;color:var(--text-dim);font-size:12px;text-align:center;">Loading...</div>';
    fetch(url)
      .then(r => r.json())
      .then(data => {
        let flat = [];
        if (data.results && typeof data.results === 'object') {
          Object.entries(data.results).forEach(([agent, entries]) => {
            (entries || []).forEach(e => flat.push({ ...e, _agent: agent }));
          });
        } else if (Array.isArray(data)) {
          flat = data;
        }
        flat.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
        window.__memoryCache = flat;
        _renderList(flat, agentFilter);
      })
      .catch(e => { list.innerHTML = `<div style="padding:20px;color:#f77;font-size:12px;">Failed: ${e.message}</div>`; });
  };

  const memSearch = win.el.querySelector('#memory-search');
  if (memSearch && !memSearch._bound) {
    memSearch._bound = true;
    let t;
    memSearch.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => doMemSearch(memSearch.value), 300); });
  }

  _memorySyncSelectionUi(win);
  doMemSearch(memSearch?.value || '');
}

function memoryQuickEdit(id, table) {
  _memExpand(id, table);
  setTimeout(() => memoryEdit(id, table), 0);
}

function _memTab(btn, agent) {
  const parent = btn.closest('#memory-agent-tabs');
  if (parent) parent.querySelectorAll('.mem-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  window.__memoryAgent = agent;
  if (window.__memoryWin) loadMemoryData(window.__memoryWin);
}

function _memSourceTab(btn, source) {
  const parent = btn.closest('#memory-source-tabs');
  if (parent) parent.querySelectorAll('.mem-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  window.__memorySource = source || 'all';
  if (window.__memoryWin) loadMemoryData(window.__memoryWin);
}

function _memExpand(id, table) {
  const win = window.__memoryWin;
  if (!win) return;
  const detail = win.el.querySelector('#mem-detail');
  const body = win.el.querySelector('#mem-det-body');
  if (!detail || !body) return;
  const m = (window.__memoryCache || []).find(x => String(x.id) === String(id) && String(x.source_table || 'memory') === String(table));
  if (!m) return;
  const agent = m._agent || m.agent || table;
  const isLocalFile = String(table) === 'local_file';
  const sourcePath = _escHtml(String(m.source || ''));
  body.innerHTML = `
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
      <span style="padding:2px 8px;background:var(--card);border-radius:10px;color:var(--accent);font-size:10px;border:1px solid var(--border);">${agent}</span>
      ${m.importance ? `<span style="padding:2px 8px;background:var(--card);border-radius:10px;color:var(--text-dim);font-size:10px;border:1px solid var(--border);">importance ${m.importance}</span>` : ''}
      ${m.tags ? `<span style="padding:2px 8px;background:var(--card);border-radius:10px;color:var(--text-dim);font-size:10px;border:1px solid var(--border);">${_escHtml(String(m.tags).slice(0,80))}</span>` : ''}
      ${isLocalFile ? `<span style="padding:2px 8px;background:var(--card);border-radius:10px;color:var(--text-dim);font-size:10px;border:1px solid var(--border);">local file</span>` : ''}
    </div>
    ${m.subject ? `<div style="font-size:12px;font-weight:600;margin-bottom:8px;">${_escHtml(m.subject)}</div>` : ''}
    <div style="font-size:12px;color:var(--text);line-height:1.6;white-space:pre-wrap;margin-bottom:10px;">${_escHtml(m.content || '')}</div>
    <div style="font-size:10px;color:var(--text-dim);">${(m.created_at || '').slice(0,16)} · source: ${sourcePath}</div>
    ${isLocalFile ?
      `<div style="margin-top:10px;font-size:11px;color:var(--text-dim);">This entry is read-only and sourced from a local sandpit file.</div>` :
      `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;">
        <button class="chat-action-btn" onclick="memoryEdit(${id},'${table}')"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:2px;"><path d="M11.5 2.5l2 2-8 8H3.5v-2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg> Edit</button>
        <button class="chat-action-btn" onclick="memoryAppend(${id},'${table}')"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:2px;"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Append</button>
        <button class="chat-action-btn" onclick="memoryAttach(${id},'${table}')"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:2px;"><path d="M7 13.5c-2-1-3.5-3-3.5-5V4.5l7-2.5v4c0 2.5-1.5 4.5-3.5 5.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Attach</button>
        <button class="chat-action-btn" onclick="memoryAssign(${id},'${table}','${_escHtml(agent)}')"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:2px;"><path d="M12 8H4M12 8l-3-3M12 8l-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Share</button>
        <button class="chat-action-btn" onclick="memoryDelete(${id},'${table}')" style="border-color:#f44336;color:#f44336;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:2px;"><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M3 4h10M4.5 4v8.5h7V4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Delete</button>
      </div>
      <div id="mem-det-action-area" style="margin-top:10px;"></div>`
    }
  `;
  detail.style.display = 'block';
}

function memoryEdit(id, table) {
  const m = (window.__memoryCache || []).find(x => String(x.id) === String(id) && String(x.source_table || 'memory') === String(table)) || {};
  const area = document.getElementById('mem-det-action-area');
  if (!area) return;
  area.innerHTML = `
    <div style="border:1px solid var(--border);border-radius:6px;padding:10px;background:var(--card);display:flex;flex-direction:column;gap:8px;">
      <div style="font-size:11px;color:var(--text-dim);">Edit memory entry</div>
      <input id="mem-edit-subject" placeholder="Subject" value="${_escHtml(String(m.subject || ''))}" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <textarea id="mem-edit-content" rows="7" placeholder="Content" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:8px;resize:vertical;">${_escapeHtml(String(m.content || ''))}</textarea>
      <div style="display:flex;gap:6px;justify-content:flex-end;">
        <button class="chat-action-btn" onclick="document.getElementById('mem-det-action-area').innerHTML=''">Cancel</button>
        <button class="chat-action-btn" onclick="memorySubmitEdit(${id}, '${table}')">Save</button>
      </div>
    </div>
  `;
}

function memorySubmitEdit(id, table) {
  const subject = document.getElementById('mem-edit-subject')?.value ?? '';
  const content = document.getElementById('mem-edit-content')?.value ?? '';
  if (!content.trim()) {
    showToast('Content is required', 'error');
    return;
  }
  fetch(`/api/memory/${id}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ table, subject, content, ..._authPayload() })
  })
    .then(_memoryParseApiResponse)
    .then(data => {
      if (!data.ok) throw new Error(data.error || 'edit failed');
      showToast('Memory updated', 'success');
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
      document.getElementById('memory-detail-modal')?.classList.remove('open');
    })
    .catch(e => showToast('Edit failed: ' + e.message, 'error'));
}

function memoryAppend(id, table) {
  const area = document.getElementById('mem-det-action-area');
  if (!area) return;
  area.innerHTML = `
    <div style="border:1px solid var(--border);border-radius:6px;padding:10px;background:var(--card);display:flex;flex-direction:column;gap:8px;">
      <div style="font-size:11px;color:var(--text-dim);">Append to memory entry</div>
      <textarea id="mem-append-content" rows="5" placeholder="Text to append" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:8px;resize:vertical;"></textarea>
      <div style="display:flex;gap:6px;justify-content:flex-end;">
        <button class="chat-action-btn" onclick="document.getElementById('mem-det-action-area').innerHTML=''">Cancel</button>
        <button class="chat-action-btn" onclick="memorySubmitAppend(${id}, '${table}')">Append</button>
      </div>
    </div>
  `;
}

function memorySubmitAppend(id, table) {
  const append = document.getElementById('mem-append-content')?.value ?? '';
  if (!append.trim()) {
    showToast('Append text is required', 'error');
    return;
  }
  fetch(`/api/memory/${id}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ table, append, ..._authPayload() })
  })
    .then(_memoryParseApiResponse)
    .then(data => {
      if (!data.ok) throw new Error(data.error || 'append failed');
      showToast('Memory appended', 'success');
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
      document.getElementById('memory-detail-modal')?.classList.remove('open');
    })
    .catch(e => showToast('Append failed: ' + e.message, 'error'));
}

function memoryAttach(id, table) {
  const area = document.getElementById('mem-det-action-area');
  if (!area) return;
  area.innerHTML = `
    <div style="border:1px solid var(--border);border-radius:6px;padding:10px;background:var(--card);display:flex;flex-direction:column;gap:8px;">
      <div style="font-size:11px;color:var(--text-dim);">Attach a reference to this memory</div>
      <input id="mem-attach-label" placeholder="Label (ticket/file/url)" value="ref" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <input id="mem-attach-value" placeholder="Value" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <div style="display:flex;gap:6px;justify-content:flex-end;">
        <button class="chat-action-btn" onclick="document.getElementById('mem-det-action-area').innerHTML=''">Cancel</button>
        <button class="chat-action-btn" onclick="memorySubmitAttach(${id}, '${table}')">Attach</button>
      </div>
    </div>
  `;
}

function memorySubmitAttach(id, table) {
  const label = document.getElementById('mem-attach-label')?.value ?? '';
  const value = document.getElementById('mem-attach-value')?.value ?? '';
  if (!label.trim() || !value.trim()) {
    showToast('Label and value are required', 'error');
    return;
  }
  fetch(`/api/memory/${id}/attach`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ table, label, value, ..._authPayload() })
  })
    .then(_memoryParseApiResponse)
    .then(data => {
      if (!data.ok) throw new Error(data.error || 'attach failed');
      showToast('Attachment added', 'success');
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
      document.getElementById('memory-detail-modal')?.classList.remove('open');
    })
    .catch(e => showToast('Attach failed: ' + e.message, 'error'));
}

function memoryAssign(id, table, defaultAgent) {
  const area = document.getElementById('mem-det-action-area');
  if (!area) return;
  area.innerHTML = `
    <div style="border:1px solid var(--border);border-radius:6px;padding:10px;background:var(--card);display:flex;flex-direction:column;gap:8px;">
      <div style="font-size:11px;color:var(--text-dim);">Share this memory with other agents</div>
      <input id="mem-share-targets" placeholder="gemma,nine,ten" value="${_escHtml(String(defaultAgent || 'gemma,nine,ten'))}" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <input id="mem-share-note" placeholder="Optional note" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
      <div style="display:flex;gap:6px;justify-content:flex-end;">
        <button class="chat-action-btn" onclick="document.getElementById('mem-det-action-area').innerHTML=''">Cancel</button>
        <button class="chat-action-btn" onclick="memorySubmitAssign(${id}, '${table}')">Share</button>
      </div>
    </div>
  `;
}

function memorySubmitAssign(id, table) {
  const targetsRaw = document.getElementById('mem-share-targets')?.value ?? '';
  const note = document.getElementById('mem-share-note')?.value ?? '';
  if (!targetsRaw.trim()) {
    showToast('Targets are required', 'error');
    return;
  }
  fetch(`/api/memory/${id}/assign`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ table, targets: targetsRaw, note, ..._authPayload() })
  })
    .then(_memoryParseApiResponse)
    .then(data => {
      if (!data.ok) throw new Error(data.error || 'assign failed');
      showToast('Memory shared: ' + (data.assigned || []).map(x => x.agent).join(', '), 'success');
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
      document.getElementById('memory-detail-modal')?.classList.remove('open');
    })
    .catch(e => showToast('Share failed: ' + e.message, 'error'));
}

function memoryDelete(id, table) {
  if (!confirm('Delete this memory entry?')) return;
  fetch(`/api/memory/${id}?table=${encodeURIComponent(table)}`, {
    method: 'DELETE',
    headers: {'Content-Type': 'application/json'}
  })
    .then(_memoryParseApiResponse)
    .then(data => {
      if (!data.deleted) throw new Error(data.error || 'delete failed');
      showToast('Memory deleted', 'success');
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
      document.getElementById('memory-detail-modal')?.classList.remove('open');
    })
    .catch(e => showToast('Delete failed: ' + e.message, 'error'));
}
