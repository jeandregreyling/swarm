'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   potato-farm.js — Potato Farm dashboard: mesh nodes, capabilities, dispatch
   ────────────────────────────────────────────────────────────────────────── */

let _pfarmTimer = null;

function _pfEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
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
  const isPotato2 = String(node.node_id || '').toLowerCase().includes('potato-2') || String(node.label || '').toLowerCase().includes('samsung');
  const isDell = platform.includes('linuxmint') || String(node.label || node.node_id || '').toLowerCase().includes('dell');
  const isMaster = (node.node_id || '').toLowerCase().includes('potato-1') || (node.label || '').toLowerCase().includes('master');
  const ramPct = (m.ram_total_mb && m.ram_free_mb != null)
    ? Math.round(100 - (100 * m.ram_free_mb / m.ram_total_mb)) : null;
  const ageS = node.last_seen_ts
    ? Math.max(0, Math.floor(Date.now()/1000 - node.last_seen_ts)) : null;
  const ageStr = ageS == null ? '—'
    : ageS < 60 ? `${ageS}s ago`
    : ageS < 3600 ? `${Math.floor(ageS/60)}m ago`
    : `${Math.floor(ageS/3600)}h ago`;
  const stale = !!node.offline || (ageS != null && ageS > 120);

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

  const capBadges = caps.map(_pfCapBadge).join('') || '<span style="font-size:9px;color:var(--text-dim);">waiting for telemetry</span>';
  const cpuStr = c.cpu_load_pct != null ? Math.round(c.cpu_load_pct) + '%' : '—';
  const ramStr = ramPct != null ? ramPct + '%' : '—';
  const battStr = p.battery_pct != null ? `${Math.round(p.battery_pct)}% ${p.on_battery ? '🔋' : '⚡'}` : '—';
  const npuOk = c.npu_present ? '✓ NPU' : '';
  const gpuOk = c.gpu_present ? '✓ GPU' : '';
  const displayName = node.label || (isDell ? 'Dell Linux Potato' : node.node_id);
  const shareHint = caps.length
    ? caps.map(cap => cap.replace('inference.', '').replace('scheduler.', '').replace('storage.', '')).join(' / ')
    : 'No shared resources reported yet';
  const gpuLine = isPotato2
    ? (c.gpu_present || caps.includes('inference.gpu')
        ? '<span style="color:#4caf50;font-weight:700;">Samsung GPU worker armed</span>'
        : '<span style="color:#ffa500;font-weight:700;">Samsung expected · waiting for app telemetry</span>')
    : '';

  return `
    <div style="background:var(--card);border:1px solid ${stale ? '#f4433655' : 'var(--border)'};border-radius:6px;padding:10px;font-size:10px;line-height:1.5;">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;flex-wrap:wrap;">
        <span style="width:8px;height:8px;border-radius:50%;background:${stale ? '#f44336' : '#4caf50'};"></span>
        <strong style="font-size:11px;color:var(--text);">${platIcon} ${_pfEsc(displayName)}</strong>
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
      <div style="margin-top:6px;padding-top:6px;border-top:1px dashed var(--border);color:var(--text-dim);font-size:9px;">
        Share: <strong style="color:var(--text);">${_pfEsc(shareHint)}</strong>
        ${gpuLine ? `<div style="margin-top:3px;">${gpuLine}</div>` : ''}
      </div>
    </div>
  `;
}

function _pfExpectedNodes(nodes) {
  const byId = new Map(nodes.map(n => [String(n.node_id || '').toLowerCase(), n]));
  const expected = [
    { node_id: 'potato-1', label: 'potato-1 Leader', platform: 'linux', expected: true },
    { node_id: 'potato-2', label: 'potato-2 Samsung S9 FE', platform: 'android', expected: true },
    { node_id: 'potato-3', label: 'potato-3 MacBook', platform: 'macos', expected: true },
    { node_id: 'potato-4', label: 'potato-4 Dell', platform: 'linux/windows', expected: true },
  ];
  const merged = nodes.slice();
  expected.forEach(e => {
    if (!byId.has(e.node_id.toLowerCase()) && !merged.some(n => String(n.node_id || '').toLowerCase().includes(e.node_id))) {
      merged.push({ ...e, offline: true, age_s: null, telemetry: { capabilities: [] } });
    }
  });
  return merged;
}

