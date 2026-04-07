// agents-config.js — Agents config view logic
// Handles agent enable/disable toggling, add modal, and detail panel

const _agentsInputStyle = 'width:100%;background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:6px 9px;font-size:12px;outline:none;box-sizing:border-box;';
const _agentsBtnStyle = 'border:1px solid var(--border);border-radius:4px;padding:5px 14px;cursor:pointer;font-size:11px;font-weight:600;';

async function agentsRefresh() {
  const listEl = document.getElementById('agents-list');
  if (!listEl) return;
  listEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-dim);">Loading...</div>';
  const res = await fetch('/api/agents/config');
  const agents = await res.json();
  window._agentsConfig = agents;
  listEl.innerHTML = agents.map(a => {
    // Online/offline indicator: green if enabled, red if not
    const statusDot = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;vertical-align:middle;background:${a.enabled ? '#4caf50' : '#f44336'};box-shadow:0 0 0 1.5px var(--window-header);"></span>`;
    return `
      <div class="agent-list-item" style="display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.18s;" onclick="agentsShowDetail('${a.name}')">
        ${statusDot}
        <span style="flex:1;font-size:13px;font-weight:600;letter-spacing:0.1px;">${_escHtmlA(a.label || a.name)}</span>
        <span style="color:var(--text-dim);font-size:11px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtmlA(a.model)}</span>
      </div>`;
  }).join('');
}

