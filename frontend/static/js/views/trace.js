// Trace view — end-to-end message tracing
// Phase 3b — Trace Troubleshooter

/* ── helpers ─────────────────────────────────────────────────────────── */
function _traceEsc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function _traceBadge(text, color) {
  return `<span style="font-size:10px;padding:1px 6px;border-radius:3px;background:${color}22;color:${color};font-weight:600;">${_traceEsc(text)}</span>`;
}

function _traceTime(iso) {
  if (!iso) return '';
  try { return iso.replace('T', ' ').slice(0, 19); } catch { return iso; }
}

const _traceEventColors = {
  dispatch: '#2196f3',
  route:    '#2196f3',
  complete: '#4caf50',
  final:    '#4caf50',
  response: '#4caf50',
  error:    '#f44336',
  skill_call:   '#ff9800',
  skill_result: '#ff9800',
  stage:    '#9c27b0',
  relay:    '#00bcd4',
  gate:     '#607d8b',
  health:   '#795548',
  proposal: '#e91e63',
};

/* ── init (called by app.js on window open) ──────────────────────────── */
function initTraceView(win) {
  // If opened from a conversation link, auto-load
  const convInput = document.getElementById('trace-conv-id');
  if (convInput && convInput.value) traceLoadConversation();
  // Default tab is 'trace' — nothing extra to do
}

/* ── tab switching ───────────────────────────────────────────────────── */
let _traceSyslogES = null;   // EventSource instance

function traceSwitchTab(tab) {
  const traceBody  = document.getElementById('trace-trace-body');
  const syslogBody = document.getElementById('trace-syslog-body');
  const tabTrace   = document.getElementById('trace-tab-trace');
  const tabSyslog  = document.getElementById('trace-tab-syslog');
  if (!traceBody || !syslogBody) return;

  if (tab === 'syslog') {
    traceBody.style.display  = 'none';
    syslogBody.style.display = 'flex';
    if (tabTrace)  { tabTrace.style.borderBottomColor  = 'transparent'; tabTrace.style.color  = 'var(--text-dim)'; tabTrace.style.fontWeight  = '400'; }
    if (tabSyslog) { tabSyslog.style.borderBottomColor = 'var(--accent)'; tabSyslog.style.color = 'var(--text)';     tabSyslog.style.fontWeight = '600'; }
    _traceStartSyslog();
  } else {
    syslogBody.style.display = 'none';
    traceBody.style.display  = 'flex';
    if (tabTrace)  { tabTrace.style.borderBottomColor  = 'var(--accent)'; tabTrace.style.color  = 'var(--text)';     tabTrace.style.fontWeight  = '600'; }
    if (tabSyslog) { tabSyslog.style.borderBottomColor = 'transparent';   tabSyslog.style.color = 'var(--text-dim)'; tabSyslog.style.fontWeight = '400'; }
    _traceStopSyslog();
  }
}

/* ── system log: start SSE stream ────────────────────────────────────── */
function _traceStartSyslog() {
  if (_traceSyslogES) return;   // already running

  const panel  = document.getElementById('trace-syslog-panel');
  const status = document.getElementById('trace-syslog-status');
  if (!panel) return;

  // Load recent entries first via REST so the panel isn't empty on open
  fetch('/api/activity?limit=100')
    .then(r => r.json())
    .then(data => {
      const entries = data.activities || [];
      if (!entries.length) {
        panel.innerHTML = '<div style="color:var(--text-dim);">No activity log entries yet.</div>';
      } else {
        panel.innerHTML = '';
        entries.reverse().forEach(e => panel.appendChild(_traceSyslogRow(e.timestamp, e.message, e.level || 'info')));
      }
    })
    .catch(() => {
      panel.innerHTML = '<div style="color:#f44336;">Failed to load activity log.</div>';
    });

  // Open SSE stream for live updates
  try {
    _traceSyslogES = new EventSource('/api/activity/stream');

    _traceSyslogES.onopen = () => {
      if (status) status.textContent = '● Live';
      if (status) status.style.color = '#4caf50';
    };

    _traceSyslogES.onmessage = (e) => {
      // Self-clean if the trace window was closed without switching tabs
      const panel = document.getElementById('trace-syslog-panel');
      if (!panel) { _traceStopSyslog(); return; }
      try {
        const row = JSON.parse(e.data);
        const ts  = (row.created_at || '').slice(0, 16).replace('T', ' ');
        const msg = `${row.service || 'system'}: ${row.event || ''} ${row.detail || ''}`.trim();
        const el  = _traceSyslogRow(ts, msg, 'live');
        panel.prepend(el);
        // Cap at 500 rows to avoid memory growth
        while (panel.children.length > 500) panel.removeChild(panel.lastChild);
      } catch (_) {}
    };

    _traceSyslogES.onerror = () => {
      if (status) { status.textContent = '⚠ Disconnected — retrying…'; status.style.color = '#ff9800'; }
    };
  } catch (err) {
    if (status) { status.textContent = 'SSE not available'; status.style.color = 'var(--text-dim)'; }
  }
}

