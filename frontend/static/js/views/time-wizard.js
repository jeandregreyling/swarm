// --- Vortex History Section ---
function renderVortexHistory() {
  const container = document.getElementById('tw-vortex-history');
  if (!container) return;
  container.innerHTML = '<div style="font-size:13px;font-weight:700;margin-bottom:8px;">Vortex History</div>' +
    (_twCheckpoints.length ? _twCheckpoints.map(c => `<div style="font-size:11px;padding:6px 0;border-bottom:1px solid var(--border);"><b>${_escHtml(c.checkpoint_name || c.name || 'checkpoint')}</b> <span style="color:var(--text-dim);">@ ${_escHtml(c.timestamp || c.created_at || '')}</span></div>`).join('') : '<div style="color:var(--text-dim);font-size:11px;">No checkpoints yet.</div>');
}

// Patch into loadTimeWizardData
const _origLoadTimeWizardData = loadTimeWizardData;
loadTimeWizardData = async function() {
  await _origLoadTimeWizardData.apply(this, arguments);
  renderVortexHistory();
};
// Time Wizard / Vortex view
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// TIME WIZARD
// ═══════════════════════════════════════════════════════════════════════════

let _twDecisions = [];
let _twCheckpoints = [];
let _twEvents = [];
let _twSessions = [];
let _twPreview = null;
let _twAutoRefreshTimer = null;
let _twAutoRefreshEnabled = true;
let _twSelected = null;

const TW_AUTO_REFRESH_KEY = 'vortex_auto_refresh';
const TW_SELECTED_KEY = 'vortex_selected_item';

function initTimeWizard() {
  const search = document.getElementById('tw-search');
  const filter = document.getElementById('tw-filter');
  const slider = document.getElementById('tw-slider');
  const auto = document.getElementById('tw-auto-refresh');

  const savedAuto = localStorage.getItem(TW_AUTO_REFRESH_KEY);
  _twAutoRefreshEnabled = savedAuto == null ? true : savedAuto === '1';
  if (auto) auto.checked = _twAutoRefreshEnabled;

  const savedSelected = localStorage.getItem(TW_SELECTED_KEY);
  if (savedSelected) {
    try {
      _twSelected = JSON.parse(savedSelected);
    } catch (_) {
      _twSelected = null;
    }
  }

  if (search) search.oninput = applyTwFilters;
  if (filter) filter.onchange = applyTwFilters;
  if (slider) {
    slider.oninput = () => {
      renderTwSliderLabel();
      previewTwCheckpoint(false);
    };
  }

  setTwAutoRefresh(_twAutoRefreshEnabled);
  loadTimeWizardData();
}

async function loadTimeWizardData() {
  const container = document.getElementById('tw-timeline');
  if (!container) return;
  try {
    const [decisionRes, checkpointRes, eventRes, sessionRes] = await Promise.all([
      fetch('/api/decisions'),
      fetch('/api/time/checkpoints?limit=60'),
      fetch('/api/time/timeline?limit=60'),
      fetch('/api/time/sessions'),
    ]);
    if (!decisionRes.ok) throw new Error(`HTTP ${decisionRes.status}`);
    if (!checkpointRes.ok) throw new Error(`HTTP ${checkpointRes.status}`);
    if (!eventRes.ok) throw new Error(`HTTP ${eventRes.status}`);
    if (!sessionRes.ok) throw new Error(`HTTP ${sessionRes.status}`);

    const decisionData = await decisionRes.json();
    const checkpointData = await checkpointRes.json();
    const eventData = await eventRes.json();
    const sessionData = await sessionRes.json();

    _twDecisions = Array.isArray(decisionData) ? decisionData : (decisionData.decisions || []);
    _twCheckpoints = (checkpointData.checkpoints || []).slice().sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
    _twEvents = eventData.timeline || [];
    _twSessions = sessionData.sessions || [];

    renderTwSummary();
    renderTwSliderLabel();
    renderTwTimeline(_twDecisions);
    renderTwHistoryPanel();
    renderTwVisualTimeline();
    restoreTwSelection();
    if (_twCheckpoints.length) {
      await previewTwCheckpoint(false);
    } else {
      renderTwPreview(null);
    }
  } catch (e) {
    if (container) container.innerHTML = `<div style="color: #f44; padding: 20px; text-align: center;">Failed to load: ${e.message}</div>`;
  }
}

