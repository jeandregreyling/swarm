/* views/localai.js — Local AI tile: Ollama · LM Studio · Picoclaw */

const _LOCAL_AGENTS = [
  { name: 'gemma',          label: 'Gemma',           model: 'gemma3:4.3B',      source: 'ollama',   desc: 'Orchestrator, front of house'   },
  { name: 'qwen',           label: 'Qwen',            model: 'qwen2.5:7.6B',     source: 'ollama',   desc: 'Deep reasoning analyst'         },
  { name: 'llama',          label: 'LLaMA',           model: 'llama3.2:3.2B',    source: 'ollama',   desc: 'Fast researcher'                },
  { name: 'mistral',        label: 'Mistral',         model: 'mistral:7.2B',     source: 'ollama',   desc: 'Developer agent, file access'   },
  { name: 'phi3',           label: 'Phi-3 Mini',      model: 'phi3:mini 3.8B',   source: 'ollama',   desc: 'Lightweight, fastest'           },
  { name: 'deepseek_local', label: 'DeepSeek R1',     model: 'deepseek-r1:7.6B', source: 'ollama',   desc: 'Local reasoning, fully offline'  },
  { name: 'lmstudio',       label: 'LM Studio',       model: 'dynamic',          source: 'lmstudio', desc: 'Whatever model is loaded'       },
];

let _localaiStatus = null;
let _ollamaInventory = [];
let _ollamaLoadedMap = {};
let _ollamaMetaCache = {};
let _ollamaSelectedModel = null;
let _lmStudioSelectedModel = null;
let _ollamaPullCatalog = [];

/* ── Pull state (pause / resume) ── */
let _pullAbort = null;       // AbortController for active stream
let _pullActiveModel = null; // model name being pulled
let _pullPaused = false;     // true when user paused

const _OLLAMA_DEFAULT_LIBRARY = [
  'gemma3:latest',
  'gemma3:4b',
  'llama3.2:3b',
  'llama3.1:8b',
  'mistral:7b',
  'qwen2.5:7b',
  'phi3:mini',
  'deepseek-r1:7b',
  'nomic-embed-text:latest',
  'snowflake-arctic-embed2:latest',
];

function _localaiSetBadge(el, running, label) {
  if (!el) return;
  el.textContent = label;
  el.style.background = running
    ? 'color-mix(in srgb,#22c55e 15%,var(--card))'
    : 'color-mix(in srgb,#ef4444 15%,var(--card))';
  el.style.color = running ? '#22c55e' : '#ef4444';
  el.style.borderColor = running ? '#22c55e55' : '#ef444455';
}

function _setOllamaStatus(message, state) {
  const el = document.getElementById('ollama-action-status');
  if (!el) return;
  el.textContent = message;
  if (state) el.dataset.state = state;
  else delete el.dataset.state;
}

function _findLoadedModel(name) {
  return _ollamaLoadedMap[name] || _ollamaLoadedMap[(name || '').replace(':latest', '')] || null;
}

function _formatBytesToGb(bytes) {
  const value = Number(bytes || 0);
  if (!value) return '—';
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function _formatCountLabel(installedCount, loadedCount) {
  return `${installedCount} installed · ${loadedCount} loaded`;
}

function _escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _fetchJson(url, fallback) {
  return fetch(url)
    .then(r => r.json())
    .catch(() => fallback);
}

async function localaiRefreshModelCatalog(silent) {
  try {
    const response = await fetch('/api/ollama/library');
    const data = await response.json();
    const remote = Array.isArray(data.models) ? data.models : [];
    const installed = (_ollamaInventory || []).map(m => m.name).filter(Boolean);
    const merged = Array.from(new Set([...installed, ...remote, ..._OLLAMA_DEFAULT_LIBRARY]))
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b));
    _ollamaPullCatalog = merged;
    _renderOllamaPullCatalog();
    if (!silent) _setOllamaStatus(`Model catalog refreshed (${merged.length} entries).`, 'ok');
  } catch (error) {
    const installed = (_ollamaInventory || []).map(m => m.name).filter(Boolean);
    _ollamaPullCatalog = Array.from(new Set([...installed, ..._OLLAMA_DEFAULT_LIBRARY])).sort((a, b) => a.localeCompare(b));
    _renderOllamaPullCatalog();
    if (!silent) _setOllamaStatus(`Catalog refresh failed; using fallback list (${error.message}).`, 'error');
  }
}

