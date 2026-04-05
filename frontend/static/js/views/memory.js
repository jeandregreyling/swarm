// Memory view — browse, edit, attach, assign, delete
// Extracted from terminal_base.html

function loadMemoryData(win) {
  const list = win.el.querySelector('#memory-list');
  if (!list) return;
  window.__memoryWin = win;
  window.__memoryCache = [];
  window.__memoryAgent = window.__memoryAgent || '';
  window.__memorySource = window.__memorySource || 'all';

  const _renderList = (flat, agentFilter) => {
    const sourceMode = window.__memorySource || 'all';
    let shown = agentFilter ? flat.filter(m => (m._agent||m.agent||'') === agentFilter) : flat;
    if (sourceMode === 'db') {
      shown = shown.filter(m => String(m.source_table || '') !== 'local_file');
    } else if (sourceMode === 'local') {
      shown = shown.filter(m => String(m.source_table || '') === 'local_file');
    }
    const countEl = win.el.querySelector('#memory-count');
    if (countEl) countEl.textContent = `${shown.length} of ${flat.length} entries`;
    if (!shown.length) {
      list.innerHTML = `<div style="padding:30px;color:var(--text-dim);font-size:12px;text-align:center;">No memories${agentFilter ? ' for '+agentFilter : ''}.</div>`;
      return;
    }
    list.innerHTML = shown.slice(0, 200).map(m => {
      const title  = _escHtml(m.subject || (m.content||'').slice(0, 100) || '(no subject)');
      const agent  = m._agent || m.agent || '?';
      const imp    = m.importance ? `<span style="color:var(--accent);font-size:9px;padding:1px 5px;border:1px solid var(--border);border-radius:8px;margin-left:4px;">i${m.importance}</span>` : '';
      const tags   = m.tags ? `<span style="color:var(--text-dim);font-size:9px;margin-left:4px;">${_escHtml(String(m.tags).slice(0,60))}</span>` : '';
      const ts     = (m.created_at||'').slice(0,16);
      const safeTable = String(m.source_table || 'memory').replace(/[^a-z_]/g,'');
      return `<div style="padding:8px 14px;border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.1s;" onmouseenter="this.style.background='rgba(255,255,255,0.03)'" onmouseleave="this.style.background=''" onclick="_memExpand(${m.id||0},'${safeTable}')">
        <div style="font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${title}</div>
        <div style="display:flex;align-items:center;gap:4px;margin-top:3px;">
          <span style="font-size:9px;padding:1px 6px;background:var(--card);border:1px solid var(--border);border-radius:8px;color:var(--text-dim);">${agent}</span>
          ${imp}${tags}
          <span style="font-size:9px;color:var(--text-dim);margin-left:auto;">${ts}</span>
        </div>
      </div>`;
    }).join('');
  };

  const doMemSearch = (q) => {
    const agentFilter = window.__memoryAgent || '';
    const sourceMode = window.__memorySource || 'all';
    const includeLocal = sourceMode === 'db' ? '0' : '1';
    const agentParam  = agentFilter ? `&agent=${encodeURIComponent(agentFilter)}` : '';
    const url = `/api/memory?min=1&limit=400&include_local=${includeLocal}${agentParam}${q ? '&q=' + encodeURIComponent(q) : ''}`;
    list.innerHTML = '<div style="padding:20px;color:var(--text-dim);font-size:12px;text-align:center;">Loading...</div>';
    fetch(url)
      .then(r => r.json())
      .then(data => {
        let flat = [];
        if (data.results && typeof data.results === 'object') {
          Object.entries(data.results).forEach(([agent, entries]) => {
            (entries||[]).forEach(e => flat.push({ ...e, _agent: agent }));
          });
        } else if (Array.isArray(data)) { flat = data; }
        flat.sort((a,b) => new Date(b.created_at||0) - new Date(a.created_at||0));
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
  doMemSearch('');
}

function _memTab(btn, agent) {
  // Activate only within agent tab row
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
  const body   = win.el.querySelector('#mem-det-body');
  if (!detail || !body) return;
  const m = (window.__memoryCache||[]).find(x => String(x.id)===String(id) && String(x.source_table||'memory')===String(table));
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
    <div style="font-size:12px;color:var(--text);line-height:1.6;white-space:pre-wrap;margin-bottom:10px;">${_escHtml(m.content||'')}</div>
    <div style="font-size:10px;color:var(--text-dim);">${(m.created_at||'').slice(0,16)} · source: ${sourcePath}</div>
    ${isLocalFile ?
      `<div style="margin-top:10px;font-size:11px;color:var(--text-dim);">This entry is read-only and sourced from a local sandpit file.</div>` :
      `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;">
        <button class="chat-action-btn" onclick="memoryEdit(${id},'${table}')">✏️ Edit</button>
        <button class="chat-action-btn" onclick="memoryAppend(${id},'${table}')">➕ Append</button>
        <button class="chat-action-btn" onclick="memoryAttach(${id},'${table}')">📎 Attach</button>
        <button class="chat-action-btn" onclick="memoryAssign(${id},'${table}','${_escHtml(agent)}')">🔁 Share</button>
        <button class="chat-action-btn" onclick="memoryDelete(${id},'${table}')" style="border-color:#f44336;color:#f44336;">🗑 Delete</button>
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
      <input id="mem-edit-subject" placeholder="Subject" value="${_escapeHtml(String(m.subject || ''))}" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
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
    .then(r => r.json())
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
    .then(r => r.json())
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
    .then(r => r.json())
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
      <input id="mem-share-targets" placeholder="gemma,nine,ten" value="${_escapeHtml(String(defaultAgent || 'gemma,nine,ten'))}" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px;">
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
    .then(r => r.json())
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
    .then(r => r.json())
    .then(data => {
      if (!data.deleted) throw new Error(data.error || 'delete failed');
      showToast('Memory deleted', 'success');
      const memoryWin = winManager.windows.get('memory');
      if (memoryWin) loadMemoryData(memoryWin);
      document.getElementById('memory-detail-modal')?.classList.remove('open');
    })
    .catch(e => showToast('Delete failed: ' + e.message, 'error'));
}