function renderTwSummary() {
  const summary = document.getElementById('tw-summary');
  const slider = document.getElementById('tw-slider');
  if (!summary || !slider) return;
  summary.innerHTML = `Sessions <strong>${_twSessions.length}</strong> · Events <strong>${_twEvents.length}</strong> · Checkpoints <strong>${_twCheckpoints.length}</strong> · Decisions <strong>${_twDecisions.length}</strong>`;
  slider.disabled = _twCheckpoints.length === 0;
  slider.max = Math.max(_twCheckpoints.length - 1, 0);
  if (Number(slider.value) > Number(slider.max)) slider.value = '0';
}

function getSelectedTwCheckpoint() {
  const slider = document.getElementById('tw-slider');
  if (!_twCheckpoints.length || !slider) return null;
  const idx = Number(slider.value || 0);
  return _twCheckpoints[idx] || null;
}

function renderTwSliderLabel() {
  const label = document.getElementById('tw-slider-label');
  if (!label) return;
  const checkpoint = getSelectedTwCheckpoint();
  if (!checkpoint) {
    label.textContent = 'No checkpoints';
    return;
  }
  label.textContent = `${checkpoint.checkpoint_name || checkpoint.name || 'checkpoint'} @ ${checkpoint.timestamp || checkpoint.created_at || 'unknown'}`;
}

function renderTwPreview(result) {
  const preview = document.getElementById('tw-restore-preview');
  if (!preview) return;
  if (!result) {
    preview.innerHTML = 'Drag the slider to inspect a checkpoint. Dry run preview will appear here.';
    return;
  }

  const summary = result.summary || {};
  const prop = (result.changes && result.changes.work_proposals) || [];
  const decs = (result.changes && result.changes.decisions) || [];
  const queue = (result.changes && result.changes.queue) || [];
  const H = _escHtml;

  // Drift rows — color-coded diff style
  const propText  = prop.length  ? prop.slice(0, 8).map(p => {
    const cur = p.current_status || 'missing';
    const snap = p.checkpoint_status || 'missing';
    return `<div style="display:flex;gap:6px;align-items:baseline;padding:1px 0;"><span style="font-family:monospace;font-size:10px;color:var(--text-dim);">${H(String(p.proposal_id))}</span><span style="color:#f77;text-decoration:line-through;font-size:10px;">${H(cur)}</span><span style="color:var(--text-dim);font-size:9px;">&rarr;</span><span style="color:#4caf50;font-size:10px;">${H(snap)}</span></div>`;
  }).join('') : '<div style="color:var(--text-dim);">No proposal drift.</div>';
  const decsText  = decs.length  ? decs.slice(0, 8).map(d => {
    const cur = d.current_status || 'missing';
    const snap = d.checkpoint_status || 'missing';
    return `<div style="display:flex;gap:6px;align-items:baseline;padding:1px 0;"><span style="font-family:monospace;font-size:10px;color:var(--text-dim);">D${H(String(d.decision_id))}</span><span style="color:#f77;text-decoration:line-through;font-size:10px;">${H(cur)}</span><span style="color:var(--text-dim);font-size:9px;">&rarr;</span><span style="color:#4caf50;font-size:10px;">${H(snap)}</span></div>`;
  }).join('') : '<div style="color:var(--text-dim);">No decision drift.</div>';
  const queueText = queue.length ? queue.slice(0, 8).map(q => {
    const cur = q.current_status || 'missing';
    const snap = q.checkpoint_status || 'missing';
    return `<div style="display:flex;gap:6px;align-items:baseline;padding:1px 0;"><span style="font-family:monospace;font-size:10px;color:var(--text-dim);">Q${H(String(q.queue_id))}</span><span style="color:#f77;text-decoration:line-through;font-size:10px;">${H(cur)}</span><span style="color:var(--text-dim);font-size:9px;">&rarr;</span><span style="color:#4caf50;font-size:10px;">${H(snap)}</span></div>`;
  }).join('') : '<div style="color:var(--text-dim);">No queue drift.</div>';

  // Git snapshot info
  const gitInfo = result.checkpoint_git || {};
  const gitTags = result.checkpoint_git_tags || {};
  const hasGit = Object.keys(gitInfo).length > 0 || Object.keys(gitTags).length > 0;
  const gitHtml = hasGit ? `
    <div style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px;">
      <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Git Snapshot</div>
      <div style="font-size:11px;line-height:1.6;color:var(--text);">
        ${Object.entries(gitInfo).map(([wt, info]) => `<div><strong>${H(wt)}</strong>: ${H(info.branch || '?')} @ <code style="font-size:10px;">${H(info.commit || '?')}</code>${gitTags[wt] ? ` · tag: <code style="font-size:10px;color:#4caf50;">${H(gitTags[wt])}</code>` : ''}</div>`).join('')}
      </div>
    </div>` : '';

  preview.innerHTML = `
    <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px;">
      <div style="font-size:12px;font-weight:700;color:var(--text);">Dry Run — ${H(result.checkpoint_name || '')}</div>
      <div style="font-size:10px;color:var(--text-dim);">${H(result.checkpoint_timestamp || '')}</div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
      <span style="padding:3px 8px;border-radius:12px;background:var(--bg);border:1px solid var(--border);color:var(--text);">Proposal drift: ${Number(summary.proposal_changes || 0)}</span>
      <span style="padding:3px 8px;border-radius:12px;background:var(--bg);border:1px solid var(--border);color:var(--text);">Decision drift: ${Number(summary.decision_changes || 0)}</span>
      <span style="padding:3px 8px;border-radius:12px;background:var(--bg);border:1px solid var(--border);color:var(--text);">Queue drift: ${Number(summary.queue_changes || 0)}</span>
      <span style="padding:3px 8px;border-radius:12px;background:${summary.restorable ? '#4caf5022' : '#8882'};border:1px solid ${summary.restorable ? '#4caf5055' : 'var(--border)'};color:${summary.restorable ? '#4caf50' : 'var(--text-dim)'};">${summary.restorable ? 'Restorable' : 'No drift'}</span>
      ${summary.has_git_tags ? '<span style="padding:3px 8px;border-radius:12px;background:#2563eb22;border:1px solid #2563eb55;color:#2563eb;">Git tags ✓</span>' : ''}
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;">
      <div style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px;">
        <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Work Proposals</div>
        <div style="line-height:1.5;color:var(--text);">${propText}</div>
      </div>
      <div style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px;">
        <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Decisions</div>
        <div style="line-height:1.5;color:var(--text);">${decsText}</div>
      </div>
      <div style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px;">
        <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Queue</div>
        <div style="line-height:1.5;color:var(--text);">${queueText}</div>
      </div>
      ${gitHtml}
    </div>`;
}