function _renderOllamaPullCatalog() {
  const datalist = document.getElementById('ollama-pull-datalist');
  const input = document.getElementById('ollama-pull-select');
  if (!datalist) return;
  if (!_ollamaPullCatalog.length) {
    datalist.innerHTML = '';
    if (input) input.placeholder = 'No catalog models available';
    return;
  }
  datalist.innerHTML = _ollamaPullCatalog.map(name => {
    const safe = _escapeHtml(name);
    return `<option value="${safe}">`;
  }).join('');
  if (input) input.placeholder = 'Type to search models…';
}

function localaiRefresh() {
  const badge = document.getElementById('localai-overall-status');
  if (badge) {
    badge.textContent = 'checking...';
    badge.style.background = 'color-mix(in srgb,#f59e0b 15%,var(--card))';
    badge.style.color = '#f59e0b';
    badge.style.borderColor = '#f59e0b55';
  }
  _setOllamaStatus('Checking Ollama…', 'busy');

  Promise.all([
    _fetchJson('/api/localai/status', { ollama: { running: false, models: [] }, lmstudio: { running: false }, picoclaw: { running: false } }),
    _fetchJson('/api/ollama/models', { models: [] }),
    _fetchJson('/api/ollama/ps', { models: [], count: 0 }),
  ]).then(([data, inventory, loaded]) => {
    _localaiStatus = data;
    _ollamaInventory = Array.isArray(inventory.models) ? inventory.models : [];
    _ollamaLoadedMap = {};
    (Array.isArray(loaded.models) ? loaded.models : []).forEach(model => {
      const modelName = model.name || model.model || '';
      if (modelName) _ollamaLoadedMap[modelName] = model;
    });

    if (!_ollamaSelectedModel || !_ollamaInventory.some(m => m.name === _ollamaSelectedModel)) {
      _ollamaSelectedModel = _ollamaInventory[0]?.name || null;
    }

    _renderOllama(data.ollama, _ollamaInventory, loaded.models || []);
    _renderLMStudio(data.lmstudio);
    _renderPicoclaw(data.picoclaw);
    _renderAgentRoster(data);
    localaiRefreshModelCatalog(true);

    const overall = data.ollama?.running ? 'ollama online' : (data.lmstudio?.running || data.picoclaw?.running ? 'partial' : 'offline');
    if (badge) {
      const isHealthy = data.ollama?.running;
      badge.textContent = overall;
      badge.style.background = isHealthy
        ? 'color-mix(in srgb,#22c55e 15%,var(--card))'
        : (overall === 'partial' ? 'color-mix(in srgb,#f59e0b 15%,var(--card))' : 'color-mix(in srgb,#ef4444 15%,var(--card))');
      badge.style.color = isHealthy ? '#22c55e' : (overall === 'partial' ? '#f59e0b' : '#ef4444');
      badge.style.borderColor = isHealthy ? '#22c55e55' : (overall === 'partial' ? '#f59e0b55' : '#ef444455');
    }

    _setOllamaStatus(data.ollama?.running
      ? `Ready · ${_formatCountLabel(_ollamaInventory.length, loaded.count || 0)}`
      : 'Ollama is offline. Start with: ollama serve', data.ollama?.running ? 'ok' : 'error');

    if (_ollamaSelectedModel) {
      selectOllamaModel(_ollamaSelectedModel, true);
    }
  }).catch(() => {
    if (badge) {
      badge.textContent = 'error';
      badge.style.color = 'var(--danger)';
    }
    _setOllamaStatus('Could not load Local AI status.', 'error');
  });
}

