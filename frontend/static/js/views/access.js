// Access control + agents config views
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// ACCESS CONTROL
// ═══════════════════════════════════════════════════════════════════════════

let _accessWinRef = null;
let _skillListCache = null;

async function loadAccessData(win) {
  _accessWinRef = win;
  window._accessWin = win;
  try {
    const [sRes, pRes] = await Promise.all([
      fetch('/api/senders'),
      fetch('/api/auth/profiles')
    ]);
    const senders  = await sRes.json();
    const profiles = await pRes.json();

    _renderSenderList(win, 'access-trusted-list',      senders.trusted      || [], 'trusted');
    _renderSenderList(win, 'access-notification-list', senders.notification || [], 'notification');
    _renderDomainList(win, 'access-domain-list',       senders.domains      || []);

    const sel = win.el.querySelector('#skill-perm-user');
    if (sel) {
      const prev = sel.value;
      sel.innerHTML = '<option value="">— select a user / agent —</option>';
      (profiles.profiles || []).forEach(p => {
        const o = document.createElement('option');
        o.value = p.username;
        o.textContent = `${p.display_name} (${p.user_type})`;
        sel.appendChild(o);
      });
      if (prev) { sel.value = prev; loadSkillPerms(); }
    }
  } catch (e) {
    console.error('loadAccessData error:', e);
  }
}

function _renderSenderList(win, id, items, listType) {
  const el = win.el.querySelector('#' + id);
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<div style="color:var(--text-dim);padding:4px 0;">— none —</div>';
    return;
  }
  el.innerHTML = items.map(item => `
    <div style="display:flex;align-items:center;gap:6px;padding:5px 8px;margin-bottom:3px;
                background:var(--card);border-radius:4px;border:1px solid var(--border);">
      <span style="flex:1;font-family:monospace;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
            title="${_esc(item.email)}">${_esc(item.email)}</span>
      <span style="color:var(--text-dim);font-size:10px;flex-shrink:0;">${(item.added_at||'').slice(0,10)}</span>
      <button onclick="accessRemove(${JSON.stringify(item.email)},${JSON.stringify(listType)})"
              style="flex-shrink:0;padding:1px 6px;background:transparent;border:1px solid var(--border);
                     border-radius:3px;color:var(--text-dim);font-size:10px;cursor:pointer;"
              title="Remove">✕</button>
    </div>`).join('');
}

function _renderDomainList(win, id, items) {
  const el = win.el.querySelector('#' + id);
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<div style="color:var(--text-dim);padding:4px 0;">— none —</div>';
    return;
  }
  el.innerHTML = items.map(item => `
    <div style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;margin:3px 3px 0 0;
                background:var(--card);border-radius:4px;border:1px solid var(--border);font-size:11px;">
      <span style="font-family:monospace;">@${_esc(item.domain)}</span>
      <span style="color:var(--text-dim);font-size:10px;">${_esc(item.channel||'email')}</span>
      <button onclick="accessRemove(${JSON.stringify(item.domain)},'domain')"
              style="padding:0 4px;background:transparent;border:none;color:var(--text-dim);cursor:pointer;font-size:10px;">✕</button>
    </div>`).join('');
}