async function previewTwCheckpoint(showToastOnSuccess = false) {
  const checkpoint = getSelectedTwCheckpoint();
  if (!checkpoint) {
    renderTwPreview(null);
    return;
  }
  try {
    const res = await fetch('/api/time/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checkpoint_name: checkpoint.checkpoint_name || checkpoint.name, actor: 'terminal_ui', dry_run: true })
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
    _twPreview = data;
    renderTwPreview(data);
    if (showToastOnSuccess) showToast(`Dry run ready: ${checkpoint.checkpoint_name || checkpoint.name}`, 'success');
  } catch (e) {
    renderTwPreview({ checkpoint_name: checkpoint.checkpoint_name || checkpoint.name, summary: {}, changes: { work_proposals: [], decisions: [], queue: [] }, checkpoint_timestamp: checkpoint.timestamp || checkpoint.created_at });
    showToast(`Dry run failed: ${e.message}`, 'error');
  }
}

async function createTwCheckpoint() {
  const label = prompt('Checkpoint label:', 'manual-step');
  if (!label) return;
  const description = prompt('Checkpoint note:', 'Manual Vortex checkpoint from UI') || '';
  try {
    const res = await fetch('/api/time/checkpoints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, description, agent: 'terminal_ui' })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    showToast(`Checkpoint created: ${data.checkpoint.checkpoint_name}`, 'success');
    await loadTimeWizardData();
  } catch (e) {
    showToast(`Checkpoint failed: ${e.message}`, 'error');
  }
}

async function applyTwRestore() {
  const checkpoint = getSelectedTwCheckpoint();
  if (!checkpoint) {
    showToast('No checkpoint selected', 'error');
    return;
  }
  await applyTwRestoreForCheckpoint(checkpoint, `Apply step-back to ${checkpoint.checkpoint_name || checkpoint.name}? A safety checkpoint will be created first.`);
}

async function applyTwRestoreForCheckpoint(checkpoint, confirmText) {
  const checkpointName = checkpoint.checkpoint_name || checkpoint.name;
  if (!checkpointName) {
    showToast('Checkpoint name unavailable', 'error');
    return;
  }
  if (!confirm(confirmText || `Apply step-back to ${checkpointName}? A safety checkpoint will be created first.`)) return;

  try {
    const res = await fetch('/api/time/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checkpoint_name: checkpointName, actor: 'terminal_ui', dry_run: false })
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
    showToast(`Step-back applied. Safety checkpoint: ${data.safety_checkpoint?.checkpoint_name || 'created'}`, 'success');
    await loadTimeWizardData();
  } catch (e) {
    showToast(`Restore failed: ${e.message}`, 'error');
  }
}

async function twRollbackToHistory(kind, id) {
  const items = getTwHistoryItems();
  const selected = items.find(x => x.kind === kind && String(x.id) === String(id));
  if (!selected) {
    showToast('History item not found', 'error');
    return;
  }

  if (kind === 'checkpoint') {
    await applyTwRestoreForCheckpoint(selected.raw, `Rollback to snapshot ${selected.checkpoint_name || selected.title}? A safety checkpoint will be created first.`);
    return;
  }

  const cp = findTwCheckpointForEventTimestamp(selected.ts);
  if (!cp) {
    showToast('No snapshot found before this event', 'error');
    return;
  }
  await applyTwRestoreForCheckpoint(cp, `Rollback to nearest snapshot before this event (${cp.checkpoint_name || cp.name})? A safety checkpoint will be created first.`);
}

function renderTwTimeline(decisions) {
  const container = document.getElementById('tw-timeline');
  if (!container) return;
  if (!decisions || decisions.length === 0) {
    container.innerHTML = '<div style="color: var(--text-dim); font-size: 12px; text-align: center; padding: 40px 20px;">No decisions recorded yet.</div>';
    return;
  }
  const statusColors = { EXECUTED: '#00ff80', PROPOSED: '#ffc800', TESTING: '#00a0ff' };
  container.innerHTML = decisions.map(d => {
    const status = (d.status || 'UNKNOWN').toUpperCase();
    const color = statusColors[status] || '#888';
    const rawId = d.id || d.decision_id || '';
    return `
      <div style="background: var(--card); border: 1px solid var(--border); border-left: 3px solid ${color}; border-radius: 4px; padding: 12px 14px; margin-bottom: 8px; cursor: pointer;" onclick="expandTwDecision(${_escHtml(JSON.stringify(rawId))})">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
          <span style="font-size: 11px; color: var(--text-dim); font-family: monospace;">${_escHtml(rawId || '—')}</span>
          <span style="font-size: 10px; font-weight: 700; color: ${color}; text-transform: uppercase;">${_escHtml(status)}</span>
        </div>
        <div style="font-size: 13px; font-weight: 600; margin-top: 4px;">${_escHtml(d.title || d.summary || '(untitled)')}</div>
        <div style="font-size: 11px; color: var(--text-dim); margin-top: 4px;">${_escHtml(d.date || d.proposed || d.timestamp || '')}</div>
      </div>`;
  }).join('');
}

function twEventDisplayTitle(event) {
  const base = event.event_type || event.type || event.action || 'event';
  const desc = event.description || event.summary || event.message || '';
  return desc ? `${base}: ${desc}` : base;
}

function getTwHistoryItems() {
  const checkpointItems = (_twCheckpoints || []).map(cp => ({
    kind: 'checkpoint',
    id: cp.checkpoint_name || cp.name || cp.id || cp.timestamp || '',
    checkpoint_name: cp.checkpoint_name || cp.name || '',
    ts: cp.timestamp || cp.created_at || '',
    title: cp.description || cp.label || cp.checkpoint_name || cp.name || 'checkpoint',
    raw: cp,
  }));

  const eventItems = (_twEvents || []).map((ev, idx) => ({
    kind: 'event',
    id: ev.event_id || ev.id || `${ev.timestamp || 'event'}-${idx}`,
    ts: ev.timestamp || ev.created_at || ev.time || '',
    title: twEventDisplayTitle(ev),
    raw: ev,
  }));

  return [...checkpointItems, ...eventItems]
    .sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || '')))
    .slice(0, 180);
}