function _renderOllama(ollama, installedModels, loadedModels) {
  const badge = document.getElementById('ollama-status-badge');
  const list  = document.getElementById('ollama-models-list');
  const sel   = document.getElementById('ollama-model-select');
  const detail = document.getElementById('ollama-selected-meta');
  if (!badge || !list || !sel || !detail) return;

  _localaiSetBadge(badge, !!ollama?.running, ollama?.running ? _formatCountLabel(installedModels.length, loadedModels.length) : 'offline');

  if (!ollama?.running) {
    list.innerHTML = '<div class="docs-empty-state docs-empty-compact">Ollama not running. Start with: ollama serve</div>';
    sel.innerHTML = '<option>—</option>';
    detail.textContent = 'Ollama metadata is unavailable until the service is running.';
    return;
  }

  list.innerHTML = installedModels.length ? installedModels.map(model => {
    const name = model.name || '';
    const loaded = _findLoadedModel(name);
    const active = name === _ollamaSelectedModel;
    const params = model.parameters || model.params || 'unknown size';
    const family = model.family || 'local';
    return `<button type="button" class="localai-model-row${active ? ' is-active' : ''}${loaded ? ' is-loaded' : ''}" onclick="selectOllamaModel(${JSON.stringify(name)})">
      <div class="localai-model-main">
        <div class="localai-model-name">${name}</div>
        <div class="localai-model-meta">${params} · ${family} · ${_formatBytesToGb(model.size)}</div>
      </div>
      <span class="localai-model-state" data-state="${loaded ? 'loaded' : 'installed'}">${loaded ? 'loaded' : 'installed'}</span>
    </button>`;
  }).join('') : '<div class="docs-empty-state docs-empty-compact">No Ollama models installed yet.</div>';

  sel.innerHTML = installedModels.length
    ? installedModels.map(m => `<option value="${m.name}" ${m.name === _ollamaSelectedModel ? 'selected' : ''}>${m.name}</option>`).join('')
    : '<option>—</option>';
}

async function selectOllamaModel(name, silent) {
  if (!name) return;
  _ollamaSelectedModel = name;
  _renderOllama(_localaiStatus?.ollama || { running: false }, _ollamaInventory, Object.values(_ollamaLoadedMap));
  const sel = document.getElementById('ollama-model-select');
  if (sel) sel.value = name;
  await ollamaRefreshSelected(silent !== false);
}

async function ollamaRefreshSelected(skipStatusUpdate) {
  const name = _ollamaSelectedModel;
  const detail = document.getElementById('ollama-selected-meta');
  if (!name || !detail) return;

  detail.innerHTML = '<div class="docs-empty-state docs-empty-compact">Loading model metadata…</div>';
  try {
    const response = await fetch(`/api/ollama/show/${encodeURIComponent(name)}`);
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    _ollamaMetaCache[name] = data;
    const loaded = _findLoadedModel(name);
    detail.innerHTML = `
      <div class="localai-detail-row"><span class="localai-detail-label">Model</span><span class="localai-detail-value">${name}</span></div>
      <div class="localai-detail-row"><span class="localai-detail-label">State</span><span class="localai-detail-value">${loaded ? `Loaded · ${loaded.size_vram_gb || 0} GB VRAM` : 'Installed only'}</span></div>
      <div class="localai-detail-row"><span class="localai-detail-label">Family</span><span class="localai-detail-value">${data.details?.family || '—'}</span></div>
      <div class="localai-detail-row"><span class="localai-detail-label">Parameters</span><span class="localai-detail-value">${data.details?.parameter_size || data.parameters || '—'}</span></div>
      <div class="localai-detail-row"><span class="localai-detail-label">Quantization</span><span class="localai-detail-value">${data.details?.quantization_level || '—'}</span></div>
      <div class="localai-detail-row"><span class="localai-detail-label">Format</span><span class="localai-detail-value">${data.details?.format || '—'}</span></div>
      <div class="localai-detail-row"><span class="localai-detail-label">Capabilities</span><span class="localai-detail-value">${(data.capabilities || []).join(', ') || 'standard'}</span></div>`;
    if (!skipStatusUpdate) _setOllamaStatus(`Metadata refreshed for ${name}.`, 'ok');
  } catch (error) {
    detail.innerHTML = `<div class="docs-error-state">${error.message}</div>`;
    _setOllamaStatus(`Failed to inspect ${name}: ${error.message}`, 'error');
  }
}

function _ollamaSelectedActionModel() {
  const select = document.getElementById('ollama-model-select');
  return _ollamaSelectedModel || select?.value || null;
}

async function _ollamaPostAction(path, body, successMessage) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  _setOllamaStatus(successMessage, 'ok');
  return data;
}

async function ollamaLoadSelected() {
  const model = _ollamaSelectedActionModel();
  if (!model) return;
  _setOllamaStatus(`Loading ${model}…`, 'busy');
  try {
    await _ollamaPostAction('/api/ollama/load', { model }, `${model} loaded.`);
    localaiRefresh();
  } catch (error) {
    _setOllamaStatus(`Load failed: ${error.message}`, 'error');
  }
}

async function ollamaUnloadSelected() {
  const model = _ollamaSelectedActionModel();
  if (!model) return;
  _setOllamaStatus(`Unloading ${model}…`, 'busy');
  try {
    await _ollamaPostAction('/api/ollama/unload', { model }, `${model} unloaded.`);
    localaiRefresh();
  } catch (error) {
    _setOllamaStatus(`Unload failed: ${error.message}`, 'error');
  }
}