async function accessAdd() {
  const win = _accessWinRef;
  if (!win) return;
  const address  = (win.el.querySelector('#access-new-address')?.value || '').trim();
  const listType = win.el.querySelector('#access-new-list')?.value || 'trusted';
  const note     = (win.el.querySelector('#access-new-note')?.value || '').trim();
  if (!address) return;
  try {
    const res  = await fetch('/api/senders', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({list: listType, address, note, proposal_id: 'DASHBOARD-ACCESS'})
    });
    const data = await res.json();
    if (data.ok) {
      win.el.querySelector('#access-new-address').value = '';
      win.el.querySelector('#access-new-note').value    = '';
      showToast(`Added ${address} to ${listType}`, 'success');
      loadAccessData(win);
    } else {
      showToast(data.error || 'Failed to add', 'error');
    }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

async function accessRemove(address, listType) {
  if (!confirm(`Remove ${address} from ${listType}?`)) return;
  try {
    const res  = await fetch('/api/senders', {
      method: 'DELETE', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({list: listType, address, proposal_id: 'DASHBOARD-ACCESS'})
    });
    const data = await res.json();
    if (data.ok) {
      showToast(`Removed ${address}`, 'success');
      loadAccessData(_accessWinRef);
    } else {
      showToast(data.error || 'Failed', 'error');
    }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

async function loadSkillPerms() {
  const win = _accessWinRef;
  if (!win) return;
  const sel      = win.el.querySelector('#skill-perm-user');
  const grid     = win.el.querySelector('#skill-perm-grid');
  const status   = win.el.querySelector('#skill-perm-status');
  const username = (sel?.value || '').trim();
  if (!grid) return;
  if (!username) {
    grid.innerHTML = '<div style="color:var(--text-dim);font-size:12px;grid-column:1/-1;">Select a user above to manage their skill permissions.</div>';
    return;
  }
  grid.innerHTML = '<div style="color:var(--text-dim);font-size:12px;grid-column:1/-1;">Loading…</div>';

  try {
    if (!_skillListCache) {
      const r = await fetch('/api/skills');
      const d = await r.json();
      _skillListCache = (d.skills || d || []).map(s => ({
        name: (s.name || s).toLowerCase(), description: s.description || ''
      }));
    }
    const permRes  = await fetch(`/api/skills/permissions?username=${encodeURIComponent(username)}`);
    const permData = await permRes.json();
    const perms    = Array.isArray(permData.permissions) ? permData.permissions : [];
    const map      = {};
    perms.forEach(p => { map[p.skill_name.toLowerCase()] = !!p.allowed; });

    if (status) status.textContent = `${Object.keys(map).length} explicit rule(s)`;

    grid.innerHTML = _skillListCache.map(skill => {
      const explicit = Object.prototype.hasOwnProperty.call(map, skill.name);
      const allowed  = explicit ? map[skill.name] : true;
      const badge    = explicit ? (allowed ? 'explicit allow' : 'explicit deny') : 'default allow';
      const badgeCol = explicit ? (allowed ? 'var(--accent)' : '#f77') : 'var(--text-dim)';
      return `
        <label style="display:flex;align-items:center;justify-content:space-between;gap:8px;
                       padding:9px 12px;border:1px solid var(--border);border-radius:6px;
                       background:var(--card);cursor:pointer;"
               onmouseover="this.style.borderColor='var(--accent)'"
               onmouseout="this.style.borderColor='var(--border)'">
          <div style="min-width:0;">
            <div style="font-size:12px;font-weight:600;text-transform:capitalize;">${_esc(skill.name)}</div>
            <div style="font-size:10px;color:${badgeCol};margin-top:1px;">${badge}</div>
          </div>
          <input type="checkbox" ${allowed ? 'checked' : ''}
                 onchange="setSkillPerm(${JSON.stringify(username)},${JSON.stringify(skill.name)},this.checked)"
                 style="width:15px;height:15px;cursor:pointer;accent-color:var(--accent);flex-shrink:0;">
        </label>`;
    }).join('');
  } catch (e) {
    grid.innerHTML = `<div style="color:#f77;font-size:12px;grid-column:1/-1;">Failed: ${_esc(e.message)}</div>`;
  }
}

async function setSkillPerm(username, skillName, allowed) {
  try {
    const res  = await fetch('/api/skills/permissions', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({username, skill_name: skillName, allowed})
    });
    const data = await res.json();
    if (data.ok === false) throw new Error(data.error || 'update failed');
    showToast(`${username} / ${skillName} → ${allowed ? 'allowed' : 'denied'}`, 'success');
    loadSkillPerms();
  } catch (e) {
    showToast(`Failed: ${e.message}`, 'error');
    loadSkillPerms();
  }
}

function _esc(text) {
  return String(text || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ═══════════════════════════════════════════════════════════════════════════
// AGENT WORKFLOW TRACKER — Display agent action logs in chat
// ═══════════════════════════════════════════════════════════════════════════

window._workflowState = {
  task: 'Theme System Fix',
  filesRead: [],
  filesModified: [],
  status: 'Ready',
  logs: []
};

function showWorkflowPanel() {
  document.getElementById('agent-workflow-panel').style.display = 'block';
}

function hideWorkflowPanel() {
  document.getElementById('agent-workflow-panel').style.display = 'none';
}

function logWorkflowFile(filepath, action) {
  if (!window._workflowState) window._workflowState = { task: '', filesRead: [], filesModified: [], status: 'Ready', logs: [] };
  
  const panel = document.getElementById('agent-workflow-panel');
  if (!panel) return;
  
  if (action === 'read') {
    if (!window._workflowState.filesRead.includes(filepath)) {
      window._workflowState.filesRead.push(filepath);
    }
    const readDiv = document.getElementById('workflow-files-read');
    if (readDiv) {
      readDiv.innerHTML = window._workflowState.filesRead
        .map(f => `<div style="margin:2px 0;">📄 ${_esc(f)}</div>`)
        .join('');
    }
  } else if (action === 'modify' || action === 'modified') {
    if (!window._workflowState.filesModified.includes(filepath)) {
      window._workflowState.filesModified.push(filepath);
    }
    const modDiv = document.getElementById('workflow-files-modified');
    if (modDiv) {
      modDiv.innerHTML = window._workflowState.filesModified
        .map(f => `<div style="margin:2px 0;color:#ff9e4d;">✏️ ${_esc(f)}</div>`)
        .join('');
    }
  }
  
  showWorkflowPanel();
}

function setWorkflowTask(taskName) {
  if (!window._workflowState) window._workflowState = { task: '', filesRead: [], filesModified: [], status: 'Ready', logs: [] };
  window._workflowState.task = taskName;
  const taskDiv = document.getElementById('workflow-task');
  if (taskDiv) taskDiv.textContent = taskName || 'None';
  showWorkflowPanel();
}

function setWorkflowStatus(status) {
  if (!window._workflowState) window._workflowState = { task: '', filesRead: [], filesModified: [], status: 'Ready', logs: [] };
  window._workflowState.status = status;
  const statusDiv = document.getElementById('workflow-status');
  if (statusDiv) statusDiv.textContent = status || 'Ready';
  if (status === 'Completed' || status === 'Complete') statusDiv.style.color = '#4caf50';
  else if (status === 'Error' || status === 'Failed') statusDiv.style.color = '#ff6b6b';
  else statusDiv.style.color = 'var(--accent)';
}

function clearWorkflow() {
  window._workflowState = { task: '', filesRead: [], filesModified: [], status: 'Ready', logs: [] };
  document.getElementById('workflow-task').textContent = 'None';
  document.getElementById('workflow-files-read').textContent = 'None';
  document.getElementById('workflow-files-modified').textContent = 'None';
  document.getElementById('workflow-status').textContent = 'Ready';
  hideWorkflowPanel();
}

// =========================================================
// AGENTS TILE
// =========================================================
function loadAgentsConfigData(win) {
  window.__agentsWin = win;
  agentsRefresh();
}

function agentsRefresh() {
  const list   = document.getElementById('agents-list');
  const detail = document.getElementById('agents-detail');
  if (list)   list.innerHTML   = '<div style="padding:20px;color:var(--text-dim);font-size:11px;">Loading…</div>';
  if (detail) detail.innerHTML = '';
  Promise.all([
    fetch('/api/agents/config').then(r => r.json()),
    fetch('/api/swarm/globals').then(r => r.json())
  ]).then(([agentsData, globalsData]) => {
    window.__agentsData  = Array.isArray(agentsData)  ? agentsData  : (agentsData.agents  || []);
    window.__globalsData = Array.isArray(globalsData) ? globalsData : (globalsData.globals || []);
    agentsRenderList(window.__agentsData);
    agentsRenderGlobals(window.__globalsData);
    if (window.__agentsData.length > 0) agentsShowDetail(window.__agentsData[0]);
  }).catch(err => {
    if (list) list.innerHTML = `<div style="padding:20px;color:#ff6b6b;font-size:11px;">Error: ${_esc(err.message)}</div>`;
  });
}

function agentsRenderList(agents) {
  const el = document.getElementById('agents-list');
  if (!el) return;
  if (!agents.length) {
    el.innerHTML = '<div style="padding:20px;color:var(--text-dim);font-size:11px;">No agents found.</div>';
    return;
  }
  el.innerHTML = agents.map(a => {
    const isLocal    = a.tier === 'local';
    const tierBadge  = isLocal
      ? '<span style="background:#1a3a1a;color:#4caf50;border-radius:3px;padding:1px 5px;font-size:9px;font-weight:700;">local</span>'
      : '<span style="background:#3a2a10;color:#ff9e4d;border-radius:3px;padding:1px 5px;font-size:9px;font-weight:700;">api</span>';
    const statusDot  = a.enabled !== false
      ? '<span style="color:#4caf50;font-size:10px;line-height:1;">●</span>'
      : '<span style="color:#555;font-size:10px;line-height:1;">○</span>';
    return `<div class="agents-list-row" data-name="${_esc(a.name)}"
      onclick="agentsShowDetail(window.__agentsData.find(x=>x.name===${JSON.stringify(a.name)}))"
      style="padding:10px 14px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:3px;transition:background 0.12s;">
      <div style="display:flex;align-items:center;gap:6px;">
        ${statusDot}
        <span style="font-size:12px;font-weight:700;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(a.label || a.name)}</span>
        ${tierBadge}
      </div>
      <div style="font-size:10px;color:var(--text-dim);padding-left:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(a.model || '')}</div>
    </div>`;
  }).join('');
}

function agentsShowDetail(agent) {
  if (!agent) return;
  document.querySelectorAll('.agents-list-row').forEach(r => {
    r.style.background = r.dataset.name === agent.name ? 'rgba(255,255,255,0.06)' : '';
  });
  const el = document.getElementById('agents-detail');
  if (!el) return;
  const isLocal   = agent.tier === 'local';
  const keyStatus = agent.api_key_set
    ? '<span style="color:#4caf50;font-size:10px;">● set</span>'
    : (isLocal
        ? '<span style="color:var(--text-dim);font-size:10px;">— local</span>'
        : '<span style="color:#ff6b6b;font-size:10px;">● not set</span>');
  el.innerHTML = `
    <div style="padding:18px 20px;max-width:700px;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
        <div style="flex:1;">
          <div style="font-size:15px;font-weight:700;">${_esc(agent.label || agent.name)}</div>
          <div style="font-size:11px;color:var(--text-dim);">${_esc(agent.name)}</div>
        </div>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;color:var(--text-dim);">
          <input type="checkbox" id="agent-enabled" ${agent.enabled !== false ? 'checked' : ''}>
          Enabled
        </label>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Label</label>
          <input id="agent-label" type="text" value="${_esc(agent.label || '')}"
            style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Model</label>
          <input id="agent-model" type="text" value="${_esc(agent.model || '')}"
            style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Tier</label>
          <select id="agent-tier"
            style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            <option value="local" ${agent.tier==='local'?'selected':''}>Local (Ollama)</option>
            <option value="paid"  ${agent.tier==='paid' ?'selected':''}>Paid API</option>
            <option value="free"  ${agent.tier==='free' ?'selected':''}>Free API</option>
          </select>
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">API Key Var</label>
          <div style="display:flex;gap:6px;align-items:center;">
            <input id="agent-key-var" type="text" value="${_esc(agent.api_key_var || '')}" placeholder="e.g. GROQ_API_KEY"
              style="flex:1;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            ${keyStatus}
          </div>
        </div>
      </div>

      ${!isLocal ? `
      <div style="margin-bottom:14px;padding:12px 14px;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:6px;">
        <div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Set API Key Value</div>
        <div style="display:flex;gap:8px;">
          <input id="agent-key-value" type="password" placeholder="Paste new key (not stored in DB)…"
            style="flex:1;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
          <button onclick="agentsSaveKey(${JSON.stringify(agent.name)})"
            style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:6px 12px;cursor:pointer;font-size:11px;">
            Save Key
          </button>
        </div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:6px;">Written to .env.agents only — never stored in the database.</div>
      </div>` : ''}

      <div style="margin-bottom:14px;">
        <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Role / Description</label>
        <input id="agent-role" type="text" value="${_esc(agent.role || '')}" placeholder="Short description of this agent's role"
          style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
      </div>

      <div style="margin-bottom:18px;">
        <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">System Prompt</label>
        <textarea id="agent-prompt" rows="10"
          style="width:100%;padding:8px 10px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:11px;font-family:monospace;outline:none;resize:vertical;box-sizing:border-box;">${_esc(agent.system_prompt || '')}</textarea>
      </div>

      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <button onclick="agentsSave(${JSON.stringify(agent.name)})"
          style="background:var(--accent);border:none;color:#000;border-radius:5px;padding:7px 18px;cursor:pointer;font-size:12px;font-weight:700;">
          Save Changes
        </button>
        <button onclick="agentsShowDetail(window.__agentsData.find(x=>x.name===${JSON.stringify(agent.name)}))"
          style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:7px 14px;cursor:pointer;font-size:12px;">
          Reset
        </button>
        <div id="agent-save-status" style="font-size:11px;color:var(--text-dim);"></div>
      </div>
    </div>
  `;
}

function agentsSave(name) {
  const statusEl = document.getElementById('agent-save-status');
  if (statusEl) { statusEl.textContent = 'Saving…'; statusEl.style.color = 'var(--text-dim)'; }
  const payload = {
    label:         document.getElementById('agent-label')?.value    || '',
    model:         document.getElementById('agent-model')?.value    || '',
    tier:          document.getElementById('agent-tier')?.value     || 'local',
    api_key_var:   document.getElementById('agent-key-var')?.value  || '',
    role:          document.getElementById('agent-role')?.value     || '',
    system_prompt: document.getElementById('agent-prompt')?.value   || '',
    enabled:       document.getElementById('agent-enabled')?.checked !== false,
  };
  fetch(`/api/agents/config/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      if (statusEl) { statusEl.textContent = '✓ Saved'; statusEl.style.color = '#4caf50'; }
      setTimeout(() => { if (statusEl) { statusEl.textContent = ''; statusEl.style.color = ''; } }, 2000);
      const idx = (window.__agentsData || []).findIndex(a => a.name === name);
      if (idx >= 0) Object.assign(window.__agentsData[idx], payload);
      agentsRenderList(window.__agentsData);
      document.querySelectorAll('.agents-list-row').forEach(r => {
        r.style.background = r.dataset.name === name ? 'rgba(255,255,255,0.06)' : '';
      });
    } else {
      if (statusEl) { statusEl.textContent = data.error || 'Save failed'; statusEl.style.color = '#ff6b6b'; }
    }
  }).catch(err => {
    if (statusEl) { statusEl.textContent = err.message; statusEl.style.color = '#ff6b6b'; }
  });
}

function agentsSaveKey(name) {
  const keyInput = document.getElementById('agent-key-value');
  const keyVar   = document.getElementById('agent-key-var')?.value.trim() || '';
  const keyValue = keyInput?.value.trim() || '';
  if (!keyValue) { showToast('Paste a key value first', 'info'); return; }
  if (!keyVar)   { showToast('Set the API key variable name first', 'info'); return; }
  fetch(`/api/agents/key/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ key_var: keyVar, value: keyValue })
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      if (keyInput) keyInput.value = '';
      showToast('Key saved to .env.agents', 'success');
      const agent = (window.__agentsData || []).find(a => a.name === name);
      if (agent) agent.api_key_set = true;
    } else {
      showToast(data.error || 'Failed to save key', 'error');
    }
  }).catch(err => showToast(err.message, 'error'));
}