function renderTwHistoryPanel() {
  const list = document.getElementById('tw-history-list');
  if (!list) return;
  const items = getTwHistoryItems();
  if (!items.length) {
    list.innerHTML = '<div style="color:var(--text-dim);font-size:11px;text-align:center;padding:20px;">No checkpoints or events recorded yet.</div>';
    return;
  }

  list.innerHTML = items.map(item => {
    const isCheckpoint = item.kind === 'checkpoint';
    const color = isCheckpoint ? '#00d084' : '#6cb6ff';
    const isActive = _twSelected && _twSelected.kind === item.kind && _twSelected.id === item.id;
    const kindLabel = isCheckpoint ? 'SNAPSHOT' : 'LOG';
    const rollbackLabel = isCheckpoint ? 'Rollback' : 'Rollback to point';
    return `<div style="margin-bottom:8px;padding:10px;border:1px solid ${isActive ? 'var(--accent)' : 'var(--border)'};border-radius:6px;background:var(--card);">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;cursor:pointer;" onclick="selectTwHistoryItem(${_escHtml(JSON.stringify(item.kind))},${_escHtml(JSON.stringify(String(item.id)))})">
        <div style="flex:1;min-width:0;">
          <div style="font-size:10px;color:${color};font-weight:700;letter-spacing:0.4px;">${kindLabel}</div>
          <div style="font-size:11px;color:var(--text);font-weight:600;line-height:1.35;margin-top:2px;word-break:break-word;">${_escHtml(item.title || '(untitled)')}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:4px;word-break:break-all;">${_escHtml(item.ts || 'unknown time')}</div>
        </div>
      </div>
      <div style="display:flex;justify-content:flex-end;margin-top:8px;">
        <button onclick="twRollbackToHistory(${_escHtml(JSON.stringify(item.kind))},${_escHtml(JSON.stringify(String(item.id)))})" style="padding:4px 8px;background:${isCheckpoint ? '#f59e0b22' : 'var(--bg)'};border:1px solid ${isCheckpoint ? '#f59e0b55' : 'var(--border)'};border-radius:4px;color:${isCheckpoint ? '#f59e0b' : 'var(--text)'};font-size:10px;cursor:pointer;">${rollbackLabel}</button>
      </div>
    </div>`;
  }).join('');
}