function _pfRenderMap(nodes, jobs) {
  const map = document.getElementById('pfarm-map');
  const meta = document.getElementById('pfarm-map-meta');
  if (!map) return;
  const displayNodes = _pfExpectedNodes(nodes);
  const w = 760, h = 260;
  const cx = w / 2, cy = h / 2;
  const radius = 92;
  const positions = {};
  displayNodes.forEach((n, i) => {
    const id = n.node_id || `node-${i}`;
    if (String(id).includes('potato-1') || String(id).includes('linux-')) {
      positions[id] = { x: cx, y: cy };
    } else {
      const angle = (-90 + (360 * i / Math.max(displayNodes.length - 1, 1))) * Math.PI / 180;
      positions[id] = { x: cx + Math.cos(angle) * radius * 2.2, y: cy + Math.sin(angle) * radius };
    }
  });
  const leader = displayNodes.find(n => String(n.node_id || '').includes('potato-1') || String(n.node_id || '').startsWith('linux-')) || displayNodes[0];
  const leaderPos = positions[leader?.node_id] || { x: cx, y: cy };
  const edges = displayNodes.filter(n => n !== leader).map(n => ({ from: leader.node_id, to: n.node_id }));
  const jobEdges = (jobs || []).filter(j => j.node_id).map(j => ({ from: 'potato-1', to: j.node_id, job: j }));
  const edgeSvg = edges.map(e => {
    const a = leaderPos, b = positions[e.to] || a;
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="var(--border)" stroke-width="1.2" stroke-dasharray="3 4"/>`;
  }).join('') + jobEdges.map(e => {
    const a = leaderPos, b = positions[e.to] || a;
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="var(--accent)" stroke-width="2.2" opacity=".8"/>`;
  }).join('');
  const nodeSvg = displayNodes.map(n => {
    const id = n.node_id || '';
    const p = positions[id] || { x: cx, y: cy };
    const live = !n.offline && Number(n.age_s ?? 9999) < 180;
    const fill = live ? (String(id).includes('potato-2') ? '#4caf50' : '#4fd1c5') : '#444';
    const stroke = n.offline ? '#f44336' : 'var(--accent)';
    const caps = ((n.telemetry || {}).capabilities || []).length;
    return `<g><circle cx="${p.x}" cy="${p.y}" r="22" fill="${fill}33" stroke="${stroke}" stroke-width="2"/><text x="${p.x}" y="${p.y - 3}" text-anchor="middle" fill="var(--text)" font-size="10" font-weight="700">${_pfEsc(id.replace('potato-', 'P'))}</text><text x="${p.x}" y="${p.y + 12}" text-anchor="middle" fill="var(--text-dim)" font-size="8">${n.offline ? 'offline' : caps + ' caps'}</text></g>`;
  }).join('');
  map.innerHTML = `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:260px;display:block;">${edgeSvg}${nodeSvg}</svg>`;
  if (meta) meta.textContent = `${nodes.length} live · ${displayNodes.filter(n => n.offline).length} expected offline`;
}

function _pfRenderHandoffs(jobs) {
  const el = document.getElementById('pfarm-handoffs');
  if (!el) return;
  if (!jobs || !jobs.length) {
    el.innerHTML = '<div>No handoffs yet. Dispatch a task to see potato routing here.</div>';
    return;
  }
  el.innerHTML = jobs.slice(0, 12).map(j => {
    const to = j.node_id || 'auto-route';
    const when = j.completed_ts || j.claimed_ts || j.created_ts;
    const age = when ? Math.max(0, Math.floor(Date.now()/1000 - when)) + 's ago' : '—';
    const color = j.status === 'completed' ? '#4caf50' : j.status === 'claimed' ? '#2196f3' : '#ffa500';
    return `<div style="display:flex;gap:8px;align-items:center;border:1px solid var(--border);border-radius:5px;padding:6px;background:rgba(0,0,0,.12);"><span style="color:${color};font-weight:700;min-width:70px;">${_pfEsc(j.status)}</span><span style="flex:1;">potato-1 → <strong>${_pfEsc(to)}</strong> · ${_pfEsc(j.kind || 'job')}</span><span>${_pfEsc(j.capability_req || '')}</span><span style="color:var(--text-dim);">${age}</span></div>`;
  }).join('');
}