function agentsShowAdd() {
  const existing = document.getElementById('agents-add-modal');
  if (existing) { existing.remove(); }
  const modal = document.createElement('div');
  modal.id = 'agents-add-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);display:flex;align-items:center;justify-content:center;z-index:9999;';
  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:24px;width:480px;max-width:95vw;max-height:90vh;overflow-y:auto;">
      <div style="font-size:14px;font-weight:700;margin-bottom:18px;">+ Add New Agent</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Name (unique, lowercase)</label>
          <input id="new-agent-name" type="text" placeholder="e.g. twelve"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Label</label>
          <input id="new-agent-label" type="text" placeholder="e.g. Twelve"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Model</label>
          <input id="new-agent-model" type="text" placeholder="e.g. claude-haiku-4-5-20251001"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Tier</label>
          <select id="new-agent-tier"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            <option value="local">Local (Ollama)</option>
            <option value="paid">Paid API</option>
            <option value="free">Free API</option>
          </select>
        </div>
        <div style="grid-column:span 2;">
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">API Key Env Var</label>
          <input id="new-agent-key-var" type="text" placeholder="e.g. ANTHROPIC_API_KEY (blank for local)"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div style="grid-column:span 2;">
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Role / Description</label>
          <input id="new-agent-role" type="text" placeholder="e.g. Creative writer, fast responses"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div style="grid-column:span 2;">
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">System Prompt</label>
          <textarea id="new-agent-prompt" rows="5" placeholder="You are…"
            style="width:100%;padding:7px 10px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:11px;font-family:monospace;outline:none;resize:vertical;box-sizing:border-box;"></textarea>
        </div>
      </div>
      <div id="agents-add-err" style="font-size:11px;color:#ff6b6b;min-height:16px;margin-bottom:10px;"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button onclick="document.getElementById('agents-add-modal').remove()"
          style="background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:7px 16px;cursor:pointer;font-size:12px;">
          Cancel
        </button>
        <button onclick="agentsSubmitAdd()"
          style="background:var(--accent);border:none;color:#000;border-radius:5px;padding:7px 18px;cursor:pointer;font-size:12px;font-weight:700;">
          Add Agent
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
  setTimeout(() => document.getElementById('new-agent-name')?.focus(), 50);
}