function saveTwSelection() {
  if (!_twSelected) return;
  localStorage.setItem(TW_SELECTED_KEY, JSON.stringify(_twSelected));
}

function restoreTwSelection() {
  if (!_twSelected || !_twSelected.id || !_twSelected.kind) return;
  const exists = getTwHistoryItems().find(x => x.kind === _twSelected.kind && String(x.id) === String(_twSelected.id));
  if (!exists) {
    _twSelected = null;
    localStorage.removeItem(TW_SELECTED_KEY);
    return;
  }
  selectTwHistoryItem(_twSelected.kind, _twSelected.id, true);
}

function selectTwHistoryItem(kind, id, silent = false) {
  const items = getTwHistoryItems();
  const selected = items.find(x => x.kind === kind && String(x.id) === String(id));
  if (!selected) {
    if (!silent) showToast('History item not found', 'error');
    return;
  }

  _twSelected = { kind, id: String(id) };
  saveTwSelection();

  if (kind === 'checkpoint') {
    const idx = _twCheckpoints.findIndex(cp => String(cp.checkpoint_name || cp.name || cp.id || cp.timestamp || '') === String(id));
    const slider = document.getElementById('tw-slider');
    if (slider && idx >= 0) {
      slider.value = String(idx);
      renderTwSliderLabel();
      previewTwCheckpoint(false);
    }
    if (!silent) showToast(`Selected snapshot: ${selected.checkpoint_name || selected.title}`, 'success');
  } else {
    const cp = findTwCheckpointForEventTimestamp(selected.ts);
    if (cp) {
      const idx = _twCheckpoints.findIndex(x => (x.checkpoint_name || x.name) === (cp.checkpoint_name || cp.name));
      if (idx >= 0) {
        const slider = document.getElementById('tw-slider');
        if (slider) slider.value = String(idx);
        renderTwSliderLabel();
      }
      renderTwPreview({
        checkpoint_name: cp.checkpoint_name || cp.name,
        checkpoint_timestamp: cp.timestamp || cp.created_at,
        summary: { restorable: true },
        changes: { work_proposals: [], decisions: [], queue: [] },
      });
      if (!silent) showToast(`Event mapped to nearest snapshot: ${cp.checkpoint_name || cp.name}`, 'info');
    } else if (!silent) {
      showToast('No snapshot available before this event', 'error');
    }
  }

  renderTwHistoryPanel();
  renderTwVisualTimeline();
}

function findTwCheckpointForEventTimestamp(ts) {
  if (!_twCheckpoints.length) return null;
  const eventMs = Date.parse(ts || '');
  if (!Number.isFinite(eventMs)) return _twCheckpoints[0];

  let best = null;
  for (const cp of _twCheckpoints) {
    const cpMs = Date.parse(cp.timestamp || cp.created_at || '');
    if (!Number.isFinite(cpMs)) continue;
    if (cpMs <= eventMs) {
      best = cp;
      break;
    }
  }
  return best || null;
}