/* ── system log: stop SSE stream ─────────────────────────────────────── */
function _traceStopSyslog() {
  if (_traceSyslogES) {
    _traceSyslogES.close();
    _traceSyslogES = null;
  }
  const status = document.getElementById('trace-syslog-status');
  if (status) { status.textContent = 'Stopped'; status.style.color = 'var(--text-dim)'; }
}

/* ── system log: clear panel ─────────────────────────────────────────── */
function traceSyslogClear() {
  const panel = document.getElementById('trace-syslog-panel');
  if (panel) panel.innerHTML = '';
}

/* ── system log: render one row ─────────────────────────────────────── */
function _traceSyslogRow(ts, msg, level) {
  const colors = { live: '#4caf50', warn: '#ff9800', error: '#f44336', info: 'var(--text-dim)' };
  const col    = colors[level] || 'var(--text-dim)';
  const el     = document.createElement('div');
  el.style.cssText = 'padding:2px 0;border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:baseline;';
  el.innerHTML = `<span style="color:${col};flex-shrink:0;min-width:130px;font-size:10px;">${_traceEsc(ts)}</span>`
               + `<span style="color:var(--text);word-break:break-all;">${_traceEsc(msg)}</span>`;
  return el;
}

/* ── load recent conversations (for quick access) ──────────────────── */
function traceLoadRecent() {
  const panel = document.getElementById('trace-jobs-panel');
  if (!panel) return;
  panel.innerHTML = '<div style="padding:12px 14px;font-size:11px;color:var(--text-dim);">Loading recent…</div>';

  fetch('/api/conversations')
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      const convs = Array.isArray(data) ? data : (data.conversations || []);
      if (!convs.length) {
        panel.innerHTML = '<div style="padding:12px 14px;font-size:11px;color:var(--text-dim);">No conversations found.</div>';
        return;
      }
      panel.innerHTML = convs.slice(0, 30).map(c => {
        const id = c.id || c.conversation_id;
        const title = (c.title || c.subject || 'Untitled').slice(0, 60);
        const ts = _traceTime(c.created_at || c.updated_at || '');
        const agent = c.agent || c.last_agent || '';
        return `<div onclick="traceLoadConversationById(${id})" style="padding:8px 14px;border-bottom:1px solid var(--border);cursor:pointer;font-size:11px;" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background=''">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong>#${id}</strong>
            ${agent ? _traceBadge(agent, '#2196f3') : ''}
          </div>
          <div style="margin-top:2px;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_traceEsc(title)}</div>
          <div style="margin-top:2px;font-size:10px;color:var(--text-dim);">${_traceEsc(ts)}</div>
        </div>`;
      }).join('');
    })
    .catch(err => {
      panel.innerHTML = `<div style="padding:12px 14px;font-size:11px;color:#f44336;">Error: ${_traceEsc(err.message)}</div>`;
    });
}

/* ── load conversation trace ─────────────────────────────────────────── */
function traceLoadConversation() {
  const input = document.getElementById('trace-conv-id');
  if (!input || !input.value) return;
  traceLoadConversationById(parseInt(input.value, 10));
}

function traceLoadConversationById(convId) {
  if (!convId) return;
  // Update input
  const input = document.getElementById('trace-conv-id');
  if (input) input.value = convId;

  const panel = document.getElementById('trace-jobs-panel');
  const detail = document.getElementById('trace-detail-panel');
  if (panel) panel.innerHTML = '<div style="padding:12px 14px;font-size:11px;color:var(--text-dim);">Loading trace…</div>';
  if (detail) detail.innerHTML = '<div style="font-size:12px;color:var(--text-dim);">Loading…</div>';

  fetch(`/api/trace/conversation/${convId}`)
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      if (data.error) { _traceShowError(data.error); return; }
      _traceRenderJobList(data);
      _traceRenderConversationOverview(data);
    })
    .catch(err => _traceShowError(err.message));
}

