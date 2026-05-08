// ═══════════════════════════════════════════════════════════════════════════
// MODEL SELECTION CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════

const _MODEL_OPTIONS = {
  ghost_coder: [
    { value: 'auto',                    label: 'Auto (Anthropic → OpenAI → Grok)' },
    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
    { value: 'claude-opus-4-20250514',   label: 'Claude Opus 4' },
    { value: 'gpt-4.1',                  label: 'GPT-4.1' },
    { value: 'gpt-4o',                   label: 'GPT-4o' },
    { value: 'grok-3',                   label: 'Grok 3' },
  ],
  paid: [
    { value: 'claude-haiku-4-5',         label: 'Claude Haiku 4.5' },
    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
    { value: 'claude-opus-4-20250514',   label: 'Claude Opus 4' },
    { value: 'gpt-4.1',                  label: 'GPT-4.1' },
    { value: 'gpt-4o',                   label: 'GPT-4o' },
    { value: 'grok-3',                   label: 'Grok 3' },
    { value: 'llama-3.3-70b-versatile',  label: 'LLaMA 3.3 70B (Groq)' },
    { value: 'gemini-2.0-flash',         label: 'Gemini 2.0 Flash' },
  ],
};

let _ollamaModelsCache = null;
let _localAiStatusCache = null;
let _localAiStatusCacheTs = 0;

async function _fetchOllamaModelList() {
  if (_ollamaModelsCache) return _ollamaModelsCache;
  try {
    const res = await fetch('/api/localai/status');
    const data = await res.json();
    _ollamaModelsCache = (data.ollama?.models || []).map(m => m.name || m);
  } catch(e) {
    _ollamaModelsCache = [];
  }
  return _ollamaModelsCache;
}

async function _fetchLocalAiStatus(force) {
  const now = Date.now();
  if (!force && _localAiStatusCache && (now - _localAiStatusCacheTs) < 8000) return _localAiStatusCache;
  try {
    const res = await fetch('/api/localai/status');
    const data = await res.json();
    _localAiStatusCache = data;
    _localAiStatusCacheTs = now;
    return data;
  } catch (e) {
    return null;
  }
}

function _buildModelSelect(agentName, agentTier, currentModel) {
  let options = [];
  if (agentName === 'ghost_coder') {
    options = _MODEL_OPTIONS.ghost_coder;
  } else if (['paid', 'free'].includes(agentTier)) {
    options = _MODEL_OPTIONS.paid;
  }
  // Always include current model if not already in list
  if (currentModel && !options.find(o => o.value === currentModel)) {
    options = [{ value: currentModel, label: currentModel + ' (current)' }, ...options];
  }
  if (options.length === 0) return null; // fallback to text input
  return '<select id="agent-model" style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;cursor:pointer;">'
    + options.map(o => `<option value="${_esc(o.value)}" ${o.value === currentModel ? 'selected' : ''}>${_esc(o.label)}</option>`).join('')
    + '</select>';
}