function agentsSubmitAdd() {
  const errEl = document.getElementById('agents-add-err');
  const name  = (document.getElementById('new-agent-name')?.value || '').trim().toLowerCase();
  if (!name) { if (errEl) errEl.textContent = 'Name is required.'; return; }
  const payload = {
    name,
    label:         (document.getElementById('new-agent-label')?.value   || '').trim() || name,
    model:         (document.getElementById('new-agent-model')?.value   || '').trim(),
    tier:           document.getElementById('new-agent-tier')?.value    || 'local',
    api_key_var:   (document.getElementById('new-agent-key-var')?.value || '').trim(),
    role:          (document.getElementById('new-agent-role')?.value    || '').trim(),
    system_prompt:  document.getElementById('new-agent-prompt')?.value  || '',
    enabled: true,
  };
  if (errEl) { errEl.textContent = 'Adding…'; errEl.style.color = 'var(--text-dim)'; }
  fetch('/api/agents/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      document.getElementById('agents-add-modal')?.remove();
      agentsRefresh();
      showToast(`Agent "${payload.label}" added`, 'success');
    } else {
      if (errEl) { errEl.textContent = data.error || 'Failed to add agent.'; errEl.style.color = '#ff6b6b'; }
    }
  }).catch(err => { if (errEl) { errEl.textContent = err.message; errEl.style.color = '#ff6b6b'; } });
}