function _escHtmlA(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function agentsToggleEnabled(name, enabled) {
  await fetch(`/api/agents/config/${name}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled: !!enabled})
  });
  agentsRefresh();
  if (window.memoryRefresh) window.memoryRefresh();
  if (window.chatRefresh) window.chatRefresh();
}

function agentsShowDetail(name) {
  const agent = (window._agentsConfig || []).find(a => a.name === name);
  const detailEl = document.getElementById('agents-detail');
  if (!agent || !detailEl) return;

  // Fetch real skills for this agent
  const [allSkills, agentSkills] = await Promise.all([
    fetchAllSkills(),
    fetchAgentSkills(name)
  ]);
  const agentSkillNames = new Set((agentSkills || []).map(s => s.name));

  const isHuman = agent.tier === 'human';
  const apiKeySection = agent.api_key_var ? `
    <div style="margin-bottom:12px;">
      <div style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">API Key</div>
      <div style="display:flex;gap:6px;align-items:center;">
        <input id="agent-key-input-${name}" type="password" placeholder="${agent.api_key_set ? '••••••••• (already set)' : 'Paste key here'}"
               style="${_agentsInputStyle}font-family:monospace;">
        <button onclick="agentsSaveKey('${name}','${agent.api_key_var}')"
                style="${_agentsBtnStyle}background:var(--accent);color:#000;border-color:transparent;">Save</button>
      </div>
      <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">Env var: <code>${_escHtmlA(agent.api_key_var)}</code> · Status: ${agent.api_key_set ? '<span style="color:#4caf50;">✓ set</span>' : '<span style="color:#f44336;">✗ missing</span>'}</div>
    </div>` : '';

  const _PROTECTED = ['gemma','llama','mistral','qwen','eight','nine','ten','eleven','twelve','ghost','librarian','duck','sniffles'];
  const isProtected = _PROTECTED.includes(name);

  // Responsive, modern layout
  // Example role lists (to be replaced with backend-driven list)
  const SAP_ROLES = [
    'SAP HCM Specialist', 'SAP Payroll Expert', 'SAP ABAP Developer', 'SAP Time Management', 'SAP EC/ECP Consultant',
    'SAP Schema Designer', 'SAP PCR Author', 'SAP Integration Lead', 'SAP Security Analyst', 'SAP Data Migration'
  ];
  const SYSTEM_ROLES = [
    'Program Manager', 'System Architect', 'AI Researcher', 'AI Developer', 'Memory Auditor',
    'Sanity Checker', 'Orchestrator', 'Researcher', 'Analyst', 'Generalist'
  ];
  // Merge and deduplicate
  let allRoles = Array.from(new Set([...SAP_ROLES, ...SYSTEM_ROLES]));
  if (window._customRoles) allRoles = Array.from(new Set([...allRoles, ...window._customRoles]));

  // Roles as chips/tags, multi-select
  let agentRoles = Array.isArray(agent.roles) ? agent.roles : (agent.role ? [agent.role] : []);
  // Fallback: if roles not array, try splitting by comma
  if (!Array.isArray(agentRoles)) agentRoles = String(agentRoles || '').split(',').map(r => r.trim()).filter(Boolean);
  // Example role lists (to be replaced with backend-driven list)
  const SAP_ROLES = [
    'SAP HCM Specialist', 'SAP Payroll Expert', 'SAP ABAP Developer', 'SAP Time Management', 'SAP EC/ECP Consultant',
    'SAP Schema Designer', 'SAP PCR Author', 'SAP Integration Lead', 'SAP Security Analyst', 'SAP Data Migration'
  ];
  const SYSTEM_ROLES = [
    'Program Manager', 'System Architect', 'AI Researcher', 'AI Developer', 'Memory Auditor',
    'Sanity Checker', 'Orchestrator', 'Researcher', 'Analyst', 'Generalist'
  ];
  let allRoles = Array.from(new Set([...SAP_ROLES, ...SYSTEM_ROLES]));
  if (window._customRoles) allRoles = Array.from(new Set([...allRoles, ...window._customRoles]));

  // Example role-skill mapping (to be replaced with backend-driven mapping)
  const ROLE_SKILLS = {
    'SAP HCM Specialist': ['Payroll', 'HCM', 'SAP Core'],
    'SAP Payroll Expert': ['Payroll', 'Wage Types'],
    'SAP ABAP Developer': ['ABAP', 'Coding'],
    'SAP Time Management': ['Time Eval', 'Absence Mgmt'],
    'SAP EC/ECP Consultant': ['EC/ECP', 'Integration'],
    'SAP Schema Designer': ['Schema', 'PCR'],
    'SAP PCR Author': ['PCR'],
    'SAP Integration Lead': ['Integration'],
    'SAP Security Analyst': ['Security'],
    'SAP Data Migration': ['Data Migration'],
    'Program Manager': ['Project Mgmt'],
    'System Architect': ['Architecture'],
    'AI Researcher': ['AI', 'Research'],
    'AI Developer': ['AI', 'Coding'],
    'Memory Auditor': ['Memory Audit'],
    'Sanity Checker': ['Sanity Check'],
    'Orchestrator': ['Orchestration'],
    'Researcher': ['Research'],
    'Analyst': ['Analysis'],
    'Generalist': ['General'],
  };
  // Default/basic skills
  const DEFAULT_SKILLS = ['Basic Agent'];
  // Compute agent skills from roles
  let agentSkills = new Set(DEFAULT_SKILLS);
  agentRoles.forEach(role => {
    (ROLE_SKILLS[role] || []).forEach(skill => agentSkills.add(skill));
  });

  detailEl.innerHTML = `
    <div style="padding:32px 5vw 32px 5vw;max-width:900px;margin:auto;display:flex;flex-direction:column;gap:24px;min-height:60vh;">
      <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:14px;">
          <span style="display:inline-block;width:16px;height:16px;border-radius:50%;background:${agent.enabled ? '#4caf50' : '#f44336'};box-shadow:0 0 0 2px var(--window-header);"></span>
          <input id="agent-name-input-${name}" value="${_escHtmlA(agent.name)}" style="${_agentsInputStyle}width:120px;font-weight:700;font-size:1.1em;background:var(--card-dim);color:var(--text-dim);" placeholder="Name" readonly>
          <input id="agent-label-input-${name}" value="${_escHtmlA(agent.label || '')}" style="${_agentsInputStyle}width:180px;font-size:1.1em;" placeholder="Label">
        </div>
        ${isHuman ? '' : `<div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button onclick="agentsConfirmToggle('${name}', ${agent.enabled})" style="padding:7px 22px;border-radius:6px;border:1.5px solid ${agent.enabled ? '#f4433655' : 'var(--border)'};background:${agent.enabled ? 'transparent' : 'var(--accent)'};color:${agent.enabled ? '#f44336' : '#000'};font-size:13px;font-weight:600;">${agent.enabled ? 'Deactivate' : 'Reactivate'}</button>
          <button onclick="agentsConfirmReset('${name}')" style="padding:7px 22px;border-radius:6px;border:1.5px solid var(--border);background:var(--card);color:var(--text);font-size:13px;font-weight:600;">↺ Reset</button>
          ${!isProtected ? `<button onclick="agentsConfirmDelete('${name}')" style="padding:7px 22px;border-radius:6px;border:1.5px solid #f4433655;background:transparent;color:#f44336;font-size:13px;font-weight:600;">✕ Delete</button>` : ''}
          <div style="display:flex;align-items:center;gap:6px;margin-left:18px;">
            <input id="agent-temp-input-${name}" type="number" min="0" max="2" step="0.01" value="${agent.temperature != null ? agent.temperature : ''}" style="${_agentsInputStyle}width:70px;max-width:90px;display:inline-block;">
            <button onclick="agentsSaveTemp('${name}')" style="${_agentsBtnStyle}background:var(--accent);color:#000;border-color:transparent;font-size:13px;padding:7px 18px;">Save</button>
          </div>
        </div>`}
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px 32px;font-size:14px;align-items:start;">
        <div><span style="color:var(--text-dim);">Model</span><br><b>${_escHtmlA(agent.model)}</b></div>
        <div>
          <span style="color:var(--text-dim);">Roles</span><br>
          <div id="agent-roles-chips-${name}" style="display:flex;flex-wrap:wrap;gap:6px 8px;margin-bottom:6px;">
            ${agentRoles.map(role => `<span class="role-chip" style="display:inline-flex;align-items:center;background:var(--card);border:1.5px solid var(--border);border-radius:16px;padding:3px 12px 3px 10px;font-size:13px;font-weight:500;gap:6px;">${_escHtmlA(role)}<button onclick="agentsRemoveRole('${name}','${_escHtmlA(role)}')" style="background:none;border:none;color:#f44336;font-size:15px;line-height:1;padding:0 0 0 3px;cursor:pointer;">×</button></span>`).join('')}
          </div>
          <select id="agent-role-add-input-${name}" style="${_agentsInputStyle}width:180px;max-width:220px;display:inline-block;">
            <option value="">+ Add role…</option>
            ${allRoles.filter(r => !agentRoles.includes(r)).map(r => `<option value="${_escHtmlA(r)}">${_escHtmlA(r)}</option>`).join('')}
          </select>
        </div>
        <div><span style="color:var(--text-dim);">Tier</span><br><b>${_escHtmlA(agent.tier || '—')}</b></div>
      </div>

      <div style="margin:18px 0 0 0;">
        <span style="color:var(--text-dim);font-size:12px;font-weight:700;">Skills</span><br>
        <div id="agent-skills-chips-${name}" style="display:flex;flex-wrap:wrap;gap:6px 8px;margin-top:4px;">
          ${allSkills.map(skill => `
            <span class="skill-chip" style="display:inline-flex;align-items:center;background:${agentSkillNames.has(skill.name) ? 'var(--main-bg)' : 'var(--card)'};border:1.5px solid var(--border);border-radius:14px;padding:2px 10px;font-size:12px;font-weight:500;cursor:pointer;${agentSkillNames.has(skill.name) ? 'box-shadow:0 0 0 2px var(--accent);' : ''}"
              onclick="toggleAgentSkill('${name}','${skill.name}')">
              ${_escHtmlA(skill.name)}
              ${agentSkillNames.has(skill.name) ? '<button style="background:none;border:none;color:#f44336;font-size:15px;line-height:1;padding:0 0 0 3px;cursor:pointer;" onclick="removeAgentSkill(event,\'' + name + '\',\'' + skill.name + '\')">×</button>' : ''}
            </span>`).join('')}
        </div>
      </div>

      ${apiKeySection}

      ${(agent.name === 'duck' || agent.name === 'sniffles' || agent.system_prompt) ? `
      <div>
        <div style="font-size:12px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">System Prompt</div>
        <textarea id="agent-prompt-input-${name}" style="${_agentsInputStyle}min-height:120px;max-height:320px;resize:vertical;font-size:13px;">${_escHtmlA(agent.system_prompt || (agent.name === 'duck' ? 'Sanity checker logic — no editable prompt.' : agent.name === 'sniffles' ? 'Memory auditor logic — no editable prompt.' : ''))}</textarea>
        <button onclick="agentsSavePrompt('${name}')" style="${_agentsBtnStyle}background:var(--accent);color:#000;border-color:transparent;margin-top:8px;">Save Prompt</button>
      </div>` : ''}
    </div>`;

  // Add role (dropdown)
  const addRoleInput = document.getElementById(`agent-role-add-input-${name}`);
  if (addRoleInput) {
    addRoleInput.addEventListener('change', async function() {
      const newRole = this.value;
      if (!newRole) return;
      // Update roles array
      const updatedRoles = [...agentRoles, newRole];
      await fetch(`/api/agents/config/${name}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({roles: updatedRoles})
      });
      agentsRefresh();
      agentsShowDetail(name);
    });
  }
  // Remove role
  window.agentsRemoveRole = async function(name, role) {
    const updatedRoles = agentRoles.filter(r => r !== role);
    await fetch(`/api/agents/config/${name}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({roles: updatedRoles})
    });
    agentsRefresh();
    agentsShowDetail(name);
  };

  // Save Label handler
  const labelInput = document.getElementById(`agent-label-input-${name}`);
  if (labelInput) labelInput.addEventListener('change', async () => {
    await fetch(`/api/agents/config/${name}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({label: labelInput.value.trim()})
    });
    agentsRefresh();
    agentsShowDetail(name);
  });

  // Add role manager UI (add/remove roles)
  window.agentsAddRolePrompt = function(name) {
    const role = prompt('Enter new role name:');
    if (!role) return;
    window._customRoles = window._customRoles || [];
    if (!window._customRoles.includes(role)) window._customRoles.push(role);
    agentsShowDetail(name);
  };

  // Save Name, Label, Role handlers
  const nameInput = document.getElementById(`agent-name-input-${name}`);
  const labelInput = document.getElementById(`agent-label-input-${name}`);
  const roleInput = document.getElementById(`agent-role-input-${name}`);
  [nameInput, labelInput, roleInput].forEach(input => {
    if (input) input.addEventListener('change', async () => {
      await fetch(`/api/agents/config/${name}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: nameInput.value.trim(),
          label: labelInput.value.trim(),
          role: roleInput.value.trim()
        })
      });
      agentsRefresh();
      agentsShowDetail(nameInput.value.trim());
    });
  });

  // Add save handler for temperature
  window.agentsSaveTemp = async function(name) {
    const input = document.getElementById(`agent-temp-input-${name}`);
    if (!input) return;
    const temp = parseFloat(input.value);
    if (isNaN(temp) || temp < 0 || temp > 2) {
      input.style.borderColor = '#f44336';
      input.value = '';
      input.placeholder = '0.0 - 2.0';
      return;
    }
    input.style.borderColor = '';
    await fetch(`/api/agents/config/${name}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({temperature: temp})
    });
    agentsRefresh();
    agentsShowDetail(name);
  };

  // Add save handler for prompt (if editable)
  window.agentsSavePrompt = async function(name) {
    const input = document.getElementById(`agent-prompt-input-${name}`);
    if (!input || input.disabled) return;
    const prompt = input.value.trim();
    if (!prompt) {
      input.style.borderColor = '#f44336';
      input.placeholder = 'Prompt cannot be empty';
      return;
    }
    input.style.borderColor = '';
    await fetch(`/api/agents/config/${name}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({system_prompt: prompt})
    });
    agentsRefresh();
    agentsShowDetail(name);
  };

  // Add save handler for temperature
  window.agentsSaveTemp = async function(name) {
    const input = document.getElementById(`agent-temp-input-${name}`);
    if (!input) return;
    const temp = parseFloat(input.value);
    if (isNaN(temp) || temp < 0 || temp > 2) {
      input.style.borderColor = '#f44336';
      input.value = '';
      input.placeholder = '0.0 - 2.0';
      return;
    }
    input.style.borderColor = '';
    await fetch(`/api/agents/config/${name}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({temperature: temp})
    });
    agentsRefresh();
    agentsShowDetail(name);
  };
}