function renderTwVisualTimeline() {
  const container = document.getElementById('tw-visual-timeline');
  if (!container) return;
  const items = getTwHistoryItems().slice().reverse(); // oldest first for left-to-right
  if (!items.length) {
    container.innerHTML = '<div style="color:var(--text-dim);font-size:10px;padding:8px 12px;">No checkpoints or events yet.</div>';
    return;
  }

  const H = _escHtml;
  const nodes = items.map((item, idx) => {
    const isCheckpoint = item.kind === 'checkpoint';
    const isActive = _twSelected && _twSelected.kind === item.kind && String(_twSelected.id) === String(item.id);
    const color = isCheckpoint ? '#00d084' : '#6cb6ff';
    const size = isCheckpoint ? 12 : 7;
    const border = isActive ? '2px solid var(--accent)' : `2px solid ${color}`;
    const bg = isActive ? 'var(--accent)' : (isCheckpoint ? color : 'transparent');
    const shape = isCheckpoint ? `border-radius:2px;transform:rotate(45deg);` : `border-radius:50%;`;
    const timeStr = (item.ts || '').slice(11, 16) || '';
    const dateStr = (item.ts || '').slice(5, 10) || '';
    const label = isCheckpoint ? (item.checkpoint_name || item.title || '').slice(0, 18) : '';
    // Connector line (not for the first node)
    const connector = idx > 0 ? `<div style="width:20px;height:2px;background:var(--border);flex-shrink:0;"></div>` : '';
    return `${connector}<div style="display:flex;flex-direction:column;align-items:center;cursor:pointer;flex-shrink:0;min-width:${isCheckpoint ? 48 : 16}px;" onclick="selectTwHistoryItem(${H(JSON.stringify(item.kind))},${H(JSON.stringify(String(item.id)))})" title="${H((item.title || '').slice(0, 80))}\n${H(item.ts || '')}">
      <div style="width:${size}px;height:${size}px;${shape}border:${border};background:${bg};flex-shrink:0;"></div>
      ${label ? `<div style="font-size:8px;color:var(--text-dim);margin-top:3px;max-width:56px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;">${H(label)}</div>` : ''}
      ${timeStr ? `<div style="font-size:7px;color:var(--text-dim);opacity:0.7;">${H(dateStr)} ${H(timeStr)}</div>` : ''}
    </div>`;
  }).join('');

  container.innerHTML = nodes;
  // Auto-scroll to end (latest) on initial render
  container.scrollLeft = container.scrollWidth;
}

function setTwAutoRefresh(enabled) {
  _twAutoRefreshEnabled = Boolean(enabled);
  localStorage.setItem(TW_AUTO_REFRESH_KEY, _twAutoRefreshEnabled ? '1' : '0');

  if (_twAutoRefreshTimer) {
    clearInterval(_twAutoRefreshTimer);
    _twAutoRefreshTimer = null;
  }

  if (_twAutoRefreshEnabled) {
    _twAutoRefreshTimer = setInterval(() => {
      if (!document.getElementById('tw-timeline')) {
        clearInterval(_twAutoRefreshTimer);
        _twAutoRefreshTimer = null;
        return;
      }
      loadTimeWizardData();
    }, 15000);
  }
}

function applyTwFilters() {
  const q = (document.getElementById('tw-search')?.value || '').toLowerCase();
  const state = document.getElementById('tw-filter')?.value || 'all';
  const filtered = _twDecisions.filter(d => {
    const matchQ = !q || (d.title || d.summary || '').toLowerCase().includes(q) || (d.id || '').toLowerCase().includes(q);
    const matchS = state === 'all' || (d.status || '').toUpperCase() === state;
    return matchQ && matchS;
  });
  renderTwTimeline(filtered);
}

