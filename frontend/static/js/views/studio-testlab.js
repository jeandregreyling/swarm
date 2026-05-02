// ═══════════════════════════════════════════════════════════════════════════
// STUDIO TEST LAB — Session 28
// Lists registered test scripts from /api/studio/testlab/scripts, lets the
// user tick which ones to run per change, and streams each selected script
// through /api/terminal/run so the existing ANSI/semantic renderer and
// hard-kill machinery are reused. No new output code lives here.
// ═══════════════════════════════════════════════════════════════════════════

(function () {
  'use strict';

  const LS_SELECTED_KEY = 'fridays-testlab-selected-v1';
  const LS_CHANGE_ID_KEY = 'fridays-testlab-change-id-v1';

  let _tlGroups = [];           // [{group, scripts:[{id,label,...}]}]
  let _tlScriptsById = {};      // id -> entry
  let _tlRunning = false;
  let _tlCurrentRunId = '';

  // ── Public entry point (wired from studio.js studioSetTab) ───────────────
  window.loadStudioTestLabPanel = function () {
    const panel = document.getElementById('studio-testlab-panel');
    if (!panel) return;
    // Restore change id input
    const changeInput = document.getElementById('testlab-change-id');
    if (changeInput && !changeInput.value) {
      const saved = localStorage.getItem(LS_CHANGE_ID_KEY) || '';
      changeInput.value = saved;
      changeInput.addEventListener('input', () => {
        localStorage.setItem(LS_CHANGE_ID_KEY, changeInput.value.trim());
      });
    }
    _tlFetchScripts();
    _tlLoadHistory();
    _tlLoadProjectsDropdown();
  };

  function _tlLoadProjectsDropdown() {
    const sel = document.getElementById('testlab-project-id');
    if (!sel) return;
    const savedPid = localStorage.getItem('fridays-testlab-project-id-v1') || '';
    fetch('/api/knowledge/projects?limit=100')
      .then(r => r.json())
      .then(data => {
        const items = (data && data.items) || [];
        sel.innerHTML = '<option value="">— none —</option>' +
          items.map(p => `<option value="${p.project_id}">${_tlEsc(p.name)} (${_tlEsc(p.methodology)})</option>`).join('');
        if (savedPid && items.some(p => p.project_id === savedPid)) {
          sel.value = savedPid;
          window.testLabOnProjectChange(savedPid);
        }
      })
      .catch(() => { /* best-effort */ });
  }

  window.testLabOnProjectChange = function (pid) {
    localStorage.setItem('fridays-testlab-project-id-v1', pid || '');
    const stepSel = document.getElementById('testlab-step-id');
    if (!stepSel) return;
    stepSel.innerHTML = '<option value="">— none —</option>';
    if (!pid) return;
    fetch('/api/knowledge/projects/' + encodeURIComponent(pid) + '/steps')
      .then(r => r.json())
      .then(data => {
        const items = (data && data.items) || [];
        stepSel.innerHTML = '<option value="">— none —</option>' +
          items.map(s => `<option value="${s.step_id}">${_tlEsc(s.title)} [${_tlEsc(s.status)}]</option>`).join('');
      })
      .catch(() => {});
  };

  function _tlFetchScripts() {
    fetch('/api/studio/testlab/scripts')
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'Failed to load scripts');
        _tlGroups = Array.isArray(data.groups) ? data.groups : [];
        _tlScriptsById = {};
        _tlGroups.forEach(g => (g.scripts || []).forEach(s => { _tlScriptsById[s.id] = s; }));
        _tlRenderList();
      })
      .catch(err => {
        const list = document.getElementById('testlab-script-list');
        if (list) list.innerHTML = `<div style="color:var(--danger,#f77);font-size:11px;padding:12px;">Failed to load scripts: ${_tlEsc(err.message || err)}</div>`;
      });
  }

  function _tlLoadSelected() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_SELECTED_KEY) || 'null');
      if (raw && typeof raw === 'object') return raw;
    } catch (_) { /* ignore */ }
    // Default: use registry default_on flags
    const defaults = {};
    Object.values(_tlScriptsById).forEach(s => {
      if (s.default_on) defaults[s.id] = true;
    });
    return defaults;
  }

  function _tlSaveSelected(selected) {
    localStorage.setItem(LS_SELECTED_KEY, JSON.stringify(selected || {}));
  }

  function _tlRenderList() {
    const list = document.getElementById('testlab-script-list');
    if (!list) return;
    if (!_tlGroups.length) {
      list.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:12px;">No scripts registered.</div>';
      return;
    }
    const selected = _tlLoadSelected();
    const html = _tlGroups.map(g => {
      const rows = (g.scripts || []).map(s => {
        const on = !!selected[s.id];
        const changeBadge = s.change_aware
          ? '<span title="change-aware — gets SWARM_CHANGE_ID env" style="font-size:9px;padding:1px 5px;border-radius:3px;background:color-mix(in srgb, var(--accent) 22%, transparent);color:var(--accent);margin-left:6px;">Δ</span>'
          : '';
        return `
          <label data-testlab-id="${_tlEsc(s.id)}" style="display:flex;gap:8px;align-items:flex-start;padding:6px 8px;border-radius:5px;cursor:pointer;${on ? 'background:color-mix(in srgb, var(--accent) 10%, transparent);' : ''}">
            <input type="checkbox" ${on ? 'checked' : ''} data-testlab-checkbox="${_tlEsc(s.id)}" style="margin-top:2px;accent-color:var(--accent);cursor:pointer;">
            <span style="flex:1;min-width:0;">
              <span style="font-size:11px;font-weight:600;color:var(--text);">${_tlEsc(s.label)}</span>${changeBadge}
              <span style="display:block;font-size:10px;color:var(--text-dim);margin-top:2px;line-height:1.4;">${_tlEsc(s.description || '')}</span>
            </span>
          </label>`;
      }).join('');
      return `
        <div style="margin-bottom:10px;">
          <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.6px;padding:4px 8px;">${_tlEsc(g.group)}</div>
          ${rows}
        </div>`;
    }).join('');
    list.innerHTML = html;

    // Bind checkbox changes
    list.querySelectorAll('[data-testlab-checkbox]').forEach(cb => {
      cb.addEventListener('change', () => {
        const id = cb.getAttribute('data-testlab-checkbox');
        const cur = _tlLoadSelected();
        if (cb.checked) cur[id] = true; else delete cur[id];
        _tlSaveSelected(cur);
        const row = list.querySelector(`[data-testlab-id="${CSS.escape(id)}"]`);
        if (row) row.style.background = cb.checked ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : '';
      });
    });
  }

  // ── Selection helpers ────────────────────────────────────────────────────
  window.testLabSelectAll = function () {
    const next = {};
    Object.keys(_tlScriptsById).forEach(id => { next[id] = true; });
    _tlSaveSelected(next);
    _tlRenderList();
  };
  window.testLabClearAll = function () {
    _tlSaveSelected({});
    _tlRenderList();
  };
  window.testLabSelectDefaults = function () {
    const next = {};
    Object.values(_tlScriptsById).forEach(s => { if (s.default_on) next[s.id] = true; });
    _tlSaveSelected(next);
    _tlRenderList();
  };
  window.testLabClearOutput = function () {
    const out = document.getElementById('testlab-output');
    if (out) out.textContent = 'Output cleared.';
  };

  // ── Run ──────────────────────────────────────────────────────────────────
  window.testLabRunSelected = async function () {
    if (_tlRunning) {
      _tlSetStatus('Run already in progress — press Stop first.', 'warn');
      return;
    }
    const selected = _tlLoadSelected();
    const ids = Object.keys(selected).filter(id => selected[id]);
    if (!ids.length) {
      _tlSetStatus('Select at least one script to run.', 'warn');
      return;
    }
    const changeId = (document.getElementById('testlab-change-id')?.value || '').trim();

    let resolved;
    try {
      const resp = await fetch('/api/studio/testlab/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_ids: ids, change_id: changeId || null })
      });
      resolved = await resp.json();
      if (!resp.ok || !resolved.ok) throw new Error((resolved && resolved.error) || `HTTP ${resp.status}`);
    } catch (err) {
      _tlSetStatus(`Resolve failed: ${err.message || err}`, 'error');
      return;
    }

    const items = Array.isArray(resolved.items) ? resolved.items : [];
    if (!items.length) {
      _tlSetStatus('No runnable scripts resolved.', 'warn');
      return;
    }

    _tlRunning = true;
    _tlCurrentRunId = 'testlab-' + Date.now();
    const runBtn = document.getElementById('testlab-run-btn');
    const stopBtn = document.getElementById('testlab-stop-btn');
    if (runBtn) { runBtn.disabled = true; runBtn.style.opacity = '0.6'; }
    if (stopBtn) { stopBtn.disabled = false; stopBtn.style.opacity = '1'; }

    const out = document.getElementById('testlab-output');
    if (out) out.textContent = '';

    let passed = 0;
    let failed = 0;
    const changeInput = document.getElementById('testlab-change-id');
    const changeIdVal = (changeInput && changeInput.value.trim()) || '';
    for (let i = 0; i < items.length; i++) {
      if (!_tlRunning) break; // stopped
      const item = items[i];
      _tlSetStatus(`Running [${i + 1}/${items.length}] ${item.label}…`, 'running');
      _tlAppendOutput(`\n── ${item.label} (${item.id}) ───────────────────────────\n$ ${item.command}\n`);
      // Session 30 — begin run record before executing.
      const runId = await _tlStartRunRecord(item, changeIdVal);
      const runResult = await _tlRunOneCommand(item.command);
      const ok = runResult.ok;
      if (ok) {
        passed++;
        _tlAppendOutput(`\n[OK] ${item.label}\n`);
      } else {
        failed++;
        _tlAppendOutput(`\n[FAIL] ${item.label}\n`);
      }
      await _tlFinishRunRecord(runId, ok, runResult.exitCode, runResult.stdoutTail);
    }

    _tlRunning = false;
    if (runBtn) { runBtn.disabled = false; runBtn.style.opacity = '1'; }
    if (stopBtn) { stopBtn.disabled = true; stopBtn.style.opacity = '0.5'; }
    const verdict = failed === 0
      ? `All ${passed} script(s) passed.`
      : `${passed} passed, ${failed} failed out of ${items.length}.`;
    _tlSetStatus(verdict, failed === 0 ? 'ok' : 'error');
    // Refresh the history pane so the new runs show up immediately.
    _tlLoadHistory();
  };

  window.testLabStop = function () {
    _tlRunning = false;
    _tlSetStatus('Stop requested — current script will finish, queue halted.', 'warn');
  };

  // ── Run a single command via /api/terminal/run (non-streaming for now).
  //    We deliberately call the sync endpoint so the loop can run scripts
  //    in order and detect pass/fail per entry. A streaming variant can be
  //    added later by hooking into _runTerminalCommandStream.
  function _tlRunOneCommand(command) {
    return fetch('/api/terminal/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: command, cwd: null })
    })
      .then(r => r.json())
      .then(data => {
        const rawOut = (data && (data.output || data.stdout || '')) || '';
        const err = (data && (data.stderr || '')) || '';
        const combined = [rawOut, err].filter(Boolean).join('\n').trimEnd();
        if (combined) {
          const pre = document.getElementById('testlab-output');
          if (pre && typeof _terminalFormatOutput === 'function') {
            const existing = pre.innerHTML;
            pre.innerHTML = existing + _terminalFormatOutput(combined) + '\n';
          } else {
            _tlAppendOutput(combined + '\n');
          }
        }
        const rc = Number((data && (data.exit_code ?? data.returncode ?? 0)));
        const ok = data && data.ok !== false && rc === 0;
        // Return enough for the run recorder.
        return {
          ok: ok,
          exitCode: rc,
          stdoutTail: (combined || '').slice(-8000),
        };
      })
      .catch(err => {
        _tlAppendOutput(`\n[ERROR] ${err.message || err}\n`);
        return { ok: false, exitCode: -1, stdoutTail: String(err && err.message || err) };
      });
  }

  // ── Session 30 — ALM-style run recording ────────────────────────────────
  async function _tlStartRunRecord(item, changeId) {
    try {
      const projectId = (document.getElementById('testlab-project-id')?.value || '').trim() || null;
      const stepId    = (document.getElementById('testlab-step-id')?.value || '').trim() || null;
      const r = await fetch('/api/knowledge/test-runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          script_id: item.id,
          change_id: changeId || null,
          command: item.command || '',
          triggered_by: changeId ? ('change:' + changeId) : 'manual',
          project_id: projectId,
          step_id: stepId,
        }),
      });
      const data = await r.json();
      return (data && data.ok && data.run_id) || '';
    } catch (_) { return ''; }
  }

  async function _tlFinishRunRecord(runId, ok, exitCode, stdoutTail) {
    if (!runId) return;
    const status = ok ? 'pass' : 'fail';
    try {
      await fetch('/api/knowledge/test-runs/' + encodeURIComponent(runId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: status,
          exit_code: Number.isFinite(exitCode) ? exitCode : null,
          stdout_tail: stdoutTail || '',
        }),
      });
    } catch (_) { /* best-effort */ }
  }

  // ── History pane — last ~30 runs, grouped by script ─────────────────────
  function _tlLoadHistory() {
    const holder = document.getElementById('testlab-history');
    if (!holder) return;
    holder.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:6px;">Loading history…</div>';
    const changeInput = document.getElementById('testlab-change-id');
    const changeFilter = (changeInput && changeInput.value.trim()) || '';
    const qs = changeFilter
      ? `?change_id=${encodeURIComponent(changeFilter)}&limit=30`
      : `?limit=30`;
    fetch('/api/knowledge/test-runs' + qs)
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'bad response');
        const items = Array.isArray(data.items) ? data.items : [];
        if (!items.length) {
          holder.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:6px;">No runs yet. Select scripts and click Run.</div>';
          return;
        }
        holder.innerHTML = items.map(r => {
          const statusColor = {
            pass: '#4caf50',
            fail: '#f44336',
            error: '#ff9800',
            running: '#29b6f6',
            aborted: '#888',
          }[r.status] || '#888';
          const t = r.started_at ? new Date(r.started_at * 1000) : null;
          const tStr = t ? `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}:${String(t.getSeconds()).padStart(2, '0')}` : '—';
          const dur = (r.duration_ms != null) ? ((r.duration_ms / 1000).toFixed(1) + 's') : '—';
          const cid = r.change_id ? `<span style="color:var(--text-dim);font-family:monospace;">#${_tlEsc(r.change_id)}</span>` : '';
          return `<div class="tl-run-row" data-run-id="${_tlEsc(r.run_id)}" style="display:grid;grid-template-columns:60px 60px 120px 1fr 60px auto;gap:8px;padding:4px 6px;border-bottom:1px solid var(--border);font-size:10px;cursor:pointer;align-items:center;">
            <span style="color:${statusColor};font-weight:700;text-transform:uppercase;">${_tlEsc(r.status || '')}</span>
            <span style="color:var(--text-dim);font-family:monospace;">${tStr}</span>
            <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_tlEsc(r.script_id || '')}</span>
            <span style="color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${cid}</span>
            <span style="color:var(--text-dim);font-family:monospace;text-align:right;">${dur}</span>
            <button onclick="testLabOpenRun('${_tlEsc(r.run_id)}');event.stopPropagation();" title="Open details"
              style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:1px 6px;cursor:pointer;font-size:9px;">Details</button>
          </div>`;
        }).join('');
      })
      .catch(err => {
        holder.innerHTML = `<div style="color:var(--danger,#f77);font-size:11px;padding:6px;">History unavailable: ${_tlEsc(err.message || err)}</div>`;
      });
  }

  window.testLabRefreshHistory = _tlLoadHistory;

  window.testLabOpenRun = function (runId) {
    if (!runId) return;
    fetch('/api/knowledge/test-runs/' + encodeURIComponent(runId))
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'not found');
        _tlShowRunModal(data.run);
      })
      .catch(err => alert('Could not load run: ' + (err.message || err)));
  };

  function _tlShowRunModal(run) {
    if (!run) return;
    let modal = document.getElementById('testlab-run-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'testlab-run-modal';
      modal.className = 'modal';
      modal.onclick = (e) => { if (e.target === modal) modal.classList.remove('open'); };
      document.body.appendChild(modal);
    }
    const statusColor = { pass: '#4caf50', fail: '#f44336', error: '#ff9800', running: '#29b6f6', aborted: '#888' }[run.status] || '#888';
    const arts = Array.isArray(run.artifacts) ? run.artifacts : [];
    const dur = (run.duration_ms != null) ? ((run.duration_ms / 1000).toFixed(2) + 's') : '—';
    const started = run.started_at ? new Date(run.started_at * 1000).toLocaleString() : '—';
    modal.innerHTML = `
      <div class="modal-content testlab-run-modal-content" style="width:92%;max-width:860px;max-height:88vh;display:flex;flex-direction:column;resize:both;overflow:auto;min-width:520px;min-height:360px;">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);">
          <h3 style="margin:0;font-size:13px;">Test Run · ${_tlEsc(run.script_id || '')}
            <span style="margin-left:8px;padding:2px 8px;border-radius:10px;background:${statusColor}22;color:${statusColor};font-size:10px;font-weight:700;">${_tlEsc((run.status || '').toUpperCase())}</span>
          </h3>
          <button onclick="document.getElementById('testlab-run-modal').classList.remove('open')" style="background:none;border:none;color:var(--text);font-size:16px;cursor:pointer;">✕</button>
        </div>
        <div style="padding:12px 16px;overflow-y:auto;flex:1;font-size:11px;">
          <div style="display:grid;grid-template-columns:120px 1fr;gap:4px 12px;margin-bottom:12px;color:var(--text-dim);">
            <div>Run ID</div><div style="color:var(--text);font-family:monospace;">${_tlEsc(run.run_id)}</div>
            <div>Started</div><div style="color:var(--text);">${_tlEsc(started)}</div>
            <div>Duration</div><div style="color:var(--text);">${_tlEsc(dur)}</div>
            <div>Exit code</div><div style="color:var(--text);font-family:monospace;">${run.exit_code == null ? '—' : run.exit_code}</div>
            <div>Change</div><div style="color:var(--text);font-family:monospace;">${_tlEsc(run.change_id || '—')}</div>
            <div>Trigger</div><div style="color:var(--text);">${_tlEsc(run.triggered_by || '—')}</div>
            <div>Command</div><div style="color:var(--text);font-family:monospace;word-break:break-all;">${_tlEsc(run.command || '—')}</div>
          </div>
          <div style="font-weight:700;margin-bottom:4px;color:var(--text-dim);text-transform:uppercase;font-size:10px;">Stdout tail</div>
          <pre style="background:var(--card);padding:8px;border-radius:4px;max-height:260px;overflow:auto;white-space:pre-wrap;font-size:10px;margin-bottom:12px;">${_tlEsc(run.stdout_tail || '(empty)')}</pre>
          <div style="font-weight:700;margin-bottom:4px;color:var(--text-dim);text-transform:uppercase;font-size:10px;">Artifacts (${arts.length})</div>
          <div id="tl-run-artifacts" style="margin-bottom:10px;">
            ${arts.map(a => `<div style="padding:6px 8px;border-left:2px solid var(--accent);background:var(--card);margin-bottom:4px;border-radius:3px;">
              <div style="font-size:9px;color:var(--text-dim);">${_tlEsc(a.kind || 'note')} · ${new Date((a.created_at || 0) * 1000).toLocaleString()}</div>
              <div style="white-space:pre-wrap;">${_tlEsc(a.body || '')}</div>
            </div>`).join('') || '<div style="color:var(--text-dim);">No artifacts yet.</div>'}
          </div>
          <div style="display:flex;gap:6px;align-items:flex-start;">
            <textarea id="tl-run-note-input" rows="2" placeholder="Add a note or paste a log snippet…"
              style="flex:1;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:3px;padding:6px;font-size:11px;"></textarea>
            <button onclick="testLabAddNote('${_tlEsc(run.run_id)}')"
              style="background:var(--accent);color:#000;border:none;padding:6px 12px;border-radius:3px;cursor:pointer;font-size:11px;font-weight:600;">Add Note</button>
          </div>
        </div>
      </div>`;
    modal.classList.add('open');
    // MD-FEATURE-0ACF6122C9F9 — persist resized run-modal dimensions so the
    // user's tuned details panel stays put across runs.
    try {
      const content = modal.querySelector('.testlab-run-modal-content');
      if (content) {
        const saved = JSON.parse(localStorage.getItem('fridays_testlab_run_modal_size') || 'null');
        if (saved && saved.w && saved.h) {
          content.style.width = saved.w + 'px';
          content.style.height = saved.h + 'px';
        }
        if (!content._tlResizeObserved) {
          content._tlResizeObserved = true;
          let _tlResizeT = null;
          new ResizeObserver(() => {
            clearTimeout(_tlResizeT);
            _tlResizeT = setTimeout(() => {
              try {
                localStorage.setItem('fridays_testlab_run_modal_size',
                  JSON.stringify({ w: Math.round(content.offsetWidth), h: Math.round(content.offsetHeight) }));
              } catch (_) {}
            }, 250);
          }).observe(content);
        }
      }
    } catch (_) {}
    // Seven sees — propose-only insight panel.
    try {
      if (window.SevenPanel) {
        const body = modal.querySelector('.modal-content > div[style*="overflow-y"]');
        if (body) window.SevenPanel.mount(body, { kind: 'run', id: run.run_id });
      }
    } catch (e) { /* noop */ }
  }

  window.testLabAddNote = function (runId) {
    const input = document.getElementById('tl-run-note-input');
    if (!input || !runId) return;
    const body = (input.value || '').trim();
    if (!body) return;
    fetch('/api/knowledge/test-runs/' + encodeURIComponent(runId) + '/artifacts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: 'note', body: body }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'failed');
        input.value = '';
        // Re-open to refresh artifacts
        window.testLabOpenRun(runId);
      })
      .catch(err => alert('Could not add note: ' + (err.message || err)));
  };

  // ── Home-tile badge (Session 30.1 — under Studio tile) ──────────────────
  // Paints latest test-run status on the Studio home card (grouped with
  // Projects / Proposals / Git / Test Lab — no separate tile any more).
  window.paintHomeTestlabBadge = function () {
    const badge = document.getElementById('home-studio-badge');
    const desc = document.getElementById('home-studio-desc');
    const defaultDesc = 'Projects · Proposals · Git · Test Lab';
    if (!badge) return;
    fetch('/api/knowledge/test-runs?limit=1')
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) return;
        const items = Array.isArray(data.items) ? data.items : [];
        if (!items.length) {
          badge.style.display = 'none';
          if (desc) desc.textContent = defaultDesc;
          return;
        }
        const r = items[0];
        const colors = {
          pass: { bg: 'rgba(76,175,80,0.2)', fg: '#4caf50' },
          fail: { bg: 'rgba(244,67,54,0.2)', fg: '#f44336' },
          error: { bg: 'rgba(255,152,0,0.2)', fg: '#ff9800' },
          running: { bg: 'rgba(41,182,246,0.2)', fg: '#29b6f6' },
          aborted: { bg: 'rgba(136,136,136,0.2)', fg: '#888' },
        };
        const c = colors[r.status] || colors.aborted;
        badge.style.display = 'inline-block';
        badge.style.background = c.bg;
        badge.style.color = c.fg;
        badge.textContent = String(r.status || '').toUpperCase();
        if (desc) {
          const when = r.started_at ? new Date(r.started_at * 1000).toLocaleTimeString() : '';
          desc.textContent = `${defaultDesc} · last run: ${r.script_id || '—'} ${when}`;
        }
      })
      .catch(() => { /* best-effort */ });
  };

  // ── Output helpers ───────────────────────────────────────────────────────
  function _tlAppendOutput(text) {
    const pre = document.getElementById('testlab-output');
    if (!pre) return;
    pre.appendChild(document.createTextNode(text));
    pre.scrollTop = pre.scrollHeight;
  }

  function _tlSetStatus(text, kind) {
    const el = document.getElementById('testlab-run-status');
    if (!el) return;
    const colors = {
      ok: 'var(--accent)',
      error: 'var(--danger, #f77)',
      warn: '#f7b84b',
      running: 'var(--info, #29b6f6)',
    };
    el.style.color = colors[kind] || 'var(--text-dim)';
    el.textContent = text;
  }

  function _tlEsc(v) {
    if (window.SwarmChat && typeof window.SwarmChat.esc === 'function') return window.SwarmChat.esc(v);
    return String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  }
})();