async function _buildLocalModelSelect(currentModel) {
  const models = await _fetchOllamaModelList();
  if (models.length === 0) return null;
  let options = models.map(m => ({ value: m, label: m }));
  if (currentModel && !options.find(o => o.value === currentModel)) {
    options.unshift({ value: currentModel, label: currentModel + ' (current)' });
  }
  return '<select id="agent-model" style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;cursor:pointer;">'
    + options.map(o => `<option value="${_esc(o.value)}" ${o.value === currentModel ? 'selected' : ''}>${_esc(o.label)}</option>`).join('')
    + '</select>';
}

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
  // Inline confirmation — no popup
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
  if (typeof window !== 'undefined' && window.SwarmChat && typeof window.SwarmChat.esc === 'function') {
    return window.SwarmChat.esc(text);
  }
  return String(text || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ═══════════════════════════════════════════════════════════════════════════
// ACCESS TILE — TAB SWITCHING
// ═══════════════════════════════════════════════════════════════════════════

let _accessActiveTab = 'senders';

function accessSwitchTab(tab) {
  _accessActiveTab = tab;
  const sP = document.getElementById('access-panel-senders');
  const uP = document.getElementById('access-panel-users');
  const sT = document.getElementById('access-tab-senders');
  const uT = document.getElementById('access-tab-users');
  const activeS = 'padding:4px 10px;background:var(--accent);color:#fff;border:1px solid var(--accent);border-radius:4px 4px 0 0;font-size:10px;font-weight:600;cursor:pointer;';
  const inactiveS = 'padding:4px 10px;background:var(--card);color:var(--text-dim);border:1px solid var(--border);border-radius:4px 4px 0 0;font-size:10px;font-weight:600;cursor:pointer;';
  if (tab === 'users') {
    if (sP) sP.style.display = 'none';
    if (uP) { uP.style.display = 'flex'; }
    if (sT) sT.style.cssText = inactiveS;
    if (uT) uT.style.cssText = activeS;
    accessLoadUsers();
  } else {
    if (sP) sP.style.display = 'flex';
    if (uP) uP.style.display = 'none';
    if (sT) sT.style.cssText = activeS;
    if (uT) uT.style.cssText = inactiveS;
  }
}

function accessRefreshTab() {
  if (_accessActiveTab === 'users') {
    accessLoadUsers();
  } else {
    loadAccessData(window._accessWin);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// USER MANAGEMENT — CRUD
// ═══════════════════════════════════════════════════════════════════════════

function _utcToLocal(s) {
  if (!s) return '';
  if (/^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}/.test(s) && !/[Z+]/.test(s.slice(-6)))
    s = s.replace(' ', 'T') + 'Z';
  const d = new Date(s);
  return isNaN(d) ? s : d.toLocaleDateString('en-AU', {day:'2-digit',month:'2-digit',year:'numeric'}) + ' ' + d.toLocaleTimeString('en-AU', {hour:'2-digit',minute:'2-digit'});
}

async function accessLoadUsers() {
  const list = document.getElementById('access-users-list');
  if (!list) return;
  list.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">Loading…</div>';
  try {
    const res = await fetch('/api/auth/users');
    const data = await res.json();
    if (!data.ok) { list.innerHTML = `<div style="color:#f77;font-size:12px;">Error: ${_esc(data.error || 'unknown')}</div>`; return; }
    const users = data.users || [];
    if (!users.length) { list.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">No users found.</div>'; return; }
    list.innerHTML = users.map(u => {
      const statusBadge = u.approved
        ? `<span style="color:#4caf50;font-size:10px;font-weight:600;">Active</span>`
        : `<span style="color:#ffa500;font-size:10px;font-weight:600;">Pending</span>`;
      const isOwner = u.username === 'ghost';
      return `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <span style="font-size:13px;font-weight:600;color:var(--text);">${_esc(u.display_name || u.username)}</span>
              ${statusBadge}
              <span style="font-size:10px;color:var(--text-dim);padding:1px 6px;background:var(--bg);border-radius:3px;">${_esc(u.role)}</span>
            </div>
            <div style="font-size:11px;color:var(--text-dim);margin-top:3px;">
              ${u.email ? _esc(u.email) + ' · ' : ''}${_esc(u.username)} · joined ${_utcToLocal(u.created_at)}
            </div>
          </div>
          <div style="display:flex;gap:4px;flex-shrink:0;">
            ${!u.approved ? `<button onclick="accessApproveUser('${_esc(u.username)}')" style="padding:4px 10px;background:#4caf5030;color:#4caf50;border:1px solid #4caf5060;border-radius:4px;font-size:10px;cursor:pointer;font-weight:600;">Approve</button>` : ''}
            ${!isOwner ? `<button onclick="accessEditUser('${_esc(u.username)}','${_esc(u.display_name||'')}','${_esc(u.email||'')}','${_esc(u.role)}')" style="padding:4px 8px;background:var(--bg);color:var(--text-dim);border:1px solid var(--border);border-radius:4px;font-size:10px;cursor:pointer;" title="Edit">✎</button>` : ''}
            ${!isOwner ? `<button onclick="accessResetPw('${_esc(u.username)}')" style="padding:4px 8px;background:var(--bg);color:var(--text-dim);border:1px solid var(--border);border-radius:4px;font-size:10px;cursor:pointer;" title="Reset Password">🔑</button>` : ''}
            ${!isOwner ? `<button onclick="accessDeleteUser('${_esc(u.username)}')" style="padding:4px 8px;background:#f4433620;color:#f44336;border:1px solid #f4433660;border-radius:4px;font-size:10px;cursor:pointer;" title="Delete">✕</button>` : ''}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = `<div style="color:#f77;font-size:12px;">Failed to load users: ${_esc(e.message)}</div>`;
  }
}

async function accessCreateUser() {
  const email = (document.getElementById('access-user-email')?.value || '').trim();
  const name = (document.getElementById('access-user-name')?.value || '').trim();
  const pw = (document.getElementById('access-user-pw')?.value || '').trim();
  const role = document.getElementById('access-user-role')?.value || 'viewer';
  if (!email) { showToast('Email is required', 'error'); return; }
  if (!pw || pw.length < 6) { showToast('Password must be at least 6 characters', 'error'); return; }
  try {
    const res = await fetch('/api/auth/users/create', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ email, display_name: name, password: pw, role })
    });
    const data = await res.json();
    if (data.ok) {
      showToast(`User ${data.display_name} created`, 'success');
      document.getElementById('access-user-email').value = '';
      document.getElementById('access-user-name').value = '';
      document.getElementById('access-user-pw').value = '';
      accessLoadUsers();
    } else {
      showToast(data.error || 'Failed', 'error');
    }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

function accessEditUser(username, currentName, currentEmail, currentRole) {
  const list = document.getElementById('access-users-list');
  if (!list) return;
  // Inline edit panel
  const editId = 'access-edit-' + username;
  const existing = document.getElementById(editId);
  if (existing) { existing.remove(); return; } // toggle off

  // Find the user row and insert edit panel after it
  const rows = list.children;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].innerHTML.includes(username)) {
      const panel = document.createElement('div');
      panel.id = editId;
      panel.style.cssText = 'padding:10px 12px;background:var(--bg);border:1px solid var(--accent);border-radius:6px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;';
      panel.innerHTML = `
        <input type="email" id="${editId}-email" value="${_esc(currentEmail)}" placeholder="Email"
               style="flex:1;min-width:160px;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;">
        <input type="text" id="${editId}-name" value="${_esc(currentName)}" placeholder="Preferred name"
               style="width:130px;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;">
        <select id="${editId}-role" style="padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;">
          <option value="viewer" ${currentRole==='viewer'?'selected':''}>Viewer</option>
          <option value="user" ${currentRole==='user'?'selected':''}>User</option>
          <option value="admin" ${currentRole==='admin'?'selected':''}>Admin</option>
        </select>
        <button onclick="accessSaveEdit('${_esc(username)}','${editId}')" style="padding:6px 12px;background:var(--accent);color:#000;border:none;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;">Save</button>
        <button onclick="document.getElementById('${editId}').remove()" style="padding:6px 8px;background:transparent;color:var(--text-dim);border:1px solid var(--border);border-radius:4px;font-size:11px;cursor:pointer;">Cancel</button>`;
      rows[i].after(panel);
      break;
    }
  }
}

async function accessSaveEdit(username, editId) {
  const email = (document.getElementById(editId + '-email')?.value || '').trim();
  const name = (document.getElementById(editId + '-name')?.value || '').trim();
  const role = document.getElementById(editId + '-role')?.value || '';
  try {
    // Update profile
    const res1 = await fetch(`/api/auth/users/${encodeURIComponent(username)}/edit`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ display_name: name, email })
    });
    const d1 = await res1.json();
    if (!d1.ok) { showToast(d1.error || 'Edit failed', 'error'); return; }
    // Update role
    if (role) {
      await fetch(`/api/auth/users/${encodeURIComponent(username)}/role`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ role })
      });
    }
    showToast('User updated', 'success');
    accessLoadUsers();
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

function accessResetPw(username) {
  const list = document.getElementById('access-users-list');
  if (!list) return;
  const editId = 'access-pw-' + username;
  const existing = document.getElementById(editId);
  if (existing) { existing.remove(); return; }

  const rows = list.children;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].innerHTML.includes(username)) {
      const panel = document.createElement('div');
      panel.id = editId;
      panel.style.cssText = 'padding:10px 12px;background:var(--bg);border:1px solid var(--accent);border-radius:6px;display:flex;gap:8px;align-items:center;';
      panel.innerHTML = `
        <span style="font-size:11px;color:var(--text-dim);">New password for ${_esc(username)}:</span>
        <input type="password" id="${editId}-pw" placeholder="New password (min 6)"
               style="flex:1;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;">
        <button onclick="accessDoResetPw('${_esc(username)}','${editId}')" style="padding:6px 12px;background:var(--accent);color:#000;border:none;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;">Reset</button>
        <button onclick="document.getElementById('${editId}').remove()" style="padding:6px 8px;background:transparent;color:var(--text-dim);border:1px solid var(--border);border-radius:4px;font-size:11px;cursor:pointer;">Cancel</button>`;
      rows[i].after(panel);
      break;
    }
  }
}

async function accessDoResetPw(username, editId) {
  const pw = (document.getElementById(editId + '-pw')?.value || '').trim();
  if (!pw || pw.length < 6) { showToast('Password must be at least 6 characters', 'error'); return; }
  try {
    const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/reset-password`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ password: pw })
    });
    const data = await res.json();
    if (data.ok) {
      showToast(`Password reset for ${username}`, 'success');
      const el = document.getElementById(editId);
      if (el) el.remove();
    } else {
      showToast(data.error || 'Failed', 'error');
    }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

async function accessApproveUser(username) {
  try {
    const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/approve`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) { showToast(`${username} approved`, 'success'); accessLoadUsers(); }
    else { showToast(data.error || 'Failed', 'error'); }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

async function accessDeleteUser(username) {
  // Inline confirmation instead of confirm()
  const list = document.getElementById('access-users-list');
  if (!list) return;
  const cId = 'access-del-' + username;
  const existing = document.getElementById(cId);
  if (existing) { existing.remove(); return; }

  const rows = list.children;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].innerHTML.includes(username)) {
      const panel = document.createElement('div');
      panel.id = cId;
      panel.style.cssText = 'padding:8px 12px;background:#f4433615;border:1px solid #f4433660;border-radius:6px;display:flex;gap:8px;align-items:center;';
      panel.innerHTML = `
        <span style="font-size:11px;color:#f44336;">Delete ${_esc(username)} permanently?</span>
        <button onclick="accessDoDelete('${_esc(username)}')" style="padding:4px 12px;background:#f44336;color:#fff;border:none;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;">Yes, delete</button>
        <button onclick="document.getElementById('${cId}').remove()" style="padding:4px 8px;background:transparent;color:var(--text-dim);border:1px solid var(--border);border-radius:4px;font-size:11px;cursor:pointer;">Cancel</button>`;
      rows[i].after(panel);
      break;
    }
  }
}

async function accessDoDelete(username) {
  try {
    const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/delete`, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) { showToast(`${username} deleted`, 'success'); accessLoadUsers(); }
    else { showToast(data.error || 'Failed', 'error'); }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
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
    fetch('/api/agents/config').then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
    fetch('/api/swarm/globals').then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
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
  // Slice 5e: filter input + tier-grouped rows for faster scanning.
  const groups = { human: [], local: [], service: [], api: [] };
  agents.forEach(a => {
    const isLocal = a.tier === 'local' || a.tier === 'human';
    const isService = a.tier === 'service';
    const key = a.tier === 'human' ? 'human' : (isService ? 'service' : (isLocal ? 'local' : 'api'));
    (groups[key] || groups.api).push(a);
  });
  const renderRow = (a) => {
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
      ? '<span style="color:#ef4444;font-size:10px;line-height:1;" title="Offline: re-enable from Agents tile">●</span>'
      : '<span style="color:#4caf50;font-size:10px;line-height:1;">●</span>';
    const dcomBadge = isDecommissioned
      ? '<span style="background:#3a1010;color:#ff8a8a;border-radius:3px;padding:1px 5px;font-size:9px;font-weight:700;">OFFLINE</span>'
      : '';
    const filterBlob = `${a.name||''} ${a.label||''} ${a.model||''} ${tierLabel}`.toLowerCase();
    return `<div class="agents-list-row" data-name="${_esc(a.name)}" data-filter="${_esc(filterBlob)}"
      style="padding:10px 14px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:3px;transition:background 0.12s;${isDecommissioned ? 'opacity:0.6;' : ''}">
      <div style="display:flex;align-items:center;gap:6px;">
        ${statusDot}
        <span style="font-size:12px;font-weight:700;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(a.label || a.name)}</span>
        ${dcomBadge}${tierBadge}
      </div>
      <div style="font-size:10px;color:var(--text-dim);padding-left:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(a.model || '')}</div>
    </div>`;
  };
  const groupBlock = (label, list) => {
    if (!list.length) return '';
    return `<div class="agents-group" data-group="${_esc(label)}">
      <div class="agents-group-head" style="position:sticky;top:0;background:var(--window-header);padding:5px 14px;font-size:9.5px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--border);z-index:1;">${_esc(label)} <span style="opacity:.7;">(${list.length})</span></div>
      ${list.map(renderRow).join('')}
    </div>`;
  };
  const filterHtml = `<div style="position:sticky;top:0;background:var(--window-header);padding:8px 12px;border-bottom:1px solid var(--border);z-index:2;">
    <input type="text" id="agents-list-filter" placeholder="Filter agents…" style="width:100%;background:var(--card);border:1px solid var(--border);border-radius:4px;padding:5px 8px;color:var(--text);font-size:11px;font-family:inherit;outline:none;">
  </div>`;
  el.innerHTML = filterHtml + groupBlock('Human', groups.human) + groupBlock('Local', groups.local) + groupBlock('Service', groups.service) + groupBlock('API', groups.api);
  // Filter wiring.
  const flt = document.getElementById('agents-list-filter');
  if (flt) {
    flt.addEventListener('input', () => {
      const q = flt.value.trim().toLowerCase();
      el.querySelectorAll('.agents-list-row').forEach(r => {
        r.style.display = (!q || (r.dataset.filter || '').includes(q)) ? '' : 'none';
      });
      // Hide group headers whose rows are all hidden.
      el.querySelectorAll('.agents-group').forEach(g => {
        const rows = g.querySelectorAll('.agents-list-row');
        const visible = Array.from(rows).some(r => r.style.display !== 'none');
        g.style.display = visible ? '' : 'none';
      });
    });
  }
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

  // Build model dropdown or text input
  const currentModel = agent.model || '';
  let modelHtml;
  if (isLocal && agent.tier !== 'human') {
    // For local agents, we'll inject the dropdown async after render
    modelHtml = `<select id="agent-model" style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;cursor:pointer;">
      <option value="${_esc(currentModel)}" selected>${_esc(currentModel || 'Loading…')}</option>
    </select>`;
  } else {
    const selectHtml = _buildModelSelect(agent.name, agent.tier, currentModel);
    modelHtml = selectHtml || `<input id="agent-model" type="text" value="${_esc(currentModel)}"
      style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">`;
  }
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
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Number / Slot</label>
          <select id="agent-number" style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;cursor:pointer;box-sizing:border-box;">
            ${(() => {
              // P4-M27: dropdown of all known slots (0..22) with current occupant shown
              const cur = Number.isFinite(Number(agent.number)) ? Number(agent.number) : -1;
              const occupants = {};
              (window.__agentsData || []).forEach(a => { if (Number.isFinite(Number(a.number))) occupants[Number(a.number)] = a.label || a.name; });
              const opts = [];
              for (let n = 0; n <= 22; n++) {
                const occ = occupants[n];
                const isMine = (n === cur);
                const taken = (!!occ && !isMine);
                const label = isMine ? `${n} — ${agent.label || agent.name} (current)`
                            : taken ? `${n} — ${occ} (taken)`
                            : `${n} — empty`;
                opts.push(`<option value="${n}" ${isMine ? 'selected' : ''} ${taken ? 'disabled' : ''}>${_esc(label)}</option>`);
              }
              return opts.join('');
            })()}
          </select>
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Label</label>
          <input id="agent-label" type="text" value="${_esc(agent.label || '')}"
            style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Model</label>
          ${modelHtml}
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
        ${isLocal && agent.tier !== 'human' ? `
        <div id="agent-local-status" style="grid-column:span 2;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);font-size:11px;color:var(--text-dim);">Checking local runtime availability...</div>
        ` : ''}
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Chat ETA / Timer (sec)</label>
          <input id="agent-eta-seconds" type="number" min="0" max="2000" value="${Number.isFinite(Number(agent.eta_seconds)) ? Number(agent.eta_seconds) : 60}"
            style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Keep-Warm (sec)</label>
          <input id="agent-keepalive-config" type="number" min="0" max="86400" value="${Number.isFinite(Number(agent.keep_alive)) ? Number(agent.keep_alive) : 300}"
            style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
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
        <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Slot Role <span style="color:var(--text-dim);text-transform:none;font-weight:400;letter-spacing:0;">— hardcoded by slot number, not editable</span></label>
        <div id="agent-slot-role-readout" style="padding:6px 9px;background:color-mix(in srgb,var(--accent) 4%,var(--card));border:1px dashed var(--border);border-radius:5px;color:var(--text);font-size:12px;font-weight:600;">${(() => {
          // P4-M28: hardcoded role per slot — must match utils/config.py + DB roster
          const SLOT_ROLES = {
            0: 'Ghost — Human operator',
            1: 'Generalist + decision maker',
            2: 'Researcher (web)',
            3: 'Quick coder',
            4: 'Deep analyst',
            5: 'Vortex — gatekeeper / time wizard',
            6: 'Sanity checker',
            7: 'Personal companion (Seven)',
            8: 'SAP HCM/Payroll specialist (Gemma4)',
            9: 'Developer Agent — system architect',
            10: 'Developer Agent — software engineer',
            11: 'Short and honest (Grok)',
            12: 'Developer Agent — Claude / continuity',
            13: 'Developer Agent — HuggingFace',
            14: 'Research · Gemini',
            15: 'Internet Search · Tavily',
            16: 'Web Search · DuckDuckGo',
            17: 'Developer Agent — Ghost Coder',
            19: 'Developer Agent — o4-mini',
            20: 'Big coder (Qwen3.6)',
            21: 'Inspector — memory auditor (DeepSeek)',
            22: 'Reserved'
          };
          const n = Number.isFinite(Number(agent.number)) ? Number(agent.number) : -1;
          return _esc(SLOT_ROLES[n] || 'Unassigned slot');
        })()}</div>
      </div>

      <div style="margin-bottom:14px;">
        <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Description <span style="color:var(--text-dim);text-transform:none;font-weight:400;letter-spacing:0;">— editable, shown in lists and tooltips</span></label>
        <input id="agent-role" type="text" value="${_esc(agent.role || '')}" placeholder="Short description of this agent's role"
          style="width:100%;padding:6px 9px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none;box-sizing:border-box;">
      </div>

      <!-- V8 S-FAFF08FF9A: per-agent temperature gauge moved here from Chat right-menu.
           Chat retains a quick slider for live tuning, but Agents detail is now the
           canonical edit surface. Posts to /api/agents/<name>/temperature. -->
      <div id="agent-temp-block" style="margin-bottom:14px;padding:10px 12px;border:1px solid var(--border);border-radius:6px;background:color-mix(in srgb,var(--accent) 3%,var(--card));">
        <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:6px;">Temperature <span style="color:var(--text-dim);text-transform:none;font-weight:400;letter-spacing:0;">— response variability (0 = deterministic, 1 = creative)</span></label>
        <div style="display:flex;gap:10px;align-items:center;">
          <input id="agent-temperature" type="range" min="0" max="1" step="0.05"
            value="${Number.isFinite(Number(agent.temperature)) ? Number(agent.temperature).toFixed(2) : '0.70'}"
            oninput="document.getElementById('agent-temperature-readout').textContent=Number(this.value).toFixed(2)"
            style="flex:1;accent-color:var(--accent);cursor:pointer;">
          <span id="agent-temperature-readout" style="font-family:monospace;font-size:12px;color:var(--text);min-width:42px;text-align:right;">${Number.isFinite(Number(agent.temperature)) ? Number(agent.temperature).toFixed(2) : '0.70'}</span>
          <button id="agent-temperature-apply" type="button"
            onclick="(function(){var v=parseFloat(document.getElementById('agent-temperature').value);fetch('/api/agents/'+encodeURIComponent('${_esc(agent.name)}')+'/temperature',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({temperature:v})}).then(function(r){return r.json();}).then(function(){window.__agentTemps=window.__agentTemps||{};window.__agentTemps['${_esc(agent.name)}'.toLowerCase()]=v;if(typeof renderChatAgentToggles==='function')renderChatAgentToggles();var st=document.getElementById('agent-temperature-status');if(st)st.textContent='Saved at '+new Date().toLocaleTimeString();}).catch(function(){var st=document.getElementById('agent-temperature-status');if(st)st.textContent='Save failed';});})()"
            style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:5px 10px;cursor:pointer;font-size:11px;white-space:nowrap;">Apply</button>
        </div>
        <div id="agent-temperature-status" style="font-size:10px;color:var(--text-dim);margin-top:4px;min-height:12px;"></div>
      </div>

      <div style="margin-bottom:18px;">
        <label style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">System Prompt</label>
        <textarea id="agent-prompt" rows="10"
          style="width:100%;padding:8px 10px;background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:11px;font-family:monospace;outline:none;resize:vertical;box-sizing:border-box;">${_esc(agent.system_prompt || '')}</textarea>
      </div>

      ${isLocal && agent.tier !== 'human' ? `
      <!-- M10: runtime controls for local agents -->
      <div style="margin-bottom:14px;padding:10px 12px;border:1px solid var(--border);border-radius:6px;background:color-mix(in srgb,var(--accent) 3%,var(--card));">
        <div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Runtime Controls</div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:11px;">
          <label style="display:flex;align-items:center;gap:4px;">Keep-warm (sec)
            <input id="agent-keepalive-seconds" type="number" min="0" max="86400" value="${Number.isFinite(Number(agent.keep_alive)) ? Number(agent.keep_alive) : 300}"
              style="width:80px;padding:4px 6px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;box-sizing:border-box;">
          </label>
          <button id="agent-keepalive-apply" type="button"
            style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:5px 10px;cursor:pointer;font-size:11px;">Apply</button>
          <button id="agent-unload-btn" type="button"
            style="background:transparent;border:1px solid #f7b84b66;color:#f7b84b;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:11px;">Unload</button>
          <button id="agent-hard-kill-btn" type="button" title="Unload immediately (keep_alive=0)"
            style="background:transparent;border:1px solid #f4433666;color:#f77;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:11px;">Hard-Kill</button>
          <div id="agent-runtime-status" style="font-size:11px;color:var(--text-dim);"></div>
        </div>
      </div>` : ''}

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
        <div style="flex:1;"></div>        ${agent.enabled == 0 ? `
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
  // M10: runtime controls for local agents
  const keepaliveBtn = el.querySelector('#agent-keepalive-apply');
  if (keepaliveBtn) {
    keepaliveBtn.addEventListener('click', async () => {
      const input = el.querySelector('#agent-keepalive-seconds');
      const statusEl = el.querySelector('#agent-runtime-status');
      const seconds = Math.max(0, Math.min(86400, parseInt(input?.value || '300', 10) || 300));
      if (statusEl) statusEl.textContent = 'Applying…';
      try {
        const r = await fetch('/api/ollama/keepalive', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ model: agent.model || '', seconds }) });
        const j = await r.json();
        if (statusEl) statusEl.textContent = j.ok ? `Keep-alive set to ${seconds}s` : `Error: ${j.error || 'unknown'}`;
      } catch (err) {
        if (statusEl) statusEl.textContent = `Error: ${err.message}`;
      }
    });
  }
  const unloadBtn = el.querySelector('#agent-unload-btn');
  if (unloadBtn) {
    unloadBtn.addEventListener('click', async () => {
      const statusEl = el.querySelector('#agent-runtime-status');
      if (statusEl) statusEl.textContent = 'Unloading…';
      try {
        const r = await fetch('/api/ollama/unload', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ model: agent.model || '' }) });
        const j = await r.json();
        if (statusEl) statusEl.textContent = j.ok ? `Unloaded ${agent.model}` : `Error: ${j.error || 'unknown'}`;
      } catch (err) {
        if (statusEl) statusEl.textContent = `Error: ${err.message}`;
      }
    });
  }
  const hardKillBtn = el.querySelector('#agent-hard-kill-btn');
  if (hardKillBtn) {
    hardKillBtn.addEventListener('click', async () => {
      const statusEl = el.querySelector('#agent-runtime-status');
      if (!confirm(`Hard-kill ${agent.model}? This will forcibly unload the model from RAM.`)) return;
      if (statusEl) statusEl.textContent = 'Hard-killing…';
      try {
        const r = await fetch('/api/ollama/unload', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ model: agent.model || '' }) });
        const j = await r.json();
        if (statusEl) statusEl.textContent = j.ok ? `✓ ${agent.model} killed` : `Error: ${j.error || 'unknown'}`;
      } catch (err) {
        if (statusEl) statusEl.textContent = `Error: ${err.message}`;
      }
    });
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

  // Async: populate local agent model dropdown with Ollama models
  if (isLocal && agent.tier !== 'human') {
    _buildLocalModelSelect(currentModel).then(selectHtml => {
      if (selectHtml) {
        const modelContainer = el.querySelector('#agent-model')?.parentElement;
        if (modelContainer) {
          const labelEl = modelContainer.querySelector('label');
          modelContainer.innerHTML = '';
          if (labelEl) modelContainer.appendChild(labelEl);
          modelContainer.insertAdjacentHTML('beforeend', selectHtml);
        }
      }
    });
    _renderLocalAgentAvailability(agent);
  }
}

async function _renderLocalAgentAvailability(agent) {
  const statusEl = document.getElementById('agent-local-status');
  if (!statusEl || !agent) return;

  const status = await _fetchLocalAiStatus(false);
  if (!status) {
    statusEl.style.borderColor = '#f59e0b55';
    statusEl.innerHTML = `
      <div style="color:#f59e0b;font-weight:600;">Could not verify local runtime status.</div>
      <div style="margin-top:4px;">Open Local AI to inspect Ollama and LM Studio manually.</div>
      <div style="margin-top:8px;"><button onclick="openWindow('localai','Local AI','view-localai')" style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:5px 10px;cursor:pointer;font-size:11px;">Open Local AI</button></div>`;
    return;
  }

  const ollamaRunning = !!status.ollama?.running;
  const installed = (status.ollama?.models || []).map(m => (m.name || m).toLowerCase());
  const model = String(agent.model || '').toLowerCase();
  const modelInstalled = installed.some(name => name === model || name.startsWith(model) || model.startsWith(name));

  if (!ollamaRunning) {
    statusEl.style.borderColor = '#ef444455';
    statusEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="width:8px;height:8px;border-radius:50%;background:#ef4444;flex-shrink:0;"></span>
        <span style="color:#ef4444;font-weight:600;font-size:12px;">Ollama offline</span>
        <button onclick="openWindow('localai','Local AI','view-localai')" style="margin-left:auto;background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 8px;cursor:pointer;font-size:10.5px;">Local AI →</button>
      </div>`;
    return;
  }

  if (!modelInstalled) {
    statusEl.style.borderColor = '#ef444455';
    statusEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="width:8px;height:8px;border-radius:50%;background:#ef4444;flex-shrink:0;"></span>
        <span style="color:#ef4444;font-weight:600;font-size:12px;">Model not installed</span>
        <span style="color:var(--text-dim);font-size:11px;">${_esc(agent.model || 'unknown')}</span>
        <button onclick="openWindow('localai','Local AI','view-localai')" style="margin-left:auto;background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 8px;cursor:pointer;font-size:10.5px;">Local AI →</button>
      </div>`;
    return;
  }

  statusEl.style.borderColor = '#22c55e55';
  statusEl.innerHTML = `<div style="display:flex;align-items:center;gap:8px;"><span style="width:8px;height:8px;border-radius:50%;background:#22c55e;flex-shrink:0;"></span><span style="color:#22c55e;font-weight:600;font-size:12px;">Local runtime ready</span><span style="color:var(--text-dim);font-size:11px;">Ollama running · model installed</span></div>`;
}

function agentsSave(name) {
  const statusEl = document.getElementById('agent-save-status');
  if (statusEl) { statusEl.textContent = 'Saving…'; statusEl.style.color = 'var(--text-dim)'; }
  const payload = {
    number:        Number(document.getElementById('agent-number')?.value || 0),
    label:         document.getElementById('agent-label')?.value    || '',
    model:         document.getElementById('agent-model')?.value    || '',
    tier:          document.getElementById('agent-tier')?.value     || 'local',
    api_key_var:   document.getElementById('agent-key-var')?.value  || '',
    role:          document.getElementById('agent-role')?.value     || '',
    system_prompt: document.getElementById('agent-prompt')?.value   || '',
    enabled:       document.getElementById('agent-enabled')?.checked !== false,
    eta_seconds:   Number(document.getElementById('agent-eta-seconds')?.value || 60),
    keep_alive:    Number(document.getElementById('agent-keepalive-config')?.value || 300),
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
        // Propagate model/label changes to chat agent registry
        if (typeof _loadAgentRegistry === 'function') _loadAgentRegistry();
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
    // Propagate model/label changes to chat agent registry
    if (typeof _loadAgentRegistry === 'function') _loadAgentRegistry();
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

// ── Agents tab switching (Agents / Local AI) ──────────────────────────────
function agentsSwitchTab(tab) {
  const agentsBody  = document.getElementById('agents-agents-body');
  const localaiBody = document.getElementById('agents-localai-body');
  const tabAgents   = document.getElementById('agents-tab-agents');
  const tabLocalai  = document.getElementById('agents-tab-localai');
  if (!agentsBody || !localaiBody) return;

  const isAgents = (tab === 'agents');
  agentsBody.style.display  = isAgents ? 'flex'  : 'none';
  localaiBody.style.display = isAgents ? 'none'  : 'block';

  if (tabAgents) {
    tabAgents.style.borderBottomColor = isAgents ? 'var(--accent)' : 'transparent';
    tabAgents.style.color             = isAgents ? 'var(--text)'   : 'var(--text-dim)';
    tabAgents.style.fontWeight        = isAgents ? '600'           : '400';
  }
  if (tabLocalai) {
    tabLocalai.style.borderBottomColor = isAgents ? 'transparent'   : 'var(--accent)';
    tabLocalai.style.color             = isAgents ? 'var(--text-dim)' : 'var(--text)';
    tabLocalai.style.fontWeight        = isAgents ? '400'           : '600';
  }

  if (!isAgents) agentsLocalAIRefresh();
}

function agentsLocalAIRefresh() {
  const ollamaBadge  = document.getElementById('agents-ollama-badge');
  const lmsBadge     = document.getElementById('agents-lmstudio-badge');
  const picoBadge    = document.getElementById('agents-picoclaw-badge');
  const ollamaModels = document.getElementById('agents-ollama-models');
  const lmsInfo      = document.getElementById('agents-lmstudio-info');

  if (ollamaBadge) ollamaBadge.textContent = 'checking…';

  const _b = (running) => ({
    background: running
      ? 'color-mix(in srgb,#22c55e 15%,var(--card))'
      : 'color-mix(in srgb,#ef4444 15%,var(--card))',
    color:  running ? '#22c55e' : '#ef4444',
    border: `1px solid ${running ? '#22c55e55' : '#ef444455'}`,
  });

  fetch('/api/localai/status')
    .then(r => r.json())
    .then(data => {
      const _light = (id, ok) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.style.background = ok ? '#22c55e' : '#ef4444';
        el.style.boxShadow = `0 0 0 2px ${ok ? '#22c55e22' : '#ef444422'}, 0 0 6px ${ok ? '#22c55e' : '#ef4444'}`;
        el.title = ok ? 'online' : 'offline · red light';
      };
      _light('agents-ollama-light',   !!data.ollama?.running);
      _light('agents-lmstudio-light', !!data.lmstudio?.running);
      _light('agents-picoclaw-light', !!data.picoclaw?.running);
      if (ollamaBadge) {
        const ok  = data.ollama?.running;
        const cnt = (data.ollama?.models || []).length;
        ollamaBadge.textContent = ok ? `${cnt} model${cnt !== 1 ? 's' : ''}` : 'offline';
        Object.assign(ollamaBadge.style, _b(ok));
      }
      if (lmsBadge) {
        const ok = data.lmstudio?.running;
        lmsBadge.textContent = ok ? 'online' : 'offline';
        Object.assign(lmsBadge.style, _b(ok));
      }
      if (picoBadge) {
        const ok = data.picoclaw?.running;
        picoBadge.textContent = ok ? 'running' : 'offline';
        Object.assign(picoBadge.style, _b(ok));
      }
      if (ollamaModels) {
        const ms = data.ollama?.models || [];
        ollamaModels.innerHTML = ms.length
          ? ms.map(m => `<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 7px;border-radius:4px;background:var(--bg);border:1px solid var(--border);font-size:11px;">${_esc(m.name || m)}</span>`).join('')
          : (data.ollama?.running ? 'No models loaded' : 'Ollama not running');
      }
      if (lmsInfo) {
        lmsInfo.textContent = data.lmstudio?.running
          ? `Loaded: ${data.lmstudio.loaded || 'unknown'}`
          : 'Not running';
      }
    })
    .catch(() => {
      if (ollamaBadge) { ollamaBadge.textContent = 'error'; ollamaBadge.style.color = 'var(--danger,#ff6b6b)'; }
    });

  // Runtime gateway health badge + warnings (Fridays runtime snapshot).
  if (typeof localaiRuntimeHealthRefresh === 'function') {
    localaiRuntimeHealthRefresh('agents-ollama-runtime', 'agents-ollama-warnings');
  }

  // STEP-AGENTS-TILE-UX-OPERATIONS-20260430 — refresh disabled-agents panel
  agentsRefreshDisabledPanel();
}

// ── STEP-AGENTS-TILE-UX-OPERATIONS-20260430 ─────────────────────────────
// Per-runner controls + disabled-agents quick re-enable panel.

function agentsCopyCmd(_id, cmd) {
  if (!cmd) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cmd).then(() => {
      if (typeof showToast === 'function') showToast('Command copied to clipboard', 'success');
    }).catch(() => {
      if (typeof showToast === 'function') showToast('Clipboard blocked — see browser permissions', 'error');
    });
  } else {
    const ta = document.createElement('textarea');
    ta.value = cmd; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); if (typeof showToast === 'function') showToast('Command copied', 'success'); } catch (_) {}
    document.body.removeChild(ta);
  }
}