async function expandTwDecision(id) {
  if (!id) return;
  try {
    const res = await fetch(`/api/decisions/${id}`);
    const d = await res.json();
    
    // Build detail panel HTML
    const H = _escHtml;
    const detailHtml = `
      <div style="background: var(--card); border: 1px solid var(--border); border-radius: 4px; padding: 16px; margin-top: 12px;">
        <div style="font-size: 14px; font-weight: 700; margin-bottom: 12px;"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M3 2h7l3 3v8a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3"/><path d="M5 8h6M5 11h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Decision Details</div>
        <div style="font-size: 12px; line-height: 1.6;">
          <div style="margin-bottom: 12px;">
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">ID</div>
            <div style="color: var(--text); font-family: monospace;">${H(d.id || d.decision_id || id)}</div>
          </div>
          <div style="margin-bottom: 12px;">
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">Status</div>
            <div style="color: var(--text);">${H(d.status || 'UNKNOWN')}</div>
          </div>
          <div style="margin-bottom: 12px;">
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">Title</div>
            <div style="color: var(--text);">${H(d.title || d.summary || '(no title)')}</div>
          </div>
          ${d.issue ? `<div style="margin-bottom: 12px;">
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">Issue</div>
            <div style="color: var(--text); white-space: pre-wrap;">${H(d.issue)}</div>
          </div>` : ''}
          ${d.solution ? `<div style="margin-bottom: 12px;">
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">Solution</div>
            <div style="color: var(--text); white-space: pre-wrap;">${H(d.solution)}</div>
          </div>` : ''}
          ${d.scope ? `<div style="margin-bottom: 12px;">
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">Scope</div>
            <div style="color: var(--text); white-space: pre-wrap;">${H(d.scope)}</div>
          </div>` : ''}
          ${d.risks ? `<div style="margin-bottom: 12px;">
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">Risks</div>
            <div style="color: var(--text); white-space: pre-wrap;">${H(d.risks)}</div>
          </div>` : ''}
          ${d.next_steps ? `<div>
            <div style="font-weight: 600; color: var(--accent); font-size: 11px; text-transform: uppercase;">Next Steps</div>
            <div style="color: var(--text); white-space: pre-wrap;">${H(d.next_steps)}</div>
          </div>` : ''}
        </div>
      </div>
    `;
    
    // Remove existing detail if present
    const existing = document.getElementById(`tw-detail-${id}`);
    if (existing) existing.remove();
    
    // Insert detail panel after timeline
    const timeline = document.getElementById('tw-timeline');
    if (timeline) {
      const wrapper = document.createElement('div');
      wrapper.id = `tw-detail-${id}`;
      wrapper.innerHTML = detailHtml;
      timeline.parentNode.insertBefore(wrapper, timeline.nextSibling);
    }
    
    showToast(`Loaded: ${d.title || d.status}`, 'success');
  } catch (e) {
    showToast(`Could not load decision ${id}`, 'error');
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// GHOST BRIEF  (window-scoped — all functions receive/store the content el)
// ─────────────────────────────────────────────────────────────────────────────

let _gbHistoryVisible = false;
let _gbBriefs = [];
let _gbContentEl = null;   // set by loadDocsGhostBrief, used by inner helpers

// Entry point called from docsSetTab('brief', contentEl)
function loadDocsGhostBrief(contentEl) {
  _gbContentEl = contentEl;
  _gbHistoryVisible = false;
  contentEl.innerHTML = `
    <div class="docs-center-stage docs-brief-stage">
      <div class="docs-panel docs-brief-shell">
        <div class="docs-toolbar docs-toolbar-spaced docs-brief-toolbar">
          <div>
            <div class="docs-title-line">Ghost Brief</div>
            <div class="docs-muted-copy">Daily synthesis, active swarm state, patterns, and the next 24h view.</div>
          </div>
          <div class="docs-quick-actions">
            <button id="gb-regen-btn" onclick="regenerateBriefInDocs()" class="knowledge-btn knowledge-btn-primary">&#8635; Generate</button>
            <button id="gb-hist-btn" onclick="toggleBriefHistoryInDocs()" class="knowledge-btn">History</button>
          </div>
        </div>
        <div id="gb-meta" class="docs-doc-row-meta docs-brief-meta"></div>
        <div id="gb-history-panel" class="docs-panel docs-brief-history-panel" style="display:none;">
          <div class="docs-section-label">Recent Briefs</div>
          <div id="gb-history-list" class="docs-scroll-list docs-doc-list">Loading...</div>
        </div>
        <div id="gb-body" class="docs-panel docs-brief-body"></div>
      </div>
    </div>`;
  _fetchAndRenderBrief(false);
}

async function _fetchAndRenderBrief(forceGenerate) {
  const body = document.getElementById('gb-body');
  const meta = document.getElementById('gb-meta');
  const btn  = document.getElementById('gb-regen-btn');
  if (!body) return;

  body.innerHTML = `<div class="docs-empty-state docs-brief-loading">
    <div class="docs-brief-loading-icon">&#128203;</div>
    <div>${forceGenerate ? 'Nine is reading the swarm state and synthesising...' : 'Loading latest brief...'}</div>
    ${forceGenerate ? '<div class="docs-doc-row-meta">This takes ~15 seconds.</div>' : ''}
  </div>`;
  if (btn) { btn.disabled = true; btn.textContent = forceGenerate ? 'Thinking...' : 'Loading...'; }

  try {
    const url    = forceGenerate ? '/api/brief/generate' : '/api/brief';
    const method = forceGenerate ? 'POST' : 'GET';
    const res    = await fetch(url, { method });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    const _raw = await res.json();
    const brief = _raw.brief || _raw; // unwrap {brief: {...}} or accept flat format

    const text = (brief.content || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const coloured = text
      .replace(/(═+)/g, '<span class="docs-brief-rule">$1</span>')
      .replace(/(GHOST BRIEF[^\n]*)/g, '<span class="docs-brief-headline">$1</span>')
      .replace(/^(SITUATION|TICKET PATTERNS|MEMORY HIGHLIGHTS|OPEN ITEMS|SYSTEM HEALTH|NINE'S TAKE|NEXT 24H)$/gm,
               '<span class="docs-brief-section">$1</span>')
      .replace(/(⚠️[^\n]*)/g, '<span class="docs-brief-warning">$1</span>')
      .replace(/(✅[^\n]*)/g, '<span class="docs-brief-success">$1</span>');

    body.innerHTML = `<div class="docs-brief-content">${coloured}</div>`;

    if (meta) {
      const genAt   = brief.generated_at || '';
      const tokens  = brief.tokens_used  || 0;
      const trigger = brief.triggered_by || 'unknown';
      meta.textContent = `Generated ${genAt} · ${tokens} tokens · trigger: ${trigger}`;
    }
  } catch (e) {
    body.innerHTML = `<div class="docs-error-state">
      <strong>Failed to load brief:</strong> ${e.message}<br>
      <span class="docs-doc-row-meta">Check ANTHROPIC_API_KEY is set and Claude API is reachable.</span>
    </div>`;
    showToast('Brief failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '\u21bb Generate'; }
  }
}

async function regenerateBriefInDocs() {
  await _fetchAndRenderBrief(true);
  if (_gbHistoryVisible) _loadBriefHistoryList();
}

function toggleBriefHistoryInDocs() {
  const panel = document.getElementById('gb-history-panel');
  const btn   = document.getElementById('gb-hist-btn');
  if (!panel) return;
  _gbHistoryVisible = !_gbHistoryVisible;
  panel.style.display = _gbHistoryVisible ? 'block' : 'none';
  if (btn) btn.classList.toggle('docs-filter-btn-active', _gbHistoryVisible);
  if (_gbHistoryVisible) _loadBriefHistoryList();
}

async function _loadBriefHistoryList() {
  const list = document.getElementById('gb-history-list');
  if (!list) return;
  try {
    const res  = await fetch('/api/brief/history?limit=20');
    const data = await res.json();
    _gbBriefs  = data.briefs || [];
    list.innerHTML = _gbBriefs.map(b => `
      <button type="button" onclick="_loadBriefPreview(${b.id})" class="docs-doc-row">
        <div class="docs-doc-row-title">#${b.id} · ${b.brief_type}</div>
        <div class="docs-doc-row-meta">${(b.generated_at||'').slice(0,16)}</div>
        <div class="docs-doc-row-meta">${b.tokens_used||0} tokens</div>
      </button>`).join('') || '<div class="docs-empty-state docs-empty-compact">No briefs yet.</div>';
  } catch (e) {
    list.innerHTML = `<div class="docs-error-state">Failed: ${e.message}</div>`;
  }
}

function _loadBriefPreview(id) {
  const body = document.getElementById('gb-body');
  const meta = document.getElementById('gb-meta');
  const brief = _gbBriefs.find(b => b.id === id);
  if (!brief || !body) { showToast('Brief not found', 'error'); return; }
  body.innerHTML = `<div class="docs-brief-content">${
    (brief.preview || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  }\n\n<span class="docs-brief-preview-note">[Brief #${id} preview — hit Generate for full text]</span></div>`;
  if (meta) meta.textContent = `Brief #${id} · ${(brief.generated_at||'').slice(0,16)} · ${brief.tokens_used||0} tokens`;
}

// Legacy no-ops (nothing should call these now)
function initGhostBrief()  {}
function regenerateBrief() {}
function toggleBriefHistory() {}
async function loadBriefHistory() {}
async function loadBriefById(id) {}

