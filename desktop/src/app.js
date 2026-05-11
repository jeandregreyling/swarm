const { invoke } = window.__TAURI__.core;

let leaderUrl = localStorage.getItem('leaderUrl') || 'http://100.87.66.45:5050';
let currentView = 'chat';

function $(id) { return document.getElementById(id); }

async function apiGet(path) {
  return invoke('api_get', { url: `${leaderUrl}${path}` });
}

async function apiPost(path, body) {
  return invoke('api_post', { url: `${leaderUrl}${path}`, body });
}

function setView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  $(`view-${name}`).classList.add('active');
  document.querySelector(`[data-view="${name}"]`).classList.add('active');
  currentView = name;
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
  addMessage(text, true);
  input.value = '';
  try {
    const res = await apiPost('/api/chat', { message: text, agent: 'seven' });
    const reply = res.response || res.reply || JSON.stringify(res);
    addMessage(reply, false);
  } catch (e) {
    addMessage(`Error: ${e}`, false);
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
  try {
    const data = await apiPost('/api/hive/enrol', { node_id: nodeId, platform: 'macos', label });
    resEl.textContent = `Enrolled! Token: ${data.token?.slice(0, 16)}...`;
    resEl.className = 'result success';
  } catch (e) {
    resEl.textContent = `Error: ${e}`;
    resEl.className = 'result error';
  }
}

function saveSettings() {
  leaderUrl = $('leaderUrl').value.trim();
  localStorage.setItem('leaderUrl', leaderUrl);
  $('settingsResult').textContent = 'Saved';
  $('settingsResult').className = 'result success';
  checkHealth();
}

async function checkHealth() {
  try {
    const data = await apiGet('/_health');
    $('connDot').className = 'status-dot online';
    $('connText').textContent = 'Connected';
  } catch (e) {
    $('connDot').className = 'status-dot offline';
    $('connText').textContent = 'Offline';
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
