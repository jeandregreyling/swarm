// Ollama model panel
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// OLLAMA MODEL PANEL
// ═══════════════════════════════════════════════════════════════════════════

// Swarm models in display order — matches orchestrator.py AGENTS
const SWARM_MODELS = [
  'gemma3:latest', 'gemma4:26b', 'llama3.2:latest',
  'qwen2.5:latest', 'qwen:latest', 'deepseek-r1:7b',
];

function loadOllamaPanel() {
  Promise.all([
    fetch('/api/ollama/models').then(r => r.json()).catch(() => ({ models: [] })),
    fetch('/api/monitor').then(r => r.json()).catch(() => ({ active_models: [] })),
  ]).then(([installed, monitor]) => {
    const installedMap = {};
    (Array.isArray(installed.models) ? installed.models : []).forEach(m => {
      if (m && m.name) installedMap[m.name] = m;
    });

    const loadedMap = {};
    (Array.isArray(monitor.active_models) ? monitor.active_models : []).forEach(m => {
      if (m && m.name) loadedMap[m.name] = m;
    });

    const rows = SWARM_MODELS.map(name => {
      const inst    = installedMap[name];
      const loaded  = loadedMap[name];
      const missing = !inst;

      let dotCls, memText, rowCls, clickAttr;

      if (missing) {
        dotCls    = 'dot-none';
        memText   = 'not installed';
        rowCls    = 'row-missing';
        clickAttr = '';
      } else if (loaded) {
        const vramGb = Number(loaded.size_vram || 0) / 1024 ** 3;
        const ramGb  = Number(loaded.size  || 0) / 1024 ** 3;
        const loc    = vramGb > 0.01 ? `${vramGb.toFixed(1)} GB VRAM` : `${ramGb.toFixed(1)} GB RAM`;
        dotCls    = 'dot-loaded';
        memText   = loc;
        rowCls    = '';
        clickAttr = `onclick="ollamaToggle('${name}')"`;
      } else {
        dotCls    = 'dot-off';
        memText   = '—';
        rowCls    = '';
        clickAttr = `onclick="ollamaToggle('${name}')"`;
      }

      return `<div class="model-row ${rowCls}" id="mrow-${name.replace(/[^a-z0-9]/gi,'-')}" ${clickAttr}>
        <span class="model-dot ${dotCls}" id="mdot-${name.replace(/[^a-z0-9]/gi,'-')}"></span>
        <span class="model-row-name" title="${name}">${name}</span>
        <span class="model-row-mem ${loaded ? '' : 'mem-off'}" id="mmem-${name.replace(/[^a-z0-9]/gi,'-')}">${memText}</span>
      </div>`;
    }).join('');

    const list = document.getElementById('ollama-swarm-list');
    if (list) list.innerHTML = rows;
  }).catch(e => console.error('loadOllamaPanel error:', e));
}

function ollamaToggle(name) {
  const safeName = name.replace(/[^a-z0-9]/gi, '-');
  const dot  = document.getElementById(`mdot-${safeName}`);
  const row  = document.getElementById(`mrow-${safeName}`);
  const mem  = document.getElementById(`mmem-${safeName}`);
  const msg  = document.getElementById('ollama-status-msg');

  // Check current state by dot class
  const isLoaded = dot && dot.classList.contains('dot-loaded');

  // Mark busy
  if (dot) { dot.className = 'model-dot dot-busy'; }
  if (row) { row.classList.add('row-busy'); row.onclick = null; }
  if (mem) { mem.textContent = isLoaded ? 'unloading…' : 'loading…'; mem.className = 'model-row-mem mem-off'; }
  if (msg) msg.textContent = `${isLoaded ? 'Unloading' : 'Loading'} ${name}…`;

  const url = isLoaded ? '/api/ollama/unload' : '/api/ollama/load';

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: name }),
  })
  .then(r => r.json())
  .then(d => {
    if (msg) msg.textContent = d.ok
      ? `✓ ${name} ${isLoaded ? 'unloaded' : 'loaded'}`
      : `✗ ${d.error || 'failed'}`;
    loadOllamaPanel();
  })
  .catch(e => {
    if (msg) msg.textContent = `✗ ${e.message}`;
    loadOllamaPanel();
  })
  .finally(() => {
    setTimeout(() => {
      const el = document.getElementById('ollama-status-msg');
      if (el) el.textContent = '';
    }, 4000);
  });
}

