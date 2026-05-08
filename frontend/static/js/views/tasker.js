// Tasker view — scheduled tasks management UI
// Wraps /api/tasker/* endpoints

let _taskerAllTasks = [];
let _taskerEditId = null;
let _taskerCalendarCursor = null;

function loadTaskerData(/* win */) {
  _taskerRefresh();
  loadWatchedTopicEvidence();
}

function _taskerRefresh() {
  fetch('/api/tasker/tasks')
    .then(r => r.json())
    .then(tasks => {
      _taskerAllTasks = Array.isArray(tasks) ? tasks : [];
      _taskerRenderStats();
      _taskerRenderCalendar();
      _taskerRenderList();
    })
    .catch(e => {
      const list = document.getElementById('tasker-list');
      if (list) list.innerHTML = '<div class="tasker-empty"><div class="tasker-empty-icon">⚠</div>Failed to load tasks: ' + _escHtml(String(e)) + '</div>';
    });
}

// ── Stats ────────────────────────────────────────────────────────────────

function _taskerRenderStats() {
  const tasks = _taskerAllTasks;
  const active = tasks.filter(t => t.enabled);
  const disabled = tasks.filter(t => !t.enabled);

  const lastFired = tasks
    .filter(t => t.last_run)
    .sort((a, b) => (b.last_run || '').localeCompare(a.last_run || ''))[0];

  const el = id => document.getElementById(id);
  const total = el('tasker-stat-total');
  const activeEl = el('tasker-stat-active');
  const disabledEl = el('tasker-stat-disabled');
  const lastEl = el('tasker-stat-last');

  if (total) total.textContent = tasks.length;
  if (activeEl) activeEl.textContent = active.length;
  if (disabledEl) disabledEl.textContent = disabled.length;
  if (lastEl) lastEl.textContent = lastFired ? _taskerRelativeTime(lastFired.last_run) : '–';
}

function _taskerRelativeTime(dateStr) {
  if (!dateStr) return '–';
  try {
    const d = new Date(dateStr.replace(' ', 'T'));
    const diff = Date.now() - d.getTime();
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    return Math.floor(diff / 86400000) + 'd ago';
  } catch (_) {
    return dateStr;
  }
}

// ── Calendar ─────────────────────────────────────────────────────────────

function shiftTaskerCalendar(days) {
  const today = _taskerStartOfDay(new Date());
  if (!_taskerCalendarCursor || days === 0) {
    _taskerCalendarCursor = today;
  } else {
    _taskerCalendarCursor = new Date(_taskerCalendarCursor.getTime() + (days * 86400000));
  }
  _taskerRenderCalendar();
}

function _taskerRenderCalendar() {
  const grid = document.getElementById('tasker-calendar-grid');
  if (!grid) return;

  const today = _taskerStartOfDay(new Date());
  const cursor = _taskerCalendarCursor ? _taskerStartOfDay(_taskerCalendarCursor) : today;
  _taskerCalendarCursor = cursor;
  const weekStart = _taskerWeekStart(cursor);
  const days = Array.from({ length: 7 }, (_, idx) => new Date(weekStart.getTime() + idx * 86400000));
  const activeTasks = _taskerAllTasks.filter(t => t.enabled && t.next_run);

  grid.innerHTML = days.map(day => {
    const dateKey = _taskerDateKey(day);
    const tasks = activeTasks
      .filter(t => _taskerDateKey(_taskerParseDate(t.next_run)) === dateKey)
      .sort((a, b) => String(a.next_run || '').localeCompare(String(b.next_run || '')));
    const isToday = dateKey === _taskerDateKey(today);
    const items = tasks.length ? tasks.map(t => _taskerCalendarItem(t)).join('') : '<div class="tasker-calendar-empty">No jobs</div>';
    return `<section class="tasker-calendar-day${isToday ? ' is-today' : ''}">
      <div class="tasker-calendar-date">
        <span>${_escHtml(day.toLocaleDateString(undefined, { weekday: 'short' }))}</span>
        <strong>${_escHtml(day.toLocaleDateString(undefined, { day: '2-digit', month: 'short' }))}</strong>
      </div>
      <div class="tasker-calendar-items">${items}</div>
    </section>`;
  }).join('');
}