function agentsOpenLogs(runner) {
  // Prefer opening the Logs tile if present, otherwise fall back to a
  // toast that points the user at the journal command.
  try {
    if (typeof openWindow === 'function') {
      openWindow('logs-' + runner, 'Logs · ' + runner, 'view-logs');
      return;
    }
  } catch (_) {}
  const cmd = (runner === 'ollama') ? 'journalctl -u ollama -f -n 200'
             : (runner === 'lmstudio') ? 'tail -f ~/.cache/lm-studio/server.log'
             : 'journalctl -u picoclaw -f -n 200';
  agentsCopyCmd(runner + '-logs', cmd);
}

function agentsOllamaPullPrompt() {
  const tag = (typeof prompt === 'function') ? prompt('Model tag to pull (e.g. gemma3:4b)', 'gemma3:4b') : '';
  if (!tag) return;
  const safe = String(tag).replace(/[^a-zA-Z0-9._:\/-]/g, '');
  if (!safe) return;
  agentsCopyCmd('ollama-pull', `ollama pull ${safe}`);
}

function agentsRefreshDisabledPanel() {
  const list = document.getElementById('agents-disabled-list');
  const count = document.getElementById('agents-disabled-count');
  if (!list) return;
  fetch('/api/agents').then(r => r.json()).then(d => {
    const arr = (d && Array.isArray(d.agents)) ? d.agents : (Array.isArray(d) ? d : []);
    const disabled = arr.filter(a => a && a.enabled === 0);
    if (count) count.textContent = String(disabled.length);
    if (!disabled.length) {
      list.innerHTML = '<div style="opacity:0.6;">No disabled agents.</div>';
      return;
    }
    list.innerHTML = disabled.map(a => {
      const safe = _esc(a.name || '');
      const label = _esc(a.label || a.name || '');
      const role = _esc(a.role || '');
      return `
        <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);">
          <span style="width:6px;height:6px;border-radius:99px;background:#ef4444;box-shadow:0 0 4px #ef4444;"></span>
          <span style="font-weight:600;color:var(--text);">${label}</span>
          <span style="font-size:10px;opacity:0.6;">${role}</span>
          <button onclick="agentsReEnable('${safe}')" style="margin-left:auto;background:var(--accent);border:none;color:#000;border-radius:4px;padding:2px 9px;font-size:10px;font-weight:700;cursor:pointer;">↻ Re-enable</button>
        </div>`;
    }).join('');
  }).catch(() => {
    list.innerHTML = '<div style="color:#ef4444;">Could not load agents.</div>';
  });
}

function agentsReEnable(name) {
  if (!name) return;
  fetch(`/api/agents/${encodeURIComponent(name)}/toggle`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: true }),
  }).then(r => r.json()).then(() => {
    if (typeof showToast === 'function') showToast(`${name} re-enabled`, 'success');
    agentsRefreshDisabledPanel();
    if (typeof agentsRefresh === 'function') agentsRefresh();
  }).catch(() => {
    if (typeof showToast === 'function') showToast('Re-enable failed', 'error');
  });
}

window.agentsCopyCmd = agentsCopyCmd;
window.agentsOpenLogs = agentsOpenLogs;
window.agentsOllamaPullPrompt = agentsOllamaPullPrompt;
window.agentsRefreshDisabledPanel = agentsRefreshDisabledPanel;
window.agentsReEnable = agentsReEnable;
