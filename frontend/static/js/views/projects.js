// ═══════════════════════════════════════════════════════════════════════════
// STUDIO PROJECTS — Session 30.1
// Projects own proposals, plan steps, test cases and test runs.
// Methodology is Agile / Waterfall / Prince2 / Mixed. Seven is the default
// owner of each project and each step.
// ═══════════════════════════════════════════════════════════════════════════

(function () {
  'use strict';

  const LS_SELECTED = 'fridays-studio-project-id-v1';
  let _projects = [];
  let _selectedId = '';

  window.loadStudioProjectsPanel = function () {
    _selectedId = localStorage.getItem(LS_SELECTED) || '';
    projectsRefresh();
  };

  window.projectsRefresh = function () {
    fetch('/api/knowledge/projects?limit=100')
      .then(r => r.json())
      .then(data => {
        _projects = (data && data.items) || [];
        _renderList();
        if (_selectedId && _projects.some(p => p.project_id === _selectedId)) {
          _loadDetail(_selectedId);
        } else if (_projects.length) {
          _loadDetail(_projects[0].project_id);
        } else {
          const det = document.getElementById('projects-detail');
          if (det) det.innerHTML = '<div style="padding:14px;color:var(--text-dim);">No projects yet. Create one above to start linking proposals, plan steps and test cases.</div>';
        }
      })
      .catch(err => {
        const list = document.getElementById('projects-list');
        if (list) list.innerHTML = `<div style="color:var(--danger,#f77);font-size:11px;padding:12px;">${_esc(err.message || err)}</div>`;
      });
  };

  window.projectsCreate = function () {
    const nameEl = document.getElementById('projects-new-name');
    const methEl = document.getElementById('projects-new-method');
    if (!nameEl) return;
    const name = (nameEl.value || '').trim();
    if (!name) { nameEl.focus(); return; }
    const methodology = (methEl && methEl.value) || 'mixed';
    fetch('/api/knowledge/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, methodology: methodology, owner: 'seven' }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'create failed');
        nameEl.value = '';
        _selectedId = data.project_id;
        localStorage.setItem(LS_SELECTED, _selectedId);
        projectsRefresh();
      })
      .catch(err => alert('Could not create project: ' + (err.message || err)));
  };

  function _renderList() {
    const list = document.getElementById('projects-list');
    if (!list) return;
    if (!_projects.length) {
      list.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:12px;">No projects. Create one above.</div>';
      return;
    }
    list.innerHTML = _projects.map(p => {
      const on = p.project_id === _selectedId;
      const pct = p.step_count ? Math.round((p.steps_done || 0) * 100 / p.step_count) : 0;
      const statusColor = p.status === 'active' ? '#4caf50' : '#888';
      return `<div class="project-row" data-pid="${_esc(p.project_id)}" onclick="projectsSelect('${_esc(p.project_id)}')"
        style="padding:8px 10px;margin-bottom:4px;border:1px solid ${on ? 'var(--accent)' : 'var(--border)'};border-radius:5px;cursor:pointer;background:${on ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'transparent'};">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
          <div style="font-size:11px;font-weight:700;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(p.name)}</div>
          <span style="font-size:8px;padding:1px 5px;border-radius:6px;background:color-mix(in srgb, var(--accent) 15%, transparent);color:var(--accent);text-transform:uppercase;">${_esc(p.methodology)}</span>
        </div>
        <div style="font-size:9px;color:var(--text-dim);margin-top:2px;font-family:monospace;">${_esc(p.project_id)}</div>
        <div style="font-size:9px;color:var(--text-dim);margin-top:3px;">
          <span style="color:${statusColor};">●</span> ${_esc(p.status)} ·
          ${p.steps_done || 0}/${p.step_count || 0} steps · ${p.case_count || 0} cases · owner: ${_esc(p.owner || 'seven')}
        </div>
        ${p.step_count ? `<div style="height:3px;background:var(--border);border-radius:2px;margin-top:4px;overflow:hidden;"><div style="height:100%;width:${pct}%;background:var(--accent);"></div></div>` : ''}
      </div>`;
    }).join('');
  }

  window.projectsSelect = function (pid) {
    _selectedId = pid;
    localStorage.setItem(LS_SELECTED, pid);
    _renderList();
    _loadDetail(pid);
  };

  function _loadDetail(pid) {
    const det = document.getElementById('projects-detail');
    if (!det) return;
    det.innerHTML = '<div style="color:var(--text-dim);">Loading…</div>';
    Promise.all([
      fetch('/api/knowledge/projects/' + encodeURIComponent(pid)).then(r => r.json()),
      fetch('/api/knowledge/test-runs?project_id=' + encodeURIComponent(pid) + '&limit=20').then(r => r.json()),
    ])
      .then(([pd, rd]) => {
        if (!pd || !pd.ok) throw new Error((pd && pd.error) || 'not found');
        const p = pd.project;
        const runs = (rd && rd.items) || [];
        det.innerHTML = _renderDetail(p, runs);
      })
      .catch(err => {
        det.innerHTML = `<div style="color:var(--danger,#f77);">${_esc(err.message || err)}</div>`;
      });
  }

  function _renderDetail(p, runs) {
    const steps = p.steps || [];
    const cases = p.test_cases || [];
    const proposals = p.proposals || [];
    return `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:14px;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:14px;font-weight:700;color:var(--text);">${_esc(p.name)}</div>
          <div style="font-size:9px;color:var(--text-dim);font-family:monospace;">${_esc(p.project_id)} · methodology: <b>${_esc(p.methodology)}</b> · owner: <b>${_esc(p.owner || 'seven')}</b> · status: ${_esc(p.status)}</div>
          ${p.description ? `<div style="margin-top:6px;color:var(--text-dim);font-size:11px;white-space:pre-wrap;">${_esc(p.description)}</div>` : ''}
        </div>
        <div style="display:flex;gap:4px;flex-shrink:0;">
          <button onclick="projectsRename('${_esc(p.project_id)}')" title="Rename project"
            style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:3px 8px;font-size:10px;cursor:pointer;">✎ Rename</button>
          <button onclick="projectsDelete('${_esc(p.project_id)}','${_esc((p.name||'').replace(/'/g, '&#39;'))}')" title="Delete project"
            style="background:none;border:1px solid var(--danger,#f77);color:var(--danger,#f77);border-radius:4px;padding:3px 8px;font-size:10px;cursor:pointer;">🗑 Delete</button>
        </div>
      </div>

      <div style="border:1px solid var(--border);border-radius:5px;padding:10px;margin-bottom:12px;background:var(--card);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;">Plan Steps (${steps.length})</div>
          <div style="display:flex;gap:4px;">
            <input id="pd-step-title" placeholder="New step title…" style="padding:3px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:10px;outline:none;">
            <button onclick="projectsAddStep('${_esc(p.project_id)}')" style="background:var(--accent);color:#000;border:none;border-radius:4px;padding:3px 10px;font-size:10px;font-weight:700;cursor:pointer;">+ Step</button>
          </div>
        </div>
        ${steps.length ? steps.map((s, i) => `
          <div style="display:grid;grid-template-columns:24px 1fr 80px 100px 64px 130px;gap:6px;padding:5px 6px;border-top:1px solid var(--border);align-items:center;font-size:10px;">
            <span style="color:var(--text-dim);font-family:monospace;">${i + 1}.</span>
            <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(s.title)}">${_esc(s.title)}</span>
            <span style="color:var(--text-dim);font-size:9px;">${_esc(s.owner || 'seven')}</span>
            <select onchange="projectsSetStepStatus('${_esc(s.step_id)}', this.value)"
              style="background:var(--window-header);border:1px solid var(--border);color:var(--text);border-radius:3px;padding:2px;font-size:9px;">
              ${['todo','doing','blocked','partial','done','skipped'].map(x => `<option value="${x}"${x === s.status ? ' selected' : ''}>${x}</option>`).join('')}
            </select>
            <span style="font-size:8px;color:${_stepStatusColor(s.status)};font-weight:700;text-transform:uppercase;text-align:right;">${_esc(s.status)}</span>
            <span style="display:flex;gap:2px;justify-content:flex-end;">
              <button onclick="projectsRunStepTests('${_esc(s.step_id)}')" title="Run only this step's tests"
                style="background:none;border:1px solid var(--border);color:var(--accent);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">▶</button>
              <button onclick="projectsCompleteStep('${_esc(s.step_id)}')" title="Mark done + auto-write KC doc"
                style="background:none;border:1px solid var(--border);color:#4caf50;border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">✓</button>
              <button onclick="projectsEditStep('${_esc(s.step_id)}','${_esc((s.title||'').replace(/'/g, '&#39;'))}')" title="Rename step"
                style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">✎</button>
              <button onclick="projectsDeleteStep('${_esc(s.step_id)}','${_esc((s.title||'').replace(/'/g, '&#39;'))}')" title="Delete step"
                style="background:none;border:1px solid var(--border);color:var(--danger,#f77);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">🗑</button>
            </span>
          </div>
        `).join('') : '<div style="padding:6px;color:var(--text-dim);font-size:10px;">No steps yet. Add one to start the plan.</div>'}
      </div>

      <div style="border:1px solid var(--border);border-radius:5px;padding:10px;margin-bottom:12px;background:var(--card);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;">Test Cases (${cases.length})</div>
          <div style="display:flex;gap:4px;">
            <input id="pd-case-title" placeholder="Case title…" style="padding:3px 6px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:10px;outline:none;width:140px;">
            <input id="pd-case-script" placeholder="script_id (optional)" style="padding:3px 6px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:10px;outline:none;width:140px;">
            <button onclick="projectsAddCase('${_esc(p.project_id)}')" style="background:var(--accent);color:#000;border:none;border-radius:4px;padding:3px 10px;font-size:10px;font-weight:700;cursor:pointer;">+ Case</button>
          </div>
        </div>
        ${cases.length ? cases.map(c => `
          <div style="display:grid;grid-template-columns:1fr 150px 70px 70px;gap:6px;padding:5px 6px;border-top:1px solid var(--border);align-items:center;font-size:10px;">
            <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(c.title)}">${_esc(c.title)}</span>
            <span style="color:var(--text-dim);font-family:monospace;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(c.script_id || '—')}</span>
            <span style="font-size:8px;color:var(--accent);font-weight:700;text-transform:uppercase;text-align:right;">${_esc(c.status)}</span>
            <span style="display:flex;gap:2px;justify-content:flex-end;">
              <button onclick="projectsEditCase('${_esc(c.case_id)}','${_esc((c.title||'').replace(/'/g, '&#39;'))}','${_esc(c.script_id||'')}')" title="Edit"
                style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">✎</button>
              <button onclick="projectsDeleteCase('${_esc(c.case_id)}','${_esc((c.title||'').replace(/'/g, '&#39;'))}')" title="Delete"
                style="background:none;border:1px solid var(--border);color:var(--danger,#f77);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">🗑</button>
            </span>
          </div>
        `).join('') : '<div style="padding:6px;color:var(--text-dim);font-size:10px;">No test cases yet. Add a case tied to a Test Lab script_id to track pass/fail per run.</div>'}
      </div>

      <div style="border:1px solid var(--border);border-radius:5px;padding:10px;margin-bottom:12px;background:var(--card);">
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;margin-bottom:6px;">Linked Proposals (${proposals.length})</div>
        ${proposals.length ? proposals.map(pr => `
          <div style="padding:4px 6px;font-size:10px;color:var(--text);border-top:1px solid var(--border);font-family:monospace;">#${_esc(pr.proposal_id)}</div>
        `).join('') : '<div style="padding:4px;color:var(--text-dim);font-size:10px;">No proposals linked yet. POST to /api/knowledge/projects/<id>/link-proposal.</div>'}
      </div>

      <div style="border:1px solid var(--border);border-radius:5px;padding:10px;background:var(--card);">
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;margin-bottom:6px;">Recent Test Runs (${runs.length})</div>
        ${runs.length ? runs.map(r => {
          const t = r.started_at ? new Date(r.started_at * 1000) : null;
          const tStr = t ? `${String(t.getHours()).padStart(2,'0')}:${String(t.getMinutes()).padStart(2,'0')}` : '—';
          return `<div style="display:grid;grid-template-columns:50px 50px 1fr 80px;gap:6px;padding:4px 6px;font-size:10px;border-top:1px solid var(--border);align-items:center;">
            <span style="color:${_runStatusColor(r.status)};font-weight:700;text-transform:uppercase;font-size:9px;">${_esc(r.status)}</span>
            <span style="color:var(--text-dim);font-family:monospace;">${tStr}</span>
            <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(r.script_id)}</span>
            <button onclick="testLabOpenRun('${_esc(r.run_id)}')" style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:1px 6px;font-size:9px;cursor:pointer;">Details</button>
          </div>`;
        }).join('') : '<div style="padding:4px;color:var(--text-dim);font-size:10px;">No runs yet for this project. Set the project_id in Test Lab to start recording runs here.</div>'}
      </div>
    `;
  }

  window.projectsAddStep = function (pid) {
    const input = document.getElementById('pd-step-title');
    if (!input) return;
    const title = (input.value || '').trim();
    if (!title) { input.focus(); return; }
    fetch('/api/knowledge/projects/' + encodeURIComponent(pid) + '/steps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title, owner: 'seven' }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'failed');
        input.value = '';
        _loadDetail(pid);
      })
      .catch(err => alert('Add step failed: ' + (err.message || err)));
  };

  window.projectsSetStepStatus = function (stepId, status) {
    fetch('/api/knowledge/steps/' + encodeURIComponent(stepId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: status }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'failed');
        if (_selectedId) _loadDetail(_selectedId);
      })
      .catch(err => alert('Update step failed: ' + (err.message || err)));
  };

  window.projectsAddCase = function (pid) {
    const titleEl = document.getElementById('pd-case-title');
    const scriptEl = document.getElementById('pd-case-script');
    if (!titleEl) return;
    const title = (titleEl.value || '').trim();
    if (!title) { titleEl.focus(); return; }
    fetch('/api/knowledge/projects/' + encodeURIComponent(pid) + '/test-cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        script_id: (scriptEl && scriptEl.value.trim()) || null,
        owner: 'seven',
      }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'failed');
        if (titleEl) titleEl.value = '';
        if (scriptEl) scriptEl.value = '';
        _loadDetail(pid);
      })
      .catch(err => alert('Add case failed: ' + (err.message || err)));
  };

  function _stepStatusColor(s) {
    return ({ todo: '#888', doing: '#29b6f6', blocked: '#f44336', partial: '#ffb74d', done: '#4caf50', skipped: '#aaa' })[s] || '#888';
  }
  function _runStatusColor(s) {
    return ({ pass: '#4caf50', fail: '#f44336', error: '#ff9800', running: '#29b6f6', aborted: '#888' })[s] || '#888';
  }

  // ── Phase 3: delete / rename / run-step-tests / complete-step ──────────

  window.projectsDelete = function (pid, name) {
    if (!pid) return;
    if (!confirm(`Delete project "${name || pid}"?\n\nThis removes the project, its steps, test cases and proposal links. Test runs keep their history.`)) return;
    fetch('/api/knowledge/projects/' + encodeURIComponent(pid), { method: 'DELETE' })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'delete failed');
        _selectedId = '';
        localStorage.removeItem(LS_SELECTED);
        projectsRefresh();
      })
      .catch(err => alert('Delete project failed: ' + (err.message || err)));
  };

  window.projectsRename = function (pid) {
    const current = (_projects.find(p => p.project_id === pid) || {}).name || '';
    const next = prompt('Rename project:', current);
    if (next === null) return;
    const trimmed = (next || '').trim();
    if (!trimmed || trimmed === current) return;
    fetch('/api/knowledge/projects/' + encodeURIComponent(pid), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: trimmed }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'rename failed');
        projectsRefresh();
      })
      .catch(err => alert('Rename failed: ' + (err.message || err)));
  };

  window.projectsDeleteStep = function (stepId, title) {
    if (!stepId) return;
    if (!confirm(`Delete step "${title || stepId}"?\n\nTest cases tied to it will be unlinked but kept.`)) return;
    fetch('/api/knowledge/steps/' + encodeURIComponent(stepId), { method: 'DELETE' })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'delete failed');
        if (_selectedId) _loadDetail(_selectedId);
      })
      .catch(err => alert('Delete step failed: ' + (err.message || err)));
  };

  window.projectsEditStep = function (stepId, currentTitle) {
    const next = prompt('Rename step:', currentTitle || '');
    if (next === null) return;
    const trimmed = (next || '').trim();
    if (!trimmed || trimmed === currentTitle) return;
    fetch('/api/knowledge/steps/' + encodeURIComponent(stepId) + '/edit', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: trimmed }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'edit failed');
        if (_selectedId) _loadDetail(_selectedId);
      })
      .catch(err => alert('Rename step failed: ' + (err.message || err)));
  };

  window.projectsDeleteCase = function (caseId, title) {
    if (!caseId) return;
    if (!confirm(`Delete test case "${title || caseId}"?`)) return;
    fetch('/api/knowledge/cases/' + encodeURIComponent(caseId), { method: 'DELETE' })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'delete failed');
        if (_selectedId) _loadDetail(_selectedId);
      })
      .catch(err => alert('Delete case failed: ' + (err.message || err)));
  };

  window.projectsEditCase = function (caseId, currentTitle, currentScript) {
    const nextTitle = prompt('Case title:', currentTitle || '');
    if (nextTitle === null) return;
    const nextScript = prompt('Test Lab script_id (blank to clear):', currentScript || '');
    if (nextScript === null) return;
    const body = {};
    const t = (nextTitle || '').trim();
    if (t && t !== currentTitle) body.title = t;
    if (nextScript !== currentScript) body.script_id = (nextScript || '').trim();
    if (!Object.keys(body).length) return;
    fetch('/api/knowledge/cases/' + encodeURIComponent(caseId) + '/edit', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'edit failed');
        if (_selectedId) _loadDetail(_selectedId);
      })
      .catch(err => alert('Edit case failed: ' + (err.message || err)));
  };

  window.projectsRunStepTests = function (stepId) {
    if (!stepId) return;
    fetch('/api/knowledge/steps/' + encodeURIComponent(stepId) + '/test-scripts')
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'lookup failed');
        const ids = data.script_ids || [];
        if (!ids.length) {
          alert('This step has no test cases with a Test Lab script_id attached.\n\nAdd a test case with a script_id, then click ▶ again.');
          return;
        }
        // Hand off to the existing Test Lab runner when present; otherwise
        // at least surface the resolved commands to the user.
        if (typeof window.testLabRunScripts === 'function') {
          window.testLabRunScripts(ids, { step_id: stepId, project_id: _selectedId || null });
        } else {
          return fetch('/api/studio/testlab/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_ids: ids }),
          })
            .then(r => r.json())
            .then(res => {
              const lines = (res && res.items || []).map(i => `• ${i.id}: ${i.command}`);
              alert(`Step tests (${ids.length}):\n\n` + (lines.join('\n') || '(no commands resolved)'));
            });
        }
      })
      .catch(err => alert('Run step tests failed: ' + (err.message || err)));
  };

  window.projectsCompleteStep = function (stepId) {
    if (!stepId) return;
    const summary = prompt('One-line summary of what this step delivered (goes into Knowledge Center):', '');
    if (summary === null) return;
    fetch('/api/knowledge/steps/' + encodeURIComponent(stepId) + '/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ summary: (summary || '').trim() }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'complete failed');
        if (_selectedId) _loadDetail(_selectedId);
      })
      .catch(err => alert('Complete step failed: ' + (err.message || err)));
  };

  function _esc(v) {
    if (window.SwarmChat && typeof window.SwarmChat.esc === 'function') return window.SwarmChat.esc(v);
    return String(v ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch]));
  }
})();