function _taskerCalendarItem(task) {
  const emailLinked = _taskerTaskHasEmail(task);
  const time = _taskerFormatTime(task.next_run);
  const type = String(task.action_type || '').toUpperCase();
  return `<button type="button" class="tasker-calendar-item${emailLinked ? ' email-linked' : ''}" onclick="editTasker(${Number(task.id)})" title="${_escHtml(task.action_data || '')}">
    <span class="tasker-calendar-time">${_escHtml(time)}</span>
    <span class="tasker-calendar-name">${_escHtml(task.name || 'task')}</span>
    <span class="tasker-calendar-type">${_escHtml(emailLinked ? 'email' : type.toLowerCase())}</span>
  </button>`;
}

function _taskerTaskHasEmail(task) {
  const haystack = `${task.action_type || ''} ${task.action_data || ''} ${task.name || ''}`.toLowerCase();
  return task.action_type === 'BRIEF' ||
    haystack.includes('email=') ||
    haystack.includes('send_reply') ||
    haystack.includes('daily_brief') ||
    haystack.includes('interest_research_update');
}

function _taskerParseDate(value) {
  if (!value) return null;
  const d = new Date(String(value).replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? null : d;
}

function _taskerStartOfDay(date) {
  const d = date instanceof Date && !Number.isNaN(date.getTime()) ? new Date(date) : new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function _taskerWeekStart(date) {
  const d = _taskerStartOfDay(date);
  const day = d.getDay();
  const offset = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + offset);
  return d;
}

function _taskerDateKey(date) {
  if (!date) return '';
  const d = _taskerStartOfDay(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function _taskerFormatTime(value) {
  const d = _taskerParseDate(value);
  if (!d) return '--:--';
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

// ── List ─────────────────────────────────────────────────────────────────

function filterTaskerList() {
  _taskerRenderList();
}

function _taskerRenderList() {
  const list = document.getElementById('tasker-list');
  if (!list) return;

  const search = (document.getElementById('tasker-search')?.value || '').toLowerCase();
  const typeFilter = document.getElementById('tasker-filter-type')?.value || '';
  const statusFilter = document.getElementById('tasker-filter-status')?.value || '';

  let filtered = _taskerAllTasks;

  if (search) {
    filtered = filtered.filter(t =>
      (t.name || '').toLowerCase().includes(search) ||
      (t.action_data || '').toLowerCase().includes(search)
    );
  }
  if (typeFilter) {
    filtered = filtered.filter(t => (t.action_type || '').toUpperCase() === typeFilter);
  }
  if (statusFilter === 'active') {
    filtered = filtered.filter(t => t.enabled);
  } else if (statusFilter === 'disabled') {
    filtered = filtered.filter(t => !t.enabled);
  }

  if (!filtered.length) {
    list.innerHTML = '<div class="tasker-empty"><div class="tasker-empty-icon">⏱</div>' +
      (_taskerAllTasks.length ? 'No tasks match your filters' : 'No scheduled tasks yet. Create one above!') +
      '</div>';
    return;
  }

  list.innerHTML = filtered.map(t => {
    const badgeClass = 'tasker-badge tasker-badge-' + (t.action_type || 'shell').toLowerCase();
    const disabledClass = t.enabled ? '' : ' disabled';
    const toggleClass = 'tasker-toggle' + (t.enabled ? ' active' : '');
    const nextRun = t.next_run ? 'Next: ' + _taskerRelativeTime(t.next_run) : '';
    const lastRun = t.last_run ? 'Last: ' + _taskerRelativeTime(t.last_run) : 'Never run';
    const dataPreview = _escHtml((t.action_data || '').slice(0, 80));

    return `<div class="tasker-card${disabledClass}" data-task-id="${t.id}">
      <button class="${toggleClass}" onclick="toggleTasker(${t.id}, ${!t.enabled})" title="${t.enabled ? 'Disable' : 'Enable'}"></button>
      <div class="tasker-info">
        <div class="tasker-name">${_escHtml(t.name)}</div>
        <div class="tasker-meta">
          <span class="${badgeClass}">${_escHtml(t.action_type)}</span>
          <span class="tasker-schedule">⏲ ${_escHtml(t.schedule)}</span>
          <span class="tasker-next-run">${nextRun}</span>
          <span>${lastRun}</span>
        </div>
        <div style="font-size:11px;color:var(--text-faint);margin-top:2px;font-family:monospace;">${dataPreview}</div>
      </div>
      <div class="tasker-actions">
        <button class="tasker-action-btn" onclick="runTaskerNow(${t.id})" title="Run now">▶</button>
        <button class="tasker-action-btn" onclick="editTasker(${t.id})" title="Edit">✎</button>
        <button class="tasker-action-btn danger" onclick="deleteTasker(${t.id}, ${_escHtml(JSON.stringify(t.name))}, event)" title="Delete">✕</button>
      </div>
    </div>`;
  }).join('');
}

// ── Form ─────────────────────────────────────────────────────────────────

function openTaskerForm(editTask) {
  _taskerEditId = editTask ? editTask.id : null;
  const form = document.getElementById('tasker-form');
  const title = document.getElementById('tasker-form-title');
  if (!form) return;

  form.classList.add('open');
  if (title) title.textContent = editTask ? 'Edit Task' : 'New Scheduled Task';

  document.getElementById('tasker-field-name').value = editTask ? editTask.name : '';
  document.getElementById('tasker-field-type').value = editTask ? editTask.action_type : 'SHELL';
  document.getElementById('tasker-field-schedule').value = editTask ? editTask.schedule : '';
  document.getElementById('tasker-field-data').value = editTask ? editTask.action_data : '';
  document.getElementById('tasker-field-creator').value = editTask ? (editTask.created_by || 'ghost') : 'ghost';

  const saveBtn = form.querySelector('.tasker-form-save');
  if (saveBtn) saveBtn.textContent = editTask ? 'Update Task' : 'Create Task';

  // Focus name field
  setTimeout(() => document.getElementById('tasker-field-name')?.focus(), 50);
}

function closeTaskerForm() {
  _taskerEditId = null;
  const form = document.getElementById('tasker-form');
  if (form) form.classList.remove('open');
}

function saveTaskerForm() {
  const name = (document.getElementById('tasker-field-name')?.value || '').trim();
  const action_type = document.getElementById('tasker-field-type')?.value || 'SHELL';
  const schedule = (document.getElementById('tasker-field-schedule')?.value || '').trim();
  const action_data = (document.getElementById('tasker-field-data')?.value || '').trim();
  const created_by = (document.getElementById('tasker-field-creator')?.value || 'ghost').trim();

  if (!name) { _taskerToast('Name is required', 'error'); return; }
  if (!schedule) { _taskerToast('Schedule is required', 'error'); return; }
  if (!action_data) { _taskerToast('Action data is required', 'error'); return; }

  const payload = { name, action_type, schedule, action_data, created_by };

  if (_taskerEditId) {
    // Update
    fetch('/api/tasker/tasks/' + _taskerEditId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          _taskerToast('Task updated');
          closeTaskerForm();
          _taskerRefresh();
        } else {
          _taskerToast(d.error || 'Update failed', 'error');
        }
      })
      .catch(e => _taskerToast('Error: ' + e, 'error'));
  } else {
    // Create
    fetch('/api/tasker/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          _taskerToast('Task created');
          closeTaskerForm();
          _taskerRefresh();
        } else {
          _taskerToast(d.error || 'Creation failed', 'error');
        }
      })
      .catch(e => _taskerToast('Error: ' + e, 'error'));
  }
}

