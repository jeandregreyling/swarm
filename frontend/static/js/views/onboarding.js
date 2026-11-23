// onboarding.js — Welcome Aboard Packager & Enrollment logic
// Drives the 6-step enrollment flow:
//   0: Welcome & Preflight → 1: Local AI & Role Models → 2: Hive Node & Telemetry
//   → 3: Cloud API Keys → 4: Remote Nodes → 5: Ready

(function () {
  'use strict';

  let _step = 0;
  const _totalSteps = 6;
  let _status = null; // cached /api/onboarding/status response
  let _lastConnectReceipt = null;

  function _shouldReopenEveryLaunch() {
    try {
      const value = localStorage.getItem('swarm_onboarding_reopen_every_launch');
      return value === '1';
    } catch (e) {
      return false;
    }
  }

  function _persistLaunchPreference(reopen) {
    try {
      localStorage.setItem('swarm_onboarding_reopen_every_launch', reopen ? '1' : '0');
      if (reopen) {
        localStorage.removeItem('swarm_onboarding_complete');
      } else {
        localStorage.setItem('swarm_onboarding_complete', '1');
      }
    } catch (e) {}
  }

  function _syncLaunchPreferenceCheckbox() {
    const cb = document.getElementById('ob-reopen-every-launch');
    if (cb) cb.checked = _shouldReopenEveryLaunch();
  }

  function _bindLaunchPreferenceCheckbox() {
    const cb = document.getElementById('ob-reopen-every-launch');
    if (!cb || cb.dataset.bound === '1') return;
    cb.dataset.bound = '1';
    cb.addEventListener('change', () => {
      _persistLaunchPreference(!!cb.checked);
    });
  }

  // ── Navigation ──────────────────────────────────────────────────────────

  function obNext() {
    if (_step < _totalSteps - 1) {
      _step++;
      _renderStep();
    }
  }

  function obBack() {
    if (_step > 0) {
      _step--;
      _renderStep();
    }
  }

  function _renderStep() {
    // Show/hide step panels
    document.querySelectorAll('.ob-step').forEach(el => {
      el.style.display = parseInt(el.dataset.step) === _step ? '' : 'none';
    });

    // Update progress dots
    document.querySelectorAll('.ob-step-dot').forEach(dot => {
      const s = parseInt(dot.dataset.step);
      dot.classList.remove('active', 'done');
      if (s === _step) dot.classList.add('active');
      else if (s < _step) dot.classList.add('done');
    });

    // Update progress lines
    const lines = document.querySelectorAll('.ob-step-line');
    lines.forEach((line, i) => {
      line.classList.toggle('done', i < _step);
    });

    // Navigation buttons
    const backBtn = document.getElementById('ob-btn-back');
    const nextBtn = document.getElementById('ob-btn-next');
    if (backBtn) backBtn.style.display = _step > 0 ? '' : 'none';
    if (nextBtn) {
      if (_step === _totalSteps - 1) {
        nextBtn.style.display = 'none'; // Ready page has its own finish button
      } else {
        nextBtn.style.display = '';
        nextBtn.textContent = _step === 0 ? 'Get Started →' : 'Next →';
      }
    }

    // Step-specific init
    if (_step === 0) _renderPreflight();
    if (_step === 1) obCheckLocal();
    if (_step === 2) _renderNodePipeForm();
    if (_step === 3) _renderKeyCards();
    if (_step === 4) _renderNodes();
    if (_step === 5) _renderSummary();
  }

  // ── Step 0: Welcome & Preflight Packager ────────────────────────────────

  function _statusBadge(state) {
    if (state === 'ok') return '<span style="color:#4caf50;font-weight:700;">✓</span>';
    if (state === 'warn') return '<span style="color:#ff9800;font-weight:700;">!</span>';
    return '<span style="color:#f44336;font-weight:700;">✗</span>';
  }

  function _renderPreflight() {
    const hwEl = document.getElementById('ob-hw-summary');
    const listEl = document.getElementById('ob-preflight-list');
    const pkg = (_status && _status.packager) || {};
    const hw = pkg.hardware || {};
    const checks = pkg.preflight || [];

    if (hwEl) {
      if (hw.os) {
        const machine = [hw.manufacturer, hw.model].filter(Boolean).join(' ') || hw.hostname || 'This host';
        const ramGb = hw.ram_total_mb ? Math.round(hw.ram_total_mb / 1024) : '?';
        const gpuName = (hw.gpus && hw.gpus[0] && hw.gpus[0].name) ? hw.gpus[0].name : 'No GPU detected';
        hwEl.innerHTML =
          `<strong style="color:var(--text);">${_esc(machine)}</strong> · ${_esc(hw.os)} · ` +
          `${_esc(hw.cpu_cores || '?')}C/${_esc(hw.cpu_threads || '?')}T · ${ramGb} GB RAM · ` +
          `${_esc(gpuName)} · tier <code style="background:var(--bg-input);padding:1px 5px;border-radius:4px;">${_esc(hw.tier || 'unknown')}</code> ` +
          `(${_esc(hw.primary_backend || 'cpu')})`;
      } else {
        hwEl.textContent = 'Hardware probe unavailable — click Re-scan.';
      }
    }

    if (listEl) {
      listEl.innerHTML = checks.map(c => `
        <div style="display:flex;align-items:flex-start;gap:8px;padding:7px 10px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;font-size:12px;">
          <span style="width:16px;text-align:center;flex-shrink:0;">${_statusBadge(c.status)}</span>
          <div style="flex:1;min-width:0;">
            <div style="color:var(--text);font-weight:600;">${_esc(c.label)}</div>
            <div style="color:var(--text-dim);font-size:11px;">${_esc(c.detail)}</div>
            ${c.status !== 'ok' && c.install_hint ? `<div style="margin-top:3px;font-size:11px;color:var(--accent);"><code>${_esc(c.install_hint)}</code></div>` : ''}
          </div>
        </div>
      `).join('');
    }
  }

  async function obRefreshPackager() {
    const hwEl = document.getElementById('ob-hw-summary');
    if (hwEl) hwEl.textContent = 'Re-scanning hardware and runtimes...';
    try {
      const [sr, pr] = await Promise.all([
        fetch('/api/onboarding/status'),
        fetch('/api/onboarding/packager?refresh=1'),
      ]);
      _status = await sr.json();
      const pkg = await pr.json();
      if (pkg && pkg.ok) _status.packager = pkg;
    } catch (e) {}
    _renderPreflight();
  }

  // ── Step 1: Local AI & Role Models ──────────────────────────────────────

  function _populateRoleModelSelects() {
    const pkg = (_status && _status.packager) || {};
    const rt = pkg.runtimes || {};
    const models = (rt.models || []).filter(m => !m.embed);
    const rec = pkg.recommended_models || {};
    const enrolledModels = (pkg.enrollment && pkg.enrollment.models) || {};
    const hw = pkg.hardware || {};

    const hintEl = document.getElementById('ob-role-models-hint');
    if (hintEl) {
      const ramGb = hw.ram_total_mb ? Math.round(hw.ram_total_mb / 1024) : '?';
      hintEl.textContent = models.length
        ? `Detected ${models.length} local chat model(s) for ${hw.tier || 'this host'} (${ramGb} GB RAM, ${hw.primary_backend || 'cpu'}).`
        : 'No local models detected yet — you can pull models via Ollama and click Re-check.';
    }

    const roles = ['apex', 'fred', 'hb'];
    roles.forEach(role => {
      const sel = document.getElementById('ob-model-' + role);
      if (!sel) return;
      const preferred = enrolledModels[role] || (rec[role] && rec[role].model) || '';
      const opts = [];
      if (models.length === 0) {
        opts.push(`<option value="${_esc(preferred)}">${_esc(preferred || '(none installed yet)')}</option>`);
      } else {
        let matched = false;
        models.forEach(m => {
          const name = m.name || '';
          const sizeStr = m.size_gb ? `${m.size_gb} GB` : '';
          const fitStr = m.fit ? ` · ${m.fit}` : '';
          const isSel = name === preferred;
          if (isSel) matched = true;
          opts.push(`<option value="${_esc(name)}" ${isSel ? 'selected' : ''}>${_esc(name)}${sizeStr ? ' (' + sizeStr + fitStr + ')' : ''}</option>`);
        });
        if (preferred && !matched) {
          opts.unshift(`<option value="${_esc(preferred)}" selected>${_esc(preferred)} (configured)</option>`);
        }
      }
      sel.innerHTML = opts.join('');
    });
  }

  async function obCheckLocal() {
    const ollamaIcon = document.getElementById('ob-ollama-icon');
    const ollamaDetail = document.getElementById('ob-ollama-detail');
    const lmsIcon = document.getElementById('ob-lmstudio-icon');
    const lmsDetail = document.getElementById('ob-lmstudio-detail');
    const helpEl = document.getElementById('ob-local-help');
    const helpBody = document.getElementById('ob-local-help-body');

    if (ollamaIcon) ollamaIcon.textContent = '...';
    if (ollamaDetail) ollamaDetail.textContent = 'Checking...';
    if (lmsIcon) lmsIcon.textContent = '...';
    if (lmsDetail) lmsDetail.textContent = 'Checking...';

    try {
      const r = await fetch('/api/onboarding/status');
      _status = await r.json();
      const ol = _status.local_ai.ollama;
      const lm = _status.local_ai.lmstudio;

      if (ollamaIcon) ollamaIcon.innerHTML = ol.running ? '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M3 8.5l3 3 7-7" stroke="#4caf50" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>' : '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M4 4l8 8M12 4l-8 8" stroke="#f44336" stroke-width="1.5" stroke-linecap="round"/></svg>';
      if (ollamaDetail) ollamaDetail.textContent = ol.running
        ? `Running — ${ol.model_count} model${ol.model_count !== 1 ? 's' : ''} installed`
        : 'Not reachable on localhost:11434';

      if (lmsIcon) lmsIcon.innerHTML = lm.running ? '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M3 8.5l3 3 7-7" stroke="#4caf50" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>' : '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><circle cx="8" cy="8" r="5" stroke="currentColor" stroke-width="1.3" opacity="0.4"/></svg>';
      if (lmsDetail) lmsDetail.textContent = lm.running
        ? `Running — ${lm.models} model${lm.models !== 1 ? 's' : ''} loaded`
        : 'Not running (optional)';

      const pkg = _status.packager || {};
      const olCheck = (pkg.preflight || []).find(c => c.id === 'ollama');
      if (helpBody && olCheck && olCheck.install_hint) {
        helpBody.innerHTML =
          `1. Install Ollama: <code style="background:var(--bg-input);padding:2px 6px;border-radius:4px;">${_esc(olCheck.install_hint)}</code><br>` +
          `2. Start it: <code style="background:var(--bg-input);padding:2px 6px;border-radius:4px;">ollama serve</code><br>` +
          `3. Pull starter models: <code style="background:var(--bg-input);padding:2px 6px;border-radius:4px;">ollama pull llama3.2:latest</code><br>` +
          `Then click <strong>Re-check</strong> below.`;
      }

      if (helpEl) helpEl.style.display = (!ol.running && !lm.running) ? '' : 'none';
      _populateRoleModelSelects();
    } catch (e) {
      if (ollamaIcon) ollamaIcon.innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M2.5 12L8 3l5.5 9z" stroke="#ff9800" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 7.5v2M8 11v.5" stroke="#ff9800" stroke-width="1.3" stroke-linecap="round"/></svg>';
      if (ollamaDetail) ollamaDetail.textContent = 'Could not check — API error';
    }
  }

  // ── Step 2: Hive Node & Telemetry Pipes ─────────────────────────────────

  function _renderNodePipeForm() {
    const pkg = (_status && _status.packager) || {};
    const enr = pkg.enrollment || {};
    const hw = pkg.hardware || {};

    const nodeIdEl = document.getElementById('ob-enroll-node-id');
    const roleEl = document.getElementById('ob-enroll-role');
    const labelEl = document.getElementById('ob-enroll-label');
    const endpointEl = document.getElementById('ob-enroll-endpoint');
    const leaderEl = document.getElementById('ob-enroll-leader');

    if (nodeIdEl && !nodeIdEl.value) nodeIdEl.value = enr.node_id || hw.hostname || '';
    if (roleEl && enr.role) roleEl.value = enr.role;
    if (labelEl && !labelEl.value) {
      const defaultLabel = [hw.manufacturer, hw.model].filter(Boolean).join(' ') || hw.hostname || '';
      labelEl.value = enr.label || defaultLabel;
    }
    if (endpointEl && !endpointEl.value) endpointEl.value = enr.endpoint_url || pkg.detected_endpoint_url || '';
    if (leaderEl && !leaderEl.value) leaderEl.value = enr.leader_url || '';
  }

  async function obConnectPipes() {
    const btn = document.getElementById('ob-connect-pipes-btn');
    const statusEl = document.getElementById('ob-connect-pipes-status');
    const receiptEl = document.getElementById('ob-connect-pipes-receipt');

    const payload = {
      node_id: (document.getElementById('ob-enroll-node-id')?.value || '').trim(),
      label: (document.getElementById('ob-enroll-label')?.value || '').trim(),
      role: (document.getElementById('ob-enroll-role')?.value || 'worker').trim(),
      endpoint_url: (document.getElementById('ob-enroll-endpoint')?.value || '').trim(),
      leader_url: (document.getElementById('ob-enroll-leader')?.value || '').trim(),
      models: {
        apex: (document.getElementById('ob-model-apex')?.value || '').trim(),
        fred: (document.getElementById('ob-model-fred')?.value || '').trim(),
        hb: (document.getElementById('ob-model-hb')?.value || '').trim(),
      },
    };

    if (btn) btn.disabled = true;
    if (statusEl) { statusEl.textContent = 'Connecting pipes...'; statusEl.style.color = 'var(--text-dim)'; }

    try {
      const r = await fetch('/api/onboarding/packager/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      _lastConnectReceipt = data;

      if (data.ok) {
        if (statusEl) { statusEl.textContent = '✓ Pipes connected & node enrolled'; statusEl.style.color = '#4caf50'; }
        const enr = data.enrollment || {};
        const m = enr.models || {};
        const lp = data.leader_push;
        const leaderLine = lp
          ? (lp.ok ? `✓ Leader handshake OK (${_esc(lp.leader_url)})` : `! Leader push failed (${_esc(lp.error || 'unreachable')})`)
          : (enr.role === 'leader' ? '✓ Running as Hive leader' : '○ Single-node mode (no leader URL set)');

        if (receiptEl) {
          receiptEl.style.display = '';
          receiptEl.innerHTML =
            `<div><strong>Node:</strong> ${_esc(enr.node_id)} (${_esc(enr.role)}) · ${_esc(enr.endpoint_url || '')}</div>` +
            `<div><strong>Role Models:</strong> APEX=<code>${_esc(m.apex || '-')}</code> · FRED=<code>${_esc(m.fred || '-')}</code> · HB=<code>${_esc(m.hb || '-')}</code></div>` +
            `<div><strong>Telemetry Heartbeat:</strong> ${data.sampler_running ? '✓ Running (30s interval)' : '! Not running'}</div>` +
            `<div><strong>Hive Link:</strong> ${leaderLine}</div>`;
        }
        // Refresh cached status
        const sr = await fetch('/api/onboarding/status');
        _status = await sr.json();
      } else {
        if (statusEl) { statusEl.textContent = data.error || 'Enrollment failed'; statusEl.style.color = 'var(--danger)'; }
      }
    } catch (e) {
      if (statusEl) { statusEl.textContent = 'Network error — try again'; statusEl.style.color = 'var(--danger)'; }
    }
    if (btn) btn.disabled = false;
  }

  // ── Step 2: Cloud API Keys ──────────────────────────────────────────────

  function _renderKeyCards() {
    const container = document.getElementById('ob-keys-list');
    if (!container || !_status) return;

    container.innerHTML = _status.cloud_agents.map(a => {
      const isSet = a.key_set;
      return `
        <div class="ob-key-card ${isSet ? 'set' : ''}" data-env="${_esc(a.env_var)}">
          <div class="ob-key-header">
            <span class="ob-key-label">${_esc(a.label)}</span>
            <span class="ob-key-status ${isSet ? 'set' : 'missing'}" id="ob-status-${_esc(a.env_var)}">
              ${isSet ? '✓ configured' : '○ not set'}
            </span>
          </div>
          <div class="ob-key-input-row">
            <input class="ob-key-input" type="password" id="ob-input-${_esc(a.env_var)}"
              placeholder="${isSet ? '••••••••• (already set — paste to replace)' : 'Paste your API key'}"
              autocomplete="off">
            <button onclick="obTestAndSaveKey('${_esc(a.agent)}', '${_esc(a.env_var)}')"
              class="ob-btn-primary" id="ob-save-${_esc(a.env_var)}">Save</button>
          </div>
          <div class="ob-key-msg" id="ob-msg-${_esc(a.env_var)}" style="color:var(--text-dim);"></div>
        </div>`;
    }).join('');
  }

  async function obTestAndSaveKey(agentName, envVar) {
    const input = document.getElementById('ob-input-' + envVar);
    const msg = document.getElementById('ob-msg-' + envVar);
    const btn = document.getElementById('ob-save-' + envVar);
    const status = document.getElementById('ob-status-' + envVar);
    const value = (input && input.value || '').trim();

    if (!value) {
      if (msg) { msg.textContent = 'Please paste a key first'; msg.style.color = 'var(--danger)'; }
      return;
    }

    if (btn) btn.disabled = true;
    if (msg) { msg.textContent = 'Testing key...'; msg.style.color = 'var(--text-dim)'; }

    try {
      // Step 1: Test the key
      const testRes = await fetch('/api/onboarding/test-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ env_var: envVar, value: value }),
      });
      const testData = await testRes.json();

      if (!testData.ok) {
        if (msg) { msg.textContent = testData.message || 'Key validation failed'; msg.style.color = 'var(--danger)'; }
        if (btn) btn.disabled = false;
        return;
      }

      // Step 2: Save the key
      const saveRes = await fetch('/api/agents/key/' + agentName, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key_var: envVar, value: value }),
      });
      const saveData = await saveRes.json();

      if (saveData.ok) {
        if (msg) { msg.textContent = '✓ Key saved and validated'; msg.style.color = '#4caf50'; }
        if (status) { status.textContent = '✓ configured'; status.className = 'ob-key-status set'; }
        if (input) { input.value = ''; input.placeholder = '••••••••• (set)'; }
        // Update cached status
        const agent = (_status.cloud_agents || []).find(a => a.env_var === envVar);
        if (agent) agent.key_set = true;
        const card = document.querySelector(`.ob-key-card[data-env="${envVar}"]`);
        if (card) card.classList.add('set');
      } else {
        if (msg) { msg.textContent = saveData.error || 'Save failed'; msg.style.color = 'var(--danger)'; }
      }
    } catch (e) {
      if (msg) { msg.textContent = 'Network error — try again'; msg.style.color = 'var(--danger)'; }
    }
    if (btn) btn.disabled = false;
  }

  // ── Step 3: Remote Nodes ────────────────────────────────────────────────

  function _renderNodes() {
    const container = document.getElementById('ob-nodes-existing');
    if (!container || !_status) return;

    if (_status.cloud_nodes > 0) {
      container.innerHTML = `
        <div class="ob-check-row">
          <span class="ob-check-icon"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.3"/><path d="M5 7l2 2 4-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          <div>
            <div style="font-size:13px;font-weight:600;color:var(--text);">${_status.cloud_nodes} remote node${_status.cloud_nodes !== 1 ? 's' : ''} connected</div>
            <div style="font-size:11px;color:var(--text-dim);">You can add more below or skip this step.</div>
          </div>
        </div>`;
    } else {
      container.innerHTML = `
        <div style="font-size:12px;color:var(--text-dim);padding:6px 0;">
          No remote nodes connected yet. This is optional — the swarm works fine as a single node.
        </div>`;
    }
  }

  async function obDiscoverNode() {
    const input = document.getElementById('ob-node-url');
    const result = document.getElementById('ob-node-result');
    const btn = document.getElementById('ob-node-discover-btn');
    const url = (input && input.value || '').trim();

    if (!url) {
      if (result) result.textContent = 'Enter a URL first';
      return;
    }

    if (btn) btn.disabled = true;
    if (result) { result.textContent = 'Discovering...'; result.style.color = 'var(--text-dim)'; }

    try {
      const r = await fetch('/api/node/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url }),
      });
      const data = await r.json();

      if (data.registered || data.ok) {
        if (result) { result.textContent = '✓ Node discovered and registered: ' + (data.name || url); result.style.color = '#4caf50'; }
        if (input) input.value = '';
        // Refresh status
        const sr = await fetch('/api/onboarding/status');
        _status = await sr.json();
        _renderNodes();
      } else {
        if (result) { result.textContent = data.error || 'Could not reach that node'; result.style.color = 'var(--danger)'; }
      }
    } catch (e) {
      if (result) { result.textContent = 'Network error'; result.style.color = 'var(--danger)'; }
    }
    if (btn) btn.disabled = false;
  }

  // ── Step 5: Summary / Ready ─────────────────────────────────────────────

  function _renderSummary() {
    const container = document.getElementById('ob-summary');
    if (!container || !_status) return;

    const ol = _status.local_ai.ollama;
    const lm = _status.local_ai.lmstudio;
    const pkg = _status.packager || {};
    const enr = pkg.enrollment || {};
    const m = enr.models || {};
    const keysSet = (_status.cloud_agents || []).filter(a => a.key_set).length;
    const keysTotal = (_status.cloud_agents || []).length;
    const nodes = _status.cloud_nodes || 0;

    const okIcon = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M3 8.5l3 3 7-7" stroke="#4caf50" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const warnIcon = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M2.5 12L8 3l5.5 9z" stroke="#ff9800" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 7.5v2M8 11v.5" stroke="#ff9800" stroke-width="1.3" stroke-linecap="round"/></svg>';
    const dimIcon = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><circle cx="8" cy="8" r="5" stroke="currentColor" stroke-width="1.3" opacity="0.4"/></svg>';

    const rows = [
      {
        icon: pkg.enrolled ? okIcon : warnIcon,
        text: pkg.enrolled
          ? `Node enrolled as <strong>${_esc(enr.node_id)}</strong> (${_esc(enr.role || 'worker')}) — APEX: ${_esc(m.apex || '-')}, FRED: ${_esc(m.fred || '-')}, HB: ${_esc(m.hb || '-')}`
          : 'Node not enrolled yet — go back to step 3 to connect telemetry & role models',
      },
      {
        icon: pkg.sampler_running ? okIcon : warnIcon,
        text: pkg.sampler_running
          ? `Hive telemetry heartbeat active (30s)${enr.leader_url ? ' → ' + _esc(enr.leader_url) : ''}`
          : 'Hive telemetry heartbeat inactive',
      },
      {
        icon: ol.running ? okIcon : (lm.running ? okIcon : warnIcon),
        text: ol.running
          ? (ol.model_count > 0
              ? `Ollama running with ${ol.model_count} model${ol.model_count !== 1 ? 's' : ''}`
              : 'Ollama running but no models installed yet — open Local AI to pull one')
          : (lm.running ? 'LM Studio running' : 'No local AI detected — local agents won\'t work until Ollama is started'),
      },
      {
        icon: keysSet > 0 ? okIcon : dimIcon,
        text: `${keysSet} of ${keysTotal} cloud API keys configured`,
      },
      {
        icon: nodes > 0 ? okIcon : dimIcon,
        text: nodes > 0
          ? `${nodes} remote node${nodes !== 1 ? 's' : ''} connected`
          : 'No remote nodes (single-node mode)',
      },
    ];

    container.innerHTML = rows.map(r =>
      `<div class="ob-summary-row">
        <span class="ob-summary-icon">${r.icon}</span>
        <span style="color:var(--text);">${r.text}</span>
      </div>`
    ).join('');
  }

  function obFinish() {
    const reopenTick = document.getElementById('ob-reopen-every-launch');
    _persistLaunchPreference(!!(reopenTick && reopenTick.checked));
    // Close the enrollment window and open Chat
    if (typeof winManager !== 'undefined' && winManager.close) {
      winManager.close('onboarding');
    }
    if (typeof openWindow === 'function') {
      openWindow('chat', 'Chat', 'view-chat');
    }
  }

  function resetOnboardingWalkthrough() {
    try {
      localStorage.removeItem('swarm_onboarding_complete');
    } catch (e) {}
    _step = 0;
    if (typeof openWindow === 'function') {
      openWindow('onboarding', 'Enrollment', 'view-onboarding');
    }
    setTimeout(() => {
      _initOnboarding();
    }, 120);
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  function _esc(s) {
    if (typeof window !== 'undefined' && window.SwarmChat && typeof window.SwarmChat.esc === 'function') {
      return window.SwarmChat.esc(s);
    }
    return String(s || '').replace(or unenrolled node ───────────────────────

  async function _maybeAutoLaunch() {
    let shouldOpen = false;
    try {
      const reopen = _shouldReopenEveryLaunch();
      const dismissed = localStorage.getItem('swarm_onboarding_complete') === '1';
      if (reopen && !dismissed) {
        shouldOpen = true;
      } else if (!dismissed) {
        // First boot on a new/unenrolled system: check if Hive node is enrolled
        const r = await fetch('/api/onboarding/packager');
        const pkg = await r.json();
        if (pkg && pkg.ok && !pkg.enrolled) {
          shouldOpen = true;
        }
      }
    } catch (e) { return; }
    if (!shouldOpen) return;
    // Auto-open enrollment after a short delay to let the home page render
    setTimeout(() => {
      if (typeof openWindow === 'function') {
        openWindow('onboarding', 'Enrollment', 'view-onboarding');
      }
    }, 800);
  }

  // Expose to global scope
  window.obNext = obNext;
  window.obBack = obBack;
  window.obCheckLocal = obCheckLocal;
  window.obRefreshPackager = obRefreshPackager;
  window.obConnectPipes = obConnectPipes─────────────────────────────────────────

  function _maybeAutoLaunch() {
    try {
      const reopen = _shouldReopenEveryLaunch();
      if (!reopen) return;
      if (localStorage.getItem('swarm_onboarding_complete') === '1') return;
    } catch (e) { return; }
    // Auto-open enrollment after a short delay to let the home page render
    setTimeout(() => {
      if (typeof openWindow === 'function') {
        openWindow('onboarding', 'Enrollment', 'view-onboarding');
      }
    }, 800);
  }

  // Expose to global scope
  window.obNext = obNext;
  window.obBack = obBack;
  window.obCheckLocal = obCheckLocal;
  window.obTestAndSaveKey = obTestAndSaveKey;
  window.obDiscoverNode = obDiscoverNode;
  window.obFinish = obFinish;
  window.resetOnboardingWalkthrough = resetOnboardingWalkthrough;
  window._initOnboarding = _initOnboarding;
  window._obMaybeAutoLaunch = _maybeAutoLaunch;

  // When window opens, init enrollment
  // The window-manager calls load callbacks — we hook into DOMContentLoaded as a fallback
  document.addEventListener('DOMContentLoaded', () => {
    _maybeAutoLaunch();
  });

})();
