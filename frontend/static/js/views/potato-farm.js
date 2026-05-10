'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   potato-farm.js — Potato Farm dashboard: mesh nodes, capabilities, dispatch
   ────────────────────────────────────────────────────────────────────────── */

let _pfarmTimer = null;

function _pfEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&':'&','<':'<','>':'>','"':'"',"'":'&#39;'
  }[c]));
}

function _pfCapColor(cap) {
  if (cap.includes('npu')) return '#9c27b0';
  if (cap.includes('gpu')) return '#2196f3';
  if (cap.includes('tflite')) return '#4caf50';
  if (cap.includes('cpu')) return '#ff9800';
  if (cap.includes('coordinator')) return '#f44336';
  if (cap.includes('worker')) return '#00bcd4';
  if (cap.includes('storage')) return '#795548';
  return 'var(--text-dim)';
}

function _pfCapBadge(cap) {
  const color = _pfCapColor(cap);
  const label = cap.replace('inference.', '').replace('scheduler.', '');
  return `<span style="display:inline-block;padding:1px 5px;border-radius:3px;background:${color}22;color:${color};border:1px solid ${color}55;font-size:8px;font-weight:600;margin-right:3px;margin-bottom:2px;">${_pfEsc(label)}</span>`;
}

function _pfRenderNode(node) {
  const t = node.telemetry || {};
  const c = t.compute || {};
  const th = t.thermal || {};
  const m = t.memory || {};
  const p = t.power || {};
  const caps = t.capabilities || [];
  const platform = (node.platform || '').toLowerCase();
  const isAndroid = platform === 'android' || platform.startsWith('android');
  const isMaster = (node.node_id || '').toLowerCase().includes('potato-1') || (node.label || '').toLowerCase().includes('master');
  const ramPct = (m.ram_total_mb && m.ram_free_mb != null)
    ? Math.round(100 - (100 * m.ram_free_mb / m.ram_total_mb)) : null;
  const ageS = node.last_seen_ts
    ? Math.max(0, Math.floor(Date.now()/1000 - node.last_seen_ts)) : null;
  const ageStr = ageS == null ? '—'
    : ageS < 60 ? `${ageS}s ago`
    : ageS < 3600 ? `${Math.floor(ageS/60)}m ago`
    : `${Math.floor(ageS/3600)}h ago`;
  const stale = ageS != null && ageS > 120;

  const platIcon = isAndroid ? '📱'
    : platform.includes('darwin') || platform.includes('mac') ? '🍎'
    : platform.includes('win') ? '🪟'
    : '🖥';

  const roleBadge = isMaster
    ? '<span style="padding:1px 5px;border-radius:3px;background:#f4433622;color:#f44336;border:1px solid #f4433655;font-size:8px;font-weight:600;">MASTER</span>'
    : '<span style="padding:1px 5px;border-radius:3px;background:#4caf5022;color:#4caf50;border:1px solid #4caf5055;font-size:8px;font-weight:600;">PEER</span>';

  const userPill = node.user
    ? `<span style="padding:1px 5px;border-radius:3px;background:var(--accent)22;color:var(--accent);border:1px solid var(--accent)55;font-size:8px;font-weight:600;">👤 ${_pfEsc(node.user)}</span>`
    : '<span style="padding:1px 5px;border-radius:3px;background:var(--border);color:var(--text-dim);border:1px solid var(--border);font-size:8px;">no user</span>';

  const capBadges = caps.map(_pfCapBadge).join('') || '<span style="font-size:9px;color:var(--text-dim);">no capabilities</span>';
  const cpuStr = c.cpu_load_pct != null ? Math.round(c.cpu_load_pct) + '%' : '—';
  const ramStr = ramPct != null ? ramPct + '%' : '—';
  const battStr = p.battery_pct != null ? `${Math.round(p.battery_pct)}% ${p.on_battery ? '🔋' : '⚡'}` : '—';
  const npuOk = c.npu_present ? '✓ NPU' : '';
  const gpuOk = c.gpu_present ? '✓ GPU' : '';

  return `
    <div style="background:var(--card);border:1px solid ${stale ? '#f4433655' : 'var(--border)'};border-radius:6px;padding:10px;font-size:10px;line-height:1.5;">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;flex-wrap:wrap;">
        <span style="width:8px;height:8px;border-radius:50%;background:${stale ? '#f44336' : '#4caf50'};"></span>
        <strong style="font-size:11px;color:var(--text);">${platIcon} ${_pfEsc(node.label || node.node_id)}</strong>
        ${roleBadge}
        <span style="flex:1;"></span>
        ${userPill}
      </div>
      <div style="color:var(--text-dim);font-size:9px;margin-bottom:6px;">
        ${_pfEsc(node.platform || '')} · ${ageStr} · ${_pfEsc(node.node_id)}
      </div>
      <div style="margin-bottom:4px;">${capBadges}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <span>CPU: <strong>${cpuStr}</strong></span>
        <span>RAM: <strong>${ramStr}</strong></span>
        ${p.battery_pct != null ? `<span>Batt: <strong>${battStr}</strong></span>` : ''}
        ${npuOk || gpuOk ? `<span style="color:var(--text-dim);">${npuOk}${npuOk && gpuOk ? ' · ' : ''}${gpuOk}</span>` : ''}
      </div>
    </div>
  `;
}