// ── Actions ──────────────────────────────────────────────────────────────

function toggleTasker(taskId, enable) {
  fetch('/api/tasker/tasks/' + taskId, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: enable }),
  })
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        _taskerToast(enable ? 'Task enabled' : 'Task disabled');
        _taskerRefresh();
      }
    })
    .catch(() => {});
}

function runTaskerNow(taskId) {
  fetch('/api/tasker/tasks/' + taskId + '/run', {
    method: 'POST',
  })
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        _taskerToast('Task fired: ' + (d.fired || ''));
        _taskerRefresh();
      } else {
        _taskerToast(d.error || 'Run failed', 'error');
      }
    })
    .catch(e => _taskerToast('Error: ' + e, 'error'));
}

function editTasker(taskId) {
  const task = _taskerAllTasks.find(t => t.id === taskId);
  if (task) openTaskerForm(task);
}

function deleteTasker(taskId, name, event) {
  var fire = function () {
    fetch('/api/tasker/tasks/' + taskId, { method: 'DELETE' })
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          _taskerToast('Task deleted');
          _taskerRefresh();
        } else {
          _taskerToast(d.error || 'Delete failed', 'error');
        }
      })
      .catch(e => _taskerToast('Error: ' + e, 'error'));
  };
  var btn = event && event.currentTarget;
  if (btn && window.SwarmChat && typeof window.SwarmChat.armToConfirm === 'function') {
    window.SwarmChat.armToConfirm(btn, fire, { confirmLabel: '?', timeoutMs: 4000 });
    return;
  }
  if (!confirm('Delete task "' + name + '"? This cannot be undone.')) return;
  fire();
}

