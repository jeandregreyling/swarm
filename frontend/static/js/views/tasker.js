// Tasker view — scheduled tasks management UI
// Wraps /api/tasker/* endpoints

let _taskerAllTasks = [];
let _taskerEditId = null;

function loadTaskerData(/* win */) {
  _taskerRefresh();
}

function _taskerRefresh() {
  fetch('/api/tasker/tasks')
    .then(r => r.json())
    .then(tasks => {
      _taskerAllTasks = Array.isArray(tasks) ? tasks : [];
      _taskerRenderStats();
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
        <button class="tasker-action-btn danger" onclick="deleteTasker(${t.id}, ${_escHtml(JSON.stringify(t.name))})" title="Delete">✕</button>
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

function deleteTasker(taskId, name) {
  if (!confirm('Delete task "' + name + '"? This cannot be undone.')) return;
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
}

// ── Toast helper (reuses showToast if available) ─────────────────────────

function _taskerToast(msg, level) {
  if (typeof showToast === 'function') {
    showToast(msg, level || 'ok');
  } else {
    console.log('[Tasker]', msg);
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