async function agentsSaveKey(name, keyVar) {
  const input = document.getElementById(`agent-key-input-${name}`);
  if (!input) return;
  const value = input.value.trim();
  if (!value) { input.placeholder = 'Key cannot be empty'; return; }
  const res = await fetch(`/api/agents/key/${name}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({key_var: keyVar, value})
  });
  const d = await res.json().catch(() => ({}));
  if (d.ok) {
    input.value = '';
    input.placeholder = '••••••••• (saved)';
    agentsRefresh();
  } else {
    input.placeholder = d.error || 'Error saving key';
  }
}

window.agentsConfirmReset = function(name) {
  _agentsModal({
    title: `Reset ${name}?`,
    body: `This will:<br>• Wipe all memory rows<br>• Clear sandpit files<br>• Re-run bootstrap to restore registries<br><br>Agent config (model, API key, system prompt) is preserved.`,
    confirmLabel: 'Reset',
    confirmDanger: false,
    onConfirm: async () => {
      const res = await fetch(`/api/agents/${name}/reset`, {method: 'POST', headers: {'Content-Type': 'application/json'}});
      const d = await res.json().catch(() => ({}));
      agentsRefresh();
      if (window.memoryRefresh) window.memoryRefresh();
      // Show result in detail panel
      const detailEl = document.getElementById('agents-detail');
      if (detailEl && d.steps) {
        const steps = Array.isArray(d.steps) ? d.steps : [];
        const errors = Array.isArray(d.errors) ? d.errors : [];
        detailEl.innerHTML = `<div style="padding:20px;font-size:12px;">
          <div style="font-weight:700;margin-bottom:10px;">Reset ${name}</div>
          ${steps.map(s => `<div style="color:var(--text-dim);padding:2px 0;">✓ ${_escHtmlA(s)}</div>`).join('')}
          ${errors.map(e => `<div style="color:#f44336;padding:2px 0;">✗ ${_escHtmlA(e)}</div>`).join('')}
          <button onclick="agentsShowDetail('${name}')" style="margin-top:12px;${_agentsBtnStyle}background:var(--card);color:var(--text);">← Back</button>
        </div>`;
      }
    }
  });
};

window.agentsConfirmDelete = function(name) {
  _agentsModal({
    title: `Permanently delete ${name}?`,
    body: `This will:<br>• Remove the agent from DB and all registries<br>• Drop its memory table<br>• Remove sandpit folder<br><br><b>This cannot be undone.</b>`,
    confirmLabel: 'Delete',
    confirmDanger: true,
    onConfirm: async () => {
      const res = await fetch(`/api/agents/${name}`, {method: 'DELETE'});
      const d = await res.json().catch(() => ({}));
      agentsRefresh();
      if (window.memoryRefresh) window.memoryRefresh();
      if (window.chatRefresh) window.chatRefresh();
      const detailEl = document.getElementById('agents-detail');
      if (detailEl) {
        detailEl.innerHTML = d.ok
          ? `<div style="padding:20px;color:var(--text-dim);font-size:12px;">${name} deleted.</div>`
          : `<div style="padding:20px;color:#f44336;font-size:12px;">Error: ${_escHtmlA(d.error || 'Unknown error')}</div>`;
      }
    }
  });
};

window.agentsConfirmToggle = function(name, enabled) {
  _agentsModal({
    title: enabled ? `Deactivate ${name}?` : `Reactivate ${name}?`,
    body: enabled
      ? `This will:<br>• Remove the agent from chat and memory<br>• Erase all its memory rows<br>• Hide it from all menus until reactivated.`
      : `This will:<br>• Restore the agent to chat and memory<br>• Allow it to participate in all workflows.`,
    confirmLabel: enabled ? 'Deactivate' : 'Reactivate',
    confirmDanger: enabled,
    onConfirm: () => agentsToggleEnabled(name, !enabled)
  });
};

function agentsShowAdd() {
  if (document.getElementById('agents-add-modal')) return;

  const overlay = document.createElement('div');
  overlay.id = 'agents-add-modal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div style="background:var(--bg,#12121a);border:1px solid var(--border);border-radius:10px;width:480px;max-width:95vw;box-shadow:0 16px 48px rgba(0,0,0,0.6);">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-bottom:1px solid var(--border);">
        <div style="font-weight:700;font-size:13px;">+ Add Agent</div>
        <button onclick="document.getElementById('agents-add-modal').remove()" style="background:transparent;border:none;color:var(--text-dim);cursor:pointer;font-size:18px;padding:0 2px;">✕</button>
      </div>
      <div style="padding:16px;display:flex;flex-direction:column;gap:12px;">
        <div>
          <label style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px;">Name <span style="color:#f44336;">*</span></label>
          <input id="add-agent-name" placeholder="e.g. fourteen" style="${_agentsInputStyle}" oninput="this.value=this.value.toLowerCase().replace(/[^a-z0-9_-]/g,'')">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px;">Label</label>
          <input id="add-agent-label" placeholder="e.g. Fourteen" style="${_agentsInputStyle}">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px;">Model <span style="color:#f44336;">*</span></label>
          <input id="add-agent-model" placeholder="e.g. gemma3:latest or gpt-4o" style="${_agentsInputStyle}">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px;">Role</label>
            <input id="add-agent-role" placeholder="e.g. Specialist" style="${_agentsInputStyle}">
          </div>
          <div>
            <label style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px;">Tier</label>
            <select id="add-agent-tier" style="${_agentsInputStyle}">
              <option value="local">local (Ollama)</option>
              <option value="paid">paid (API)</option>
              <option value="free">free (API)</option>
            </select>
          </div>
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px;">Temperature</label>
          <input id="add-agent-temp" type="number" min="0" max="2" step="0.1" value="0.5" style="${_agentsInputStyle}">
        </div>
        <div id="add-agent-err" style="color:#f44336;font-size:11px;display:none;"></div>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px;padding:12px 16px;border-top:1px solid var(--border);">
        <button onclick="document.getElementById('agents-add-modal').remove()" style="${_agentsBtnStyle}background:var(--card);color:var(--text);">Cancel</button>
        <button onclick="_agentsSubmitAdd()" style="${_agentsBtnStyle}background:var(--accent);color:#000;border-color:transparent;">Add Agent</button>
      </div>
    </div>`;
  overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  document.getElementById('add-agent-name').focus();
}

async function _agentsSubmitAdd() {
  const name  = (document.getElementById('add-agent-name')?.value || '').trim();
  const label = (document.getElementById('add-agent-label')?.value || '').trim();
  const model = (document.getElementById('add-agent-model')?.value || '').trim();
  const role  = (document.getElementById('add-agent-role')?.value || '').trim();
  const tier  = (document.getElementById('add-agent-tier')?.value || 'local');
  const temp  = parseFloat(document.getElementById('add-agent-temp')?.value || 0.5);
  const errEl = document.getElementById('add-agent-err');

  if (!name || !model) {
    if (errEl) { errEl.textContent = 'Name and model are required.'; errEl.style.display = ''; }
    return;
  }

  const res = await fetch('/api/agents/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, label: label || name, model, role, tier, temperature: temp})
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.error) {
    if (errEl) { errEl.textContent = d.error || 'Failed to add agent.'; errEl.style.display = ''; }
    return;
  }
  document.getElementById('agents-add-modal')?.remove();
  agentsRefresh();
}


// Generic confirm modal — no native confirm() calls
function _agentsModal({title, body, confirmLabel='OK', confirmDanger=false, onConfirm}) {
  if (document.getElementById('agents-confirm-modal')) document.getElementById('agents-confirm-modal').remove();
  const overlay = document.createElement('div');
  overlay.id = 'agents-confirm-modal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:10000;display:flex;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div style="background:var(--bg,#12121a);border:1px solid var(--border);border-radius:10px;width:360px;max-width:95vw;box-shadow:0 16px 48px rgba(0,0,0,0.6);padding:22px 20px 16px;">
      <div style="font-weight:700;font-size:13px;margin-bottom:12px;">${title}</div>
      <div style="font-size:12px;color:var(--text-dim);line-height:1.5;margin-bottom:20px;">${body}</div>
      <div style="display:flex;justify-content:flex-end;gap:8px;">
        <button onclick="document.getElementById('agents-confirm-modal').remove()" style="${_agentsBtnStyle}background:var(--card);color:var(--text);">Cancel</button>
        <button id="agents-confirm-btn" style="${_agentsBtnStyle}background:${confirmDanger ? '#c62828' : 'var(--accent)'};color:#fff;border-color:transparent;">${confirmLabel}</button>
      </div>
    </div>`;
  overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  document.getElementById('agents-confirm-btn').onclick = () => {
    overlay.remove();
    if (typeof onConfirm === 'function') onConfirm();
  };
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('agents-list')) agentsRefresh();
});

// Fetch all available skills for the system
async function fetchAllSkills() {
  const res = await fetch('/api/skills');
  return await res.json();
}

// Fetch skills for a specific agent
async function fetchAgentSkills(agentName) {
  const res = await fetch(`/api/agents/${agentName}/skills`);
  return await res.json();
}

// Update skills for a specific agent
async function updateAgentSkills(agentName, skills) {
  await fetch(`/api/agents/${agentName}/skills`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({skills})
  });
}