// ── Watched Topic Creator ───────────────────────────────────────────────

function createWatchedTopicTask() {
  const val = id => (document.getElementById(id)?.value || '').trim();
  const payload = {
    topic: val('tasker-watch-topic'),
    schedule: val('tasker-watch-schedule') || 'daily 06:30',
    depth: val('tasker-watch-depth') || 'standard',
    agent: val('tasker-watch-agent') || 'eight',
    email: val('tasker-watch-email') || 'ghost',
    min_quality: val('tasker-watch-min-quality') || '0.45',
    min_novelty: val('tasker-watch-min-novelty') || '0.35',
    min_score: val('tasker-watch-min-score') || '0.50',
    max_items: val('tasker-watch-max-items') || '10',
    historical_years: val('tasker-watch-historical-years') || '5',
  };

  if (!payload.topic) {
    _taskerToast('Topic is required', 'error');
    return;
  }

  fetch('/api/tasker/watch-topic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data }) => {
      if (ok && data.ok) {
        _taskerToast('Watched topic scheduled: ' + (data.name || payload.topic));
        const evidenceTopic = document.getElementById('tasker-evidence-topic');
        if (evidenceTopic) evidenceTopic.value = payload.topic;
        const topicField = document.getElementById('tasker-watch-topic');
        if (topicField) topicField.value = '';
        _taskerRefresh();
        loadWatchedTopicEvidence();
      } else {
        _taskerToast(data.error || 'Watch creation failed', 'error');
      }
    })
    .catch(e => _taskerToast('Error: ' + e, 'error'));
}

// ── Watched Evidence Review ─────────────────────────────────────────────

