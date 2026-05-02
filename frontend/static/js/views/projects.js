// ═══════════════════════════════════════════════════════════════════════════
// STUDIO PROJECTS — Session 30.1
// Projects own proposals, plan steps, test cases and test runs.
// Methodology is Agile / Waterfall / Prince2 / Mixed. Seven is the default
// owner of each project and each step.
// ═══════════════════════════════════════════════════════════════════════════

(function () {
  'use strict';

  const LS_SELECTED = 'fridays-studio-project-id-v1';
  const LS_STATUS_FILTER = 'fridays-studio-project-status-filter-v1';
  let _projects = [];
  let _selectedId = '';
  let _statusFilter = 'active'; // 'active' | 'all' | 'archived'

  function _loadStatusFilter() {
    try {
      const v = localStorage.getItem(LS_STATUS_FILTER);
      if (v === 'active' || v === 'all' || v === 'archived') _statusFilter = v;
    } catch (e) { /* ignore */ }
    const sel = document.getElementById('projects-status-filter');
    if (sel) sel.value = _statusFilter;
  }

  function _filteredProjects() {
    if (_statusFilter === 'all') return _projects.slice();
    if (_statusFilter === 'archived') return _projects.filter(p => p.status === 'archived');
    // 'active' mode → active + on_hold (anything not archived)
    return _projects.filter(p => p.status !== 'archived');
  }

  window.projectsSetStatusFilter = function (v) {
    if (v !== 'active' && v !== 'all' && v !== 'archived') v = 'active';
    _statusFilter = v;
    try { localStorage.setItem(LS_STATUS_FILTER, v); } catch (e) { /* ignore */ }
    _renderList();
    // If currently selected project is now hidden, fall back to first visible.
    const visible = _filteredProjects();
    if (_selectedId && !visible.some(p => p.project_id === _selectedId)) {
      if (visible.length) {
        _selectedId = visible[0].project_id;
        try { localStorage.setItem(LS_SELECTED, _selectedId); } catch (e) {}
        _loadDetail(_selectedId);
      } else {
        const det = document.getElementById('projects-detail');
        if (det) det.innerHTML = '<div style="padding:14px;color:var(--text-dim);">No projects in this view. Switch the filter to <b>All</b> to see archived work.</div>';
      }
    }
  };

  window.loadStudioProjectsPanel = function () {
    _selectedId = localStorage.getItem(LS_SELECTED) || '';
    _loadStatusFilter();
    projectsRefresh();
  };

  window.projectsRefresh = function () {
    fetch('/api/knowledge/projects?limit=100')
      .then(r => r.json())
      .then(data => {
        _projects = (data && data.items) || [];
        _renderList();
        const visible = _filteredProjects();
        if (_selectedId && visible.some(p => p.project_id === _selectedId)) {
          _loadDetail(_selectedId);
        } else if (visible.length) {
          _loadDetail(visible[0].project_id);
        } else {
          const det = document.getElementById('projects-detail');
          if (det) det.innerHTML = '<div style="padding:14px;color:var(--text-dim);">No projects in this view. Use the filter above to switch to <b>All</b> or <b>Archived</b>.</div>';
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
    const visible = _filteredProjects();
    const archivedCount = _projects.filter(p => p.status === 'archived').length;
    const activeCount = _projects.length - archivedCount;
    const hint = `<div style="font-size:9px;color:var(--text-dim);padding:4px 6px 6px;">${_esc(_statusFilter)} view · ${visible.length} shown · ${activeCount} active / ${archivedCount} archived</div>`;
    if (!visible.length) {
      list.innerHTML = hint + '<div style="color:var(--text-dim);font-size:11px;padding:12px;">No projects match this filter.</div>';
      return;
    }
    list.innerHTML = hint + visible.map(p => {
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
        // Seven sees — propose-only insight panel.
        try {
          if (window.SevenPanel) {
            window.SevenPanel.mount(det, { kind: 'project', id: p.project_id });
          }
        } catch (e) { /* noop */ }
      })
      .catch(err => {
        det.innerHTML = `<div style="color:var(--danger,#f77);">${_esc(err.message || err)}</div>`;
      });
  }

  function _renderDetail(p, runs) {
    const steps = p.steps || [];
    const cases = p.test_cases || [];
    const blackboard = p.blackboard_notes || [];
    const proposals = p.proposals || [];
    return `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:14px;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:14px;font-weight:700;color:var(--text);">${_esc(p.name)}</div>
          <div style="font-size:9px;color:var(--text-dim);font-family:monospace;">${_esc(p.project_id)} · methodology: <b>${_esc(p.methodology)}</b> · owner: <b>${_esc(p.owner || 'seven')}</b> · status: ${_esc(p.status)}</div>
          ${p.description ? `<div style="margin-top:6px;color:var(--text-dim);font-size:11px;white-space:pre-wrap;">${_esc(p.description)}</div>` : ''}
          ${_renderProjectTypeRow(p)}
        </div>
        <div style="display:flex;gap:4px;flex-shrink:0;">
          <button onclick="projectsPreviewContext('${_esc(p.project_id)}')" title="Preview the local-agent context pack"
            style="background:none;border:1px solid var(--accent);color:var(--accent);border-radius:4px;padding:3px 8px;font-size:10px;cursor:pointer;">Preview Context</button>
          <button onclick="projectsRename('${_esc(p.project_id)}')" title="Rename project"
            style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:3px 8px;font-size:10px;cursor:pointer;">✎ Rename</button>
          <button onclick="projectsDelete('${_esc(p.project_id)}','${_esc((p.name||'').replace(/'/g, '&#39;'))}')" title="Delete project"
            style="background:none;border:1px solid var(--danger,#f77);color:var(--danger,#f77);border-radius:4px;padding:3px 8px;font-size:10px;cursor:pointer;">🗑 Delete</button>
        </div>
      </div>

      <div id="pd-context-preview" style="display:none;border:1px solid color-mix(in srgb,var(--accent) 45%,var(--border));border-radius:5px;padding:10px;margin-bottom:12px;background:color-mix(in srgb,var(--accent) 7%,var(--card));">
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px;">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--accent);font-weight:800;">Agent Context Preview</div>
          <button onclick="projectsHideContextPreview()" style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:1px 6px;font-size:9px;cursor:pointer;">Close</button>
        </div>
        <pre id="pd-context-preview-body" style="white-space:pre-wrap;margin:0;color:var(--text);font-size:10px;line-height:1.45;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;max-height:360px;overflow:auto;"></pre>
      </div>

      ${_renderPacketRollup(p, steps)}
      <div style="border:1px solid var(--border);border-radius:5px;padding:10px;margin-bottom:12px;background:linear-gradient(135deg,color-mix(in srgb,var(--card) 92%,var(--accent) 8%),var(--card));">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px;">
          <div>
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;">Project Blackboard (${blackboard.length})</div>
            <div style="font-size:9px;color:var(--text-dim);margin-top:2px;">Visible handoff notes for agents: decisions, risks, tests, research, and next steps.</div>
          </div>
          <div style="display:grid;grid-template-columns:92px minmax(180px,1fr) auto;gap:4px;align-items:start;max-width:620px;flex:1;">
            <select id="pd-blackboard-kind" style="padding:4px 6px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:10px;">
              ${['note','handoff','decision','risk','test','research'].map(x => `<option value="${x}">${x}</option>`).join('')}
            </select>
            <textarea id="pd-blackboard-content" rows="2" placeholder="Leave a compact visible handoff note for the next agent…" style="padding:5px 7px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:10px;outline:none;resize:vertical;min-height:34px;"></textarea>
            <button onclick="projectsAddBlackboardNote('${_esc(p.project_id)}')" style="background:var(--accent);color:#000;border:none;border-radius:4px;padding:5px 10px;font-size:10px;font-weight:700;cursor:pointer;white-space:nowrap;">+ Note</button>
          </div>
        </div>
        ${blackboard.length ? blackboard.map(note => `
          <div style="display:grid;grid-template-columns:86px 76px 1fr 112px;gap:6px;padding:6px;border-top:1px solid var(--border);align-items:start;font-size:10px;">
            <span style="font-size:8px;color:var(--accent);font-weight:800;text-transform:uppercase;letter-spacing:0.4px;">${_esc(note.kind || 'note')}</span>
            <span style="color:var(--text-dim);font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(note.author || 'agent')}">${_esc(note.author || 'agent')}</span>
            <span style="color:var(--text);white-space:pre-wrap;line-height:1.35;">${_esc(note.content || '')}</span>
            <span style="display:flex;gap:3px;justify-content:flex-end;">
              <button onclick="projectsSetBlackboardStatus('${_esc(note.note_id)}','resolved')" title="Mark resolved"
                style="background:none;border:1px solid var(--border);color:#4caf50;border-radius:3px;padding:2px 6px;font-size:9px;cursor:pointer;">Resolve</button>
              <button onclick="projectsSetBlackboardStatus('${_esc(note.note_id)}','archived')" title="Archive note"
                style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:2px 6px;font-size:9px;cursor:pointer;">Archive</button>
            </span>
          </div>
        `).join('') : '<div style="padding:6px;color:var(--text-dim);font-size:10px;border-top:1px solid var(--border);">No blackboard notes yet. Add the first handoff note so the next agent starts warm instead of cold.</div>'}
      </div>

      <div style="border:1px solid var(--border);border-radius:5px;padding:10px;margin-bottom:12px;background:var(--card);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;">Plan Steps (${(_packetFilter ? steps.filter(s => _packetOf(s) === _packetFilter) : steps).length}${_packetFilter ? ' / ' + steps.length + ' — filtered to ' + _packetFilter : ''})</div>
          <div style="display:flex;gap:4px;">
            <input id="pd-step-title" placeholder="New step title…" style="padding:3px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:10px;outline:none;">
            <button onclick="projectsAddStep('${_esc(p.project_id)}')" style="background:var(--accent);color:#000;border:none;border-radius:4px;padding:3px 10px;font-size:10px;font-weight:700;cursor:pointer;">+ Step</button>
          </div>
        </div>
        ${(() => {
          const visible = _packetFilter ? steps.filter(s => _packetOf(s) === _packetFilter) : steps;
          return visible.length ? visible.map((s, i) => `
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
              <button onclick="projectsOpenStep('${_esc(s.step_id)}')" title="Open step detail (ALM)"
                style="background:none;border:1px solid var(--border);color:var(--accent);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">⤢</button>
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
        `).join('') : `<div style="padding:6px;color:var(--text-dim);font-size:10px;">${_packetFilter ? 'No steps in ' + _esc(_packetFilter) + '. Click clear filter above.' : 'No steps yet. Add one to start the plan.'}</div>`;
        })()}
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
              <button onclick="projectsOpenCase('${_esc(c.case_id)}')" title="Open case detail (ALM)"
                style="background:none;border:1px solid var(--border);color:var(--accent);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">⤢</button>
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

  window.projectsAddBlackboardNote = function (pid) {
    const kindEl = document.getElementById('pd-blackboard-kind');
    const contentEl = document.getElementById('pd-blackboard-content');
    if (!contentEl) return;
    const content = (contentEl.value || '').trim();
    if (!content) { contentEl.focus(); return; }
    fetch('/api/knowledge/projects/' + encodeURIComponent(pid) + '/blackboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kind: (kindEl && kindEl.value) || 'note',
        content: content,
        author: 'seven',
      }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'failed');
        contentEl.value = '';
        _loadDetail(pid);
      })
      .catch(err => alert('Add blackboard note failed: ' + (err.message || err)));
  };

  window.projectsSetBlackboardStatus = function (noteId, status) {
    if (!noteId || !status) return;
    fetch('/api/knowledge/blackboard/' + encodeURIComponent(noteId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: status }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'failed');
        if (_selectedId) _loadDetail(_selectedId);
      })
      .catch(err => alert('Update blackboard note failed: ' + (err.message || err)));
  };

  window.projectsPreviewContext = function (pid) {
    const box = document.getElementById('pd-context-preview');
    const body = document.getElementById('pd-context-preview-body');
    if (!box || !body) return;
    box.style.display = 'block';
    body.textContent = 'Building project context...';
    fetch('/api/knowledge/projects/' + encodeURIComponent(pid) + '/context-preview')
      .then(r => r.json().then(data => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok || !data.ok) throw new Error((data && data.error) || 'preview failed');
        body.textContent = data.context || '(empty context)';
      })
      .catch(err => {
        body.textContent = 'Context preview failed: ' + (err.message || err);
      });
  };

  window.projectsHideContextPreview = function () {
    const box = document.getElementById('pd-context-preview');
    if (box) box.style.display = 'none';
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

  // STEP-PROJECT-TYPE-ROUTING-STUDIO-MEDIA-PROGRAMMING-20260430 — projects
  // remain ALM-tracked, but each one can be tagged as Media or Programming so
  // the detail panel surfaces routing buttons into the right tooling. Tag is
  // persisted in localStorage keyed by project_id; falls back to a heuristic
  // that scans name/description for media keywords.
  const PROJECT_TYPE_KEY = 'swarm-project-type';
  const _MEDIA_KEYWORDS = /(media|music|video|audio|synth|track|song|film|photo|render|image|art|design|newsletter)/i;
  function _projectTypeOverrides() {
    try { return JSON.parse(localStorage.getItem(PROJECT_TYPE_KEY) || '{}') || {}; }
    catch (_e) { return {}; }
  }
  function _saveProjectTypeOverrides(map) {
    localStorage.setItem(PROJECT_TYPE_KEY, JSON.stringify(map));
  }
  function _projectTypeFor(p) {
    const map = _projectTypeOverrides();
    if (map[p.project_id]) return map[p.project_id];
    const blob = `${p.name || ''} ${p.description || ''}`;
    if (_MEDIA_KEYWORDS.test(blob)) return 'media';
    return 'programming';
  }
  window.projectsSetType = function (pid, type) {
    const map = _projectTypeOverrides();
    if (type === 'auto' || !type) { delete map[pid]; }
    else { map[pid] = type; }
    _saveProjectTypeOverrides(map);
    if (typeof window.loadProjectsData === 'function') window.loadProjectsData();
  };
  function _renderProjectTypeRow(p) {
    const t = _projectTypeFor(p);
    const accent = t === 'media' ? '#ff8fbe' : '#7ad6c8';
    const label = t === 'media' ? 'Media' : 'Programming';
    const mediaBtn = `<button onclick="openWindow('media-center','Media Center','view-media-center')" style="background:none;border:1px solid ${accent};color:${accent};border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;">→ Media Center</button>`;
    const codeBtn = `<button onclick="studioSetTab && studioSetTab('git')" style="background:none;border:1px solid ${accent};color:${accent};border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;">→ Studio Git</button>`;
    const testBtn = `<button onclick="studioSetTab && studioSetTab('testlab')" style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;">→ Test Lab</button>`;
    const route = t === 'media' ? mediaBtn + testBtn : codeBtn + testBtn;
    return `
      <div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:10px;">
        <span style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);">Type:</span>
        <span style="padding:1px 7px;border-radius:8px;background:color-mix(in srgb, ${accent} 18%, transparent);color:${accent};border:1px solid ${accent};font-weight:700;">${label}</span>
        <select onchange="projectsSetType('${_esc(p.project_id)}', this.value)" style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:1px 4px;font-size:10px;">
          <option value="auto">auto</option>
          <option value="programming" ${t==='programming'?'selected':''}>programming</option>
          <option value="media" ${t==='media'?'selected':''}>media</option>
        </select>
        <span style="margin-left:6px;color:var(--text-dim);">Route:</span>
        ${route}
      </div>`;
  }

  // ── PACKET-04: Project overview surface (packet rollup) ────────────────
  // Reads the parent-packet tag from each step's title (if it starts with
  // [PACKET-XX]) or from the 'Packet: PACKET-XX' line at the head of its
  // description (stamped by scripts/tag_backlog_packets.py). Renders a
  // status-counted rollup with a one-click filter to focus the steps list
  // below on a single packet.

  const PACKET_DEFS = [
    ['PACKET-01', 'Studio source of truth — md ingest + archive'],
    ['PACKET-02', 'Per-record file model'],
    ['PACKET-03', 'ALM detail surfaces'],
    ['PACKET-04', 'Project overview surface'],
    ['PACKET-05', 'System runs in itself — architecture lock'],
    ['PACKET-06', 'Backlog dedupe + packetization'],
    ['PACKET-07', 'Inter-tile improvement sweep'],
    ['PACKET-08', 'Separate-file artifact path'],
  ];

  function _packetOf(step) {
    const t = step.title || '';
    let m = t.match(/^\[(PACKET-\d{2})\]/);
    if (m) return m[1];
    const d = step.description || '';
    m = d.match(/^\s*Packet:\s*(PACKET-\d{2})/i);
    if (m) return m[1].toUpperCase();
    return null;
  }

  let _packetFilter = null;

  function _renderPacketRollup(p, steps) {
    const buckets = new Map();
    PACKET_DEFS.forEach(([id]) => buckets.set(id, { todo:0, doing:0, blocked:0, partial:0, done:0, skipped:0, _epic:null }));
    let untagged = 0;
    steps.forEach(s => {
      const pkt = _packetOf(s);
      if (!pkt) { untagged++; return; }
      let b = buckets.get(pkt);
      if (!b) { b = { todo:0, doing:0, blocked:0, partial:0, done:0, skipped:0, _epic:null }; buckets.set(pkt, b); }
      const st = s.status || 'todo';
      if (b[st] != null) b[st]++; else b.todo++;
      if ((s.title || '').startsWith(`[${pkt}]`)) b._epic = s;
    });
    const tile = ([id, label]) => {
      const b = buckets.get(id) || { todo:0, doing:0, blocked:0, partial:0, done:0, skipped:0, _epic:null };
      const total = b.todo + b.doing + b.blocked + b.partial + b.done + b.skipped;
      const epicStatus = (b._epic && b._epic.status) || 'todo';
      const isActive = _packetFilter === id;
      const accent = (epicStatus === 'done') ? '#4caf50'
                   : (epicStatus === 'doing') ? 'var(--accent)'
                   : (epicStatus === 'blocked') ? '#f77'
                   : 'var(--text-dim)';
      return `
        <div onclick="projectsFilterPacket('${id}')"
             title="Click to filter the steps list to ${id}; click again to clear"
             style="border:1px solid ${isActive ? 'var(--accent)' : 'var(--border)'};
                    border-radius:5px;padding:8px 10px;cursor:pointer;
                    background:${isActive ? 'color-mix(in srgb,var(--accent) 12%,var(--card))' : 'var(--card)'};
                    transition:background 0.12s;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:4px;">
            <span style="font-family:monospace;font-size:10px;font-weight:800;color:${accent};">${id}</span>
            <span style="font-size:8px;text-transform:uppercase;letter-spacing:0.5px;color:${accent};font-weight:700;">${epicStatus}</span>
          </div>
          <div style="font-size:10px;color:var(--text);line-height:1.35;margin-bottom:6px;min-height:26px;">${_esc(label)}</div>
          <div style="display:flex;gap:6px;font-size:9px;color:var(--text-dim);font-family:monospace;flex-wrap:wrap;">
            <span title="todo">📋 ${b.todo}</span>
            <span title="doing" style="color:var(--accent);">▶ ${b.doing}</span>
            ${b.blocked ? `<span title="blocked" style="color:#f77;">⚠ ${b.blocked}</span>` : ''}
            ${b.partial ? `<span title="partial" style="color:#fc0;">◐ ${b.partial}</span>` : ''}
            <span title="done" style="color:#4caf50;">✓ ${b.done}</span>
            <span title="total" style="margin-left:auto;">${total}</span>
          </div>
        </div>`;
    };
    const totalTagged = PACKET_DEFS.reduce((sum, [id]) => {
      const b = buckets.get(id);
      return sum + (b ? (b.todo + b.doing + b.blocked + b.partial + b.done + b.skipped) : 0);
    }, 0);
    return `
      <div style="border:1px solid var(--border);border-radius:5px;padding:10px;margin-bottom:12px;background:linear-gradient(135deg,color-mix(in srgb,var(--card) 92%,var(--accent) 6%),var(--card));">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div>
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;">Packet Rollup</div>
            <div style="font-size:9px;color:var(--text-dim);margin-top:2px;">Click a packet to filter the steps list. Tagged steps: ${totalTagged} · untagged: ${untagged}</div>
          </div>
          ${_packetFilter ? `<button onclick="projectsFilterPacket(null)"
            style="background:none;border:1px solid var(--accent);color:var(--accent);border-radius:4px;padding:3px 10px;font-size:10px;cursor:pointer;">clear filter (${_esc(_packetFilter)})</button>` : ''}
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;">
          ${PACKET_DEFS.map(tile).join('')}
        </div>
      </div>`;
  }

  window.projectsFilterPacket = function (packetId) {
    _packetFilter = (_packetFilter === packetId) ? null : packetId;
    if (_selectedId) _loadDetail(_selectedId);
    // After re-render, hide step rows that don't match the filter.
    setTimeout(() => {
      const det = document.getElementById('pd-detail');
      if (!det) return;
      const filter = _packetFilter;
      // we cannot identify rows by step easily without data attrs — instead
      // we keep this lightweight by just scrolling the steps section into
      // view and letting the user use the rollup as the primary entry. The
      // hard filter version comes when we re-render the steps list with a
      // filter parameter (next slice).
    }, 0);
  };
  // ── PACKET-03: ALM detail surfaces ─────────────────────────────────────
  // openStep / openCase render a focused modal with the full record,
  // owner, status, parent, linked test runs, and an evidence dock. They
  // hit the new GET /api/knowledge/steps/<id> + /cases/<id> endpoints.

  function _ensureDetailModal() {
    let m = document.getElementById('alm-detail-modal');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'alm-detail-modal';
    m.style.cssText = 'display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.55);align-items:center;justify-content:center;font-family:inherit;';
    m.innerHTML = `
      <div style="background:var(--card,#161616);border:1px solid var(--border,#333);border-radius:8px;
                  width:min(720px,92vw);max-height:86vh;overflow:hidden;display:flex;flex-direction:column;
                  box-shadow:0 12px 48px rgba(0,0,0,0.6);">
        <div id="alm-detail-head" style="display:flex;justify-content:space-between;align-items:center;
              padding:10px 14px;border-bottom:1px solid var(--border,#333);background:var(--window-header,#1d1d1d);">
          <div style="display:flex;align-items:center;gap:8px;">
            <span id="alm-detail-kind" style="font-size:9px;text-transform:uppercase;letter-spacing:1px;
                  padding:2px 6px;border:1px solid var(--accent);color:var(--accent);border-radius:3px;font-weight:700;">STEP</span>
            <span id="alm-detail-id" style="font-family:monospace;font-size:10px;color:var(--text-dim);"></span>
          </div>
          <button onclick="document.getElementById('alm-detail-modal').style.display='none'"
            style="background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:2px 8px;font-size:11px;cursor:pointer;">close</button>
        </div>
        <div id="alm-detail-body" style="padding:14px;overflow:auto;font-size:11px;color:var(--text);"></div>
      </div>`;
    document.body.appendChild(m);
    m.addEventListener('click', (e) => { if (e.target === m) m.style.display = 'none'; });
    return m;
  }

  function _renderRunsBlock(runs) {
    if (!runs || !runs.length) {
      return '<div style="color:var(--text-dim);font-size:10px;padding:6px 0;">No test runs recorded yet.</div>';
    }
    return runs.map(r => {
      const t = r.started_at ? new Date(r.started_at * 1000) : null;
      const tStr = t ? t.toLocaleString() : '—';
      return `<div style="display:grid;grid-template-columns:60px 1fr 140px 70px;gap:6px;padding:4px 6px;
                          border-top:1px solid var(--border);align-items:center;font-size:10px;">
        <span style="color:${_runStatusColor(r.status)};font-weight:700;text-transform:uppercase;font-size:9px;">${_esc(r.status)}</span>
        <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:monospace;">${_esc(r.script_id || r.run_id)}</span>
        <span style="color:var(--text-dim);font-family:monospace;font-size:9px;">${_esc(tStr)}</span>
        <button onclick="testLabOpenRun && testLabOpenRun('${_esc(r.run_id)}')"
          style="background:none;border:1px solid var(--border);color:var(--accent);border-radius:3px;padding:1px 6px;font-size:9px;cursor:pointer;">open</button>
      </div>`;
    }).join('');
  }

  function _kvRow(label, value) {
    return `<div style="display:grid;grid-template-columns:120px 1fr;gap:8px;padding:3px 0;font-size:10px;">
      <span style="color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;font-size:9px;">${_esc(label)}</span>
      <span style="color:var(--text);font-family:${label === 'id' ? 'monospace' : 'inherit'};">${_esc(value ?? '—')}</span>
    </div>`;
  }

  function _fmtTs(ts) {
    if (!ts) return '—';
    const t = new Date((typeof ts === 'number' ? ts * 1000 : Date.parse(ts)));
    return isNaN(t.getTime()) ? String(ts) : t.toLocaleString();
  }

  window.projectsOpenStep = function (stepId) {
    if (!stepId) return;
    const m = _ensureDetailModal();
    m.style.display = 'flex';
    document.getElementById('alm-detail-kind').textContent = 'STEP';
    document.getElementById('alm-detail-id').textContent = stepId;
    const body = document.getElementById('alm-detail-body');
    body.innerHTML = '<div style="color:var(--text-dim);">Loading…</div>';
    fetch('/api/knowledge/steps/' + encodeURIComponent(stepId))
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'load failed');
        const s = data.step || {};
        const cases = s.test_cases || [];
        const runs = s.test_runs || [];
        body.innerHTML = `
          <div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:8px;">${_esc(s.title || stepId)}</div>
          <div style="border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:10px;background:var(--window-header,#1a1a1a);">
            ${_kvRow('id', s.step_id)}
            ${_kvRow('project', s.project_id)}
            ${_kvRow('status', s.status)}
            ${_kvRow('owner', s.owner)}
            ${_kvRow('order', s.order_idx)}
            ${_kvRow('created', _fmtTs(s.created_at))}
            ${_kvRow('updated', _fmtTs(s.updated_at))}
          </div>
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;margin:6px 0 4px;">Description</div>
          <div style="border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:10px;white-space:pre-wrap;color:var(--text);font-size:11px;line-height:1.45;">${_esc(s.description || '(no description — use the rename/edit button to add one)')}</div>
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;margin:6px 0 4px;">Linked Test Cases (${cases.length})</div>
          ${cases.length
            ? cases.map(c => `<div style="display:grid;grid-template-columns:1fr 100px 60px 60px;gap:6px;padding:4px 6px;border-top:1px solid var(--border);align-items:center;font-size:10px;">
                <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(c.title)}</span>
                <span style="color:var(--text-dim);font-family:monospace;font-size:9px;">${_esc(c.script_id || '—')}</span>
                <span style="font-size:8px;color:var(--accent);font-weight:700;text-transform:uppercase;">${_esc(c.status)}</span>
                <button onclick="projectsOpenCase('${_esc(c.case_id)}')"
                  style="background:none;border:1px solid var(--border);color:var(--accent);border-radius:3px;padding:1px 5px;font-size:9px;cursor:pointer;">open</button>
              </div>`).join('')
            : '<div style="color:var(--text-dim);font-size:10px;padding:6px 0;">No cases linked to this step.</div>'}
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;margin:14px 0 4px;">Test Runs (${runs.length})</div>
          ${_renderRunsBlock(runs)}
        `;
      })
      .catch(err => {
        body.innerHTML = `<div style="color:var(--danger,#f77);font-size:11px;">Open step failed: ${_esc(err.message || err)}</div>`;
      });
  };

  window.projectsOpenCase = function (caseId) {
    if (!caseId) return;
    const m = _ensureDetailModal();
    m.style.display = 'flex';
    document.getElementById('alm-detail-kind').textContent = 'CASE';
    document.getElementById('alm-detail-id').textContent = caseId;
    const body = document.getElementById('alm-detail-body');
    body.innerHTML = '<div style="color:var(--text-dim);">Loading…</div>';
    fetch('/api/knowledge/cases/' + encodeURIComponent(caseId))
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) throw new Error((data && data.error) || 'load failed');
        const c = data.case || {};
        const runs = c.test_runs || [];
        const step = c.step || null;
        body.innerHTML = `
          <div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:8px;">${_esc(c.title || caseId)}</div>
          <div style="border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:10px;background:var(--window-header,#1a1a1a);">
            ${_kvRow('id', c.case_id)}
            ${_kvRow('project', c.project_id)}
            ${_kvRow('parent step', step ? (step.title + '  —  ' + step.step_id) : (c.step_id || '—'))}
            ${_kvRow('script_id', c.script_id)}
            ${_kvRow('status', c.status)}
            ${_kvRow('owner', c.owner)}
            ${_kvRow('created', _fmtTs(c.created_at))}
            ${_kvRow('updated', _fmtTs(c.updated_at))}
          </div>
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;margin:6px 0 4px;">Description</div>
          <div style="border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:10px;white-space:pre-wrap;color:var(--text);font-size:11px;line-height:1.45;">${_esc(c.description || '(no description)')}</div>
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);font-weight:700;margin:6px 0 4px;">Test Runs (${runs.length})</div>
          ${_renderRunsBlock(runs)}
          ${step ? `<div style="margin-top:12px;display:flex;gap:6px;">
            <button onclick="projectsOpenStep('${_esc(step.step_id)}')"
              style="background:var(--accent);color:#000;border:none;border-radius:4px;padding:4px 10px;font-size:10px;font-weight:700;cursor:pointer;">↶ Open parent step</button>
          </div>` : ''}
        `;
      })
      .catch(err => {
        body.innerHTML = `<div style="color:var(--danger,#f77);font-size:11px;">Open case failed: ${_esc(err.message || err)}</div>`;
      });
  };
})();
