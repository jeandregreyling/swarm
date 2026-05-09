// --- Vortex History Section ---
function renderVortexHistory() {
  const container = document.getElementById('tw-vortex-history');
  if (!container) return;
  container.innerHTML = '<div style="font-size:13px;font-weight:700;margin-bottom:8px;">Vortex History</div>' +
    (_twCheckpoints.length ? _twCheckpoints.map(c => `<div style="font-size:11px;padding:6px 0;border-bottom:1px solid var(--border);"><b>${_escHtml(c.checkpoint_name || c.name || 'checkpoint')}</b> <span style="color:var(--text-dim);">@ ${_escHtml(c.timestamp || c.created_at || '')}</span></div>`).join('') : '<div style="color:var(--text-dim);font-size:11px;">No checkpoints yet.</div>');
}

// MD-FEATURE-FBB9A817653C / MD-FEATURE-485CDCA789E8 — per-section "?" help popover
// for the Vortex side rail. Each section explains what it shows + offers a KC link.
const _TW_SECTION_HELP = {
  history: { title: 'Vortex History', blurb: 'Snapshot checkpoints captured by the Vortex (formerly Time Wizard). Every agent tool action ships a [vortex] commit so you can roll the workspace back step-by-step. Select a checkpoint to inspect or restore.', kc: '/knowledge?topic=vortex-history' },
  spine:   { title: 'Spine Feed', blurb: 'Live event stream from Seven\'s spine — every routing decision, queued ticket, and agent emit. The Open Traced button widens this into the full Traced window for filtering and audit.', kc: '/knowledge?topic=spine-feed' },
};
function twShowSectionHelp(key) {
  const meta = _TW_SECTION_HELP[key] || { title: key, blurb: 'No help blurb registered for this section yet.', kc: '/knowledge' };
  let modal = document.getElementById('tw-section-help-modal');
  if (modal) modal.remove();
  modal = document.createElement('div');
  modal.id = 'tw-section-help-modal';
  modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;';
  const safeTitle = (meta.title || key).replace(/[<>]/g, '');
  const safeBlurb = (meta.blurb || '').replace(/[<>]/g, '');
  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 20px;width:min(420px,90vw);box-shadow:0 14px 40px rgba(0,0,0,.4);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div style="font-size:13px;font-weight:700;display:inline-flex;align-items:center;gap:8px;color:var(--accent);">
          <span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:color-mix(in srgb,var(--accent) 18%,transparent);border:1px solid var(--accent);font-size:13px;">?</span>
          <span>Vortex — ${safeTitle}</span>
        </div>
        <button onclick="document.getElementById('tw-section-help-modal').remove()" aria-label="Close" style="background:transparent;border:none;color:var(--text-dim);font-size:18px;cursor:pointer;">×</button>
      </div>
      <div style="font-size:12px;line-height:1.55;color:var(--text);margin-bottom:12px;">${safeBlurb}</div>
      <div style="display:flex;gap:6px;justify-content:flex-end;">
        <a href="${meta.kc}" onclick="event.preventDefault();openWindow('knowledge','Knowledge','view-knowledge');document.getElementById('tw-section-help-modal').remove();" style="background:var(--accent);color:#000;border:none;border-radius:6px;padding:6px 12px;font-size:11px;font-weight:700;cursor:pointer;text-decoration:none;">Open KC manual →</a>
        <button onclick="document.getElementById('tw-section-help-modal').remove()" style="background:transparent;border:1px solid var(--border);border-radius:6px;padding:6px 12px;color:var(--text-dim);font-size:11px;cursor:pointer;">Close</button>
      </div>
      <div style="margin-top:10px;font-size:9px;color:var(--text-dim);text-align:right;">Press <kbd style="padding:0 5px;border:1px solid var(--border);border-radius:3px;background:var(--bg);">Esc</kbd> to close</div>
    </div>`;
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
  const escH = (e) => { if (e.key === 'Escape') { const m = document.getElementById('tw-section-help-modal'); if (m) m.remove(); document.removeEventListener('keydown', escH); } };
  document.addEventListener('keydown', escH);
  document.body.appendChild(modal);
}
window.twShowSectionHelp = twShowSectionHelp;

// Vortex explainer popover — what is this thing, how do checkpoints differ from git,
// what step-back actually does. Surfaced via the (i) button in the header.
function twOpenInfo() {
  let modal = document.getElementById('tw-info-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'tw-info-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.5);backdrop-filter:blur(4px);opacity:0;pointer-events:none;transition:opacity .15s;';
    modal.innerHTML = `
      <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:22px 26px;max-width:560px;width:92%;max-height:86vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,0.4);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="font-size:14px;font-weight:700;color:var(--text);">About Vortex</div>
          <button onclick="document.getElementById('tw-info-modal').style.opacity=0;document.getElementById('tw-info-modal').style.pointerEvents='none';" style="background:none;border:none;color:var(--text-dim);cursor:pointer;display:flex;align-items:center;padding:4px;">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </button>
        </div>
        <div style="font-size:12px;line-height:1.65;color:var(--text);">
          <p style="margin:0 0 10px;"><strong>Vortex</strong> is the swarm's traceability layer — every architectural decision, proposal, and state change flows through it. It's what lets you understand <em>why</em> the system is in its current shape, and step back if something went wrong.</p>
          <div style="display:grid;grid-template-columns:auto 1fr;gap:6px 12px;margin:12px 0;font-size:11.5px;">
            <div style="color:var(--accent);font-weight:700;">Decisions</div><div>Proposals from agents or the user that change architecture. Status: <code style="font-size:10.5px;">PROPOSED</code> → <code style="font-size:10.5px;">TESTING</code> → <code style="font-size:10.5px;">EXECUTED</code>.</div>
            <div style="color:var(--accent);font-weight:700;">Checkpoints</div><div>Snapshots of the DB plus tracked files, captured manually with <strong>Capture Checkpoint</strong> or automatically by proposals.</div>
            <div style="color:var(--accent);font-weight:700;">Events</div><div>Fine-grained state transitions (proposal merged, config changed, migration applied). Useful for audit.</div>
            <div style="color:var(--accent);font-weight:700;">Step-Back</div><div>Restores the DB and key files to a checkpoint. Always <strong>Dry Run</strong> first to see the diff.</div>
          </div>
          <div style="padding:10px 12px;border:1px solid color-mix(in srgb,var(--warning) 45%,var(--border));border-radius:8px;background:color-mix(in srgb,var(--warning) 9%,var(--card));margin:10px 0 12px;font-size:11px;color:var(--text);">
            <strong>Not the same as git.</strong> Git tracks code. Vortex tracks <em>state</em> — DB rows, attachments, chat history, proposal outcomes. Both can be used together; roll back Vortex for data, roll back git for code.
          </div>
          <div style="padding:10px 12px;border:1px solid color-mix(in srgb,var(--accent) 45%,var(--border));border-radius:8px;background:color-mix(in srgb,var(--accent) 9%,var(--card));margin:10px 0 12px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <svg viewBox="0 0 20 20" width="14" height="14" fill="none" style="color:var(--accent);"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" stroke-width="1.6"/><path d="M13 13l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
              <strong>Find a proposal or decision fast</strong>
              <kbd style="margin-left:auto;background:var(--window-header);border:1px solid var(--border);border-radius:3px;padding:1px 6px;font-size:11px;font-family:inherit;">Ctrl+Space</kbd>
            </div>
            <div style="font-size:11px;color:var(--text-dim);">Spotlight searches proposals by ID or title — type <code style="font-size:10.5px;">PROP-</code> or a keyword to jump straight to one.</div>
          </div>
          <p style="margin:6px 0 0;font-size:11.5px;color:var(--text-dim);">
            <strong style="color:var(--text);">Safety:</strong> apply-step-back is irreversible without another checkpoint — the system prompts you to capture one first if none exists within the last hour.
          </p>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) { modal.style.opacity = '0'; modal.style.pointerEvents = 'none'; }
    });
  }
  modal.style.opacity = '1';
  modal.style.pointerEvents = 'auto';
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

  _initTwSectionToggles();
  _initTwHistoryResize();
  setTwAutoRefresh(_twAutoRefreshEnabled);
  loadTimeWizardData();
}