function runWatchedTopicNow() {
  const topic = (document.getElementById('tasker-evidence-topic')?.value || '').trim();
  const list = document.getElementById('tasker-evidence-list');
  const summary = document.getElementById('tasker-evidence-summary');
  if (!topic) {
    _taskerToast('Topic is required for Run Topic Now', 'error');
    return;
  }
  if (summary) summary.textContent = 'Running watched-topic research now...';
  if (list) {
    list.innerHTML = '<div class="tasker-empty"><div class="tasker-empty-icon">⌕</div>Running watched-topic research now. This can take a little while.</div>';
  }
  fetch('/api/tasker/watch-topic/run-now', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data }) => {
      if (!ok || !data.ok) {
        throw new Error(data.error || 'Run failed');
      }
      _taskerToast('Watched topic run complete: ' + (data.name || topic));
      if (summary) summary.textContent = data.output || 'Watched-topic run complete.';
      const evidence = data.evidence || [];
      _taskerRenderEvidence(evidence, evidence.length ? [{
        topic,
        total: evidence.length,
        qualified_count: evidence.filter(item => item.qualified).length,
        historical_count: evidence.filter(item => item.is_historical).length,
        notified_count: evidence.filter(item => item.notified).length,
      }] : []);
      _taskerRefresh();
    })
    .catch(e => {
      _taskerToast('Run failed: ' + (e.message || e), 'error');
      loadWatchedTopicEvidence();
    });
}

function loadWatchedTopicEvidence() {
  const list = document.getElementById('tasker-evidence-list');
  const summary = document.getElementById('tasker-evidence-summary');
  if (!list) return;

  const topic = (document.getElementById('tasker-evidence-topic')?.value || '').trim();
  const status = document.getElementById('tasker-evidence-status')?.value || 'all';
  const params = new URLSearchParams({ status, limit: '25' });
  if (topic) params.set('topic', topic);

  list.innerHTML = '<div class="tasker-empty"><div class="tasker-empty-icon">⌕</div>Loading watched evidence...</div>';
  fetch('/api/tasker/watch-topic/evidence?' + params.toString())
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data }) => {
      if (!ok || !data.ok) {
        list.innerHTML = '<div class="tasker-empty"><div class="tasker-empty-icon">⚠</div>' + _escHtml(data.error || 'Failed to load watched evidence') + '</div>';
        if (summary) summary.textContent = 'Evidence unavailable.';
        return;
      }
      _taskerRenderEvidence(data.evidence || [], data.topics || []);
    })
    .catch(e => {
      list.innerHTML = '<div class="tasker-empty"><div class="tasker-empty-icon">⚠</div>Error: ' + _escHtml(String(e)) + '</div>';
      if (summary) summary.textContent = 'Evidence unavailable.';
    });
}