async function pfarmRefresh() {
  const grid = document.getElementById('pfarm-grid');
  const meta = document.getElementById('pfarm-meta');
  const targetSelect = document.getElementById('pfarm-target-node');
  const gitStatus = document.getElementById('pfarm-git-status');
  if (!grid) return;

  try {
    // Fetch nodes
    const r = await fetch('/api/hive/nodes');
    const j = await r.json();
    if (!j || !j.ok) throw new Error('not ok');
    const nodes = j.nodes || [];

    if (meta) meta.textContent = `${nodes.length} node${nodes.length === 1 ? '' : 's'}`;

    if (!nodes.length) {
      grid.innerHTML = '<div style="color:var(--text-dim);font-size:10px;">No nodes enrolled yet.</div>';
    } else {
      grid.innerHTML = nodes.map(_pfRenderNode).join('');
    }

    // Update target node dropdown
    if (targetSelect) {
      const current = targetSelect.value;
      targetSelect.innerHTML = '<option value="">Auto-route (best node)</option>' +
        nodes.map(n => `<option value="${_pfEsc(n.node_id)}">${_pfEsc(n.label || n.node_id)}</option>`).join('');
      targetSelect.value = current;
    }

    // Git status (best effort)
    if (gitStatus) {
      fetch('/api/git/status?env=prod')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(g => {
          const ahead = g.ahead || 0;
          const behind = g.behind || 0;
          const branch = g.branch || 'unknown';
          gitStatus.innerHTML = `Branch: <strong>${_pfEsc(branch)}</strong>` +
            (ahead ? ` · <span style="color:#4caf50;">${ahead} ahead</span>` : '') +
            (behind ? ` · <span style="color:#ffa500;">${behind} behind origin</span>` : '') +
            (!ahead && !behind ? ' · <span style="color:#4caf50;">synced</span>' : '');
        })
        .catch(() => { gitStatus.textContent = 'Git status unavailable'; });
    }

    pfarmLog(`Refreshed: ${nodes.length} node(s)`);
  } catch (e) {
    grid.innerHTML = `<div style="color:#f77;font-size:10px;">Mesh unreachable: ${_pfEsc(e.message || e)}</div>`;
    pfarmLog(`Error: ${e.message || e}`);
  }
}

function pfarmDispatch() {
  const typeSel = document.getElementById('pfarm-task-type');
  const targetSel = document.getElementById('pfarm-target-node');
  const payloadIn = document.getElementById('pfarm-task-payload');
  const status = document.getElementById('pfarm-dispatch-status');

  const taskType = typeSel ? typeSel.value : 'custom';
  const target = targetSel ? targetSel.value : '';
  const payload = payloadIn ? payloadIn.value.trim() : '';

  const envelope = {
    contract: 'seven.task/v0',
    task_id: 'T-' + Math.random().toString(36).slice(2, 10).toUpperCase(),
    origin_node: 'potato-1',
    target_node: target || null,
    required_capabilities: _pfTaskCaps(taskType),
    priority: 'normal',
    payload: { type: taskType, data: payload },
    timeout_seconds: 300,
    max_retries: 2,
    created_at: Math.floor(Date.now() / 1000)
  };

  if (status) status.innerHTML = `<span style="color:var(--accent);">Routing ${envelope.task_id}…</span>`;

  fetch('/api/hive/task', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(envelope)
  })
  .then(r => r.ok ? r.json() : Promise.reject(r.status))
  .then(d => {
    if (status) status.innerHTML = `<span style="color:#4caf50;">✓ Routed to ${d.target_node || 'auto'}</span>`;
    pfarmLog(`Dispatched ${envelope.task_id} → ${d.target_node || 'auto'}`);
  })
  .catch(e => {
    if (status) status.innerHTML = `<span style="color:#f44336;">✗ Failed: ${_pfEsc(String(e))}</span>`;
    pfarmLog(`Dispatch failed: ${e}`);
  });
}

function _pfTaskCaps(type) {
  const map = {
    'tflite.inference': ['inference.tflite', 'scheduler.worker'],
    'ollama.chat': ['inference.ollama', 'scheduler.worker'],
    'agent.run': ['scheduler.worker'],
    'git.sync': ['scheduler.worker'],
    'custom': ['scheduler.worker']
  };
  return map[type] || ['scheduler.worker'];
}

function pfarmLog(msg) {
  const el = document.getElementById('pfarm-log');
  if (!el) return;
  const ts = new Date().toLocaleTimeString();
  el.insertAdjacentHTML('afterbegin', `<div>[${ts}] ${_pfEsc(msg)}</div>`);
  while (el.children.length > 50) el.lastChild.remove();
}

function pfarmStartAutoRefresh() {
  pfarmRefresh();
  if (_pfarmTimer) clearInterval(_pfarmTimer);
  _pfarmTimer = setInterval(pfarmRefresh, 20000);
}

window.pfarmRefresh = pfarmRefresh;
window.pfarmDispatch = pfarmDispatch;
window.pfarmLog = pfarmLog;

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('pfarm-grid')) {
    pfarmStartAutoRefresh();
  } else {
    let tries = 0;
    const probe = setInterval(() => {
      if (document.getElementById('pfarm-grid') || ++tries > 20) {
        clearInterval(probe);
        if (document.getElementById('pfarm-grid')) pfarmStartAutoRefresh();
      }
    }, 500);
  }
});