async function ollamaDeleteSelected() {
  const model = _ollamaSelectedActionModel();
  if (!model) return;
  if (!confirm(`Delete ${model} from local Ollama storage?`)) return;
  _setOllamaStatus(`Deleting ${model}…`, 'busy');
  try {
    await _ollamaPostAction('/api/ollama/delete', { model }, `${model} deleted.`);
    if (_ollamaSelectedModel === model) _ollamaSelectedModel = null;
    localaiRefresh();
  } catch (error) {
    _setOllamaStatus(`Delete failed: ${error.message}`, 'error');
  }
}

async function ollamaPullModel(resumeModel) {
  const input = document.getElementById('ollama-pull-input');
  const select = document.getElementById('ollama-pull-select');
  const model = resumeModel || input?.value?.trim() || select?.value || '';
  if (!model) {
    _setOllamaStatus('Choose or enter a model name to pull.', 'error');
    return;
  }

  // Abort any existing pull stream
  if (_pullAbort) { try { _pullAbort.abort(); } catch {} }
  _pullAbort = new AbortController();
  _pullActiveModel = model;
  _pullPaused = false;

  _setOllamaStatus(`Pulling ${model}…`, 'busy');
  _pullRenderControls(true);

  // Insert progress bar below status strip
  let _pullBar = document.getElementById('ollama-pull-bar');
  if (!_pullBar) {
    const strip = document.getElementById('ollama-action-status');
    if (strip) {
      _pullBar = document.createElement('div');
      _pullBar.id = 'ollama-pull-bar';
      _pullBar.className = 'localai-pull-progress';
      _pullBar.innerHTML = '<div class="localai-pull-progress-fill" id="ollama-pull-bar-fill"></div>';
      strip.after(_pullBar);
    }
  }
  const _pullFill = document.getElementById('ollama-pull-bar-fill');

  try {
    const response = await fetch('/api/ollama/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
      signal: _pullAbort.signal,
    });
    if (!response.body) throw new Error('No pull stream available');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let _pullStart = Date.now();
    let _pullLastBytes = 0;
    let _pullLastTime = _pullStart;
    let _pullSpeed = 0;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.error) throw new Error(event.error);
        if (event.status === 'done') {
          _setOllamaStatus(`${model} pulled successfully.`, 'ok');
          if (_pullFill) _pullFill.style.width = '100%';
        } else {
          const completed = Number(event.completed || 0);
          const total = Number(event.total || 0);
          const pct = total ? Math.round((completed / total) * 100) : 0;
          if (_pullFill && total) _pullFill.style.width = pct + '%';

          // Calculate speed + ETA
          let speedStr = '';
          let etaStr = '';
          const now = Date.now();
          const dtMs = now - _pullLastTime;
          if (dtMs > 500 && completed > _pullLastBytes) {
            _pullSpeed = ((completed - _pullLastBytes) / (dtMs / 1000));
            _pullLastBytes = completed;
            _pullLastTime = now;
          }
          if (_pullSpeed > 0) {
            speedStr = _pullSpeed >= 1024 * 1024
              ? `${(_pullSpeed / 1024 / 1024).toFixed(1)} MB/s`
              : `${(_pullSpeed / 1024).toFixed(0)} KB/s`;
            const remaining = total - completed;
            if (remaining > 0) {
              const etaSec = Math.round(remaining / _pullSpeed);
              etaStr = etaSec >= 60 ? `${Math.floor(etaSec / 60)}m ${etaSec % 60}s` : `${etaSec}s`;
            }
          }

          const extra = [
            total ? `${pct}%` : '',
            speedStr,
            etaStr ? `ETA ${etaStr}` : '',
          ].filter(Boolean).join(' · ');
          _setOllamaStatus(`${model} · ${event.status || 'pulling'}${extra ? ' · ' + extra : ''}`, 'busy');
        }
      }
    }
    if (input) input.value = '';
    if (select) select.value = model;
    _pullActiveModel = null;
    localaiRefresh();
  } catch (error) {
    if (error.name === 'AbortError') {
      // Paused by user — keep state for resume
      if (_pullPaused) {
        _setOllamaStatus(`${model} — paused. Click Resume to continue.`, 'warn');
        return; // don't clean up bar or state
      }
    }
    _setOllamaStatus(`Pull failed: ${error.message}`, 'error');
    _pullActiveModel = null;
  } finally {
    _pullAbort = null;
    if (!_pullPaused) {
      _pullRenderControls(false);
      const bar = document.getElementById('ollama-pull-bar');
      if (bar) setTimeout(() => bar.remove(), 2000);
    }
  }
}

