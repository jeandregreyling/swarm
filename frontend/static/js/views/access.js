// ═══════════════════════════════════════════════════════════════════════════
// ROLES–SKILLS MAPPING (META MANAGEMENT)
// ═══════════════════════════════════════════════════════════════════════════

async function loadRolesSkillsGrid() {
  const panel = document.getElementById('roles-skills-admin-panel');
  if (!panel) return;
  panel.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">Loading roles & skills…</div>';
  try {
    // Fetch all skills
    if (!_skillListCache) {
      const r = await fetch('/api/skills');
      const d = await r.json();
      _skillListCache = (d.skills || d || []).map(s => ({
        name: (s.name || '').toLowerCase(),
        label: s.name || '',
        description: s.description || ''
      }));
    }
    // Fetch all roles (from agents and mapping)
    const agentsRes = await fetch('/api/agents/config');
    const agents = await agentsRes.json();
    let allRoles = [];
    (agents || []).forEach(a => {
      (Array.isArray(a.roles) ? a.roles : []).forEach(r => allRoles.push(r));
    });
    // Fetch mapping
    const mapRes = await fetch('/api/roles-skills');
    const mapData = await mapRes.json();
    let mapping = (mapData && mapData.mapping) || {};
    // Merge in any roles from mapping not in agents
    Object.keys(mapping).forEach(r => { if (!allRoles.includes(r)) allRoles.push(r); });
    allRoles = Array.from(new Set(allRoles)).sort();
    // Render grid
    panel.innerHTML = `<table style="border-collapse:collapse;width:100%;font-size:12px;">
      <thead><tr><th style="text-align:left;padding:6px 8px;">Role</th>${_skillListCache.map(s => `<th style='padding:6px 4px;text-align:center;'>${_esc(s.label)}</th>`).join('')}</tr></thead>
      <tbody>
        ${allRoles.map(role => `<tr>
          <td style='padding:6px 8px;font-weight:600;'>${_esc(role)}</td>
          ${_skillListCache.map(skill => {
            const checked = (mapping[role]||[]).includes(skill.name) ? 'checked' : '';
            return `<td style='text-align:center;'><input type='checkbox' data-role='${_esc(role)}' data-skill='${_esc(skill.name)}' ${checked}></td>`;
          }).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    <button id='roles-skills-save-btn' style='margin-top:12px;padding:7px 18px;background:var(--accent);color:#000;border:none;border-radius:4px;font-size:12px;font-weight:600;cursor:pointer;'>Save Mapping</button>`;
    // Save handler
    document.getElementById('roles-skills-save-btn').onclick = async function() {
      // Build new mapping from checkboxes
      const newMap = {};
      panel.querySelectorAll('input[type=checkbox][data-role][data-skill]').forEach(cb => {
        const role = cb.getAttribute('data-role');
        const skill = cb.getAttribute('data-skill');
        if (!newMap[role]) newMap[role] = [];
        if (cb.checked) newMap[role].push(skill);
      });
      const res = await fetch('/api/roles-skills', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({mapping: newMap})
      });
      const data = await res.json();
      if (data.ok) {
        showToast('Roles–skills mapping saved', 'success');
      } else {
        showToast('Failed to save: ' + (data.error || 'unknown error'), 'error');
      }
    };
  } catch (e) {
    panel.innerHTML = `<div style='color:#f77;font-size:12px;'>Failed: ${_esc(e.message)}</div>`;
  }
}

// Auto-load grid when Access tile opens
if (window.addEventListener) {
  window.addEventListener('DOMContentLoaded', () => {
    setTimeout(loadRolesSkillsGrid, 500);
  });
}
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
        .map(f => `<div style="margin:2px 0;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:2px;"><path d="M4.5 1.5h4.59L12.5 5v9.5h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M9 1.5v4h3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> ${_esc(f)}</div>`)
        .join('');
    }
  } else if (action === 'modify' || action === 'modified') {
    if (!window._workflowState.filesModified.includes(filepath)) {
      window._workflowState.filesModified.push(filepath);
    }
    const modDiv = document.getElementById('workflow-files-modified');
    if (modDiv) {
      modDiv.innerHTML = window._workflowState.filesModified
        .map(f => `<div style="margin:2px 0;color:#ff9e4d;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><path d="M11.5 2.5l2 2M5 9l-1 3 3-1 7-7-2-2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg> ${_esc(f)}</div>`)
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
  return Promise.all([
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
    const isLocal    = a.tier === 'local' || a.tier === 'human';
    const isService  = a.tier === 'service';
    const tierLabel  = a.tier === 'human' ? 'human' : isService ? 'service' : (isLocal ? 'local' : 'api');
    const tierColor  = a.tier === 'human'
      ? 'background:#1a1a3a;color:#9b8cff;'
      : isService ? 'background:#1a2a3a;color:#60a5fa;'
      : (isLocal ? 'background:#1a3a1a;color:#4caf50;' : 'background:#3a2a10;color:#ff9e4d;');
    const tierBadge  = `<span style="${tierColor}border-radius:3px;padding:1px 5px;font-size:9px;font-weight:700;">${tierLabel}</span>`;
    const isDecommissioned = a.enabled == 0;
    const statusDot = isDecommissioned
      ? '<span style="color:#ffb366;font-size:10px;line-height:1;" title="Decommissioned">◌</span>'
      : '<span style="color:#4caf50;font-size:10px;line-height:1;">●</span>';
    const dcomBadge = isDecommissioned
      ? '<span style="background:#3a2a00;color:#ffb366;border-radius:3px;padding:1px 5px;font-size:9px;font-weight:700;">OFF</span>'
      : '';
    return `<div class="agents-list-row" data-name="${_esc(a.name)}"
      style="padding:10px 14px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:3px;transition:background 0.12s;${isDecommissioned ? 'opacity:0.6;' : ''}">
      <div style="display:flex;align-items:center;gap:6px;">
        ${statusDot}
        <span style="font-size:12px;font-weight:700;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(a.label || a.name)}</span>
        ${dcomBadge}${tierBadge}
      </div>
      <div style="font-size:10px;color:var(--text-dim);padding-left:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(a.model || '')}</div>
    </div>`;
  }).join('');
  // Attach click listeners after rendering — avoids double-quote conflicts with JSON.stringify in onclick attributes
  el.querySelectorAll('.agents-list-row').forEach(row => {
    row.addEventListener('click', () => {
      const name = row.dataset.name;
      const agent = (window.__agentsData || []).find(x => x.name === name);
      if (agent) agentsShowDetail(agent);
    });
  });
}

function agentsShowDetail(agent) {
  if (!agent) return;
  document.querySelectorAll('.agents-list-row').forEach(r => {
    r.style.background = r.dataset.name === agent.name ? 'rgba(255,255,255,0.06)' : '';
  });
  const el = document.getElementById('agents-detail');
  if (!el) return;
  const isLocal   = agent.tier === 'local' || agent.tier === 'human';
  const keyStatus = agent.api_key_set
    ? '<span style="color:#4caf50;font-size:10px;">● set</span>'
    : (isLocal
        ? '<span style="color:var(--text-dim);font-size:10px;">— n/a</span>'
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
            <option value="local"   ${agent.tier==='local'   ?'selected':''}>Local (Ollama)</option>
            <option value="paid"    ${agent.tier==='paid'    ?'selected':''}>Paid API</option>
            <option value="free"    ${agent.tier==='free'    ?'selected':''}>Free API</option>
            <option value="service" ${agent.tier==='service' ?'selected':''}>Service (no chat/memory)</option>
            <option value="human"   ${agent.tier==='human'   ?'selected':''}>Human</option>
          </select>
        </div>
        <div style="grid-column:span 2;">
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">API Key</label>
          ${isLocal ? `<span style="font-size:11px;color:var(--text-dim);">— n/a for ${agent.tier} agents</span>` : `
          <div style="display:flex;gap:6px;align-items:center;">
            <input id="agent-key-var" type="text" value="${_esc(agent.api_key_var || '')}" placeholder="Env var name e.g. GROQ_API_KEY"
              style="width:140px;flex-shrink:0;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            <input id="agent-key-value" type="password" placeholder="Paste key value…"
              style="flex:1;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            <button id="agent-save-key-btn"
              style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:6px 12px;cursor:pointer;font-size:11px;white-space:nowrap;">
              Save Key
            </button>
            ${keyStatus}
          </div>`}
        </div>
      </div>

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
        <button id="agent-save-btn"
          style="background:var(--accent);border:none;color:#000;border-radius:5px;padding:7px 18px;cursor:pointer;font-size:12px;font-weight:700;">
          Save Changes
        </button>
        <button id="agent-reset-btn"
          style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:7px 14px;cursor:pointer;font-size:12px;">
          Reset
        </button>
        <div id="agent-save-status" style="font-size:11px;color:var(--text-dim);"></div>
        <div style="flex:1;"></div>
        ${agent.enabled == 0 ? `
        <span style="font-size:10px;color:#ffb366;border:1px solid #ffb36644;border-radius:10px;padding:2px 10px;">DECOMMISSIONED</span>
        <button id="agent-reactivate-btn"
          style="background:var(--card);border:1px solid #72e6a666;color:#72e6a6;border-radius:5px;padding:7px 14px;cursor:pointer;font-size:11px;">
          Reactivate
        </button>` : ''}
        ${!['gemma','llama','mistral','qwen','eight','nine','ten','eleven','twelve','ghost','librarian','duck','sniffles'].includes(agent.name) && agent.enabled != 0 ? `
        <button id="agent-bootstrap-btn"
          style="background:var(--card);border:1px solid #72e6a666;color:#72e6a6;border-radius:5px;padding:7px 14px;cursor:pointer;font-size:11px;">
          Initialize
        </button>` : ''}
        ${agent.name !== 'ghost' && agent.enabled != 0 ? `
        <button id="agent-reset-agent-btn"
          style="background:transparent;border:1px solid #60a5fa44;color:#60a5fa;border-radius:5px;padding:7px 14px;cursor:pointer;font-size:11px;">
          Reset
        </button>` : ''}
        ${agent.name !== 'ghost' ? `
        <button id="agent-decommission-btn"
          style="background:transparent;border:1px solid #ffb36644;color:#ffb366;border-radius:5px;padding:7px 14px;cursor:pointer;font-size:11px;">
          Decommission
        </button>` : ''}
      </div>
    </div>
  `;
  const saveBtn = el.querySelector('#agent-save-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => agentsSave(agent.name));
  }
  const saveKeyBtn = el.querySelector('#agent-save-key-btn');
  if (saveKeyBtn) {
    saveKeyBtn.addEventListener('click', () => agentsSaveKey(agent.name));
  }
  const resetBtn = el.querySelector('#agent-reset-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      const fresh = (window.__agentsData || []).find(x => x.name === agent.name);
      if (fresh) agentsShowDetail(fresh);
    });
  }
  const bootstrapBtn = el.querySelector('#agent-bootstrap-btn');
  if (bootstrapBtn) {
    bootstrapBtn.addEventListener('click', () => agentsBootstrap(agent.name, agent.label || agent.name));
  }
  const reactivateBtn = el.querySelector('#agent-reactivate-btn');
  if (reactivateBtn) {
    reactivateBtn.addEventListener('click', () => agentsReactivate(agent.name, agent.label || agent.name));
  }
  const resetAgentBtn = el.querySelector('#agent-reset-agent-btn');
  if (resetAgentBtn) {
    resetAgentBtn.addEventListener('click', () => agentsReset(agent.name, agent.label || agent.name));
  }
  const decommissionBtn = el.querySelector('#agent-decommission-btn');
  if (decommissionBtn) {
    decommissionBtn.addEventListener('click', () => agentsDecommission(agent.name, agent.label || agent.name));
  }
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
  const keyValue = (document.getElementById('agent-key-value')?.value || '').trim();
  const keyVar   = (document.getElementById('agent-key-var')?.value  || '').trim();

  fetch(`/api/agents/config/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  }).then(r => r.json()).then(data => {
    if (!data.ok) {
      if (statusEl) { statusEl.textContent = data.error || 'Save failed'; statusEl.style.color = '#ff6b6b'; }
      return;
    }
    // If a key value was pasted, save it to .env.agents too
    if (keyValue && keyVar) {
      return fetch(`/api/agents/key/${encodeURIComponent(name)}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key_var: keyVar, value: keyValue})
      }).then(r => r.json()).then(kd => {
        const keyInput = document.getElementById('agent-key-value');
        if (keyInput) keyInput.value = '';
        const idx = (window.__agentsData || []).findIndex(a => a.name === name);
        if (idx >= 0) {
          Object.assign(window.__agentsData[idx], payload);
          if (kd.ok) window.__agentsData[idx].api_key_set = true;
        }
        _agentsRefreshDetail(name);
        if (kd.ok) {
          if (statusEl) { statusEl.textContent = '✓ Saved'; statusEl.style.color = '#4caf50'; }
          setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 2000);
        } else {
          if (statusEl) { statusEl.textContent = kd.error || 'Config saved, key failed'; statusEl.style.color = '#ff6b6b'; }
        }
      });
    }
    if (statusEl) { statusEl.textContent = '✓ Saved'; statusEl.style.color = '#4caf50'; }
    setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 2000);
    const idx = (window.__agentsData || []).findIndex(a => a.name === name);
    if (idx >= 0) Object.assign(window.__agentsData[idx], payload);
    _agentsRefreshDetail(name);
  }).catch(err => {
    if (statusEl) { statusEl.textContent = err.message; statusEl.style.color = '#ff6b6b'; }
  });
}

function _agentsRefreshDetail(name) {
  agentsRenderList(window.__agentsData);
  document.querySelectorAll('.agents-list-row').forEach(r => {
    r.style.background = r.dataset.name === name ? 'rgba(255,255,255,0.06)' : '';
  });
  const updated = (window.__agentsData || []).find(a => a.name === name);
  if (updated) agentsShowDetail(updated);
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
      const agent = (window.__agentsData || []).find(a => a.name === name);
      if (agent) agent.api_key_set = true;
      _agentsRefreshDetail(name);
      showToast('Key saved', 'success');
    } else {
      showToast(data.error || 'Failed to save key', 'error');
    }
  }).catch(err => showToast(err.message, 'error'));
}

function _agentsInitModal() {
  const modal   = document.getElementById('agent-init-modal');
  const body    = document.getElementById('agent-init-body');
  const pill    = document.getElementById('agent-init-status-pill');
  const sub     = document.getElementById('agent-init-subtitle');
  const footer  = document.getElementById('agent-init-footer');
  const footMsg = document.getElementById('agent-init-footer-msg');
  const dismiss = document.getElementById('agent-init-dismiss-btn');
  const close   = document.getElementById('agent-init-close-btn');
  return { modal, body, pill, sub, footer, footMsg, dismiss, close };
}

function _agentsInitModalOpen(label) {
  const { modal, body, pill, sub, footer } = _agentsInitModal();
  if (!modal) return;
  body.textContent = '';
  pill.textContent = 'LIVE';
  pill.style.color = '#22c55e';
  pill.style.background = '#22c55e22';
  pill.style.borderColor = '#22c55e44';
  sub.textContent = label;
  footer.style.display = 'none';
  modal.style.display = 'flex';

  // drag
  const handle = document.getElementById('agent-init-drag-handle');
  if (handle && !handle.dataset.dragBound) {
    handle.dataset.dragBound = '1';
    handle.addEventListener('mousedown', (ev) => {
      if (ev.target.closest('button')) return;
      const rect = modal.getBoundingClientRect();
      const ox = ev.clientX - rect.left, oy = ev.clientY - rect.top;
      const move = (e) => {
        const left = Math.min(Math.max(8, e.clientX - ox), window.innerWidth - rect.width - 8);
        const top  = Math.min(Math.max(8, e.clientY - oy), window.innerHeight - rect.height - 8);
        modal.style.left = left + 'px'; modal.style.top = top + 'px';
        modal.style.right = 'auto'; modal.style.bottom = 'auto';
      };
      const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); };
      window.addEventListener('mousemove', move);
      window.addEventListener('mouseup', up);
    });
  }

  const { close, dismiss } = _agentsInitModal();
  const closeModal = () => { modal.style.display = 'none'; };
  if (close) { close.onclick = closeModal; }
  if (dismiss) { dismiss.onclick = closeModal; }
}

function _agentsInitModalAppend(text, color) {
  const { body } = _agentsInitModal();
  if (!body) return;
  const line = document.createElement('span');
  line.style.color = color || 'var(--text-dim)';
  line.textContent = text + '\n';
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function _agentsInitModalDone(ok, summary, failedChecks) {
  const { pill, footer, footMsg } = _agentsInitModal();
  if (pill) {
    pill.textContent = ok ? 'DONE' : 'ERRORS';
    pill.style.color = ok ? '#72e6a6' : '#ff6b6b';
    pill.style.background = ok ? '#22c55e11' : '#ff6b6b11';
    pill.style.borderColor = ok ? '#22c55e44' : '#ff6b6b44';
  }
  if (footer && footMsg) {
    footer.style.display = 'flex';
    if (ok) {
      const warn = failedChecks?.length ? ` · ${failedChecks.length} check(s) need server restart` : '';
      footMsg.textContent = summary + warn;
      footMsg.style.color = failedChecks?.length ? '#ffb366' : '#72e6a6';
    } else {
      footMsg.textContent = summary;
      footMsg.style.color = '#ff6b6b';
    }
  }
}

function agentsBootstrap(name, label) {
  const btn = document.getElementById('agent-bootstrap-btn');
  if (btn) { btn.textContent = 'Initializing…'; btn.style.pointerEvents = 'none'; }

  _agentsInitModalOpen(label || name);
  _agentsInitModalAppend(`Initializing agent: ${label || name}`, 'var(--text)');
  _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');

  fetch('/api/agents/bootstrap', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name})
  }).then(r => r.json()).then(bs => {
    const steps = bs.steps || [];
    const errors = bs.errors || [];
    const checks = bs.checks || {};
    const failed = bs.failed_checks || [];

    steps.forEach(s => {
      const lower = s.toLowerCase();
      const isFail = lower.includes('fail') || lower.includes('error') || s.startsWith(' FAIL');
      const isSkip = lower.includes('skip') || lower.includes('already');
      const color = isFail ? '#ff6b6b' : isSkip ? '#aaa' : '#72e6a6';
      _agentsInitModalAppend('  ✓ ' + s, color);
    });

    if (errors.length) {
      _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
      _agentsInitModalAppend('Errors:', '#ff6b6b');
      errors.forEach(e => _agentsInitModalAppend('  ' + e, '#ff6b6b'));
      _glitchLog('bootstrap', `${name}: ${errors.join('; ')}`);
    }

    if (Object.keys(checks).length) {
      _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
      _agentsInitModalAppend('Verification:', 'var(--text-dim)');
      Object.entries(checks).forEach(([k, v]) => {
        const pass = v === true;
        _agentsInitModalAppend(`  ${pass ? '✓' : '✗'} ${k}`, pass ? '#72e6a6' : '#ffb366');
      });
    }

    if (failed.length) {
      _glitchLog('bootstrap-checks', `${name} failed checks: ${failed.join(', ')}`);
    }

    _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
    const doneMsg = bs.ok
      ? `Done · ${steps.length} step(s) completed`
      : `Completed with errors · ${errors.length} error(s)`;
    _agentsInitModalAppend(bs.ok ? '✓ ' + doneMsg : '⚠ ' + doneMsg, bs.ok ? '#72e6a6' : '#ff6b6b');
    if (bs.ok) _agentsInitModalAppend('Restart the server to go live.', '#ffb366');

    _agentsInitModalDone(bs.ok, bs.ok ? 'Automation complete' : `${errors.length} error(s)`, failed);

    if (btn) { btn.textContent = bs.ok ? '✓ Initialized' : '⚠ Errors'; btn.style.pointerEvents = 'auto'; }
    if (bs.ok) {
      showToast(`"${label}" initialized — restart server to go live`, 'success');
    } else {
      showToast('Initialization had errors — see Initialization window', 'warning');
    }
  }).catch(err => {
    _agentsInitModalAppend('Network error: ' + err.message, '#ff6b6b');
    _agentsInitModalDone(false, err.message, []);
    _glitchLog('bootstrap', `${name}: ${err.message}`);
    if (btn) { btn.textContent = 'Initialize'; btn.style.pointerEvents = 'auto'; }
    showToast('Initialization failed — see Initialization window', 'error');
  });
}

function _agentsDeleteModal() {
  return {
    modal:   document.getElementById('agent-delete-modal'),
    body:    document.getElementById('agent-delete-body'),
    pill:    document.getElementById('agent-delete-status-pill'),
    sub:     document.getElementById('agent-delete-subtitle'),
    footer:  document.getElementById('agent-delete-footer'),
    footMsg: document.getElementById('agent-delete-footer-msg'),
    dismiss: document.getElementById('agent-delete-dismiss-btn'),
    close:   document.getElementById('agent-delete-close-btn'),
  };
}

function _agentsDeleteModalOpen(label) {
  const { modal, body, pill, sub, footer, close, dismiss } = _agentsDeleteModal();
  if (!modal) return;
  body.textContent = '';
  pill.textContent = 'RUNNING';
  pill.style.color = '#ff6b6b'; pill.style.background = '#ff6b6b22'; pill.style.borderColor = '#ff6b6b44';
  sub.textContent = label;
  footer.style.display = 'none';
  modal.style.display = 'flex';

  const handle = document.getElementById('agent-delete-drag-handle');
  if (handle && !handle.dataset.dragBound) {
    handle.dataset.dragBound = '1';
    handle.addEventListener('mousedown', (ev) => {
      if (ev.target.closest('button')) return;
      const rect = modal.getBoundingClientRect();
      const ox = ev.clientX - rect.left, oy = ev.clientY - rect.top;
      const move = (e) => {
        modal.style.left = Math.min(Math.max(8, e.clientX - ox), window.innerWidth - rect.width - 8) + 'px';
        modal.style.top  = Math.min(Math.max(8, e.clientY - oy), window.innerHeight - rect.height - 8) + 'px';
        modal.style.right = 'auto'; modal.style.bottom = 'auto';
      };
      const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); };
      window.addEventListener('mousemove', move); window.addEventListener('mouseup', up);
    });
  }
  const closeModal = () => { modal.style.display = 'none'; };
  if (close)   close.onclick = closeModal;
  if (dismiss) dismiss.onclick = closeModal;
}

function _agentsDeleteModalAppend(text, color) {
  const { body } = _agentsDeleteModal();
  if (!body) return;
  const line = document.createElement('span');
  line.style.color = color || 'var(--text-dim)';
  line.textContent = text + '\n';
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function _agentsDeleteModalDone(ok, summary) {
  const { pill, footer, footMsg } = _agentsDeleteModal();
  if (pill) {
    pill.textContent = ok ? 'DONE' : 'ERRORS';
    pill.style.color = ok ? '#72e6a6' : '#ff6b6b';
    pill.style.background = ok ? '#22c55e11' : '#ff6b6b11';
    pill.style.borderColor = ok ? '#22c55e44' : '#ff6b6b44';
  }
  if (footer && footMsg) {
    footer.style.display = 'flex';
    footMsg.textContent = summary;
    footMsg.style.color = ok ? '#72e6a6' : '#ff6b6b';
  }
}

function agentsReset(name, label) {
  const confirm = document.createElement('div');
  confirm.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;';
  confirm.innerHTML = `
    <div style="background:var(--card);border:1px solid #60a5fa44;border-radius:8px;padding:24px;width:400px;max-width:90vw;">
      <div style="font-size:14px;font-weight:700;margin-bottom:8px;color:#60a5fa;">Reset Agent</div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:18px;">
        All memory rows and sandpit files for <strong style="color:var(--text);">${label}</strong> will be wiped.
        Config, API key, and system prompt are preserved. Automation runs fresh afterwards.
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button id="rst-cancel" style="background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:7px 16px;cursor:pointer;font-size:12px;">Cancel</button>
        <button id="rst-confirm" style="background:#60a5fa;border:none;color:#000;border-radius:5px;padding:7px 18px;cursor:pointer;font-size:12px;font-weight:700;">Reset</button>
      </div>
    </div>`;
  document.body.appendChild(confirm);
  confirm.querySelector('#rst-cancel').addEventListener('click', () => confirm.remove());
  confirm.querySelector('#rst-confirm').addEventListener('click', () => {
    confirm.remove();
    _agentsInitModalOpen(label || name);
    _agentsInitModalAppend(`Resetting agent: ${label || name}`, 'var(--text)');
    _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
    fetch(`/api/agents/${encodeURIComponent(name)}/reset`, { method: 'POST' })
      .then(r => r.json()).then(data => {
        (data.steps || []).forEach(s => {
          const isSkip = s.toLowerCase().includes('skip') || s.toLowerCase().includes('not found') || s.toLowerCase().includes('already');
          const isWipe = s.toLowerCase().includes('cleared') || s.toLowerCase().includes('deleted') || s.toLowerCase().includes('removed');
          _agentsInitModalAppend('  ✓ ' + s, isWipe ? '#ff6b6b' : isSkip ? '#aaa' : '#72e6a6');
        });
        (data.errors || []).forEach(e => _agentsInitModalAppend('  ✗ ' + e, '#ff6b6b'));
        if (Object.keys(data.checks || {}).length) {
          _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
          Object.entries(data.checks).forEach(([k, v]) =>
            _agentsInitModalAppend(`  ${v ? '✓' : '✗'} ${k}`, v ? '#72e6a6' : '#ffb366'));
        }
        _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
        _agentsInitModalAppend(data.ok ? '✓ Reset complete — restart server to go live' : '⚠ Reset had errors', data.ok ? '#72e6a6' : '#ff6b6b');
        _agentsInitModalDone(data.ok, data.ok ? 'Reset complete' : 'Errors', data.failed_checks || []);
        showToast(data.ok ? `"${label}" reset — restart server` : 'Reset had errors', data.ok ? 'success' : 'warning');
      }).catch(err => {
        _agentsInitModalAppend('Network error: ' + err.message, '#ff6b6b');
        _agentsInitModalDone(false, err.message, []);
      });
  });
}

function agentsDecommission(name, label) {
  const confirm = document.createElement('div');
  confirm.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;';
  confirm.innerHTML = `
    <div style="background:var(--card);border:1px solid #ffb36666;border-radius:8px;padding:24px;width:400px;max-width:90vw;">
      <div style="font-size:14px;font-weight:700;margin-bottom:8px;color:#ffb366;">Decommission Agent</div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:18px;">
        <strong style="color:var(--text);">${label}</strong> will be removed from all active registries and
        won't be usable until reactivated. All memory, sandpit data, and the agent module are preserved.
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button id="dcom-cancel" style="background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:7px 16px;cursor:pointer;font-size:12px;">Cancel</button>
        <button id="dcom-confirm" style="background:#ffb366;border:none;color:#000;border-radius:5px;padding:7px 18px;cursor:pointer;font-size:12px;font-weight:700;">Decommission</button>
      </div>
    </div>`;
  document.body.appendChild(confirm);
  confirm.querySelector('#dcom-cancel').addEventListener('click', () => confirm.remove());
  confirm.querySelector('#dcom-confirm').addEventListener('click', () => {
    confirm.remove();
    _agentsDeleteModalOpen(label || name);
    _agentsDeleteModalAppend(`Decommissioning: ${label || name}`, 'var(--text)');
    _agentsDeleteModalAppend('──────────────────────────────────────────────────', '#333');
    fetch(`/api/agents/${encodeURIComponent(name)}/decommission`, { method: 'POST' })
      .then(r => r.json()).then(data => {
        (data.steps || []).forEach(s => {
          const isSkip = s.toLowerCase().includes('skip') || s.toLowerCase().includes('not found');
          _agentsDeleteModalAppend('  ✓ ' + s, isSkip ? '#aaa' : '#72e6a6');
        });
        (data.errors || []).forEach(e => _agentsDeleteModalAppend('  ✗ ' + e, '#ff6b6b'));
        _agentsDeleteModalAppend('──────────────────────────────────────────────────', '#333');
        if (data.ok) {
          _agentsDeleteModalAppend('✓ Decommissioned — data preserved, reactivate any time', '#ffb366');
          _agentsDeleteModalDone(true, 'Decommissioned · use Reactivate to restore');
          // Refresh and show with decommissioned state
          agentsRefresh().then(() => {
            const updated = (window.__agentsData || []).find(a => a.name === name);
            if (updated) agentsShowDetail(updated);
          });
          showToast(`"${label}" decommissioned`, 'info');
        } else {
          _agentsDeleteModalAppend('⚠ ' + (data.errors?.[0] || 'Decommission had errors'), '#ff6b6b');
          _agentsDeleteModalDone(false, 'Errors — check log');
        }
      }).catch(err => {
        _agentsDeleteModalAppend('Network error: ' + err.message, '#ff6b6b');
        _agentsDeleteModalDone(false, err.message);
      });
  });
}

function agentsReactivate(name, label) {
  const btn = document.getElementById('agent-reactivate-btn');
  if (btn) { btn.textContent = 'Reactivating…'; btn.style.pointerEvents = 'none'; }
  _agentsInitModalOpen(label || name);
  _agentsInitModalAppend(`Reactivating agent: ${label || name}`, 'var(--text)');
  _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
  fetch(`/api/agents/${encodeURIComponent(name)}/reactivate`, { method: 'POST' })
    .then(r => r.json()).then(bs => {
      (bs.steps || []).forEach(s => {
        const isSkip = s.toLowerCase().includes('skip') || s.toLowerCase().includes('already');
        _agentsInitModalAppend('  ✓ ' + s, isSkip ? '#aaa' : '#72e6a6');
      });
      (bs.errors || []).forEach(e => _agentsInitModalAppend('  ✗ ' + e, '#ff6b6b'));
      if (Object.keys(bs.checks || {}).length) {
        _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
        Object.entries(bs.checks).forEach(([k, v]) =>
          _agentsInitModalAppend(`  ${v ? '✓' : '✗'} ${k}`, v ? '#72e6a6' : '#ffb366'));
      }
      _agentsInitModalAppend('──────────────────────────────────────────────────', '#333');
      _agentsInitModalAppend(bs.ok ? '✓ Reactivated — restart server to go live' : '⚠ Errors during reactivation', bs.ok ? '#72e6a6' : '#ff6b6b');
      _agentsInitModalDone(bs.ok, bs.ok ? 'Reactivated' : 'Errors', bs.failed_checks || []);
      if (btn) { btn.textContent = bs.ok ? '✓ Reactivated' : '⚠ Errors'; btn.style.pointerEvents = 'auto'; }
      agentsRefresh().then(() => {
        const updated = (window.__agentsData || []).find(a => a.name === name);
        if (updated) agentsShowDetail(updated);
      });
      showToast(bs.ok ? `"${label}" reactivated — restart server` : 'Reactivation had errors', bs.ok ? 'success' : 'warning');
    }).catch(err => {
      _agentsInitModalAppend('Network error: ' + err.message, '#ff6b6b');
      _agentsInitModalDone(false, err.message, []);
      if (btn) { btn.textContent = 'Reactivate'; btn.style.pointerEvents = 'auto'; }
    });
}

function agentsDelete(name, label) {
  // Confirmation dialog first
  const confirm = document.createElement('div');
  confirm.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;';
  confirm.innerHTML = `
    <div style="background:var(--card);border:1px solid #ff6b6b66;border-radius:8px;padding:24px;width:380px;max-width:90vw;">
      <div style="font-size:14px;font-weight:700;margin-bottom:8px;color:#ff6b6b;">Delete Agent</div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:16px;">
        Permanently remove <strong style="color:var(--text);">${label}</strong> from the DB, all registries, chat, memory, and sandpit.
        This cannot be undone. A log window will show exactly what was removed.
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button id="del-cancel" style="background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:7px 16px;cursor:pointer;font-size:12px;">Cancel</button>
        <button id="del-confirm" style="background:#ff6b6b;border:none;color:#fff;border-radius:5px;padding:7px 18px;cursor:pointer;font-size:12px;font-weight:700;">Delete</button>
      </div>
    </div>`;
  document.body.appendChild(confirm);
  confirm.querySelector('#del-cancel').addEventListener('click', () => confirm.remove());
  confirm.querySelector('#del-confirm').addEventListener('click', () => {
    confirm.remove();

    _agentsDeleteModalOpen(label || name);
    _agentsDeleteModalAppend(`Deleting agent: ${label || name}`, 'var(--text)');
    _agentsDeleteModalAppend('──────────────────────────────────────────────────', '#333');

    fetch(`/api/agents/${encodeURIComponent(name)}`, {
      method: 'DELETE',
      headers: {'Content-Type': 'application/json'}
    }).then(r => r.json()).then(data => {
      const steps = data.steps || [];
      const errors = data.errors || [];
      const failed = data.failed_checks || [];

      steps.forEach(s => {
        const lower = s.toLowerCase();
        const isErr = lower.includes('error') || lower.includes('fail');
        const isSkip = lower.includes('skip') || lower.includes('not found') || lower.includes('already');
        _agentsDeleteModalAppend('  ✓ ' + s, isErr ? '#ff6b6b' : isSkip ? '#aaa' : '#72e6a6');
      });

      if (errors.length) {
        _agentsDeleteModalAppend('──────────────────────────────────────────────────', '#333');
        errors.forEach(e => _agentsDeleteModalAppend('  ✗ ' + e, '#ff6b6b'));
        _glitchLog('delete-agent', `${name}: ${errors.join('; ')}`);
      }

      if (data.ok) {
        _agentsDeleteModalAppend('──────────────────────────────────────────────────', '#333');
        _agentsDeleteModalAppend(`✓ ${name} removed from all registries`, '#72e6a6');
        if (failed.length) _agentsDeleteModalAppend('  Some checks need server restart: ' + failed.join(', '), '#ffb366');
        _agentsDeleteModalDone(true, `${label} deleted · restart server to fully apply`);
        window.__agentsData = (window.__agentsData || []).filter(a => a.name !== name);
        agentsRenderList(window.__agentsData);
        document.getElementById('agents-detail').innerHTML = '';
        showToast(`Agent "${label}" deleted`, 'success');
      } else {
        _agentsDeleteModalAppend('──────────────────────────────────────────────────', '#333');
        _agentsDeleteModalAppend('⚠ ' + (data.error || 'Delete failed'), '#ff6b6b');
        _agentsDeleteModalDone(false, data.error || 'Delete failed');
      }
    }).catch(err => {
      _agentsDeleteModalAppend('Network error: ' + err.message, '#ff6b6b');
      _agentsDeleteModalDone(false, err.message);
      _glitchLog('delete-agent', `${name}: ${err.message}`);
    });
  });
}

function agentsShowAdd() {
  const existing = document.getElementById('agents-add-modal');
  if (existing) { existing.remove(); }
  const modal = document.createElement('div');
  modal.id = 'agents-add-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);display:flex;align-items:center;justify-content:center;z-index:9999;';

  // Known API key vars — seeded list + anything previously typed, stored in localStorage
  const _SEED_KEY_VARS = [
    'GROQ_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','XAI_API_KEY',
    'HF_API_TOKEN','GEMINI_API_KEY','TAVILY_API_KEY','COHERE_API_KEY',
    'MISTRAL_API_KEY','TOGETHER_API_KEY','PERPLEXITY_API_KEY',
  ];
  const _savedKeyVars = JSON.parse(localStorage.getItem('__knownApiKeyVars') || '[]');
  const _allKeyVars = [...new Set([..._SEED_KEY_VARS, ..._savedKeyVars])];
  const _datalistOpts = _allKeyVars.map(v => `<option value="${v}">`).join('');

  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:24px;width:520px;max-width:95vw;max-height:90vh;overflow-y:auto;">
      <div style="font-size:14px;font-weight:700;margin-bottom:18px;">+ Add New Agent</div>
      <datalist id="key-var-list">${_datalistOpts}</datalist>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Name (unique, lowercase)</label>
          <input id="new-agent-name" type="text" placeholder="e.g. fourteen"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Label</label>
          <input id="new-agent-label" type="text" placeholder="e.g. Fourteen"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Model</label>
          <input id="new-agent-model" type="text" placeholder="e.g. gpt-4o-mini"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Tier</label>
          <select id="new-agent-tier"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            <option value="local">Local (Ollama)</option>
            <option value="paid">Paid API</option>
            <option value="free">Free API</option>
            <option value="service">Service (no chat/memory)</option>
            <option value="human">Human</option>
          </select>
        </div>

        <div id="new-agent-key-section" style="grid-column:span 2;">
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:6px;">API Key</label>
          <div style="display:flex;gap:6px;align-items:center;">
            <input id="new-agent-key-var" list="key-var-list" type="text" placeholder="Select or type env var name…"
              style="width:160px;flex-shrink:0;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            <input id="new-agent-key-value" type="password" placeholder="Paste key value…"
              style="flex:1;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;">
            <button id="new-agent-key-confirm-btn"
              style="background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:6px 12px;cursor:pointer;font-size:11px;white-space:nowrap;">
              Confirm
            </button>
            <span id="new-agent-key-status" style="font-size:16px;min-width:18px;">⚪</span>
          </div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">Key saved to .env.agents — not stored in DB. Required before adding.</div>
        </div>

        <div style="grid-column:span 2;">
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Role / Description</label>
          <input id="new-agent-role" type="text" placeholder="e.g. Open-source ML research"
            style="width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div style="grid-column:span 2;">
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">System Prompt</label>
          <textarea id="new-agent-prompt" rows="5" placeholder="You are…"
            style="width:100%;padding:7px 10px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:11px;font-family:monospace;outline:none;resize:vertical;box-sizing:border-box;"></textarea>
        </div>
      </div>
      <div id="agents-add-err" style="font-size:11px;color:#ff6b6b;min-height:16px;margin-bottom:10px;"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;">
        <span style="font-size:10px;color:var(--text-dim);margin-right:auto;">Initialization runs from the agent detail screen after adding.</span>
        <button onclick="document.getElementById('agents-add-modal').remove()"
          style="background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:7px 16px;cursor:pointer;font-size:12px;">
          Cancel
        </button>
        <button id="new-agent-submit-btn"
          style="background:var(--accent);border:none;color:#000;border-radius:5px;padding:7px 18px;cursor:pointer;font-size:12px;font-weight:700;opacity:0.4;pointer-events:none;">
          Add Agent
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });

  // Show/hide key section based on tier
  const tierSel = modal.querySelector('#new-agent-tier');
  const keySec  = modal.querySelector('#new-agent-key-section');
  const submitBtn = modal.querySelector('#new-agent-submit-btn');
  function _updateTierVis() {
    const isNoKey = tierSel.value === 'local' || tierSel.value === 'human' || tierSel.value === 'service';
    keySec.style.display = isNoKey ? 'none' : '';
    // local/human/service don't need key confirmation
    if (isNoKey) _setAddReady(true);
    else _setAddReady(false);
  }
  function _setAddReady(ready) {
    submitBtn.style.opacity = ready ? '1' : '0.4';
    submitBtn.style.pointerEvents = ready ? 'auto' : 'none';
  }
  tierSel.addEventListener('change', _updateTierVis);
  _updateTierVis();

  // Confirm button — validates both fields filled, saves to __pendingKeyConfirm
  window.__pendingNewAgentKey = null;
  modal.querySelector('#new-agent-key-confirm-btn').addEventListener('click', () => {
    const keyVar   = (modal.querySelector('#new-agent-key-var')?.value || '').trim();
    const keyValue = (modal.querySelector('#new-agent-key-value')?.value || '').trim();
    const statusEl = modal.querySelector('#new-agent-key-status');
    if (!keyVar || !keyValue) {
      statusEl.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f44336;"></span>';
      const errEl = modal.querySelector('#agents-add-err');
      if (errEl) { errEl.textContent = 'Both env var name and key value are required.'; errEl.style.color = '#ff6b6b'; }
      return;
    }
    // Save new var name to localStorage if not already known
    const saved = JSON.parse(localStorage.getItem('__knownApiKeyVars') || '[]');
    if (!saved.includes(keyVar)) {
      saved.push(keyVar);
      localStorage.setItem('__knownApiKeyVars', JSON.stringify(saved));
      // Add to datalist live
      const dl = modal.querySelector('#key-var-list');
      if (dl) { const opt = document.createElement('option'); opt.value = keyVar; dl.appendChild(opt); }
    }
    window.__pendingNewAgentKey = {keyVar, keyValue};
    statusEl.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#4caf50;"></span>';
    _setAddReady(true);
    const errEl = modal.querySelector('#agents-add-err');
    if (errEl) { errEl.textContent = ''; }
  });

  // Reset status if user changes key fields after confirming
  ['#new-agent-key-var','#new-agent-key-value'].forEach(sel => {
    modal.querySelector(sel)?.addEventListener('input', () => {
      window.__pendingNewAgentKey = null;
      const statusEl = modal.querySelector('#new-agent-key-status');
      if (statusEl) statusEl.textContent = '⚪';
      const tier = tierSel.value;
      if (tier !== 'local' && tier !== 'human' && tier !== 'service') _setAddReady(false);
    });
  });

  submitBtn.addEventListener('click', agentsSubmitAdd);
  setTimeout(() => document.getElementById('new-agent-name')?.focus(), 50);
}

function agentsSubmitAdd() {
  const modal  = document.getElementById('agents-add-modal');
  const errEl  = modal?.querySelector('#agents-add-err');
  const name   = (modal?.querySelector('#new-agent-name')?.value || '').trim().toLowerCase();
  if (!name) { if (errEl) { errEl.textContent = 'Name is required.'; errEl.style.color = '#ff6b6b'; } return; }
  const tier   = modal?.querySelector('#new-agent-tier')?.value || 'local';
  const isNoKey = tier === 'local' || tier === 'human' || tier === 'service';
  const pending = window.__pendingNewAgentKey;
  if (!isNoKey && !pending) {
    if (errEl) { errEl.textContent = 'Confirm the API key first (click Confirm button).'; errEl.style.color = '#ff6b6b'; }
    return;
  }
  const payload = {
    name,
    label:         (modal?.querySelector('#new-agent-label')?.value   || '').trim() || name,
    model:         (modal?.querySelector('#new-agent-model')?.value   || '').trim(),
    tier,
    api_key_var:   pending?.keyVar || (modal?.querySelector('#new-agent-key-var')?.value || '').trim(),
    role:          (modal?.querySelector('#new-agent-role')?.value    || '').trim(),
    system_prompt:  modal?.querySelector('#new-agent-prompt')?.value  || '',
    enabled: true,
  };

  if (errEl) { errEl.textContent = 'Adding…'; errEl.style.color = 'var(--text-dim)'; }

  fetch('/api/agents/config', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  }).then(r => r.json()).then(data => {
    if (!data.ok) {
      if (errEl) { errEl.textContent = data.error || 'Failed to add agent.'; errEl.style.color = '#ff6b6b'; }
      return;
    }
    // Save key if confirmed
    const saveKey = pending ? fetch(`/api/agents/key/${encodeURIComponent(name)}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key_var: pending.keyVar, value: pending.keyValue})
    }).then(r => r.json()).then(kd => {
      if (!kd.ok) _glitchLog('key-save', `${name}: ${kd.error}`);
    }) : Promise.resolve();

    saveKey.then(() => {
      window.__pendingNewAgentKey = null;
      modal?.remove();
      agentsRefresh().then(() => {
        // Select the new agent so Bootstrap button is visible
        const added = (window.__agentsData || []).find(a => a.name === name);
        if (added) agentsShowDetail(added);
      });
      showToast(`Agent "${payload.label}" added — open it and click Automate to wire it in`, 'success');
    });
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

