/**
 * Seven Desktop App (Tauri v2) UI bootstrap.
 * Fix for "buttons do nothing": guard invoke availability and surface errors
 * in UI instead of silent failures.
 */

function $(id) { return document.getElementById(id); }

let leaderUrl = localStorage.getItem('leaderUrl') || 'http://127.0.0.1:5050';
let currentView = 'chat';

function ensureTopErrorNode() {
  let el = $('topError');
  if (!el) {
    el = document.createElement('div');
    el.id = 'topError';
    el.style.cssText = `
      position: fixed;
      top: 8px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 9999;
      padding: 10px 14px;
      max-width: 980px;
      width: calc(100% - 24px);
      background: rgba(190, 40, 40, 0.95);
      color: white;
      border-radius: 10px;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      font-size: 13px;
      display: none;
    `;
    el.textContent = '';
    document.body.appendChild(el);
  }
  return el;
}

function showTopError(msg) {
  try {
    const el = ensureTopErrorNode();
    el.textContent = String(msg || 'Unknown error');
    el.style.display = 'block';
  } catch (e) {
    // ignore
  }
}

function clearTopError() {
  try {
    const el = $('topError');
    if (el) el.style.display = 'none';
  } catch (e) {
    // ignore
  }
}

function getInvoke() {
  // Tauri injects this in the webview. Guard so JS doesn't crash silently.
  const core = window && window.__TAURI__ && window.__TAURI__.core;
  if (!core || typeof core.invoke !== 'function') return null;
  return core.invoke.bind(core);
}

const invoke = getInvoke();

if (!invoke) {
  showTopError(
    "Tauri invoke bridge not available (window.__TAURI__.core.invoke is missing). " +
    "Desktop UI actions may not work. Rebuild the desktop app and ensure Tauri is loaded."
  );
}

async function apiGet(path) {
  if (invoke) return invoke('api_get', { url: `${leaderUrl}${path}` });
  const r = await fetch(`${leaderUrl}${path}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function apiPost(path, body) {
  try {
    if (invoke) return await invoke('api_post', { url: `${leaderUrl}${path}`, body });
    const r = await fetch(`${leaderUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    // Preserve tauri invoke error payloads in a readable way.
    const msg =
      (e && e.message) ? e.message :
      (typeof e === 'string' ? e : JSON.stringify(e));
    throw new Error(msg);
  }
}

function setView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  $(`view-${name}`).classList.add('active');
  document.querySelector(`[data-view="${name}"]`).classList.add('active');
  currentView = name;
  clearTopError();
  if (name === 'nodes') loadNodes();
}

function addMessage(text, isUser) {
  const div = document.createElement('div');
  div.className = `message ${isUser ? 'user' : 'bot'}`;
  div.innerHTML = `<div class="sender">${isUser ? 'You' : 'Seven'}</div>${escapeHtml(text)}`;
  $('chatMessages').appendChild(div);
  $('chatMessages').scrollTop = $('chatMessages').scrollHeight;
}

function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML;
}

async function sendChat() {
  const input = $('chatInput');
  const text = input.value.trim();
  if (!text) return;

  clearTopError();
  addMessage(text, true);
  input.value = '';

  try {
    const res = await apiPost('/api/chat', { message: text, agent: 'seven' });
    // Support multiple response shapes: {ok,response}, {response}, or full JSON.
    const reply =
      (res && (res.response || res.reply)) ? (res.response || res.reply) :
      (res && res.ok === false && (res.error || res.response)) ? (res.error || res.response) :
      JSON.stringify(res, null, 2);
    addMessage(reply, false);
  } catch (e) {
    const msg =
      (e && e.message) ? e.message :
      (typeof e === 'string' ? e : JSON.stringify(e));
    addMessage(`Error: ${msg}`, false);
    showTopError(msg);
  }
}

async function loadNodes() {
  $('nodeCount').textContent = 'Loading...';
  $('nodesGrid').innerHTML = '';
  try {
    const data = await apiGet('/api/hive/nodes');
    const nodes = data.nodes || [];
    $('nodeCount').textContent = `${nodes.length} node(s) enrolled`;
    nodes.forEach(n => {
      const card = document.createElement('div');
      card.className = 'node-card';
      const telem = n.telemetry || {};
      const caps = telem.capabilities || [];
      const capTags = caps.map(c => `<span class="cap">${c.replace('inference.', '')}</span>`).join('');
      card.innerHTML = `
        <h3>${escapeHtml(n.node_id)}</h3>
        <div class="meta">${escapeHtml(n.platform)} • ${n.age_s != null ? n.age_s + 's ago' : 'unknown'}</div>
        <div class="caps">${capTags}</div>
      `;
      $('nodesGrid').appendChild(card);
    });
  } catch (e) {
    $('nodeCount').textContent = `Error: ${e}`;
  }
}

async function enrolNode() {
  const nodeId = $('enrolNodeId').value.trim();
  const label = $('enrolLabel').value.trim();
  const resEl = $('enrolResult');
  if (!nodeId) {
    resEl.textContent = 'Node ID required';
    resEl.className = 'result error';
    return;
  }

  clearTopError();
  try {
    const data = await apiPost('/api/hive/enrol', { node_id: nodeId, platform: 'macos', label });
    resEl.textContent = `Enrolled! Token: ${data.token?.slice(0, 16)}...`;
    resEl.className = 'result success';
  } catch (e) {
    const msg =
      (e && e.message) ? e.message :
      (typeof e === 'string' ? e : JSON.stringify(e));
    resEl.textContent = `Error: ${msg}`;
    resEl.className = 'result error';
    showTopError(msg);
  }
}

function saveSettings() {
  leaderUrl = $('leaderUrl').value.trim();
  localStorage.setItem('leaderUrl', leaderUrl);
  $('settingsResult').textContent = 'Saved';
  $('settingsResult').className = 'result success';
  clearTopError();
  checkHealth();
}

async function checkHealth() {
  try {
    clearTopError();
    const data = await apiGet('/_health');
    $('connDot').className = 'status-dot online';
    $('connText').textContent = 'Connected';
  } catch (e) {
    const msg =
      (e && e.message) ? e.message :
      (typeof e === 'string' ? e : JSON.stringify(e));
    $('connDot').className = 'status-dot offline';
    $('connText').textContent = 'Offline';
    showTopError(msg || 'Offline');
  }
}

// Events
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => setView(btn.dataset.view));
});

$('sendBtn').addEventListener('click', sendChat);
$('chatInput').addEventListener('keydown', e => { if (e.key === 'Enter') sendChat(); });
$('enrolBtn').addEventListener('click', enrolNode);
$('saveSettingsBtn').addEventListener('click', saveSettings);

// Init
$('leaderUrl').value = leaderUrl;
addMessage("Seven online. Swarm active. What do you need?", false);
checkHealth();
setInterval(checkHealth, 30000);