function ollamaPausePull() {
  if (!_pullAbort || !_pullActiveModel) return;
  _pullPaused = true;
  try { _pullAbort.abort(); } catch {}
  _pullRenderControls(false);
  // Show resume button
  const wrap = document.getElementById('ollama-pull-controls');
  if (wrap) {
    wrap.innerHTML = `<button onclick="ollamaPullModel('${_pullActiveModel.replace(/'/g, "\\'")}')" class="knowledge-btn" title="Resume download">▶ Resume</button>`
      + `<button onclick="ollamaCancelPull()" class="localai-danger-btn" title="Cancel download">✕</button>`;
    wrap.style.display = '';
  }
}

function ollamaCancelPull() {
  if (_pullAbort) { try { _pullAbort.abort(); } catch {} }
  _pullActiveModel = null;
  _pullPaused = false;
  _pullAbort = null;
  _setOllamaStatus('Pull cancelled.', 'error');
  _pullRenderControls(false);
  const bar = document.getElementById('ollama-pull-bar');
  if (bar) bar.remove();
}

function _pullRenderControls(pulling) {
  let wrap = document.getElementById('ollama-pull-controls');
  if (!wrap) {
    const row = document.querySelector('#ollama-pull-input')?.parentElement;
    if (!row) return;
    wrap = document.createElement('span');
    wrap.id = 'ollama-pull-controls';
    wrap.style.display = 'none';
    row.appendChild(wrap);
  }
  if (pulling) {
    wrap.innerHTML = `<button onclick="ollamaPausePull()" class="knowledge-btn" title="Pause download">⏸ Pause</button>`
      + `<button onclick="ollamaCancelPull()" class="localai-danger-btn" title="Cancel download">✕</button>`;
    wrap.style.display = '';
  } else if (!_pullPaused) {
    wrap.style.display = 'none';
    wrap.innerHTML = '';
  }
}

async function ollamaCreateVariant() {
  const base = _ollamaSelectedActionModel();
  const name = document.getElementById('ollama-create-name')?.value?.trim();
  const system = document.getElementById('ollama-create-system')?.value?.trim() || '';
  if (!base) return _setOllamaStatus('Select a base model first.', 'error');
  if (!name) return _setOllamaStatus('Enter a name for the new model.', 'error');
  _setOllamaStatus(`Creating ${name} from ${base}…`, 'busy');
  try {
    await _ollamaPostAction('/api/ollama/create', { name, base, system }, `${name} created from ${base}.`);
    document.getElementById('ollama-create-name').value = '';
    document.getElementById('ollama-create-system').value = '';
    localaiRefresh();
  } catch (error) {
    _setOllamaStatus(`Create failed: ${error.message}`, 'error');
  }
}

function _renderLMStudio(lms) {
  const badge = document.getElementById('lmstudio-status-badge');
  const info  = document.getElementById('lmstudio-model-info');
  const modelSelect = document.getElementById('lmstudio-model-select');
  if (!badge || !info) return;

  _localaiSetBadge(badge, !!lms?.running, lms?.running ? 'online' : 'offline');

  if (!lms?.running) {
    if (modelSelect) modelSelect.innerHTML = '<option value="">LM Studio offline</option>';
    info.innerHTML = `<div class="localai-copy">LM Studio is not running.</div>
      <div class="localai-muted">Start LM Studio, load a model, then refresh. When running, use the <strong>lmstudio</strong> agent in Chat for full conversation support.</div>`;
    return;
  }

  const models = Array.isArray(lms.models) ? lms.models : [];
  const loaded = lms.loaded || 'unknown';
  if (!_lmStudioSelectedModel || !models.includes(_lmStudioSelectedModel)) {
    _lmStudioSelectedModel = lms.loaded || models[0] || null;
  }
  if (modelSelect) {
    modelSelect.innerHTML = models.length
      ? models.map(m => {
        const safe = _escapeHtml(m);
        return `<option value="${safe}" ${m === _lmStudioSelectedModel ? 'selected' : ''}>${safe}</option>`;
      }).join('')
      : `<option value="${_escapeHtml(loaded)}">${_escapeHtml(loaded)}</option>`;
    if (_lmStudioSelectedModel) modelSelect.value = _lmStudioSelectedModel;
  }
  info.innerHTML = `<div class="localai-detail-row"><span class="localai-detail-label">Loaded</span><span class="localai-detail-value">${loaded}</span></div>
    <div class="localai-muted">All models: ${(models || []).join(', ') || '—'}</div>
    <div class="localai-copy">Use <strong>lmstudio</strong> agent in Chat for full conversation with memory.</div>`;
}

