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
  listEl.innerHTML = agents.map(a => `
    <div class="agent-list-item" style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;"
         onclick="agentsShowDetail('${a.name}')">
      <span style="flex:1;font-size:12px;">${a.number != null ? '<span style=\'color:var(--text-dim);font-size:10px;\'>' + a.number + '</span> ' : ''}${_escHtmlA(a.label || a.name)}</span>
      <span style="color:var(--text-dim);font-size:10px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtmlA(a.model)}</span>
      ${a.tier === 'human' ? '' : `<button onclick="event.stopPropagation();agentsConfirmToggle('${a.name}', ${a.enabled})" style="padding:2px 8px;border-radius:4px;border:1px solid ${a.enabled ? '#f4433655' : 'transparent'};background:${a.enabled ? 'transparent' : 'var(--accent)'};color:${a.enabled ? '#f44336' : '#000'};font-size:10px;">${a.enabled ? 'Off' : 'On'}</button>`}
    </div>`).join('');
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

  detailEl.innerHTML = `
    <div style="padding:20px;max-width:640px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:15px;">${_escHtmlA(agent.label || agent.name)}</h3>
        ${isHuman ? '' : `<div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button onclick="agentsConfirmToggle('${name}', ${agent.enabled})"
            style="padding:3px 12px;border-radius:4px;border:1px solid ${agent.enabled ? '#f4433655' : 'transparent'};
                   background:${agent.enabled ? 'transparent' : 'var(--accent)'};color:${agent.enabled ? '#f44336' : '#000'};font-size:11px;">
            ${agent.enabled ? 'Deactivate' : 'Reactivate'}</button>
          <button onclick="agentsConfirmReset('${name}')"
            style="padding:3px 12px;border-radius:4px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:11px;">
            ↺ Reset</button>
          ${!isProtected ? `<button onclick="agentsConfirmDelete('${name}')"
            style="padding:3px 12px;border-radius:4px;border:1px solid #f4433655;background:transparent;color:#f44336;font-size:11px;">
            ✕ Delete</button>` : ''}
        </div>`}
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 20px;margin-bottom:16px;font-size:12px;">
        <div><span style="color:var(--text-dim);">Model</span><br><b>${_escHtmlA(agent.model)}</b></div>
        <div><span style="color:var(--text-dim);">Role</span><br><b>${_escHtmlA(agent.role || '—')}</b></div>
        <div><span style="color:var(--text-dim);">Temperature</span><br><b>${agent.temperature != null ? agent.temperature : '—'}</b></div>
        <div><span style="color:var(--text-dim);">Tier</span><br><b>${_escHtmlA(agent.tier || '—')}</b></div>
      </div>

      ${apiKeySection}

      ${agent.system_prompt ? `
      <div>
        <div style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">System Prompt</div>
        <pre style="background:var(--card);padding:10px;border-radius:4px;font-size:11px;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto;">${_escHtmlA(agent.system_prompt)}</pre>
      </div>` : ''}
    </div>`;
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

function agentsToggleGlobals() {
  const body = document.getElementById('agents-globals-body');
  const chevron = document.getElementById('agents-globals-chevron');
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (chevron) chevron.textContent = open ? '▸' : '▾';
  if (!open && !body.innerHTML.trim()) _agentsLoadGlobals(body);
}

async function _agentsLoadGlobals(body) {
  body.innerHTML = '<div style="padding:4px 0;color:var(--text-dim);font-size:11px;">Loading...</div>';
  const res = await fetch('/api/agents/config').catch(() => null);
  if (!res || !res.ok) { body.innerHTML = '<div style="color:#f44336;font-size:11px;">Could not load config.</div>'; return; }
  const agents = await res.json();
  const locals = agents.filter(a => a.tier === 'local' && a.temperature != null);
  body.innerHTML = locals.map(a => `
    <div style="display:flex;align-items:center;gap:10px;padding:5px 0;font-size:11px;border-bottom:1px solid rgba(255,255,255,0.04);">
      <span style="min-width:90px;color:var(--text-dim);">${_escHtmlA(a.label || a.name)}</span>
      <span style="min-width:60px;">Temp: <b>${a.temperature}</b></span>
    </div>`).join('') || '<div style="color:var(--text-dim);font-size:11px;">No local agents with temperature config.</div>';
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