// ── Slice 5d: collapsible side sections ────────────────────────────────────
function _initTwSectionToggles() {
  const KEY = 'vortex_section_collapsed';
  let collapsed = {};
  try { collapsed = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (_) {}
  document.querySelectorAll('.tw-section-toggle').forEach(btn => {
    const target = btn.getAttribute('data-target');
    if (!target) return;
    const tgt = document.getElementById(target);
    const caret = btn.querySelector('.tw-toggle-caret');
    const apply = (isCollapsed) => {
      if (tgt) tgt.style.display = isCollapsed ? 'none' : '';
      if (caret) caret.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
      btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
    };
    apply(!!collapsed[target]);
    btn.onclick = () => {
      collapsed[target] = !collapsed[target];
      try { localStorage.setItem(KEY, JSON.stringify(collapsed)); } catch (_) {}
      apply(!!collapsed[target]);
    };
  });
}

// ── Slice 5d: resizable history panel ──────────────────────────────────────
function _initTwHistoryResize() {
  const KEY = 'vortex_history_width';
  const handle = document.getElementById('tw-history-resizer');
  const panel = document.getElementById('tw-history-panel');
  if (!handle || !panel) return;
  const apply = (w) => {
    if (!w) { panel.style.width = ''; return; }
    const max = Math.floor(window.innerWidth * 0.6);
    const clamped = Math.max(220, Math.min(max, w));
    panel.style.width = clamped + 'px';
  };
  const saved = parseInt(localStorage.getItem(KEY) || '0', 10);
  if (saved > 0) apply(saved);

  let dragging = false;
  const onMove = (e) => {
    if (!dragging) return;
    const x = (e.touches && e.touches[0]) ? e.touches[0].clientX : e.clientX;
    const rect = panel.getBoundingClientRect();
    const newW = rect.right - x;
    apply(newW);
    try { localStorage.setItem(KEY, String(parseInt(panel.style.width, 10) || 0)); } catch (_) {}
    e.preventDefault();
  };
  const onUp = () => {
    dragging = false;
    document.body.style.cursor = '';
    handle.style.background = '';
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.removeEventListener('touchmove', onMove);
    document.removeEventListener('touchend', onUp);
  };
  const onDown = (e) => {
    dragging = true;
    document.body.style.cursor = 'col-resize';
    handle.style.background = 'var(--accent)';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('touchend', onUp);
    e.preventDefault();
  };
  handle.addEventListener('mousedown', onDown);
  handle.addEventListener('touchstart', onDown, { passive: false });
  handle.addEventListener('dblclick', () => {
    try { localStorage.removeItem(KEY); } catch (_) {}
    apply(0);
  });
  handle.addEventListener('keydown', (e) => {
    const cur = parseInt(panel.getBoundingClientRect().width, 10) || 320;
    if (e.key === 'ArrowLeft')  { apply(cur + 24); e.preventDefault(); }
    else if (e.key === 'ArrowRight') { apply(cur - 24); e.preventDefault(); }
    else if (e.key === 'Home')  { apply(0); try { localStorage.removeItem(KEY); } catch (_) {} e.preventDefault(); return; }
    else return;
    try { localStorage.setItem(KEY, String(parseInt(panel.style.width, 10) || 0)); } catch (_) {}
  });
}

// ── Slice 5d: Vortex health pill ───────────────────────────────────────────
function _renderTwHealth() {
  const pill = document.querySelector('#tw-health-strip .tw-health-pill');
  if (!pill) return;
  const dot = pill.querySelector('.tw-health-dot');
  const label = pill.querySelector('.tw-health-label');
  const sessions = (_twSessions || []).length;
  const checkpoints = (_twCheckpoints || []).length;
  const events = (_twEvents || []).length;
  const decisions = (_twDecisions || []).length;
  let state = 'ok', text = '';
  if (!sessions && !checkpoints && !events && !decisions) {
    state = 'idle';
    text = 'Vortex idle — no sessions or checkpoints yet';
  } else if (!checkpoints) {
    state = 'warn';
    text = `Vortex live · ${events} events · 0 checkpoints (save one to enable rollback)`;
  } else if (!sessions) {
    state = 'warn';
    text = `Vortex history present · ${checkpoints} checkpoints · session inactive`;
  } else {
    state = 'ok';
    text = `Vortex healthy · ${sessions} session${sessions===1?'':'s'} · ${checkpoints} checkpoints · ${events} events`;
  }
  const palette = {
    ok:    { bg:'#22c55e', fg:'#22c55e', border:'#22c55e55' },
    warn:  { bg:'#f59e0b', fg:'#f59e0b', border:'#f59e0b55' },
    idle:  { bg:'var(--text-dim)', fg:'var(--text-dim)', border:'var(--border)' },
  }[state];
  if (dot)   dot.style.background = palette.bg;
  if (label) label.textContent = text;
  pill.style.borderColor = palette.border;
  pill.style.color = palette.fg;
  pill.setAttribute('data-state', state);
}

let _twGitDriftToastKey = '';

async function checkVortexGitDrift() {
  if (typeof checkVortexGitSyncDrift === 'function') {
    checkVortexGitSyncDrift();
    return;
  }
  try {
    const resp = await fetch('/api/git/status?check_remote=1');
    const data = await resp.json().catch(() => ({}));
    if (!data || !data.ok) return;
    const sync = data.out_of_sync || {};
    const remote = data.remote_check || {};
    if (!remote.checked || !remote.ok) return;
    if (!sync.needs_pull) return;
    const key = `${data.branch || ''}:${data.upstream || ''}:${data.behind || 0}`;
    if (key === _twGitDriftToastKey) return;
    _twGitDriftToastKey = key;
    const msg = sync.summary || `Git is behind by ${data.behind || 0} commit(s). Pull before continuing.`;
    if (typeof showToast === 'function') showToast(`Vortex Git sync: ${msg}`, 'warning');
  } catch (_) {}
}

async function loadTimeWizardData() {
  // Y.58 — install Cyber + VPN tabs alongside the timeline. Idempotent.
  twInstallTabs();
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
    checkVortexGitDrift();
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
  try { _renderTwHealth(); } catch (_) {}
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
  // Top-of-Vortex Seven life-story summary — system-wide narrative.
  try {
    if (window.SevenPanel) {
      const parent = container.parentNode;
      let host = document.getElementById('tw-seven-life');
      if (!host && parent) {
        host = document.createElement('div');
        host.id = 'tw-seven-life';
        host.style.cssText = 'margin:0 0 10px 0;';
        parent.insertBefore(host, container);
      }
      if (host && !host.dataset.mounted) {
        host.dataset.mounted = '1';
        window.SevenPanel.mount(host, { kind: 'system', id: 'vortex' });
      }
    }
  } catch (e) { /* noop */ }
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
      // Seven life-story panel — pulls /api/seven/related at depth 2 for
      // this record id and renders a propose-only insight footer.
      try {
        if (window.SevenPanel) {
          // Decision id may be a UUID, ticket number, or record id. SevenPanel
          // tries to resolve via /api/seven/observe?focus=<id> and renders
          // narrative + proposals; failure-quiet if not a record kind.
          const inner = wrapper.querySelector(':scope > div');
          if (inner) {
            window.SevenPanel.mount(inner, { kind: 'decision', id: String(id) });
          }
        }
      } catch (e) { /* noop */ }
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


// ── Session 29 — Vortex spine feed ───────────────────────────────────────
// Small live list in the sidebar that shows the last ~30 significant spine
// events (relay steps, watchdog stalls, tickets, checkpoints, testlab runs).
// Subscribes to window.__trace; falls back to a one-shot fetch if the bus
// isn't online yet.
(function () {
  const MAX = 30;
  const KINDS = new Set(['relay_step', 'watchdog', 'checkpoint', 'ticket', 'testlab', 'guardian']);
  const buf = [];

  function render() {
    const el = document.getElementById('tw-spine-feed');
    if (!el) return;
    if (!buf.length) {
      el.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:8px;">No spine events yet.</div>';
      return;
    }
    el.innerHTML = buf.map(ev => {
      const ts = new Date((ev.ts || 0) * 1000);
      const hh = String(ts.getHours()).padStart(2, '0');
      const mm = String(ts.getMinutes()).padStart(2, '0');
      const sevClr = { warn: '#d8a032', error: '#d85032', critical: '#ff3860', info: '#6a8ab0', debug: '#555' }[ev.severity] || '#6a8ab0';
      return `<div style="display:flex;gap:6px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
        <span style="color:var(--text-dim);font-family:monospace;">${hh}:${mm}</span>
        <span style="color:${sevClr};font-weight:700;text-transform:uppercase;font-size:8px;min-width:54px;">${_escHtml(ev.kind || '')}</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(ev.agent ? ev.agent + ' · ' : '')}${_escHtml(ev.message || '')}</span>
      </div>`;
    }).join('');
  }

  function push(ev) {
    if (!ev || !KINDS.has(ev.kind)) return;
    buf.unshift(ev);
    if (buf.length > MAX) buf.length = MAX;
    render();
  }

  function primeFromApi() {
    fetch('/api/spine/events?limit=30&source=db&kinds=' + Array.from(KINDS).join(','))
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) return;
        buf.length = 0;
        (data.items || []).forEach(ev => { if (KINDS.has(ev.kind)) buf.push(ev); });
        render();
      })
      .catch(() => {});
  }

  function attach() {
    primeFromApi();
    if (window.__trace && !window.__tw_spine_bound) {
      window.__trace.on('event', push);
      window.__tw_spine_bound = true;
    }
  }

  // Re-attach whenever the Vortex window becomes visible.
  document.addEventListener('DOMContentLoaded', attach);
  const _origLoadTimeWizard = window.loadTimeWizardData;
  window.loadTimeWizardData = function () {
    const r = _origLoadTimeWizard ? _origLoadTimeWizard.apply(this, arguments) : undefined;
    setTimeout(attach, 120);
    return r;
  };
})();