function _pfRenderProof(nodes, jobs) {
  const el = document.getElementById('pfarm-proof');
  const potato2 = (nodes || []).find(n => String(n.node_id || '').toLowerCase() === 'potato-2');
  const p2Telemetry = potato2?.telemetry || {};
  const caps = p2Telemetry.capabilities || [];
  const proofJob = (jobs || []).find(j =>
    (j.node_id === 'potato-2' || j.capability_req === 'inference.gpu') &&
    (j.kind === 'tflite.gpu' || j.kind === 'gpu.probe' || j.kind === 'tflite.inference')
  );
  const liveAge = potato2?.age_s;
  const liveText = liveAge == null ? 'expected' : liveAge < 180 ? 'live' : `${liveAge}s old`;
  const status = proofJob?.status || 'waiting';
  const ok = status === 'completed' && caps.includes('inference.gpu');
  if (el) {
    el.style.borderColor = ok ? '#4caf50' : 'var(--accent)';
    el.style.background = ok ? 'rgba(76,175,80,.12)' : 'color-mix(in srgb,var(--accent) 14%,var(--card))';
    el.innerHTML = `
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <span style="width:10px;height:10px;border-radius:50%;background:${ok ? '#4caf50' : '#ffa500'};display:inline-block;"></span>
        <strong style="font-size:12px;color:var(--text);">Samsung GPU handoff ${_pfEsc(status)}</strong>
        <span style="color:var(--text-dim);">${_pfEsc(proofJob?.job_id || 'no job yet')}</span>
      </div>
      <div style="margin-top:4px;color:var(--text-dim);font-size:10px;">
        potato-2 is ${_pfEsc(liveText)} · ${_pfEsc(caps.join(', ') || 'no capabilities')} · route ${_pfEsc(proofJob?.kind || 'tflite.gpu')} -> potato-2
      </div>
    `;
  }
  const globalProof = document.getElementById('potato-global-proof');
  const globalText = document.getElementById('potato-global-proof-text');
  if (globalProof && globalText) {
    globalProof.style.borderColor = ok ? '#4caf50' : '#ffa500';
    globalProof.style.background = ok ? 'rgba(18,32,23,.96)' : 'rgba(40,28,10,.96)';
    globalText.textContent = ok
      ? `POTATO2 GPU OK · ${proofJob.kind} -> potato-2 completed`
      : `POTATO2 ${caps.includes('inference.gpu') ? 'GPU visible' : 'waiting'} · ${status}`;
  }
}