/* ── load single job trace ───────────────────────────────────────────── */
function traceLoadJob() {
  const input = document.getElementById('trace-job-id');
  if (!input || !input.value.trim()) return;
  const jobId = input.value.trim();

  const detail = document.getElementById('trace-detail-panel');
  if (detail) detail.innerHTML = '<div style="font-size:12px;color:var(--text-dim);">Loading…</div>';

  fetch(`/api/trace/${encodeURIComponent(jobId)}`)
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      if (data.error) { _traceShowError(data.error); return; }
      _traceRenderJobDetail(data);
    })
    .catch(err => _traceShowError(err.message));
}

function traceLoadJobById(jobId) {
  const input = document.getElementById('trace-job-id');
  if (input) input.value = jobId;

  const detail = document.getElementById('trace-detail-panel');
  if (detail) detail.innerHTML = '<div style="font-size:12px;color:var(--text-dim);">Loading…</div>';

  fetch(`/api/trace/${encodeURIComponent(jobId)}`)
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      if (data.error) { _traceShowError(data.error); return; }
      _traceRenderJobDetail(data);
    })
    .catch(err => _traceShowError(err.message));
}

/* ── render: job list (left panel) ───────────────────────────────────── */
function _traceRenderJobList(data) {
  const panel = document.getElementById('trace-jobs-panel');
  if (!panel) return;
  const jobs = data.jobs || [];
  if (!jobs.length) {
    panel.innerHTML = '<div style="padding:12px 14px;font-size:11px;color:var(--text-dim);">No jobs found for this conversation.</div>';
    return;
  }

  panel.innerHTML = `<div style="padding:8px 14px;border-bottom:1px solid var(--border);font-size:10px;color:var(--text-dim);font-weight:600;">
    ${jobs.length} job${jobs.length === 1 ? '' : 's'} &middot; conv #${data.conversation_id}
  </div>` + jobs.map(j => {
    const st = j.status || 'unknown';
    const stColor = st === 'complete' || st === 'done' ? '#4caf50'
                  : st === 'error' || st === 'failed' ? '#f44336'
                  : st === 'running' || st === 'dispatched' ? '#ff9800'
                  : '#888';
    const elapsed = j.elapsed_ms ? `${(j.elapsed_ms / 1000).toFixed(1)}s` : '';
    const tokens = j.tokens ? `${j.tokens} tok` : '';
    const agent = j.agent || '?';
    const ts = _traceTime(j.started_at || '');
    const jid = j.job_id || '';
    const stages = (j.stage_trace || []).length;
    return `<div onclick="traceLoadJobById('${_traceEsc(jid)}')" style="padding:8px 14px;border-bottom:1px solid var(--border);cursor:pointer;font-size:11px;" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background=''">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;">
        ${_traceBadge(agent, '#2196f3')}
        ${_traceBadge(st, stColor)}
      </div>
      <div style="margin-top:4px;display:flex;gap:8px;font-size:10px;color:var(--text-dim);">
        ${elapsed ? `<span>⏱ ${elapsed}</span>` : ''}
        ${tokens ? `<span><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><path d="M3 4h10M3 8h7M3 12h10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> ${tokens}</span>` : ''}
        ${stages ? `<span><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="2" y="9" width="3" height="4" rx="0.5" stroke="currentColor" stroke-width="1.2"/><rect x="6.5" y="5" width="3" height="8" rx="0.5" stroke="currentColor" stroke-width="1.2"/><rect x="11" y="2" width="3" height="11" rx="0.5" stroke="currentColor" stroke-width="1.2"/></svg> ${stages} stages</span>` : ''}
      </div>
      <div style="margin-top:2px;font-size:10px;color:var(--text-dim);">${_traceEsc(ts)}</div>
      <div style="margin-top:1px;font-size:9px;color:var(--text-dim);opacity:0.6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_traceEsc(jid)}</div>
    </div>`;
  }).join('');
}

/* ── render: conversation overview (right panel) ─────────────────────── */
function _traceRenderConversationOverview(data) {
  const detail = document.getElementById('trace-detail-panel');
  if (!detail) return;

  const jobs = data.jobs || [];
  const timeline = data.timeline || [];
  const messages = data.messages || [];

  let html = `<div style="margin-bottom:16px;">
    <div style="font-weight:700;font-size:14px;margin-bottom:8px;">Conversation #${data.conversation_id}</div>
    <div style="display:flex;gap:16px;font-size:12px;color:var(--text-dim);">
      <span><strong>${jobs.length}</strong> job${jobs.length !== 1 ? 's' : ''}</span>
      <span><strong>${timeline.length}</strong> timeline events</span>
      <span><strong>${messages.length}</strong> messages</span>
    </div>
  </div>`;

  // Unified timeline: merge timeline + jobs into chronological event list
  const events = [];
  timeline.forEach(t => {
    events.push({
      ts: t.created_at || '',
      type: t.event_type || 'event',
      agent: t.agent || '',
      payload: t.payload || '',
      jobId: t.job_id || '',
      source: 'timeline',
    });
  });
  jobs.forEach(j => {
    (j.stage_trace || []).forEach(st => {
      events.push({
        ts: st.ts || st.timestamp || j.started_at || '',
        type: 'stage',
        agent: j.agent || '',
        payload: st.stage || st.label || JSON.stringify(st),
        jobId: j.job_id || '',
        source: 'stage_trace',
      });
    });
  });
  events.sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));

  if (events.length) {
    html += `<div style="font-weight:600;font-size:12px;margin-bottom:8px;">Unified Timeline</div>`;
    html += `<div style="border-left:2px solid var(--border);padding-left:12px;">`;
    events.slice(0, 200).forEach(ev => {
      const color = _traceEventColors[ev.type] || '#888';
      html += `<div style="margin-bottom:6px;font-size:11px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="width:6px;height:6px;border-radius:50%;background:${color};flex-shrink:0;"></span>
          ${_traceBadge(ev.type, color)}
          ${ev.agent ? `<span style="font-size:10px;color:var(--text-dim);">${_traceEsc(ev.agent)}</span>` : ''}
          <span style="font-size:10px;color:var(--text-dim);margin-left:auto;">${_traceEsc(_traceTime(ev.ts))}</span>
        </div>
        <div style="margin-left:12px;margin-top:2px;color:var(--text);font-size:11px;word-break:break-all;">${_traceEsc(String(ev.payload).slice(0, 300))}</div>
      </div>`;
    });
    html += `</div>`;
  }

  // Messages summary
  if (messages.length) {
    html += `<div style="font-weight:600;font-size:12px;margin:16px 0 8px;">Messages</div>`;
    messages.slice(0, 50).forEach(m => {
      const from = m.from_agent || 'user';
      const dir = from === 'user' ? '→' : '←';
      const preview = (m.content || '').slice(0, 120);
      html += `<div style="margin-bottom:4px;font-size:11px;padding:4px 8px;background:var(--bg);border-radius:4px;">
        <span style="font-weight:600;">${_traceEsc(from)}</span> ${dir}
        <span style="color:var(--text-dim);">${_traceEsc(m.to_agent || '')}</span>
        <span style="float:right;font-size:10px;color:var(--text-dim);">${_traceEsc(_traceTime(m.created_at || ''))}</span>
        <div style="margin-top:2px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_traceEsc(preview)}</div>
      </div>`;
    });
  }

  detail.innerHTML = html;
}

/* ── render: single job detail (right panel) ─────────────────────────── */
function _traceRenderJobDetail(data) {
  const detail = document.getElementById('trace-detail-panel');
  if (!detail) return;

  const job = data.job || {};
  const stageTrace = data.stage_trace || [];
  const timeline = data.timeline || [];
  const response = data.response;

  const st = job.status || 'unknown';
  const stColor = st === 'complete' || st === 'done' ? '#4caf50'
                : st === 'error' || st === 'failed' ? '#f44336'
                : '#888';

  let html = `<div style="margin-bottom:16px;">
    <div style="font-weight:700;font-size:14px;margin-bottom:6px;">Job Detail</div>
    <table style="font-size:11px;border-collapse:collapse;width:100%;">
      <tr><td style="padding:3px 8px;color:var(--text-dim);white-space:nowrap;">Job ID</td><td style="padding:3px 8px;font-family:monospace;font-size:10px;word-break:break-all;">${_traceEsc(job.job_id || '')}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Agent</td><td style="padding:3px 8px;">${_traceBadge(job.agent || '?', '#2196f3')}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Status</td><td style="padding:3px 8px;">${_traceBadge(st, stColor)}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Runtime</td><td style="padding:3px 8px;">${_traceEsc(job.runtime_class || '')}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Stage</td><td style="padding:3px 8px;">${_traceEsc(job.stage || '')}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Elapsed</td><td style="padding:3px 8px;">${job.elapsed_ms ? (job.elapsed_ms / 1000).toFixed(2) + 's' : '—'}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Tokens</td><td style="padding:3px 8px;">${job.tokens || '—'}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">ETA</td><td style="padding:3px 8px;">${job.eta_seconds ? job.eta_seconds + 's' : '—'}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Started</td><td style="padding:3px 8px;">${_traceEsc(_traceTime(job.started_at || ''))}</td></tr>
      <tr><td style="padding:3px 8px;color:var(--text-dim);">Updated</td><td style="padding:3px 8px;">${_traceEsc(_traceTime(job.updated_at || ''))}</td></tr>
    </table>
    ${job.error ? `<div style="margin-top:8px;padding:8px;background:#f4433622;border:1px solid #f4433644;border-radius:5px;font-size:11px;color:#f44336;">${_traceEsc(job.error)}</div>` : ''}
  </div>`;

  // Stage trace
  if (stageTrace.length) {
    html += `<div style="font-weight:600;font-size:12px;margin-bottom:8px;">Stage Trace (${stageTrace.length})</div>`;
    html += `<div style="border-left:2px solid var(--border);padding-left:12px;margin-bottom:16px;">`;
    stageTrace.forEach(st => {
      const label = st.stage || st.label || JSON.stringify(st);
      html += `<div style="margin-bottom:4px;font-size:11px;">
        <span style="width:6px;height:6px;border-radius:50%;background:#9c27b0;display:inline-block;"></span>
        <span style="margin-left:6px;">${_traceEsc(String(label))}</span>
        <span style="font-size:10px;color:var(--text-dim);margin-left:8px;">${_traceEsc(_traceTime(st.ts || st.timestamp || ''))}</span>
      </div>`;
    });
    html += `</div>`;
  }

  // Timeline events
  if (timeline.length) {
    html += `<div style="font-weight:600;font-size:12px;margin-bottom:8px;">Timeline Events (${timeline.length})</div>`;
    html += `<div style="border-left:2px solid var(--border);padding-left:12px;margin-bottom:16px;">`;
    timeline.forEach(ev => {
      const color = _traceEventColors[ev.event_type] || '#888';
      html += `<div style="margin-bottom:6px;font-size:11px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="width:6px;height:6px;border-radius:50%;background:${color};flex-shrink:0;"></span>
          ${_traceBadge(ev.event_type || 'event', color)}
          <span style="font-size:10px;color:var(--text-dim);margin-left:auto;">${_traceEsc(_traceTime(ev.created_at || ''))}</span>
        </div>
        <div style="margin-left:12px;margin-top:2px;color:var(--text);font-size:11px;word-break:break-all;">${_traceEsc(String(ev.payload || '').slice(0, 500))}</div>
      </div>`;
    });
    html += `</div>`;
  }

  // Response
  if (response) {
    html += `<div style="font-weight:600;font-size:12px;margin-bottom:8px;">Response</div>`;
    html += `<div style="padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:11px;white-space:pre-wrap;max-height:300px;overflow-y:auto;">${_traceEsc(response.content || '(empty)')}</div>`;
    html += `<div style="margin-top:4px;font-size:10px;color:var(--text-dim);">
      ${response.tokens_used ? `Tokens: ${response.tokens_used}` : ''} &middot; ${_traceEsc(_traceTime(response.created_at || ''))}
    </div>`;
  }

  detail.innerHTML = html;
}

/* ── error display ───────────────────────────────────────────────────── */
function _traceShowError(msg) {
  const detail = document.getElementById('trace-detail-panel');
  if (detail) {
    detail.innerHTML = `<div style="font-size:12px;color:#f44336;padding:20px;">Error: ${_traceEsc(msg)}</div>`;
  }
}
