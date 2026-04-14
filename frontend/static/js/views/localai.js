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

function localaiRefresh() {
  const badge = document.getElementById('localai-overall-status');
  if (badge) badge.textContent = 'checking...';
  fetch('/api/localai/status')
    .then(r => r.json())
    .then(data => {
      _localaiStatus = data;
      _renderOllama(data.ollama);
      _renderLMStudio(data.lmstudio);
      _renderPicoclaw(data.picoclaw);
      _renderAgentRoster(data);
      if (badge) {
        const allOk = data.ollama?.running;
        badge.textContent = allOk ? 'ollama online' : 'partial';
        badge.style.background = allOk ? 'color-mix(in srgb,#22c55e 15%,var(--card))' : 'color-mix(in srgb,#f59e0b 15%,var(--card))';
        badge.style.color = allOk ? '#22c55e' : '#f59e0b';
        badge.style.borderColor = allOk ? '#22c55e55' : '#f59e0b55';
      }
    })
    .catch(() => {
      if (badge) { badge.textContent = 'error'; badge.style.color = 'var(--danger)'; }
    });
}

function _badge(running, extraLabel) {
  const label = extraLabel || (running ? 'online' : 'offline');
  return `background:${running
    ? 'color-mix(in srgb,#22c55e 15%,var(--card))'
    : 'color-mix(in srgb,#ef4444 15%,var(--card))'};
    color:${running ? '#22c55e' : '#ef4444'};
    border:1px solid ${running ? '#22c55e55' : '#ef444455'}`;
}

function _renderOllama(ollama) {
  const badge = document.getElementById('ollama-status-badge');
  const list  = document.getElementById('ollama-models-list');
  const sel   = document.getElementById('ollama-model-select');
  if (!badge || !list || !sel) return;

  badge.textContent = ollama?.running ? `${(ollama.models||[]).length} models` : 'offline';
  badge.style.cssText = _badge(ollama?.running);

  if (!ollama?.running) {
    list.textContent = 'Ollama not running — start with: ollama serve';
    sel.innerHTML = '<option>—</option>';
    return;
  }

  const models = ollama.models || [];
  list.innerHTML = models.map(m =>
    `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid var(--border);">
      <span style="color:var(--text);font-size:12px;">${m.name}</span>
      <span style="margin-left:auto;color:var(--text-dim);font-size:11px;">${m.params} · ${m.size_gb}GB</span>
     </div>`
  ).join('') || '<div style="color:var(--text-dim)">No models loaded</div>';

  sel.innerHTML = models.map(m => `<option value="${m.name}">${m.name} (${m.params})</option>`).join('');
}

function _renderLMStudio(lms) {
  const badge = document.getElementById('lmstudio-status-badge');
  const info  = document.getElementById('lmstudio-model-info');
  if (!badge || !info) return;

  badge.textContent = lms?.running ? 'online' : 'offline';
  badge.style.cssText = _badge(lms?.running);

  if (!lms?.running) {
    info.innerHTML = `<div>LM Studio is not running.</div>
      <div style="margin-top:4px;color:var(--accent);">Start LM Studio, load a model, then refresh.</div>
      <div style="margin-top:6px;font-size:11px;">When running, use the <strong>lmstudio</strong> agent in Chat for full conversation support.</div>`;
    return;
  }

  const loaded = lms.loaded || 'unknown';
  info.innerHTML = `<div style="margin-bottom:4px;"><strong>Loaded:</strong> ${loaded}</div>
    <div style="font-size:11px;color:var(--text-dim);">All models: ${(lms.models||[]).join(', ') || '—'}</div>
    <div style="margin-top:6px;font-size:11px;">Use <strong>lmstudio</strong> agent in Chat for full conversation with memory.</div>`;
}

function _renderPicoclaw(pc) {
  const badge = document.getElementById('picoclaw-status-badge');
  if (!badge) return;
  badge.textContent = pc?.running ? 'running' : 'offline';
  badge.style.cssText = _badge(pc?.running);
}

function _renderAgentRoster(data) {
  const el = document.getElementById('localai-agent-roster');
  if (!el) return;
  const ollamaRunning   = data?.ollama?.running;
  const lmsRunning      = data?.lmstudio?.running;
  const ollamaModels    = (data?.ollama?.models || []).map(m => m.name);

  el.innerHTML = _LOCAL_AGENTS.map(a => {
    const available = a.source === 'ollama'
      ? (ollamaRunning && ollamaModels.some(m => m.startsWith(a.name === 'deepseek_local' ? 'deepseek-r1' : a.name === 'llama' ? 'llama' : a.name)))
      : (a.source === 'lmstudio' ? lmsRunning : false);
    const dot = available ? '#22c55e' : '#94a3b8';
    return `<div style="border:1px solid var(--border);border-radius:7px;padding:10px;background:var(--bg);">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
        <span style="width:7px;height:7px;border-radius:50%;background:${dot};flex-shrink:0;"></span>
        <span style="font-weight:600;font-size:12px;">${a.label}</span>
        <span style="margin-left:auto;font-size:10px;color:var(--text-dim);">${a.source}</span>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">${a.desc}</div>
      <div style="font-size:10px;color:var(--text-dim);">${a.model}</div>
      <div style="margin-top:6px;">
        <button onclick="localaiOpenChat('${a.name}')"
          style="font-size:11px;padding:3px 10px;border-radius:5px;border:1px solid var(--border);
                 background:var(--card);color:var(--text);cursor:pointer;">
          Open in Chat
        </button>
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
  const result = document.getElementById('lmstudio-quick-result');
  if (!prompt || !result) return;
  result.style.display = 'block';
  result.textContent = 'Thinking...';
  fetch('/api/localai/lmstudio/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: prompt}),
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
