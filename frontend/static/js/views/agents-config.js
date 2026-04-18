// agents-config.js — Agents config view with model selection
// Handles agent enable/disable, model swapping, detail panel, API keys

(function() {
    const _agentsInputStyle = 'width:100%;background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:6px 9px;font-size:12px;outline:none;box-sizing:border-box;';
    const _agentsBtnStyle  = 'border:1px solid var(--border);border-radius:4px;padding:5px 14px;cursor:pointer;font-size:11px;font-weight:600;';
    const _sectionLabel    = 'font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;';

    // Known API models per tier
    const API_MODELS = {
        ghost_coder: [
            { value: 'auto',                      label: 'Auto (Anthropic → OpenAI → Grok)' },
            { value: 'claude-sonnet-4-20250514',   label: 'Claude Sonnet 4' },
            { value: 'claude-opus-4-20250514',     label: 'Claude Opus 4' },
            { value: 'gpt-4.1',                    label: 'GPT-4.1' },
            { value: 'gpt-4o',                     label: 'GPT-4o' },
            { value: 'grok-3',                     label: 'Grok 3' },
        ],
        paid: [
            { value: 'claude-haiku-4-5',           label: 'Claude Haiku 4.5' },
            { value: 'claude-sonnet-4-20250514',   label: 'Claude Sonnet 4' },
            { value: 'claude-opus-4-20250514',     label: 'Claude Opus 4' },
            { value: 'gpt-4.1',                    label: 'GPT-4.1' },
            { value: 'gpt-4o',                     label: 'GPT-4o' },
            { value: 'grok-3',                     label: 'Grok 3' },
            { value: 'llama-3.3-70b-versatile',    label: 'LLaMA 3.3 70B (Groq)' },
            { value: 'gemini-2.0-flash',           label: 'Gemini 2.0 Flash' },
            { value: 'meta-llama/Llama-3.3-70B-Instruct', label: 'LLaMA 3.3 70B (Together)' },
        ],
    };

    const _PROTECTED = ['gemma','llama','mistral','qwen','eight','nine','ten','eleven','twelve','ghost','librarian','duck','sniffles'];

    // Cache for Ollama models
    let _ollamaModels = null;

    function _escHtmlA(s) {
        return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    async function _fetchOllamaModels() {
        if (_ollamaModels) return _ollamaModels;
        try {
            const res = await fetch('/api/localai/status');
            const data = await res.json();
            _ollamaModels = (data.ollama?.models || []).map(m => m.name || m);
        } catch(e) {
            _ollamaModels = [];
        }
        return _ollamaModels;
    }

    // ── List view ───────────────────────────────────────────────────────────
    async function agentsRefresh() {
        const listEl = document.getElementById('agents-list');
        if (!listEl) return;
        listEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-dim);">Loading...</div>';
        try {
            const res = await fetch('/api/agents/config');
            const agents = await res.json();
            window._agentsConfig = agents;
            listEl.innerHTML = agents.map(a => {
                const dot = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;vertical-align:middle;background:${a.enabled ? '#4caf50' : '#f44336'};box-shadow:0 0 0 1.5px var(--window-header);"></span>`;
                return `
                    <div class="agent-list-item" style="display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.18s;" onclick="agentsShowDetail('${a.name}')">
                        ${dot}
                        <span style="flex:1;font-size:13px;font-weight:600;letter-spacing:0.1px;">${_escHtmlA(a.label || a.name)}</span>
                        <span style="color:var(--text-dim);font-size:11px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtmlA(a.model)}</span>
                    </div>`;
            }).join('');
        } catch(e) {
            listEl.innerHTML = '<div style="padding:20px;text-align:center;color:#f44336;">Failed to load agents</div>';
        }
    }

    // ── Detail view ─────────────────────────────────────────────────────────
    async function agentsShowDetail(name) {
        const agent = (window._agentsConfig || []).find(a => a.name === name);
        const detailEl = document.getElementById('agents-detail');
        if (!agent || !detailEl) return;

        const isHuman    = agent.tier === 'human';
        const isProtected = _PROTECTED.includes(name);
        const isLocal    = ['local','ollama'].includes((agent.tier || '').toLowerCase())
                           || ['gemma','llama','mistral','qwen','librarian','duck','sniffles','phi3','deepseek_local'].includes(name);

        // Build model options
        const ollamaModels = await _fetchOllamaModels();
        let modelOptions = [];

        if (name === 'ghost_coder') {
            modelOptions = API_MODELS.ghost_coder;
        } else if (isLocal) {
            modelOptions = ollamaModels.map(m => ({ value: m, label: m }));
        } else {
            // Paid/API agents — show API models + current if not in list
            modelOptions = [...API_MODELS.paid];
        }
        // Always include current model if not already listed
        const currentModel = agent.model || '';
        if (currentModel && !modelOptions.find(m => m.value === currentModel)) {
            modelOptions.unshift({ value: currentModel, label: currentModel + ' (current)' });
        }

        const modelSelect = modelOptions.length > 0
            ? `<select id="agent-model-select-${name}" style="${_agentsInputStyle}cursor:pointer;">
                ${modelOptions.map(m =>
                    `<option value="${_escHtmlA(m.value)}" ${m.value === currentModel ? 'selected' : ''}>${_escHtmlA(m.label)}</option>`
                ).join('')}
               </select>`
            : `<input id="agent-model-input-${name}" value="${_escHtmlA(currentModel)}" style="${_agentsInputStyle}" placeholder="Model name">`;

        // API key section
        const apiKeySection = agent.api_key_var ? `
            <div style="margin-bottom:12px;">
                <div style="${_sectionLabel}">API Key</div>
                <div style="display:flex;gap:6px;align-items:center;">
                    <input id="agent-key-input-${name}" type="password" placeholder="${agent.api_key_set ? '••••••••• (already set)' : 'Paste key here'}"
                           style="${_agentsInputStyle}font-family:monospace;">
                    <button onclick="agentsSaveKey('${name}','${agent.api_key_var}')"
                            style="${_agentsBtnStyle}background:var(--accent);color:#000;border-color:transparent;">Save</button>
                </div>
                <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">Env var: <code>${_escHtmlA(agent.api_key_var)}</code> · Status: ${agent.api_key_set ? '<span style="color:#4caf50;">✓ set</span>' : '<span style="color:#f44336;">✗ missing</span>'}</div>
            </div>` : '';

        // Roles section
        const SAP_ROLES = ['SAP HCM Specialist','SAP Payroll Expert','SAP ABAP Developer','SAP Time Management','SAP EC/ECP Consultant','SAP Schema Designer','SAP PCR Author','SAP Integration Lead','SAP Security Analyst','SAP Data Migration'];
        const SYSTEM_ROLES = ['Program Manager','System Architect','AI Researcher','AI Developer','Memory Auditor','Sanity Checker','Orchestrator','Researcher','Analyst','Generalist'];
        let allRoles = Array.from(new Set([...SAP_ROLES, ...SYSTEM_ROLES]));
        if (window._customRoles) allRoles = Array.from(new Set([...allRoles, ...window._customRoles]));

        let agentRoles = Array.isArray(agent.roles) ? agent.roles : (agent.role ? [agent.role] : []);
        if (!Array.isArray(agentRoles)) agentRoles = String(agentRoles || '').split(',').map(r => r.trim()).filter(Boolean);

        const rolesHtml = allRoles.map(r => {
            const checked = agentRoles.includes(r) ? 'checked' : '';
            return `<label style="display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:3px 8px;border:1px solid var(--border);border-radius:12px;cursor:pointer;background:${checked ? 'var(--accent)' : 'transparent'};color:${checked ? '#000' : 'var(--text)'};transition:all .15s;">
                <input type="checkbox" class="agent-role-cb" value="${_escHtmlA(r)}" ${checked} style="display:none;"> ${_escHtmlA(r)}
            </label>`;
        }).join(' ');

        detailEl.innerHTML = `
            <div style="padding:24px 4vw;max-width:900px;margin:auto;display:flex;flex-direction:column;gap:20px;">
                <!-- Header row -->
                <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;justify-content:space-between;">
                    <div style="display:flex;align-items:center;gap:12px;">
                        <span style="display:inline-block;width:16px;height:16px;border-radius:50%;background:${agent.enabled ? '#4caf50' : '#f44336'};box-shadow:0 0 0 2px var(--window-header);"></span>
                        <input id="agent-name-input-${name}" value="${_escHtmlA(agent.name)}" style="${_agentsInputStyle}width:120px;font-weight:700;font-size:1.1em;background:var(--card-dim);color:var(--text-dim);" readonly>
                        <input id="agent-label-input-${name}" value="${_escHtmlA(agent.label || '')}" style="${_agentsInputStyle}width:180px;font-size:1.1em;" placeholder="Label">
                    </div>
                    ${isHuman ? '' : `<div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <button onclick="agentsConfirmToggle('${name}', ${agent.enabled})" style="padding:7px 18px;border-radius:6px;border:1.5px solid ${agent.enabled ? '#f4433655' : 'var(--border)'};background:${agent.enabled ? 'transparent' : 'var(--accent)'};color:${agent.enabled ? '#f44336' : '#000'};font-size:12px;font-weight:600;cursor:pointer;">${agent.enabled ? 'Deactivate' : 'Reactivate'}</button>
                        <button onclick="agentsConfirmReset('${name}')" style="padding:7px 18px;border-radius:6px;border:1.5px solid var(--border);background:var(--card);color:var(--text);font-size:12px;font-weight:600;cursor:pointer;">↺ Reset</button>
                        ${!isProtected ? `<button onclick="agentsConfirmDelete('${name}')" style="padding:7px 18px;border-radius:6px;border:1.5px solid #f4433655;background:transparent;color:#f44336;font-size:12px;font-weight:600;cursor:pointer;">✕ Delete</button>` : ''}
                    </div>`}
                </div>

                <!-- Model selection -->
                <div>
                    <div style="${_sectionLabel}">Model</div>
                    <div style="display:flex;gap:8px;align-items:center;">
                        ${modelSelect}
                        <button id="agent-model-save-${name}" onclick="agentsSaveModel('${name}')"
                            style="${_agentsBtnStyle}background:var(--accent);color:#000;border-color:transparent;white-space:nowrap;">Apply</button>
                    </div>
                    <div id="agent-model-status-${name}" style="font-size:10px;color:var(--text-dim);margin-top:3px;">Current: ${_escHtmlA(currentModel)}</div>
                </div>

                <!-- API Key -->
                ${apiKeySection}

                <!-- Roles -->
                <div>
                    <div style="${_sectionLabel}">Roles</div>
                    <div id="agent-roles-wrap-${name}" style="display:flex;flex-wrap:wrap;gap:6px;">
                        ${rolesHtml}
                    </div>
                </div>

                <!-- System Prompt -->
                <div>
                    <div style="${_sectionLabel}">System Prompt</div>
                    <textarea id="agent-prompt-${name}" rows="6" style="${_agentsInputStyle}font-family:monospace;resize:vertical;min-height:80px;">${_escHtmlA(agent.system_prompt || '')}</textarea>
                </div>

                <!-- Save all -->
                <div style="display:flex;gap:10px;justify-content:flex-end;">
                    <button onclick="agentsSaveAll('${name}')" style="${_agentsBtnStyle}background:var(--accent);color:#000;border-color:transparent;padding:8px 28px;font-size:13px;">Save Changes</button>
                </div>

                <!-- Info -->
                <div style="font-size:10px;color:var(--text-dim);border-top:1px solid var(--border);padding-top:12px;">
                    Tier: ${_escHtmlA(agent.tier)} · Number: ${agent.number ?? '—'} · Enabled: ${agent.enabled ? 'Yes' : 'No'}
                </div>
            </div>`;

        // Role pill toggle behaviour
        detailEl.querySelectorAll('.agent-role-cb').forEach(cb => {
            cb.parentElement.addEventListener('click', function(e) {
                e.preventDefault();
                cb.checked = !cb.checked;
                this.style.background = cb.checked ? 'var(--accent)' : 'transparent';
                this.style.color = cb.checked ? '#000' : 'var(--text)';
            });
        });
    }

    // ── Model save ──────────────────────────────────────────────────────────
    async function agentsSaveModel(name) {
        const select = document.getElementById(`agent-model-select-${name}`);
        const input  = document.getElementById(`agent-model-input-${name}`);
        const model  = (select ? select.value : (input ? input.value.trim() : ''));
        if (!model) return;

        const statusEl = document.getElementById(`agent-model-status-${name}`);
        if (statusEl) statusEl.textContent = 'Saving…';

        const res = await fetch(`/api/agents/config/${name}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ model })
        });
        const d = await res.json().catch(() => ({}));
        if (statusEl) statusEl.textContent = d.error ? `Error: ${d.error}` : `✓ Model set to ${model}`;
        _ollamaModels = null; // bust cache
        agentsRefresh();
    }

    // ── Save all fields ─────────────────────────────────────────────────────
    async function agentsSaveAll(name) {
        const label = (document.getElementById(`agent-label-input-${name}`) || {}).value || '';
        const prompt = (document.getElementById(`agent-prompt-${name}`) || {}).value || '';
        const select = document.getElementById(`agent-model-select-${name}`);
        const input  = document.getElementById(`agent-model-input-${name}`);
        const model  = (select ? select.value : (input ? input.value.trim() : ''));

        // Gather checked roles
        const roleEls = document.querySelectorAll(`#agent-roles-wrap-${name} .agent-role-cb:checked`);
        const roles = Array.from(roleEls).map(cb => cb.value);

        const body = { label, system_prompt: prompt, roles };
        if (model) body.model = model;

        const res = await fetch(`/api/agents/config/${name}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const d = await res.json().catch(() => ({}));
        const statusEl = document.getElementById(`agent-model-status-${name}`);
        if (statusEl) statusEl.textContent = d.error ? `Error: ${d.error}` : '✓ Saved';
        _ollamaModels = null;
        agentsRefresh();
    }

    // ── Enable/disable toggle ───────────────────────────────────────────────
    async function agentsToggleEnabled(name, enabled) {
        await fetch(`/api/agents/config/${name}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ enabled: !!enabled })
        });
        agentsRefresh();
        if (window.memoryRefresh) window.memoryRefresh();
        if (window.chatRefresh) window.chatRefresh();
    }

    function agentsConfirmToggle(name, currentlyEnabled) {
        if (currentlyEnabled) {
            if (confirm(`Deactivate ${name}? This will disable the agent and clear its memory.`)) {
                agentsToggleEnabled(name, false);
            }
        } else {
            agentsToggleEnabled(name, true);
        }
    }

    function agentsConfirmReset(name) {
        if (confirm(`Reset ${name}? This will clear the agent's memory and restore defaults.`)) {
            fetch(`/api/agents/config/${name}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ enabled: true })
            }).then(() => agentsRefresh());
        }
    }

    function agentsConfirmDelete(name) {
        if (confirm(`Delete ${name}? This cannot be undone.`)) {
            fetch(`/api/agents/config/${name}`, {
                method: 'DELETE'
            }).then(() => {
                document.getElementById('agents-detail').innerHTML = '';
                agentsRefresh();
            });
        }
    }

    // ── API key save ────────────────────────────────────────────────────────
    async function agentsSaveKey(name, keyVar) {
        const input = document.getElementById(`agent-key-input-${name}`);
        if (!input) return;
        const value = input.value.trim();
        if (!value) { input.placeholder = 'Key cannot be empty'; return; }
        const res = await fetch(`/api/agents/key/${name}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ key_var: keyVar, value })
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

    // ── Expose to window for onclick handlers ───────────────────────────────
    window.agentsRefresh       = agentsRefresh;
    window.agentsShowDetail    = agentsShowDetail;
    window.agentsSaveModel     = agentsSaveModel;
    window.agentsSaveAll       = agentsSaveAll;
    window.agentsToggleEnabled = agentsToggleEnabled;
    window.agentsConfirmToggle = agentsConfirmToggle;
    window.agentsConfirmReset  = agentsConfirmReset;
    window.agentsConfirmDelete = agentsConfirmDelete;
    window.agentsSaveKey       = agentsSaveKey;

    console.log('[Agents Config] Loaded with model selection support');
})();