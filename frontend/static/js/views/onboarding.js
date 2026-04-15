// onboarding.js — Setup wizard logic
// Drives the 5-step onboarding wizard (Welcome → Local AI → Keys → Nodes → Ready)

(function () {
  'use strict';

  let _step = 0;
  const _totalSteps = 5;
  let _status = null; // cached /api/onboarding/status response

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
    if (_step === 1) obCheckLocal();
    if (_step === 2) _renderKeyCards();
    if (_step === 3) _renderNodes();
    if (_step === 4) _renderSummary();
  }

  // ── Step 1: Local AI ────────────────────────────────────────────────────

  async function obCheckLocal() {
    const ollamaIcon = document.getElementById('ob-ollama-icon');
    const ollamaDetail = document.getElementById('ob-ollama-detail');
    const lmsIcon = document.getElementById('ob-lmstudio-icon');
    const lmsDetail = document.getElementById('ob-lmstudio-detail');
    const helpEl = document.getElementById('ob-local-help');

    if (ollamaIcon) ollamaIcon.textContent = '⏳';
    if (ollamaDetail) ollamaDetail.textContent = 'Checking...';
    if (lmsIcon) lmsIcon.textContent = '⏳';
    if (lmsDetail) lmsDetail.textContent = 'Checking...';

    try {
      const r = await fetch('/api/onboarding/status');
      _status = await r.json();
      const ol = _status.local_ai.ollama;
      const lm = _status.local_ai.lmstudio;

      if (ollamaIcon) ollamaIcon.textContent = ol.running ? '✅' : '❌';
      if (ollamaDetail) ollamaDetail.textContent = ol.running
        ? `Running — ${ol.model_count} model${ol.model_count !== 1 ? 's' : ''} installed`
        : 'Not reachable on localhost:11434';

      if (lmsIcon) lmsIcon.textContent = lm.running ? '✅' : '⚪';
      if (lmsDetail) lmsDetail.textContent = lm.running
        ? `Running — ${lm.models} model${lm.models !== 1 ? 's' : ''} loaded`
        : 'Not running (optional)';

      if (helpEl) helpEl.style.display = (!ol.running && !lm.running) ? '' : 'none';
    } catch (e) {
      if (ollamaIcon) ollamaIcon.textContent = '⚠️';
      if (ollamaDetail) ollamaDetail.textContent = 'Could not check — API error';
    }
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
          <span class="ob-check-icon">🌐</span>
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

  // ── Step 4: Summary / Ready ─────────────────────────────────────────────

  function _renderSummary() {
    const container = document.getElementById('ob-summary');
    if (!container || !_status) return;

    const ol = _status.local_ai.ollama;
    const lm = _status.local_ai.lmstudio;
    const keysSet = (_status.cloud_agents || []).filter(a => a.key_set).length;
    const keysTotal = (_status.cloud_agents || []).length;
    const nodes = _status.cloud_nodes || 0;

    const rows = [
      {
        icon: ol.running ? '✅' : (lm.running ? '✅' : '⚠️'),
        text: ol.running
          ? `Ollama running with ${ol.model_count} model${ol.model_count !== 1 ? 's' : ''}`
          : (lm.running ? 'LM Studio running' : 'No local AI detected — local agents won\'t work until Ollama is started'),
      },
      {
        icon: keysSet > 0 ? '✅' : '⚪',
        text: `${keysSet} of ${keysTotal} cloud API keys configured`,
      },
      {
        icon: nodes > 0 ? '✅' : '⚪',
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
    try { localStorage.setItem('swarm_onboarding_complete', '1'); } catch (e) {}
    // Close the wizard window and open Chat
    if (typeof winManager !== 'undefined' && winManager.close) {
      winManager.close('onboarding');
    }
    if (typeof openWindow === 'function') {
      openWindow('chat', '💬 Chat', 'view-chat');
    }
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // ── Auto-init ───────────────────────────────────────────────────────────

  async function _initOnboarding() {
    // Fetch initial status
    try {
      const r = await fetch('/api/onboarding/status');
      _status = await r.json();
    } catch (e) {
      _status = { local_ai: { ollama: { running: false }, lmstudio: { running: false }, ready: false }, cloud_agents: [], cloud_agents_configured: 0, cloud_agents_total: 0, cloud_nodes: 0, complete: false };
    }
    _step = 0;
    _renderStep();
  }

  // ── Auto-launch on first visit ──────────────────────────────────────────

  function _maybeAutoLaunch() {
    try {
      if (localStorage.getItem('swarm_onboarding_complete') === '1') return;
    } catch (e) { return; }
    // Auto-open the wizard after a short delay to let the home page render
    setTimeout(() => {
      if (typeof openWindow === 'function') {
        openWindow('onboarding', '🧭 Setup Wizard', 'view-onboarding');
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
  window._initOnboarding = _initOnboarding;
  window._obMaybeAutoLaunch = _maybeAutoLaunch;

  // When window opens, init the wizard
  // The window-manager calls load callbacks — we hook into DOMContentLoaded as a fallback
  document.addEventListener('DOMContentLoaded', () => {
    _maybeAutoLaunch();
  });

})();