/* ───────────────────────────────────────────────────────────────────────
 * Y.58 — Vortex tabs (Timeline / Cyber / VPN). Cyber + VPN panes were
 * promoted from standalone home tiles into Vortex per user request.
 * ─────────────────────────────────────────────────────────────────────── */
function twInstallTabs() {
  // Find the Vortex root: any open window whose content includes #tw-timeline
  const tlNode = document.getElementById('tw-timeline');
  if (!tlNode) return;
  const root = tlNode.closest('.content-view');
  if (!root || root.dataset.twTabsInstalled === '1') return;
  root.dataset.twTabsInstalled = '1';

  // Locate the header (first child div with border-bottom). Safer: the div
  // containing the <h3> with "Vortex".
  let header = null;
  root.querySelectorAll('div').forEach((d) => {
    if (!header && d.querySelector && d.querySelector('h3') && /Vortex/i.test(d.textContent || '')) header = d;
  });
  if (!header) return;

  // Build a tab-bar and insert it directly after the header.
  const tabBar = document.createElement('div');
  tabBar.id = 'tw-tabbar';
  tabBar.style.cssText = 'display:flex;gap:2px;padding:0 10px;border-bottom:1px solid var(--border);background:var(--window-header);flex-shrink:0;';
  tabBar.innerHTML = `
    <button type="button" class="tw-tab-btn" data-tw-tab="timeline" style="padding:8px 14px;background:transparent;border:none;border-bottom:2px solid var(--accent);color:var(--text);font-size:11px;font-weight:700;cursor:pointer;">Timeline</button>
    <button type="button" class="tw-tab-btn" data-tw-tab="cyber" style="padding:8px 14px;background:transparent;border:none;border-bottom:2px solid transparent;color:var(--text-dim);font-size:11px;font-weight:600;cursor:pointer;">🛡 Cyber Security</button>
    <button type="button" class="tw-tab-btn" data-tw-tab="vpn" style="padding:8px 14px;background:transparent;border:none;border-bottom:2px solid transparent;color:var(--text-dim);font-size:11px;font-weight:600;cursor:pointer;">🔐 VPN / Tailscale</button>
  `;
  header.insertAdjacentElement('afterend', tabBar);

  // Wrap everything after the tabBar inside a #tw-pane-timeline div so we
  // can hide it as a unit when switching tabs.
  const timelinePane = document.createElement('div');
  timelinePane.id = 'tw-pane-timeline';
  timelinePane.style.cssText = 'display:flex;flex-direction:column;flex:1;min-height:0;';
  let nxt = tabBar.nextSibling;
  while (nxt) {
    const after = nxt.nextSibling;
    timelinePane.appendChild(nxt);
    nxt = after;
  }
  root.appendChild(timelinePane);

  // Cyber pane (clones the wishlist-cyber template).
  const cyberPane = document.createElement('div');
  cyberPane.id = 'tw-pane-cyber';
  cyberPane.style.cssText = 'display:none;flex:1;min-height:0;overflow:hidden;';
  root.appendChild(cyberPane);

  // VPN pane (clones the view-vpn template).
  const vpnPane = document.createElement('div');
  vpnPane.id = 'tw-pane-vpn';
  vpnPane.style.cssText = 'display:none;flex:1;min-height:0;overflow:hidden;';
  root.appendChild(vpnPane);

  let cyberLoaded = false;
  let vpnLoaded = false;

  tabBar.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.tw-tab-btn');
    if (!btn) return;
    const tab = btn.dataset.twTab;
    tabBar.querySelectorAll('.tw-tab-btn').forEach((b) => {
      const on = b === btn;
      b.style.borderBottomColor = on ? 'var(--accent)' : 'transparent';
      b.style.color = on ? 'var(--text)' : 'var(--text-dim)';
      b.style.fontWeight = on ? '700' : '600';
    });
    timelinePane.style.display = tab === 'timeline' ? 'flex' : 'none';
    cyberPane.style.display = tab === 'cyber' ? 'flex' : 'none';
    vpnPane.style.display = tab === 'vpn' ? 'flex' : 'none';

    if (tab === 'cyber' && !cyberLoaded) {
      cyberLoaded = true;
      const tpl = document.getElementById('view-wishlist-cyber');
      if (tpl) {
        cyberPane.appendChild(tpl.content.cloneNode(true));
        // Trigger the existing pillar live-loader if available.
        try {
          if (typeof window.loadWishlistPillar === 'function') {
            window.loadWishlistPillar({ el: cyberPane }, 'cyber-security');
          } else if (typeof window.pillarLiveInit === 'function') {
            window.pillarLiveInit(cyberPane, 'cyber-security');
          }
        } catch (_) {}
      } else {
        cyberPane.innerHTML = '<div style="padding:14px;color:var(--text-dim);font-size:11px;">Cyber pillar template not found.</div>';
      }
    }
    if (tab === 'vpn' && !vpnLoaded) {
      vpnLoaded = true;
      const tpl = document.getElementById('view-vpn');
      if (tpl) {
        vpnPane.appendChild(tpl.content.cloneNode(true));
        try {
          if (typeof window.loadVpnData === 'function') {
            window.loadVpnData({ el: vpnPane });
          }
        } catch (_) {}
      } else {
        vpnPane.innerHTML = '<div style="padding:14px;color:var(--text-dim);font-size:11px;">VPN template not found.</div>';
      }
    }
  });
}