function localaiSelectLMStudioModel(name) {
  _lmStudioSelectedModel = name || null;
}

function _renderPicoclaw(pc) {
  const badge = document.getElementById('picoclaw-status-badge');
  if (!badge) return;
  _localaiSetBadge(badge, !!pc?.running, pc?.running ? 'running' : 'offline');
}

function _renderAgentRoster(data) {
  const el = document.getElementById('localai-agent-roster');
  if (!el) return;
  const ollamaRunning   = data?.ollama?.running;
  const lmsRunning      = data?.lmstudio?.running;
  const ollamaModels    = (data?.ollama?.models || []).map(m => m.name);

  el.innerHTML = _LOCAL_AGENTS.map(a => {
    const prefix = (a.name === 'deepseek_local' ? 'deepseek-r1' : a.name === 'llama' ? 'llama' : a.name).toLowerCase();
    const available = a.source === 'ollama'
      ? (ollamaRunning && ollamaModels.some(m => m.toLowerCase().startsWith(prefix)))
      : (a.source === 'lmstudio' ? lmsRunning : false);
    const dot = available ? '#22c55e' : '#ef4444';
    return `<div class="localai-agent-card">
      <div class="localai-agent-top">
        <span class="localai-agent-dot" style="background:${dot};"></span>
        <span class="localai-agent-title">${a.label}</span>
        <span class="localai-agent-source">${a.source}</span>
      </div>
      <div class="localai-agent-copy">${a.desc}</div>
      <div class="localai-agent-model">${a.model}</div>
      <div class="localai-action-row">
        <button onclick="localaiOpenChat('${a.name}')" class="knowledge-btn">Open in Chat</button>
      </div>
    </div>`;
  }).join('');
}

function localaiOpenChat(agentName) {
  // Switch to chat view and pre-select the agent
  if (typeof openWindow === 'function') openWindow('chat', 'Chat', 'view-chat');
  // Give the chat view a moment to render, then select the agent
  setTimeout(() => {
    const toggles = document.querySelectorAll('.agent-toggle-btn, [data-agent]');
    toggles.forEach(btn => {
      const name = (btn.dataset.agent || btn.textContent || '').toLowerCase();
      if (name === agentName.toLowerCase()) btn.click();
    });
  }, 400);
}

function localaiOllamaChat() {
  const prompt = (document.getElementById('ollama-quick-prompt') || {}).value?.trim();
  const model  = (document.getElementById('ollama-model-select') || {}).value;
  const result = document.getElementById('ollama-quick-result');
  if (!prompt || !model || !result) return;
  result.style.display = 'block';
  result.textContent = 'Thinking...';
  fetch('/api/localai/ollama/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model, message: prompt}),
  })
    .then(r => r.json())
    .then(d => { result.textContent = d.ok ? d.answer : `Error: ${d.error}`; })
    .catch(e => { result.textContent = `Error: ${e}`; });
}

function localaiLMStudioChat() {
  const prompt = (document.getElementById('lmstudio-quick-prompt') || {}).value?.trim();
  const selected = (document.getElementById('lmstudio-model-select') || {}).value;
  const result = document.getElementById('lmstudio-quick-result');
  if (!prompt || !result) return;
  result.style.display = 'block';
  result.textContent = 'Thinking...';
  fetch('/api/localai/lmstudio/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: prompt, model: selected || _lmStudioSelectedModel || undefined}),
  })
    .then(r => r.json())
    .then(d => { result.textContent = d.ok ? d.answer : `Error: ${d.error}`; })
    .catch(e => { result.textContent = `Error: ${e}`; });
}

function localaiTogglePicoEmbed() {
  const container = document.getElementById('pico-embed-container');
  const btn       = document.getElementById('pico-embed-btn');
  if (!container) return;
  const visible = container.style.display !== 'none';
  container.style.display = visible ? 'none' : 'block';
  if (btn) btn.textContent = visible ? 'Embed' : 'Close';
}

function initializeLocalAiPanel() {
  localaiRefresh();
}