function _taskerRenderEvidence(evidence, topics) {
  const list = document.getElementById('tasker-evidence-list');
  const summary = document.getElementById('tasker-evidence-summary');
  if (!list) return;

  const totals = topics.reduce((acc, item) => {
    acc.total += Number(item.total || 0);
    acc.qualified += Number(item.qualified_count || 0);
    acc.notified += Number(item.notified_count || 0);
    acc.historical += Number(item.historical_count || 0);
    return acc;
  }, { total: 0, qualified: 0, notified: 0, historical: 0 });
  if (summary) {
    summary.textContent = topics.length
      ? `${topics.length} watched topic(s) · ${totals.total} findings · ${totals.qualified} current-qualified · ${totals.historical} historical · ${totals.notified} notified`
      : `${evidence.length} finding(s)`;
  }

  if (!evidence.length) {
    list.innerHTML = '<div class="tasker-empty"><div class="tasker-empty-icon">⌕</div>No watched evidence matches this filter yet.</div>';
    return;
  }

  list.innerHTML = evidence.map(item => {
    const status = item.is_historical ? 'historical' : (item.qualified ? 'qualified' : (String(item.reason || '').includes('duplicate') ? 'duplicate' : 'filtered'));
    const notified = item.notified ? '<span class="tasker-evidence-pill notified">notified</span>' : '<span class="tasker-evidence-pill quiet">not emailed</span>';
    const dateLabel = item.recency_label || item.evidence_date || 'undated';
    const url = item.source_url
      ? `<a href="${_escHtml(item.source_url)}" target="_blank" rel="noreferrer">${_escHtml(_taskerHost(item.source_url))}</a>`
      : '<span>No source URL</span>';
    return `<div class="tasker-evidence-card ${status}">
      <div class="tasker-evidence-topline">
        <span class="tasker-evidence-pill ${status}">${status}</span>
        ${notified}
        ${item.review_status ? `<span class="tasker-evidence-pill review">${_escHtml(item.review_status)}</span>` : ''}
        <span class="tasker-evidence-topic">${_escHtml(item.topic || '')}</span>
      </div>
      <div class="tasker-evidence-title">${_escHtml(item.title || 'Untitled evidence')}</div>
      <div class="tasker-evidence-scores">
        <span>score ${_taskerScore(item.combined_score)}</span>
        <span>quality ${_taskerScore(item.quality_score)}</span>
        <span>novelty ${_taskerScore(item.novelty_score)}</span>
        <span>recency ${_taskerScore(item.recency_score)}</span>
        <span>date ${_escHtml(dateLabel)}</span>
      </div>
      <div class="tasker-evidence-source">${url}</div>
      <div class="tasker-evidence-snippet">${_escHtml((item.snippet || '').slice(0, 260))}</div>
      <div class="tasker-evidence-reason">${_escHtml(item.reason || '')}</div>
      ${item.review_note ? `<div class="tasker-evidence-reason">review: ${_escHtml(item.review_note)}</div>` : ''}
      <div class="tasker-evidence-actions">
        <button type="button" onclick="updateWatchedEvidence(${Number(item.id)}, 'promote')">Promote</button>
        <button type="button" onclick="updateWatchedEvidence(${Number(item.id)}, 'ignore')">Ignore</button>
        <button type="button" onclick="updateWatchedEvidence(${Number(item.id)}, '${item.notified ? 'mark_unnotified' : 'mark_notified'}')">${item.notified ? 'Mark Unsent' : 'Mark Emailed'}</button>
        <button type="button" onclick="updateWatchedEvidence(${Number(item.id)}, 'reset')">Reset Review</button>
      </div>
    </div>`;
  }).join('');
}

function updateWatchedEvidence(evidenceId, action) {
  let note = '';
  if (action === 'promote' || action === 'ignore') {
    note = prompt(action === 'promote' ? 'Why promote this finding?' : 'Why ignore this finding?', '') || '';
  }
  fetch('/api/tasker/watch-topic/evidence/' + encodeURIComponent(evidenceId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, note }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data }) => {
      if (ok && data.ok) {
        _taskerToast('Evidence updated');
        loadWatchedTopicEvidence();
      } else {
        _taskerToast(data.error || 'Evidence update failed', 'error');
      }
    })
    .catch(e => _taskerToast('Error: ' + e, 'error'));
}

function _taskerScore(value) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n.toFixed(2) : '0.00';
}

function _taskerHost(url) {
  try {
    return new URL(url).host.replace(/^www\./, '');
  } catch (_) {
    return url;
  }
}

// ── Toast helper (reuses showToast if available) ─────────────────────────

function _taskerToast(msg, level) {
  if (typeof showToast === 'function') {
    showToast(msg, level || 'ok');
  } else if (window.__SWARM_DEBUG) {
    console.debug('[Tasker]', msg);
  }
}

// ── Bootstrap — register default Python tasks ───────────────────────────

function bootstrapTasker() {
  if (!confirm('Register built-in tasks (housekeeping, SLA, digest, etc.)? Existing tasks are kept.')) return;
  fetch('/api/tasker/bootstrap', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        _taskerToast('Bootstrapped ' + (d.bootstrapped || 0) + ' default tasks');
        _taskerRefresh();
      } else {
        _taskerToast(d.error || 'Bootstrap failed', 'error');
      }
    })
    .catch(e => _taskerToast('Error: ' + e, 'error'));
}