async function pfarmRefresh() {
  const grid = document.getElementById('pfarm-grid');
  const meta = document.getElementById('pfarm-meta');
  const targetSelect = document.getElementById('pfarm-target-node');
  const gitStatus = document.getElementById('pfarm-git-status');
  if (!grid) return;

  try {
    // Fetch nodes + handoff/job history
    const [r, jr] = await Promise.all([fetch('/api/hive/nodes'), fetch('/api/hive/jobs')]);
    const j = await r.json();
    const jobsJson = jr.ok ? await jr.json() : { jobs: [] };
    if (!j || !j.ok) throw new Error('not ok');
    const nodes = j.nodes || [];
    const jobs = jobsJson.jobs || [];

    if (meta) meta.textContent = `${nodes.length} node${nodes.length === 1 ? '' : 's'}`;

    const displayNodes = _pfExpectedNodes(nodes);
    if (!displayNodes.length) {
      grid.innerHTML = '<div style="color:var(--text-dim);font-size:10px;">No nodes enrolled yet.</div>';
    } else {
      grid.innerHTML = displayNodes.map(_pfRenderNode).join('');
    }
    _pfRenderMap(nodes, jobs);
    _pfRenderProof(nodes, jobs);
    _pfRenderHandoffs(jobs);

    // Update target node dropdown
    if (targetSelect) {
      const current = targetSelect.value;
      targetSelect.innerHTML = '<option value="">Auto-route (best node)</option>' +
        displayNodes.map(n => `<option value="${_pfEsc(n.node_id)}">${_pfEsc(n.label || n.node_id)}${n.offline ? ' (expected)' : ''}</option>`).join('');
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

    pfarmLog(`Refreshed: ${nodes.length} live node(s), ${jobs.length} handoff(s)`);
  } catch (e) {
    grid.innerHTML = `<div style="color:#f77;font-size:10px;">Mesh unreachable: ${_pfEsc(e.message || e)}</div>`;
    pfarmLog(`Error: ${e.message || e}`);
  }
}

async function pfarmRefreshHomeBadge() {
  const badge = document.getElementById('home-potato-badge');
  const desc = document.getElementById('home-potato-desc');
  if (!badge && !desc) return;
  try {
    const [nodesRes, jobsRes] = await Promise.all([fetch('/api/hive/nodes'), fetch('/api/hive/jobs')]);
    const nodesJson = await nodesRes.json();
    const jobsJson = await jobsRes.json();
    const potato2 = (nodesJson.nodes || []).find(n => String(n.node_id || '').toLowerCase() === 'potato-2');
    const caps = (potato2?.telemetry || {}).capabilities || [];
    const proofJob = (jobsJson.jobs || []).find(j =>
      (j.node_id === 'potato-2' || j.capability_req === 'inference.gpu') &&
      (j.kind === 'tflite.gpu' || j.kind === 'gpu.probe' || j.kind === 'tflite.inference')
    );
    const ok = proofJob?.status === 'completed' && caps.includes('inference.gpu');
    if (badge) {
      badge.style.display = 'inline-block';
      badge.textContent = ok ? 'GPU OK' : (proofJob?.status || 'WAIT');
      badge.style.background = ok ? '#4caf5022' : '#ffa50022';
      badge.style.color = ok ? '#4caf50' : '#ffa500';
      badge.style.border = `1px solid ${ok ? '#4caf5055' : '#ffa50055'}`;
    }
    if (desc) {
      desc.textContent = ok
        ? `Samsung handoff completed · ${proofJob.job_id}`
        : `potato-2 ${caps.includes('inference.gpu') ? 'GPU visible' : 'waiting'} · ${proofJob?.status || 'no handoff'}`;
    }
  } catch (_e) {
    if (badge) {
      badge.style.display = 'inline-block';
      badge.textContent = 'ERR';
      badge.style.color = 'var(--danger,#f44336)';
    }
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

  const caps = _pfTaskCaps(taskType);
  const envelope = {
    kind: taskType,
    payload: {
      data: payload,
      target_node: target || null,
      packet_profile: taskType.includes('tflite') ? 'tiny-quantized' : 'standard',
      quantization: taskType.includes('tflite') ? 'int8-preferred' : null,
    },
    capability_req: caps[0] || null,
    node_id: target || null,
  };

  if (status) status.innerHTML = `<span style="color:var(--accent);">Submitting handoff…</span>`;

  fetch('/api/hive/jobs/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(envelope)
  })
  .then(r => r.ok ? r.json() : Promise.reject(r.status))
  .then(d => {
    if (status) status.innerHTML = `<span style="color:#4caf50;">✓ Submitted ${_pfEsc(d.job_id || 'job')}</span>`;
    pfarmLog(`Submitted handoff ${d.job_id || ''} (${taskType})`);
    pfarmRefresh();
  })
  .catch(e => {
    if (status) status.innerHTML = `<span style="color:#f44336;">✗ Failed: ${_pfEsc(String(e))}</span>`;
    pfarmLog(`Dispatch failed: ${e}`);
  });
}

function _pfTaskCaps(type) {
  const map = {
    'tflite.gpu': ['inference.gpu'],
    'tflite.inference': ['inference.tflite'],
    'ollama.chat': ['inference.ollama'],
    'agent.run': ['inference.cpu'],
    'git.sync': ['scheduler.coordinator'],
    'custom': ['inference.cpu']
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

function pfarmEnsureVisible() {
  pfarmRefreshHomeBadge();
  if (document.getElementById('pfarm-grid')) pfarmStartAutoRefresh();
}

const _pfarmPrevWindowRendered = window.fridaysWindowRendered;
window.fridaysWindowRendered = function fridaysPotatoFarmWindowRendered(id, winState) {
  if (typeof _pfarmPrevWindowRendered === 'function') {
    try { _pfarmPrevWindowRendered(id, winState); } catch (_err) { /* preserve later hooks */ }
  }
  const baseId = String(winState?.baseId || id || '').toLowerCase();
  if (baseId === 'potato-farm') {
    setTimeout(pfarmEnsureVisible, 0);
  }
};

window.pfarmRefresh = pfarmRefresh;
window.pfarmDispatch = pfarmDispatch;
window.pfarmLog = pfarmLog;
window.pfarmRefreshHomeBadge = pfarmRefreshHomeBadge;
window.pfarmEnsureVisible = pfarmEnsureVisible;

document.addEventListener('DOMContentLoaded', () => {
  pfarmRefreshHomeBadge();
  setInterval(pfarmRefreshHomeBadge, 20000);
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