function agentsToggleGlobals() {
  const body    = document.getElementById('agents-globals-body');
  const chevron = document.getElementById('agents-globals-chevron');
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (chevron) chevron.textContent = open ? '▸' : '▾';
}

function agentsRenderGlobals(globals) {
  const el = document.getElementById('agents-globals-body');
  if (!el) return;
  if (!globals || !globals.length) {
    el.innerHTML = '<div style="font-size:11px;color:var(--text-dim);">No global parameters defined.</div>';
    return;
  }
  el.innerHTML = globals.map(g => `
    <div style="margin-bottom:12px;">
      <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:flex;justify-content:space-between;margin-bottom:4px;">
        <span>${_esc(g.key)}</span>
        <span style="font-style:italic;text-transform:none;font-weight:400;">${_esc(g.description || '')}</span>
      </label>
      <div style="display:flex;gap:8px;align-items:flex-start;">
        <textarea id="global-val-${_esc(g.key)}" rows="${g.key === 'global_rules' ? 4 : 1}"
          style="flex:1;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:11px;font-family:monospace;outline:none;resize:vertical;">${_esc(g.value || '')}</textarea>
        <button onclick="agentsSaveGlobal(${JSON.stringify(g.key)})"
          style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:5px 12px;cursor:pointer;font-size:11px;white-space:nowrap;">
          Save
        </button>
      </div>
    </div>
  `).join('');
}

function agentsSaveGlobal(key) {
  const el = document.getElementById(`global-val-${key}`);
  if (!el) return;
  const value = el.value;
  fetch('/api/swarm/globals', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ key, value })
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      // Update local cache
      const idx = (window.__globalsData || []).findIndex(g => g.key === key);
      if (idx >= 0) window.__globalsData[idx].value = value;
      showToast(`"${key}" saved`, 'success');
    } else {
      showToast(data.error || 'Save failed', 'error');
    }
  }).catch(err => showToast(err.message, 'error'));
}

