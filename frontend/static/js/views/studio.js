// Studio view — proposals, pipeline, agent details, custom cards
// Extracted from terminal_base.html
//
// NOTE (2026-04-23): earlier versions of loadStudioData() rewrote the entire
// Studio window header via `parent.innerHTML = headerHTML + content.outerHTML`.
// That pattern destroyed the sibling Git / Test Lab / Projects panels AND
// replaced the 6-tab header with a stale 3-tab version — causing Test Lab /
// Git / Projects tabs to disappear as soon as Studio was opened. The template
// in terminal_base.html already has the correct header + all three panels,
// so loadStudioData() now just runs the initial tab switch and leaves the
// DOM alone.

function loadStudioData(win) {
  // Ensure the global handler is bound (template calls it from onclick).
  window.createNewProposalFromStudio = createNewProposalFromStudio;
  // Slice 5f: remember last-used tab across sessions instead of always
  // landing on 'projects'. Falls back to 'projects' on first ever open.
  if (!window._studioTab) {
    try { window._studioTab = localStorage.getItem('studio_last_tab') || 'projects'; }
    catch (_) { window._studioTab = 'projects'; }
  }
  studioSetTab(window._studioTab);
}

// Handler for New Proposal button in Studio header
function createNewProposalFromStudio() {
  const title = prompt('New proposal title:');
  if (!title || !title.trim()) return;

  const description = prompt('Description (optional):', '');

  fetch('/api/queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: title.trim(),
      description: (description || '').trim(),
      agent: 'ghost',
      source_type: 'studio'
    })
  })
  .then(r => r.json())
  .then(data => {
    if (data.ok) {
      showToast('Proposal created — check Pending tab', 'success');
      const container = document.getElementById('studio-content');
      if (container) loadProposals(container, window._studioTab || 'pending');
    } else {
      showToast(data.error || 'Failed to create proposal', 'error');
    }
  })
  .catch(e => showToast('Error: ' + e.message, 'error'));
}

// ── Studio status palette (shared) ──────────────────────────────────────────
const _PROPOSAL_STATUS = {
  pending:     { color: '#ffa500', bg: '#ffa50022', border: '#ffa50044', label: 'Pending',     step: 0 },
  approved:    { color: '#4caf50', bg: '#4caf5020', border: '#4caf5060', label: 'Approved',    step: 1 },
  in_progress: { color: '#29b6f6', bg: '#29b6f620', border: '#29b6f660', label: 'In Progress', step: 2 },
  done:        { color: '#ab47bc', bg: '#ab47bc20', border: '#ab47bc60', label: 'Done',        step: 3 },
  uat:         { color: '#fbc02d', bg: '#fbc02d20', border: '#fbc02d60', label: 'UAT',         step: 4 },
  executed:    { color: '#2196f3', bg: '#2196f320', border: '#2196f360', label: 'Executed',    step: 5 },
  closed:      { color: '#78909c', bg: '#78909c20', border: '#78909c60', label: 'Closed',      step: 6 },
  rejected:    { color: '#f44336', bg: '#f4433620', border: '#f4433660', label: 'Rejected',    step: -1 },
};

function studioSetTab(tab) {
  window._studioTab = tab;
  // Slice 5f: persist for next session.
  try { localStorage.setItem('studio_last_tab', tab); } catch (_) { /* private mode */ }
  const isGit = (tab === 'git');
  const isTestLab = (tab === 'testlab');
  const isProjects = (tab === 'projects');
  const isMedia = (tab === 'media');
  const isRecords = (tab === 'records');
  const isAppCenter = (tab === 'appcenter');

  // Style proposal tab buttons
  ['pending','in_progress','all','projects','media','git','appcenter','testlab','records'].forEach(t => {
    const btn = document.getElementById('studio-tab-' + t);
    if (!btn) return;
    const on = tab === t;
    // Test Lab tab gets a distinct "info-tinted" identity so it's visually
    // discoverable among the row of proposal tabs (Seven reported missing it).
    if (t === 'media') {
      btn.style.cssText = btn.style.cssText.replace(/background[^;]+;|color[^;]+;|border-color[^;]+;|box-shadow[^;]+;/g,'') +
        (on ? 'background:color-mix(in srgb, var(--accent) 88%, black 12%);color:var(--text-on-accent, #fff);border-color:var(--accent);box-shadow:0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent);'
            : 'background:color-mix(in srgb, var(--accent) 10%, transparent);color:var(--accent);border-color:color-mix(in srgb, var(--accent) 35%, var(--border));');
      return;
    }
    if (t === 'projects') {
      btn.style.cssText = btn.style.cssText.replace(/background[^;]+;|color[^;]+;|border-color[^;]+;|box-shadow[^;]+;/g,'') +
        (on ? 'background:var(--accent);color:#000;border-color:var(--accent);box-shadow:0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent),0 0 12px 2px color-mix(in srgb, var(--accent) 55%, transparent);'
            : 'background:color-mix(in srgb, var(--accent) 14%, transparent);color:var(--accent);border-color:color-mix(in srgb, var(--accent) 50%, var(--border));box-shadow:0 0 8px 1px color-mix(in srgb, var(--accent) 35%, transparent);');
      return;
    }
    if (t === 'testlab') {
      btn.style.cssText = btn.style.cssText.replace(/background[^;]+;|color[^;]+;|border-color[^;]+;|box-shadow[^;]+;/g,'') +
        (on ? 'background:var(--info);color:#fff;border-color:var(--info);box-shadow:0 0 0 2px color-mix(in srgb, var(--info) 40%, transparent);'
            : 'background:color-mix(in srgb, var(--info) 18%, transparent);color:var(--info);border-color:var(--info);box-shadow:0 0 0 1px color-mix(in srgb, var(--info) 30%, transparent);');
      return;
    }
    btn.style.cssText = btn.style.cssText.replace(/background[^;]+;|color[^;]+;|border-color[^;]+;/g,'') +
      (on ? 'background:var(--accent);color:#000;border-color:var(--accent);'
          : 'background:transparent;color:var(--text-dim);border-color:var(--border);');
  });

  // Toggle between proposals content, git, test lab, and projects panels
  const container  = document.getElementById('studio-content');
  const gitPanel   = document.getElementById('studio-git-panel');
  const testLabPanel = document.getElementById('studio-testlab-panel');
  const projectsPanel = document.getElementById('studio-projects-panel');
  const mediaPanel = document.getElementById('studio-media-panel');
  const recordsPanel = document.getElementById('studio-records-panel');
  const appCenterPanel = document.getElementById('studio-appcenter-panel');
  if (container)      container.style.display      = (isGit || isTestLab || isProjects || isMedia || isRecords || isAppCenter) ? 'none' : '';
  if (gitPanel)       gitPanel.style.display       = isGit       ? 'flex' : 'none';
  if (testLabPanel)   testLabPanel.style.display   = isTestLab   ? 'flex' : 'none';
  if (projectsPanel)  projectsPanel.style.display  = isProjects  ? 'flex' : 'none';
  if (mediaPanel)     mediaPanel.style.display     = isMedia     ? 'flex' : 'none';
  if (recordsPanel)   recordsPanel.style.display   = isRecords   ? 'flex' : 'none';
  if (appCenterPanel) appCenterPanel.style.display = isAppCenter ? 'flex' : 'none';

  if (isGit) {
    const fakeWin = {
      el: gitPanel,
      id: 'studio-git',
      querySelector: (sel) => gitPanel.querySelector(sel),
    };
    if (typeof loadGitData === 'function') loadGitData(fakeWin);
    if (typeof gitRefreshStatus === 'function') gitRefreshStatus();
  } else if (isTestLab) {
    if (typeof loadStudioTestLabPanel === 'function') loadStudioTestLabPanel();
  } else if (isProjects) {
    if (typeof loadStudioProjectsPanel === 'function') loadStudioProjectsPanel();
  } else if (isMedia) {
    if (typeof loadStudioMediaPanel === 'function') loadStudioMediaPanel();
  } else if (isRecords) {
    if (typeof loadStudioRecordsPanel === 'function') loadStudioRecordsPanel();
  } else if (isAppCenter) {
    if (typeof loadStudioAppCenterPanel === 'function') loadStudioAppCenterPanel();
  } else {
    if (container) loadProposals(container, tab);
  }
}

async function loadStudioAppCenterPanel() {
  const body = document.getElementById('appcenter-body');
  if (!body) return;
  body.innerHTML = '<div style="color:var(--text-dim);font-size:11px;text-align:center;padding:14px;">Loading App Center...</div>';
  try {
    const [projectsResp, registryResp] = await Promise.all([
      fetch('/api/app-center/projects'),
      fetch('/api/app-center/registry')
    ]);
    const projectsData = await projectsResp.json().catch(() => ({}));
    const registryData = await registryResp.json().catch(() => ({}));
    if (!projectsData.ok) throw new Error(projectsData.error || 'App Center projects failed');
    if (!registryData.ok) throw new Error(registryData.error || 'App Center registry failed');
    const projects = projectsData.projects || [];
    const kinds = registryData.kinds || [];
    const frameworks = registryData.frameworks || [];
    const targets = registryData.targets || [];
    body.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:12px;">
        <div style="border:1px solid var(--border);background:var(--card);border-radius:6px;padding:10px;">
          <div style="font-size:11px;font-weight:700;margin-bottom:4px;">Backend app/game build projects</div>
          <div style="font-size:11px;color:var(--text-dim);line-height:1.45;">Not Studio Git. Backend features must be registered as Flask blueprints and exposed through visible UI routes, tabs, or tiles before they are considered usable.</div>
        </div>
        <div style="border:1px solid var(--border);background:var(--card);border-radius:6px;padding:10px;">
          <div style="font-size:11px;font-weight:700;margin-bottom:4px;">Registry</div>
          <div style="font-size:10px;color:var(--text-dim);line-height:1.45;">Kinds: ${_escHtml(kinds.join(', ') || 'none')}</div>
          <div style="font-size:10px;color:var(--text-dim);line-height:1.45;">Frameworks: ${_escHtml(frameworks.slice(0, 16).join(', ') || 'none')}${frameworks.length > 16 ? '...' : ''}</div>
          <div style="font-size:10px;color:var(--text-dim);line-height:1.45;">Targets: ${_escHtml(targets.join(', ') || 'none')}</div>
        </div>
      </div>
      <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin:8px 0;">Projects (${projects.length})</div>
      ${projects.length ? projects.map(p => `
        <div style="border:1px solid var(--border);background:var(--card);border-radius:6px;padding:10px;margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start;flex-wrap:wrap;">
            <div>
              <div style="font-size:12px;font-weight:700;">${_escHtml(p.name || p.project_id || 'Untitled')}</div>
              <div style="font-size:10px;color:var(--text-dim);font-family:monospace;">${_escHtml(p.project_id || '')}</div>
            </div>
            <div style="display:flex;gap:5px;flex-wrap:wrap;">
              <span style="font-size:10px;border:1px solid var(--border);border-radius:999px;padding:2px 8px;color:var(--accent);">${_escHtml(p.kind || 'unknown')}</span>
              <span style="font-size:10px;border:1px solid var(--border);border-radius:999px;padding:2px 8px;color:var(--text-dim);">${_escHtml(p.framework || 'custom')}</span>
              <span style="font-size:10px;border:1px solid var(--border);border-radius:999px;padding:2px 8px;color:var(--text-dim);">${_escHtml(p.status || 'draft')}</span>
            </div>
          </div>
          ${p.studio_project_id ? `<div style="font-size:10px;color:var(--text-dim);margin-top:6px;">Studio link: <code>${_escHtml(p.studio_project_id)}</code></div>` : ''}
        </div>
      `).join('') : '<div style="padding:16px;text-align:center;color:var(--text-dim);font-size:11px;border:1px dashed var(--border);border-radius:6px;">No App Center projects yet.</div>'}
    `;
  } catch (e) {
    body.innerHTML = `<div style="color:#f77;padding:20px;font-size:12px;">App Center failed: ${_escHtml(e.message || e)}</div>`;
  }
}

function loadProposals(container, tab) {
  const mode = tab || window._studioTab || 'pending';
  let url;

  if (mode === 'all') {
    url = '/api/work-proposals?limit=400';  // history gets everything
  } else if (mode === 'in_progress') {
    url = '/api/work-proposals?status=in_progress&status=approved&status=uat&limit=200';
  } else {
    url = '/api/work-proposals?status=pending&status=proposed&limit=200';
  }

  fetch(url)
    .then(r => r.json())
    .then(data => {
      let proposals = data.proposals || [];

      // Strict client-side filtering so tabs stay clean
      if (mode === 'pending') {
        proposals = proposals.filter(p => ['pending', 'proposed'].includes((p.status || '').toLowerCase()));
      } else if (mode === 'in_progress') {
        proposals = proposals.filter(p => ['in_progress', 'approved', 'uat'].includes((p.status || '').toLowerCase()));
      } else if (mode === 'all') {
        // History can include done/executed/rejected
        proposals = proposals.filter(p => !['pending', 'proposed'].includes((p.status || '').toLowerCase()));
      }

      window._proposals = proposals;

      if (!proposals.length) {
        container.innerHTML = `<div style="text-align:center;padding:40px;color:var(--text-dim);">
          <div style="font-size:32px;margin-bottom:12px;">${mode==='all'?'<svg viewBox="0 0 16 16" width="32" height="32" fill="none"><rect x="3" y="2" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>':'<svg viewBox="0 0 16 16" width="32" height="32" fill="none"><rect x="3" y="2" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M6 8h4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>'}</div>
          <div style="font-size:14px;font-weight:600;">No ${mode} proposals</div>
        </div>`;
        return;
      }

      const labels = { pending: 'Pending Review', in_progress: 'In Progress, Approved & UAT', all: 'History' };
      container.innerHTML = `
        <div style="padding:12px 0 8px;font-size:11px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
          ${proposals.length} Proposal${proposals.length !== 1 ? 's' : ''} — ${labels[mode] || mode}
        </div>
        ${proposals.map(p => _proposalCard(p)).join('')}
      `;
    })
    .catch(e => {
      container.innerHTML = `<div style="color:#f77;padding:20px;font-size:12px;">Error: ${e.message}</div>`;
    });
}

function _proposalCard(p) {
  // Treat 'proposed' as 'pending' for UI actions
  let status = (p.status || 'pending').toLowerCase();
  if (status === 'proposed') status = 'pending';
  const m = _PROPOSAL_STATUS[status] || _PROPOSAL_STATUS.pending;
  const pid = p.proposal_id || '';
  const pidJs = _jsStr(pid);
  const title = _escHtml(p.title || pid || 'Untitled');
  const created = (p.created_at || '').slice(0,16);
  const agent = _escHtml(p.agent || '?');
  const description = p.description || '';
  const descriptionPreview = _escHtml(description.slice(0,300));
  const ticketLink = p.ticket_number
    ? `<span style="padding:2px 6px;border-radius:8px;background:#2196f320;color:#2196f3;font-size:10px;border:1px solid #2196f340;cursor:pointer;" onclick='event.stopPropagation();openTicketDetail(${_jsStr(p.ticket_number)})'><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 7h12" stroke="currentColor" stroke-width="1.3"/></svg> ${_escHtml(p.ticket_number)}</span>`
    : '';

  // Stage label
  const stage = p.stage || 3;
  const stageLabel = stage === 1 ? 'PROD' : stage === 2 ? 'UAT' : 'DEV';
  const stageColor = stage === 1 ? '#d32f2f' : stage === 2 ? '#fbc02d' : '#388e3c';

  // Pipeline mini-bar (only for non-rejected)
  const pipelineHtml = status !== 'rejected' ? `
    <div style="display:flex;gap:3px;margin-top:10px;align-items:center;">
      ${['Proposed','Approved','In Progress','Done','UAT','Executed'].map((label, i) => {
        const active = m.step === i;
        const done   = m.step > i;
        return `<div style="flex:1;text-align:center;font-size:9px;padding:3px 0;border-radius:3px;
          background:${done?m.bg:active?m.bg:'transparent'};
          color:${done||active?m.color:'var(--text-dim)'};
          border:1px solid ${done||active?m.border:'var(--border)'};">${done?'✓ ':''}${label}</div>`;
      }).join('<div style="color:var(--text-dim);font-size:9px;">›</div>')}
    </div>
    ${(status === 'done' || status === 'uat') && p.git_branch ? `<div style="margin-top:5px;font-size:9.5px;color:var(--text-dim);display:flex;gap:10px;flex-wrap:wrap;"><span title="Available from this state">Alternates:</span><span style="color:#ff8a8a;">↩ Revert</span>${status==='done'?`<span style="color:#ffa726;">→ UAT</span>`:''}${status==='uat'?`<span style="color:#66bb6a;">→ PROD</span>`:''}</div>` : ''}
    ${status === 'rejected' ? `<div style="margin-top:8px;padding:5px 8px;background:#f4433611;border:1px dashed #f4433655;border-radius:4px;font-size:10px;color:#ff8a8a;">Rejected — re-open from action menu to revisit.</div>` : ''}` : '';

  // Promote button for DEV and UAT (only when status is 'done')
  let promoteBtn = '';
  if (status === 'done' && stage === 3) {
    promoteBtn = `<button onclick='event.stopPropagation();promoteProposal(${pidJs})' style="flex:1;padding:6px;background:#1976d2;border:1px solid #1976d2;border-radius:4px;color:#fff;font-size:11px;font-weight:600;cursor:pointer;">Promote to UAT</button>`;
  } else if (status === 'done' && stage === 2) {
    promoteBtn = `<button onclick='event.stopPropagation();promoteProposal(${pidJs})' style="flex:1;padding:6px;background:#d32f2f;border:1px solid #d32f2f;border-radius:4px;color:#fff;font-size:11px;font-weight:600;cursor:pointer;">Promote to PROD</button>`;
  }

  // Developer agent fast-path: show Self-Approve+Start if owner
  let devAutoBtn = '';
  if (status === 'pending' && window._effectiveUser && agent.toLowerCase() === window._effectiveUser.toLowerCase() && window._ghostAgentNames && window._ghostAgentNames.includes(window._effectiveUser)) {
    devAutoBtn = `<button onclick='event.stopPropagation();selfApproveAndStart(${pidJs}, "${agent}")' style="flex:1;padding:6px;background:#1976d2;border:1px solid #1976d2;border-radius:4px;color:#fff;font-size:11px;font-weight:600;cursor:pointer;">Self-Approve + Start</button>`;
  }
  const actionBtns = status === 'pending' ? `
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"approved")'
        style="flex:1;padding:6px;background:#4caf5020;border:1px solid #4caf5060;border-radius:4px;color:#4caf50;font-size:11px;font-weight:600;cursor:pointer;">✓ Approve</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"rejected")'
        style="flex:1;padding:6px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;font-weight:600;cursor:pointer;">✗ Reject</button>
      ${devAutoBtn}
    </div>` :
  status === 'approved' ? `
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"in_progress")'
        style="flex:1;padding:6px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:11px;font-weight:600;cursor:pointer;">▶ Start</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"rejected")'
        style="flex:1;padding:6px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;font-weight:600;cursor:pointer;">✗ Reject</button>
      ${promoteBtn}
    </div>` :
  status === 'in_progress' ? `
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"done")'
        style="flex:1;padding:6px;background:#ab47bc20;border:1px solid #ab47bc60;border-radius:4px;color:#ab47bc;font-size:11px;font-weight:600;cursor:pointer;">✓ Mark Done</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"rejected")'
        style="flex:1;padding:6px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;font-weight:600;cursor:pointer;">✗ Reject</button>
      ${promoteBtn}
    </div>` :
  status === 'done' ? `
    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
      <button onclick='event.stopPropagation();viewProposalDiff(${pidJs})'
        style="flex:1;min-width:80px;padding:6px;background:#1565c020;border:1px solid #1565c060;border-radius:4px;color:#42a5f5;font-size:11px;font-weight:600;cursor:pointer;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><circle cx="7" cy="7" r="4.5" stroke="currentColor" stroke-width="1.3"/><path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Review Diff</button>
      ${p.git_branch ? `
        <button onclick='event.stopPropagation();approveToUat(${pidJs})'
          style="flex:1;min-width:80px;padding:6px;background:#f57f1720;border:1px solid #f57f1760;border-radius:4px;color:#ffa726;font-size:11px;font-weight:600;cursor:pointer;">→ Approve to UAT</button>
        <button onclick='event.stopPropagation();revertProposal(${pidJs})'
          style="flex:1;min-width:80px;padding:6px;background:#c62828;border:1px solid #c62828;border-radius:4px;color:#fff;font-size:11px;font-weight:600;cursor:pointer;">✗ Revert</button>
      ` : `
        <button onclick='event.stopPropagation();moveProposal(${pidJs},"closed")'
          style="flex:1;padding:6px;background:#4caf5020;border:1px solid #4caf5060;border-radius:4px;color:#4caf50;font-size:11px;font-weight:600;cursor:pointer;">✓ Close</button>
        <button onclick='event.stopPropagation();moveProposal(${pidJs},"rejected")'
          style="flex:1;padding:6px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;font-weight:600;cursor:pointer;">✗ Reject</button>
      `}
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"in_progress")'
        style="flex:1;padding:6px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:11px;font-weight:600;cursor:pointer;">↩ Reopen</button>
    </div>` :
  status === 'uat' ? `
    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
      <button onclick='event.stopPropagation();promoteToProd(${pidJs})'
        style="flex:1;min-width:80px;padding:6px;background:#2e7d32;border:1px solid #388e3c;border-radius:4px;color:#fff;font-size:11px;font-weight:600;cursor:pointer;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M8 13V3m0 0l3.5 3.5M8 3L4.5 6.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Promote to PROD</button>
      <button onclick='event.stopPropagation();revertProposal(${pidJs})'
        style="flex:1;min-width:80px;padding:6px;background:#c62828;border:1px solid #c62828;border-radius:4px;color:#fff;font-size:11px;font-weight:600;cursor:pointer;">✗ Revert</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"in_progress")'
        style="flex:1;padding:6px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:11px;font-weight:600;cursor:pointer;">↩ Reopen</button>
    </div>` : '';
  const deleteBtn = `
    <button data-proposal-id="${pid}"
            class="delete-btn"
            onclick="event.stopPropagation();deleteProposalSafe('${pid}')"
            style="margin-left:6px;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;background:#f4433620;border:1px solid #f4433660;border-radius:6px;color:#f44336;font-size:13px;font-weight:700;cursor:pointer;flex:0 0 auto;"><svg viewBox="0 0 16 16" width="13" height="13" fill="none"><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M3 4h10M4.5 4l.5 9a1 1 0 001 1h4a1 1 0 001-1l.5-9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`;

  return `<div data-proposal-id="${pid}" style="background:var(--card);border:1px solid var(--border);border-left:3px solid ${m.color};border-radius:6px;padding:14px;margin-bottom:10px;opacity:${status==='rejected'?'0.6':'1'};cursor:pointer;" onclick='openProposalDetail(${pidJs})'>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
      <div style="flex:1;">
        <div style="font-weight:700;font-size:13px;margin-bottom:4px;">${title}</div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
          <span style="font-size:10px;color:var(--text-dim);">By ${agent} · ${created}</span>
          ${ticketLink}
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex:0 0 auto;">
        <span style="padding:2px 8px;border-radius:10px;background:${stageColor};color:#fff;font-size:10px;font-weight:700;white-space:nowrap;border:1px solid ${stageColor};">${stageLabel}</span>
        <span style="padding:2px 8px;border-radius:10px;background:${m.bg};color:${m.color};font-size:10px;font-weight:700;white-space:nowrap;border:1px solid ${m.border};">${m.label}</span>
        ${deleteBtn}
      </div>
    </div>
    ${description ? `<div style="margin-top:8px;font-size:11px;color:var(--text-dim);white-space:pre-wrap;max-height:60px;overflow:hidden;line-height:1.5;font-family:monospace;">${descriptionPreview}${description.length>300?'…':''}</div>` : ''}
    ${pipelineHtml}
    ${actionBtns}
  </div>`;
}

function promoteProposal(proposalId) {
  if (!proposalId) return;
  if (!confirm('Mark this proposal as executed (promoted)?')) return;
  moveProposal(proposalId, 'executed');
}

// Self-Approve + Start handler for developer agents (uses agent-advance API)
async function selfApproveAndStart(proposalId, agent) {
  if (!proposalId || !agent) return;
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}/agent-advance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ..._authPayload(), agent: agent, action: 'start' })
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || 'failed');
    showToast('Proposal self-approved and started', 'success');
    const container = document.getElementById('studio-content');
    if (container) loadProposals(container, window._studioTab || 'pending');
  } catch (e) {
    showToast('Self-approve failed: ' + (e.message || e), 'error');
  }
}

async function viewProposalDiff(proposalId) {
  if (!proposalId) return;
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}/diff`);
    const data = await resp.json();
    if (!data.ok) { showToast(data.error || 'Could not fetch diff', 'error'); return; }

    let overlay = document.getElementById('proposal-diff-overlay');
    if (overlay) overlay.remove();
    overlay = document.createElement('div');
    overlay.id = 'proposal-diff-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:#000c;z-index:9999;display:flex;align-items:center;justify-content:center;';
    document.body.appendChild(overlay);

    // Slice 5f: tighten git chips into a single compact pill (icon + branch · commit).
    const _bShort = data.git_branch || '';
    const _cShort = data.git_commit ? String(data.git_commit).slice(0, 8) : '';
    const _gitPill = (_bShort || _cShort)
      ? `<span title="${_escapeHtml(_bShort)}${_cShort?(' @ '+_escapeHtml(_cShort)):''}" style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:10px;background:#2a2a2a;border:1px solid var(--border);font-size:10px;font-family:monospace;color:var(--text-dim);"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="flex:0 0 auto;"><circle cx="4" cy="4" r="1.6" stroke="currentColor" stroke-width="1.2"/><circle cx="12" cy="12" r="1.6" stroke="currentColor" stroke-width="1.2"/><circle cx="4" cy="12" r="1.6" stroke="currentColor" stroke-width="1.2"/><path d="M4 5.6v4.8M5.6 12h4.8M5.2 5.2l5.6 5.6" stroke="currentColor" stroke-width="1.2"/></svg>${_escapeHtml(_bShort || '(detached)')}${_cShort?` <span style="opacity:.6;">·</span> ${_escapeHtml(_cShort)}`:''}</span>`
      : '';
    const branch = _gitPill;
    const commit = '';
    const envBadge = data.worktrees_active
      ? '<span style="background:#2e7d32;color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">✓ Isolated — DEV only</span>'
      : '<span style="background:#c62828;color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">⚠ No worktrees — changes are live</span>';

    const testHtml = data.test_results
      ? `<div style="border-top:1px solid var(--border);padding:12px 16px;">
           <div style="font-size:11px;font-weight:700;margin-bottom:6px;color:var(--text-dim);">DEV Test Results</div>
           <pre style="font-size:10px;line-height:1.4;margin:0;white-space:pre-wrap;word-break:break-all;color:var(--text);max-height:180px;overflow:auto;">${_escapeHtml(data.test_results)}</pre>
         </div>`
      : '';

    overlay.innerHTML = `
      <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;max-width:960px;width:95%;max-height:90vh;display:flex;flex-direction:column;overflow:hidden;">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <div style="font-weight:700;font-size:14px;">Review — ${_escapeHtml(proposalId)}</div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            ${envBadge}
            <span style="font-size:11px;color:var(--text-dim);">${branch}${branch&&commit?' · ':''}${commit}</span>
            <button onclick="document.getElementById('proposal-diff-overlay').remove()" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:18px;padding:0 4px;">✕</button>
          </div>
        </div>
        <pre style="flex:1;overflow:auto;padding:16px;font-size:11px;line-height:1.5;margin:0;white-space:pre-wrap;word-break:break-all;color:var(--text);background:var(--bg);min-height:200px;">${_escapeHtml(data.diff || '(empty — no file changes recorded)')}</pre>
        ${testHtml}
        <div style="padding:12px 16px;border-top:1px solid var(--border);display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">
          ${data.git_branch ? `<button onclick="approveToUat('${proposalId}')" style="padding:8px 18px;background:#e65100;border:1px solid #e65100;border-radius:6px;color:#fff;font-weight:600;cursor:pointer;">→ Approve to UAT</button>` : ''}
          <button onclick="revertProposal('${proposalId}')" style="padding:8px 18px;background:#c62828;border:1px solid #c62828;border-radius:6px;color:#fff;font-weight:600;cursor:pointer;">✗ Revert</button>
          <button onclick="document.getElementById('proposal-diff-overlay').remove()" style="padding:8px 18px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);cursor:pointer;">Close</button>
        </div>
      </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  } catch (e) {
    showToast('Diff error: ' + e.message, 'error');
  }
}

async function approveToUat(proposalId) {
  if (!proposalId) return;
  if (!confirm(`Approve "${proposalId}" to UAT? Changes will appear on port 5053 for testing. PROD (5050) stays unchanged.`)) return;
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}/approve-to-uat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ..._authPayload(), actor: 'ghost' })
    });
    const data = await resp.json();
    if (!data.ok) { showToast('Approve to UAT failed: ' + (data.error || 'unknown'), 'error'); return; }
    showToast(`Approved to UAT — test on port 5053`, 'success');
    document.getElementById('proposal-diff-overlay')?.remove();
    const container = document.getElementById('studio-content');
    if (container) loadProposals(container, 'active');
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function promoteToProd(proposalId) {
  if (!proposalId) return;
  if (!confirm(`Promote "${proposalId}" to PROD? This merges to master and restarts the live server (port 5050). Are you sure?`)) return;
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}/promote-to-prod`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ..._authPayload(), actor: 'ghost' })
    });
    const data = await resp.json();
    if (!data.ok) { showToast('Promote failed: ' + (data.error || 'unknown'), 'error'); return; }
    showToast(`Promoted to PROD — server restarting`, 'success');
    document.getElementById('proposal-diff-overlay')?.remove();
    const container = document.getElementById('studio-content');
    if (container) loadProposals(container, window._studioTab || 'pending');
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

function _escapeHtml(str) {
  if (typeof window !== 'undefined' && window.SwarmChat && typeof window.SwarmChat.esc === 'function') {
    return window.SwarmChat.esc(str);
  }
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// mergeProposal removed — replaced by approveToUat() → promoteToProd() two-step flow

async function revertProposal(proposalId) {
  if (!proposalId) return;
  if (!confirm(`Revert and reject "${proposalId}"? Agent's file changes will be undone.`)) return;
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}/revert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ..._authPayload(), actor: 'ghost' })
    });
    const data = await resp.json();
    if (!data.ok) { showToast('Revert failed: ' + (data.error || 'unknown'), 'error'); return; }
    showToast(`Reverted and rejected: ${proposalId}`, 'success');
    document.getElementById('proposal-diff-overlay')?.remove();
    const container = document.getElementById('studio-content');
    if (container) loadProposals(container, window._studioTab || 'pending');
  } catch (e) {
    showToast('Revert error: ' + e.message, 'error');
  }
}

function moveProposal(proposalId, newStatus) {
  fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ..._authPayload(), status: newStatus })
  })
    .then(r => r.json())
    .then(data => {
      if (!data.ok) { showToast(data.error || 'failed', 'error'); return; }
      showToast(`Moved to ${newStatus}`, newStatus==='rejected'?'info':'success');
      // close detail modal if open
      const dm = document.getElementById('proposal-detail-modal');
      if (dm?.classList.contains('open')) dm.classList.remove('open');
      // refresh list
      const container = document.getElementById('studio-content');
      if (container) loadProposals(container, window._studioTab || 'pending');
    })
    .catch(e => showToast('Error: ' + e.message, 'error'));
}

async function duckExecuteProposal(proposalId) {
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}/duck-execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ..._authPayload(), actor: 'duck' })
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.message || 'failed');
    showToast('Duck executed the proposal', 'success');
    const dm = document.getElementById('proposal-detail-modal');
    if (dm?.classList.contains('open')) dm.classList.remove('open');
    const container = document.getElementById('studio-content');
    if (container) loadProposals(container, window._studioTab || 'pending');
  } catch (e) {
    showToast('Duck execute failed: ' + (e.message || e), 'error');
  }
}

async function deleteProposal(proposalId, closeModal = false) {
  const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ..._authPayload() })
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${resp.status}`);
  }
  showToast('Proposal deleted', 'success');

  if (closeModal) {
    const dm = document.getElementById('proposal-detail-modal');
    if (dm?.classList.contains('open')) dm.classList.remove('open');
  }

  const container = document.getElementById('studio-content');
  if (container) loadProposals(container, window._studioTab || 'pending');
  if (typeof gitLoadProposals === 'function') gitLoadProposals();
  if (typeof loadAttentionPanel === 'function') loadAttentionPanel();
  return data;
}

async function deleteProposalSafe(proposalId, closeModal = false) {
  if (!proposalId) {
    showToast('No proposal ID', 'error');
    return;
  }

  // Prefer the current click's button (works for both cards and modal header).
  var ev = (typeof window !== 'undefined') ? window.event : null;
  var btn = ev && ev.currentTarget;
  if (!btn) {
    var card = document.querySelector(`[data-proposal-id="${proposalId}"]`);
    btn = card ? card.querySelector('.delete-btn') : null;
  }

  var fire = async function () {
    try {
      const result = await deleteProposal(proposalId, closeModal);
      if (result && result.ok) {
        // Refresh handled inside deleteProposal(); toast already shown there.
        const container = document.getElementById('studio-content');
        if (container) loadProposals(container, window._studioTab || 'pending');
      }
    } catch (e) {
      showToast('Delete failed: ' + (e.message || e), 'error');
    }
  };

  if (btn && window.SwarmChat && typeof window.SwarmChat.armToConfirm === 'function') {
    window.SwarmChat.armToConfirm(btn, fire, { confirmLabel: 'Confirm', timeoutMs: 4000 });
    return;
  }
  // Fallback: native confirm if SwarmChat unavailable.
  if (!confirm(`Delete proposal ${proposalId}? This cannot be undone.`)) return;
  fire();
}

// Keep voteProposal as alias for ALM terminal auto-approve
function voteProposal(proposalId, action, _cardEl) {
  moveProposal(proposalId, action === 'approve' ? 'approved' : 'rejected');
}

function proposalTestArtifacts(p) {
  const text = `${p?.title||''} ${p?.description||''}`.toLowerCase();
  const links = [];
  if (/(test|validate|verification|smoke|dry run|e2e|qa|audit)/.test(text))
    links.push({ file: 'ALM_TEST_SPECIFICATION.md', label: 'ALM Test Spec' });
  if (/(time wizard|timeline|checkpoint|session)/.test(text))
    links.push({ file: 'TIME_WIZARD_TESTS.md', label: 'Vortex Tests' });
  if (/(uat|user acceptance)/.test(text))
    links.push({ file: 'UAT_TEST_SCRIPTS.md', label: 'UAT Scripts' });
  links.push({ file: 'ALM_DRIVER.md', label: 'ALM Driver' });
  links.push({ file: 'CHANGELOG.md', label: 'Change Log' });
  return links;
}

function _proposalPipelineBar(status) {
  const steps = [
    { key: 'pending',     label: 'Proposed' },
    { key: 'approved',    label: 'Approved' },
    { key: 'in_progress', label: 'In Progress' },
    { key: 'done',        label: 'Done' },
    { key: 'uat',         label: 'UAT' },
    { key: 'executed',    label: 'Executed' },
  ];
  const currentStep = (_PROPOSAL_STATUS[status] || {}).step ?? -1;
  return `<div style="display:flex;gap:0;margin-bottom:16px;border:1px solid var(--border);border-radius:6px;overflow:hidden;">
    ${steps.map(s => {
      const sm = _PROPOSAL_STATUS[s.key];
      const isActive  = s.key === status;
      const isComplete = sm.step < currentStep && currentStep >= 0;
      return `<div style="flex:1;text-align:center;padding:8px 4px;font-size:11px;font-weight:${isActive?'700':'500'};
        background:${isActive?sm.bg:isComplete?'#ffffff08':'transparent'};
        color:${isActive?sm.color:isComplete?'var(--text-dim)':'var(--text-dim)'};
        border-right:1px solid var(--border);">
        ${isComplete?'✓ ':''}${s.label}
      </div>`;
    }).join('')}
  </div>`;
}

function openProposalDetail(proposalId) {
  const cached = (window._proposals || []).find(x => (x.proposal_id || '') === proposalId);
  if (!cached) {
    // Cache miss (e.g. called from a different tab's data set) — fetch directly
    fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`)
      .then(r => r.json())
      .then(data => {
        const p = data.proposal || data;
        if (!p || !p.proposal_id) { showToast('Proposal not found', 'error'); return; }
        _openProposalDetailRender(p);
      })
      .catch(e => showToast('Could not load proposal: ' + e.message, 'error'));
    return;
  }
  _openProposalDetailRender(cached);
}

function _openProposalDetailRender(p) {
  const pidJs = _jsStr(p.proposal_id || '');
  const ticketJs = _jsStr(p.ticket_number || '');
  const safeTitle = _escHtml(p.title || p.proposal_id || 'Untitled Proposal');
  const safeDescription = _escHtml(p.description || '');
  const safeAgent = _escHtml(p.agent || '');
  const safeProposalId = _escHtml(p.proposal_id || '—');
  const safeTicketNumber = _escHtml(p.ticket_number || '');

  let modal = document.getElementById('proposal-detail-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'proposal-detail-modal';
    modal.className = 'modal';
    modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = `
      <div class="modal-content" style="width:90%;max-width:820px;max-height:85vh;display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:16px;border-bottom:1px solid var(--border);flex-shrink:0;">
          <h2 id="pdet-title" style="margin:0;font-size:15px;font-family:monospace;"></h2>
          <button onclick="document.getElementById('proposal-detail-modal').classList.remove('open')"
                  style="background:none;border:none;color:var(--text);font-size:18px;cursor:pointer;line-height:1;">&#x2715;</button>
        </div>
        <div id="pdet-body" style="overflow-y:auto;padding:16px;flex:1;"></div>
      </div>`;
    document.body.appendChild(modal);
  }

  const status = (p.status || 'pending').toLowerCase();
  const m = _PROPOSAL_STATUS[status] || _PROPOSAL_STATUS.pending;
  const created = (p.created_at || '').slice(0, 16);
  const updated = (p.updated_at || '').slice(0, 16);
  const title = p.title || p.proposal_id || 'Untitled Proposal';
  const artifacts = proposalTestArtifacts(p);
  const duckVerdict = p.duck_verdict || '';
  const duckNote    = p.duck_note    || '';
  const srcConvId   = p.source_conv_id;

  document.getElementById('pdet-title').textContent = title;
  document.getElementById('pdet-body').innerHTML = `
    ${_proposalPipelineBar(status)}

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;">
      <span style="padding:3px 10px;border-radius:12px;background:${m.bg};color:${m.color};font-size:11px;font-weight:700;border:1px solid ${m.border};">${m.label}</span>
      ${p.agent ? `<span style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;">Agent: ${safeAgent}</span>` : ''}
      ${p.ticket_number ? `<span onclick='openTicketDetail(${ticketJs})' style="padding:3px 10px;border-radius:12px;background:#2196f320;color:#2196f3;font-size:11px;cursor:pointer;border:1px solid #2196f340;">Ticket: ${safeTicketNumber}</span>` : ''}
      ${p.queue_id ? `<span style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;">Queue: ${_escHtml(String(p.queue_id))}</span>` : ''}
      ${srcConvId ? `<span onclick='openConversation(${Number(srcConvId)})' style="padding:3px 10px;border-radius:12px;background:#4caf5020;color:#4caf50;font-size:11px;cursor:pointer;border:1px solid #4caf5040;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><path d="M2.5 3h11a1 1 0 011 1v6a1 1 0 01-1 1h-3l-3 2.5V11h-5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> View in Chat</span>` : ''}
      <span onclick='window.openRecord && window.openRecord("proposal", ${pidJs})' title="Open this proposal in Studio Records" style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;cursor:pointer;border:1px solid var(--border);">In Records</span>
      <span onclick='window.revealInFiles && window.revealInFiles("proposal", ${pidJs})' title="Reveal this proposal in the Files tile" style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;cursor:pointer;border:1px solid var(--border);">In Files</span>
    </div>

    ${duckVerdict ? `<div style="margin-bottom:14px;padding:10px 14px;border-radius:6px;background:${duckVerdict==='approved'?'#4caf5015':'#f4433615'};border:1px solid ${duckVerdict==='approved'?'#4caf5040':'#f4433640'};">
      <div style="font-size:11px;font-weight:700;color:${duckVerdict==='approved'?'#4caf50':'#f44336'};text-transform:uppercase;margin-bottom:4px;">
        ${duckVerdict==='approved'?'<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M3.5 8.5l3 3 6-7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>':'<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'} Duck Review — ${duckVerdict.toUpperCase()}
      </div>
      ${duckNote ? `<div style="font-size:12px;color:var(--text);line-height:1.5;">${_escHtml(duckNote)}</div>` : ''}
    </div>` : ''}

    <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:16px;">
      <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;width:130px;">Proposal ID</td><td style="font-family:monospace;font-size:11px;">${safeProposalId}</td></tr>
      <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Created</td><td>${_escHtml(created||'—')}</td></tr>
      ${updated && updated !== created ? `<tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Updated</td><td>${_escHtml(updated)}</td></tr>` : ''}
    </table>

    <div style="margin-bottom:14px;" id="pdet-edit-block">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;">Description</div>
        <button onclick="_pdetToggleEdit(${pidJs})" id="pdet-edit-btn"
          style="padding:2px 10px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);cursor:pointer;">Edit</button>
      </div>
      <div id="pdet-desc-view" style="background:var(--card);padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap;max-height:180px;overflow-y:auto;font-family:monospace;line-height:1.5;">${safeDescription || '<span style="color:var(--text-dim);font-style:italic;">No description</span>'}</div>
      <div id="pdet-edit-form" style="display:none;">
        <div style="font-size:11px;color:var(--text-dim);margin:6px 0 2px;">Title</div>
        <input id="pdet-edit-title" value="${_escAttr(p.title||'')}"
          style="width:100%;box-sizing:border-box;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:13px;margin-bottom:8px;">
        <div style="font-size:11px;color:var(--text-dim);margin-bottom:2px;">Description</div>
        <textarea id="pdet-edit-desc" rows="5"
          style="width:100%;box-sizing:border-box;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;font-family:monospace;resize:vertical;">${_escHtml(p.description||'')}</textarea>
        <div style="font-size:11px;color:var(--text-dim);margin:8px 0 2px;">Notes</div>
        <textarea id="pdet-edit-notes" rows="3"
          style="width:100%;box-sizing:border-box;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;font-family:monospace;resize:vertical;">${_escHtml(p.notes||'')}</textarea>
        <div style="display:flex;gap:8px;margin-top:8px;">
          <button onclick="_pdetSaveEdit(${pidJs})"
            style="padding:6px 14px;background:#4caf5020;border:1px solid #4caf5060;border-radius:4px;color:#4caf50;font-size:12px;cursor:pointer;">Save</button>
          <button onclick="_pdetToggleEdit(${pidJs})"
            style="padding:6px 14px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);font-size:12px;cursor:pointer;">Cancel</button>
        </div>
      </div>
      ${p.notes ? `<div style="margin-top:8px;"><div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:4px;">Notes</div><div style="background:var(--card);padding:10px;border-radius:4px;font-size:12px;white-space:pre-wrap;font-family:monospace;line-height:1.5;" id="pdet-notes-view">${_escHtml(p.notes)}</div></div>` : `<div id="pdet-notes-view"></div>`}
    </div>

    <div style="margin-bottom:14px;" id="pdet-agent-notes-block">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;">Agent Notes</div>
        <button onclick="_pdetAddAgentNote(${pidJs})"
          style="padding:2px 10px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);cursor:pointer;">+ Add Note</button>
      </div>
      <div id="pdet-agent-notes-list" style="display:flex;flex-direction:column;gap:4px;min-height:20px;">
        <span style="font-size:11px;color:var(--text-dim);font-style:italic;">Loading...</span>
      </div>
    </div>

    <div style="margin-bottom:14px;" id="pdet-attachments-block">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;">Attachments</div>
        <label style="padding:2px 10px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);cursor:pointer;">
          + Upload<input type="file" id="pdet-att-input" style="display:none" onchange="_pdetUploadAttachment(${pidJs}, this)">
        </label>
      </div>
      <div id="pdet-att-list" style="display:flex;flex-direction:column;gap:4px;min-height:20px;">
        <span style="font-size:11px;color:var(--text-dim);font-style:italic;">Loading...</span>
      </div>
    </div>

    <div style="margin-bottom:14px;">
      <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Documentation</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;">
        ${artifacts.map(a => `<button onclick="openDocDetail('${a.file}','${a.label}')" style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">${a.label}</button>`).join('')}
      </div>
    </div>

    <div style="padding-top:12px;border-top:1px solid var(--border);">
      <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">Actions</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        ${status==='pending' ? (() => {
          // Detect sudo approval requests — extract token from description
          const isSudo = (p.title || '').startsWith('[sudo]');
          const tokenMatch = isSudo && (p.description || '').match(/Approval token:\s*`?([a-f0-9]{32,})`?/i);
          const sudoToken = tokenMatch ? tokenMatch[1] : null;
          const sudoBtn = (isSudo && sudoToken)
            ? `<button onclick='sudoApproveRun("${sudoToken}", ${pidJs})'
                style="padding:8px 16px;background:#ff980020;border:1px solid #ff980060;border-radius:4px;color:#ff9800;font-size:12px;font-weight:700;cursor:pointer;">&#9654; Approve &amp; Run</button>`
            : '';
          return `${sudoBtn}
          <button onclick='moveProposal(${pidJs},"approved")'
            style="padding:8px 16px;background:#4caf5020;border:1px solid #4caf5060;border-radius:4px;color:#4caf50;font-size:12px;font-weight:600;cursor:pointer;">&#10003; Approve</button>
          <button onclick='moveProposal(${pidJs},"rejected")'
            style="padding:8px 16px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:12px;font-weight:600;cursor:pointer;">&#10007; Reject</button>`;
        })() : ''}
        ${status==='approved' ? `
          <button onclick='moveProposal(${pidJs},"in_progress")'
            style="padding:8px 16px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:12px;font-weight:600;cursor:pointer;">&#9654; Start Work</button>
          <button onclick='moveProposal(${pidJs},"rejected")'
            style="padding:8px 16px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:12px;font-weight:600;cursor:pointer;">&#10007; Reject</button>` : ''}
        ${status==='in_progress' ? `
          <button onclick='moveProposal(${pidJs},"done")'
            style="padding:8px 16px;background:#ab47bc20;border:1px solid #ab47bc60;border-radius:4px;color:#ab47bc;font-size:12px;font-weight:600;cursor:pointer;">&#10003; Mark Done</button>
          <button onclick='moveProposal(${pidJs},"rejected")'
            style="padding:8px 16px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:12px;font-weight:600;cursor:pointer;">&#10007; Reject</button>` : ''}
        ${status==='done' ? `
          <button onclick='moveProposal(${pidJs},"in_progress")'
            style="padding:8px 16px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:12px;font-weight:600;cursor:pointer;">&#x21A9; Reopen</button>` : ''}
        ${status==='uat' ? `
          <button onclick='moveProposal(${pidJs},"executed")'
            style="padding:8px 16px;background:#2196f320;border:1px solid #2196f360;border-radius:4px;color:#2196f3;font-size:12px;font-weight:600;cursor:pointer;">&#10003; Mark Executed</button>
          <button onclick='duckExecuteProposal(${pidJs})'
            style="padding:8px 16px;background:#fbc02d20;border:1px solid #fbc02d60;border-radius:4px;color:#fbc02d;font-size:12px;font-weight:600;cursor:pointer;"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-1px;"><path d="M4 9.5c0 2 1.8 3 4 3s4-1 4-3c0-1.5-1-2.5-3-2.5H8c1 0 2-1 2-2S9 3 8 3C6.5 3 5.5 4 5.5 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M12 7.5l2 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Ask Duck to Execute</button>
          <button onclick='moveProposal(${pidJs},"in_progress")'
            style="padding:8px 16px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:12px;font-weight:600;cursor:pointer;">&#x21A9; Reopen</button>` : ''}
        <button onclick='deleteProposalSafe(${pidJs}, true)'
          title="Delete proposal"
          aria-label="Delete proposal"
          style="width:32px;height:32px;display:inline-flex;align-items:center;justify-content:center;background:#f4433620;border:1px solid #f4433660;border-radius:6px;color:#f44336;font-size:14px;font-weight:700;cursor:pointer;">&#128465;</button>
        <button onclick='pinItemToDeferred(${pidJs}, ${_jsStr(title.slice(0,80))}, "proposal")'
          style="padding:8px 16px;background:transparent;border:1px solid var(--border);border-radius:4px;color:var(--text-dim);font-size:12px;cursor:pointer;">&#128204; Pin to Brief</button>
      </div>
    </div>`;

  modal.classList.add('open');
  // Load attachments and agent notes asynchronously
  _pdetLoadAttachments(p.proposal_id);
  _pdetLoadAgentNotes(p.proposal_id);
  // Seven sees — propose-only insight panel.
  try {
    if (window.SevenPanel) {
      window.SevenPanel.mount(document.getElementById('pdet-body'),
        { kind: 'proposal', id: p.proposal_id });
    }
  } catch (e) { /* noop */ }
}

async function sudoApproveRun(token, proposalId) {
  if (!confirm('Run this shell command now? It will execute immediately on the server.')) return;
  try {
    const r = await fetch(`/api/shell/approve/${token}`, { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      showToast('Command executed successfully', 'success');
      // Mark the proposal as executed
      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'executed' }),
      });
      const dm = document.getElementById('proposal-detail-modal');
      if (dm?.classList.contains('open')) dm.classList.remove('open');
      const container = document.getElementById('studio-content');
      if (container) loadProposals(container, window._studioTab || 'pending');
    } else {
      showToast('Command failed: ' + (d.error || d.output || 'unknown error'), 'error');
    }
  } catch (e) {
    showToast('Approve & Run failed: ' + e.message, 'error');
  }
}

function _escAttr(s) {
  if (typeof window !== 'undefined' && window.SwarmChat && typeof window.SwarmChat.escAttr === 'function') {
    return window.SwarmChat.escAttr(s);
  }
  return String(s || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _pdetToggleEdit(pid) {
  const form = document.getElementById('pdet-edit-form');
  const view = document.getElementById('pdet-desc-view');
  const btn  = document.getElementById('pdet-edit-btn');
  if (!form) return;
  const editing = form.style.display === 'none' || form.style.display === '';
  form.style.display = editing ? 'block' : 'none';
  view.style.display = editing ? 'none' : 'block';
  btn.textContent    = editing ? 'Cancel' : 'Edit';
}

async function _pdetSaveEdit(pid) {
  const title = document.getElementById('pdet-edit-title')?.value?.trim() || '';
  const desc  = document.getElementById('pdet-edit-desc')?.value || '';
  const notes = document.getElementById('pdet-edit-notes')?.value || '';
  const resp = await fetch(`/api/work-proposals/${encodeURIComponent(pid)}/edit`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, description: desc, notes})
  });
  const data = await resp.json();
  if (!data.ok) { showToast('Save failed: ' + (data.error || '?'), 'error'); return; }
  showToast('Proposal saved', 'success');
  // Update cached entry
  const cached = (window._proposals || []).find(x => x.proposal_id === pid);
  if (cached) { cached.title = title; cached.description = desc; cached.notes = notes; }
  // Re-render
  const p = data.proposal;
  document.getElementById('pdet-title').textContent = p.title || pid;
  document.getElementById('pdet-desc-view').innerHTML = _escHtml(p.description || '') || '<span style="color:var(--text-dim);font-style:italic;">No description</span>';
  const notesView = document.getElementById('pdet-notes-view');
  if (notesView) notesView.innerHTML = p.notes ? _escHtml(p.notes) : '';
  _pdetToggleEdit(pid);
}

async function _pdetLoadAttachments(pid) {
  const list = document.getElementById('pdet-att-list');
  if (!list) return;
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(pid)}/attachments`);
    const data = await resp.json();
    const atts = data.attachments || [];
    if (!atts.length) {
      list.innerHTML = '<span style="font-size:11px;color:var(--text-dim);font-style:italic;">No attachments</span>';
      return;
    }
    list.innerHTML = atts.map(a => `
      <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--card);border-radius:4px;border:1px solid var(--border);">
        <span style="font-size:11px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(a.original_name)}</span>
        <span style="font-size:10px;color:var(--text-dim);">${_fmtBytes(a.size_bytes)}</span>
        <a href="/api/work-proposals/${encodeURIComponent(pid)}/attachments/${a.id}" download="${_escAttr(a.original_name)}"
           style="font-size:11px;color:#2196f3;text-decoration:none;">↓</a>
        <button onclick="_pdetDeleteAttachment(${_jsStr(pid)}, ${a.id}, event)"
          style="background:none;border:none;color:#f44336;cursor:pointer;font-size:14px;line-height:1;padding:0;">×</button>
      </div>`).join('');
  } catch(e) {
    list.innerHTML = '<span style="font-size:11px;color:#f44336;">Failed to load</span>';
  }
}

function _fmtBytes(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  return (b/1048576).toFixed(1) + ' MB';
}

async function _pdetUploadAttachment(pid, input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  fd.append('uploaded_by', 'ghost');
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(pid)}/attachments`, {method:'POST', body:fd});
    const data = await resp.json();
    if (!data.ok) { showToast('Upload failed: ' + (data.error || '?'), 'error'); return; }
    showToast('Attached: ' + file.name, 'success');
    _pdetLoadAttachments(pid);
  } catch(e) {
    showToast('Upload error', 'error');
  }
  input.value = '';
}

async function _pdetDeleteAttachment(pid, attId, event) {
  var fire = async function () {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(pid)}/attachments/${attId}`, {method:'DELETE'});
    const data = await resp.json();
    if (!data.ok) { showToast('Delete failed', 'error'); return; }
    _pdetLoadAttachments(pid);
  };
  var btn = event && event.currentTarget;
  if (btn && window.SwarmChat && typeof window.SwarmChat.armToConfirm === 'function') {
    window.SwarmChat.armToConfirm(btn, fire, { confirmLabel: '?', timeoutMs: 4000 });
    return;
  }
  if (!confirm('Remove this attachment?')) return;
  fire();
}

async function _pdetLoadAgentNotes(pid) {
  const list = document.getElementById('pdet-agent-notes-list');
  if (!list) return;
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(pid)}/notes`);
    const data = await resp.json();
    const notes = data.notes || [];
    if (!notes.length) {
      list.innerHTML = '<span style="font-size:11px;color:var(--text-dim);font-style:italic;">No agent notes yet</span>';
      return;
    }
    list.innerHTML = notes.map(n => `
      <div style="background:var(--card);border:1px solid var(--border);border-radius:4px;padding:8px 10px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
          <span style="font-size:10px;font-weight:700;color:var(--text-dim);">${_escHtml(n.author || 'agent')}</span>
          <span style="font-size:10px;color:var(--text-dim);">${_escHtml((n.created_at || '').slice(0,16))}</span>
        </div>
        <div style="font-size:12px;white-space:pre-wrap;line-height:1.4;">${_escHtml(n.content || '')}</div>
      </div>`).join('');
  } catch (e) {
    list.innerHTML = `<span style="font-size:11px;color:#f44;font-style:italic;">Error loading notes</span>`;
  }
}

async function _pdetAddAgentNote(pid) {
  const content = prompt('Add a note to this proposal:');
  if (!content || !content.trim()) return;
  const resp = await fetch(`/api/work-proposals/${encodeURIComponent(pid)}/notes`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({content: content.trim(), author: 'ghost'})
  });
  const data = await resp.json();
  if (!data.ok) { showToast(data.error || 'Failed to add note', 'error'); return; }
  _pdetLoadAgentNotes(pid);
}

function openDocDetail(filename, title) {
  let modal = document.getElementById('doc-detail-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'doc-detail-modal';
    modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = `
      <div class="modal-content" style="width:92%;max-width:900px;max-height:88vh;display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--border);flex-shrink:0;">
          <h3 id="doc-det-title" style="margin:0;font-size:14px;"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M4 2h5l4 4v8H4a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 2v4h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></h3>
          <button onclick="document.getElementById('doc-detail-modal').classList.remove('open')"
                  style="background:none;border:none;color:var(--text);font-size:18px;cursor:pointer;">✕</button>
        </div>
        <div id="doc-det-body" style="overflow-y:auto;padding:20px;flex:1;font-size:12px;line-height:1.7;white-space:pre-wrap;font-family:monospace;"></div>
      </div>`;
    document.body.appendChild(modal);
  }
  document.getElementById('doc-det-title').innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M4 2h5l4 4v8H4a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 2v4h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> ' + _escHtml(title || filename);
  document.getElementById('doc-det-body').innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:30px;">Loading…</div>';
  modal.classList.add('open');

  fetch(`/docs/html/${encodeURIComponent(filename)}`)
    .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.text(); })
    .then(html => { document.getElementById('doc-det-body').style.fontFamily = 'inherit'; document.getElementById('doc-det-body').innerHTML = html; })
    .catch(() => {
      // Fallback: try text/markdown docs endpoint, then KB endpoint
      fetch(`/api/docs/text/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(data => {
          if (!data?.ok) throw new Error('not found');
          document.getElementById('doc-det-body').style.fontFamily = 'monospace';
          document.getElementById('doc-det-body').textContent = data.content || 'Document content not available.';
        })
        .catch(() => fetch(`/api/kb`))
        .then(r => r && r.json ? r.json() : null)
        .then(data => {
          if (!data) return;
          const docs = Array.isArray(data) ? data : (data.docs || []);
          const doc = docs.find(d => d.filename === filename || d.title === title);
          document.getElementById('doc-det-body').style.fontFamily = 'monospace';
          document.getElementById('doc-det-body').textContent = doc?.content || doc?.body || 'Document content not available.';
        })
        .catch(() => { document.getElementById('doc-det-body').textContent = 'Could not load document.'; });
    });
}

function openTicketDetail(ticketNumber) {
  // Create or reuse modal
  let modal = document.getElementById('ticket-detail-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'ticket-detail-modal';
    modal.className = 'modal';
    modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = `
      <div class="modal-content" style="width:90%;max-width:800px;max-height:85vh;display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:16px;border-bottom:1px solid var(--border);flex-shrink:0;">
          <h2 id="tdet-title" style="margin:0;font-size:16px;font-family:monospace;"></h2>
          <button onclick="document.getElementById('ticket-detail-modal').classList.remove('open')"
                  style="background:none;border:none;color:var(--text);font-size:18px;cursor:pointer;line-height:1;">✕</button>
        </div>
        <div id="tdet-body" style="overflow-y:auto;padding:16px;flex:1;"></div>
      </div>`;
    document.body.appendChild(modal);
  }

  document.getElementById('tdet-title').innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 7h12" stroke="currentColor" stroke-width="1.3"/></svg> ' + _escHtml(ticketNumber);
  document.getElementById('tdet-body').innerHTML = '<div style="color:var(--text-dim);padding:20px;text-align:center;">Loading…</div>';
  modal.classList.add('open');

  fetch(`/api/tickets/${ticketNumber}`)
    .then(r => r.json())
    .then(data => {
      // API returns {ticket: {...}, notes: [...], messages: [...], snoozes: [...], proposals: [...]}
      const t = data.ticket || data;
      const notes = data.notes || t.notes || [];
      const linkedProposals = data.proposals || [];
      const stColor = t.status === 'open' ? '#4caf50' : t.status === 'in_progress' ? '#ffa500' : '#888';
      const noteRows = notes.map(n =>
        `<div style="padding:8px 10px;background:var(--bg);border-radius:4px;border-left:2px solid var(--accent);margin-bottom:6px;font-size:12px;">
          <div style="color:var(--text-dim);font-size:10px;margin-bottom:4px;">${_escHtml((n.created_at||'').slice(0,16))} — ${_escHtml(n.author||'system')}</div>
          <div style="white-space:pre-wrap;">${_escHtml(n.content||'')}</div>
        </div>`
      ).join('');

      // Pre-compute JS-safe ticket number for inline button handlers
      const tnJs = JSON.stringify(ticketNumber);
      const questionHintJs = JSON.stringify((t.question||'').slice(0,80));

      document.getElementById('tdet-body').innerHTML = `
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;">
          <span style="padding:3px 10px;border-radius:12px;background:${stColor}22;color:${stColor};font-size:11px;font-weight:700;border:1px solid ${stColor}44;">${_escHtml(t.status||'unknown')}</span>
          <span style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;">Priority: ${_escHtml(String(t.priority||5))}</span>
          ${t.snooze_count ? `<span style="padding:3px 10px;border-radius:12px;background:#ff980022;color:#ff9800;font-size:11px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><path d="M4 5h6L4 11h6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> ${_escHtml(String(t.snooze_count))} snooze</span>` : ''}
          <span onclick='window.openRecord && window.openRecord("ticket", ${tnJs})' title="Open this ticket in Studio Records" style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;cursor:pointer;border:1px solid var(--border);">In Records</span>
          <span onclick='window.revealInFiles && window.revealInFiles("ticket", ${tnJs})' title="Reveal this ticket in the Files tile" style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;cursor:pointer;border:1px solid var(--border);">In Files</span>
        </div>

        <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:16px;">
          <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;width:120px;">From</td><td>${_escHtml(t.sender_email||'—')}</td></tr>
          <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Created</td><td>${_escHtml((t.created_at||'').slice(0,16))}</td></tr>
          ${t.closed_at ? `<tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Closed</td><td>${_escHtml(t.closed_at.slice(0,16))}</td></tr>` : ''}
          ${t.gemma_routing ? `<tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Routing</td><td style="font-size:10px;color:var(--text-dim);">${_escHtml(t.gemma_routing)}</td></tr>` : ''}
        </table>

        ${linkedProposals.length ? `
        <div style="margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Linked Proposals (${linkedProposals.length})</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            ${linkedProposals.map(p => {
              const pc = p.status === 'approved' || p.status === 'done' ? '#4caf50' : p.status === 'pending' ? '#ffa500' : '#888';
              const pJs = JSON.stringify(p.proposal_id);
              return `<span onclick='openProposalDetail(${pJs})' style="padding:3px 10px;border-radius:12px;background:${pc}20;color:${pc};font-size:11px;cursor:pointer;border:1px solid ${pc}40;">${_escHtml(p.proposal_id)} · ${_escHtml(p.status||'')} · ${_escHtml(p.agent||'')}</span>`;
            }).join('')}
          </div>
        </div>` : ''}

        <div style="margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Question</div>
          <div style="background:var(--card);padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap;max-height:200px;overflow-y:auto;">${_escHtml(t.question||'—')}</div>
        </div>

        ${t.duck_result ? `
        <div style="margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Duck Result</div>
          <div style="background:var(--card);padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap;max-height:150px;overflow-y:auto;">${_escHtml(t.duck_result)}</div>
        </div>` : ''}

        ${t.final_answer ? `
        <div style="margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Final Answer</div>
          <div style="background:var(--card);padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap;max-height:250px;overflow-y:auto;">${_escHtml(t.final_answer)}</div>
        </div>` : ''}

        ${noteRows ? `
        <div>
          <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Notes (${notes.length})</div>
          ${noteRows}
        </div>` : ''}

        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px;padding-top:12px;border-top:1px solid var(--border);">
          <button onclick="sendTicketToChat(${tnJs}, ${questionHintJs})"
            style="padding:6px 14px;background:#2196f31a;border:1px solid #2196f344;border-radius:4px;color:#2196f3;font-size:12px;cursor:pointer;font-weight:600;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M2.5 3h11a1 1 0 011 1v6a1 1 0 01-1 1h-3l-3 2.5V11h-5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Send to Chat</button>
          ${t.status !== 'closed'
            ? `<button onclick="closeTicketFromModal(${tnJs})" style="padding:6px 14px;background:#f443361a;border:1px solid #f4433644;border-radius:4px;color:#f44336;font-size:12px;cursor:pointer;">Close Ticket</button>`
            : `<button onclick="reopenTicketFromModal(${tnJs})" style="padding:6px 14px;background:#4caf501a;border:1px solid #4caf5044;border-radius:4px;color:#4caf50;font-size:12px;cursor:pointer;">Reopen</button>`}
          <button onclick="createProposalFromTicket(${tnJs}, ${questionHintJs})"
            style="padding:6px 14px;background:#4caf501a;border:1px solid #4caf5044;border-radius:4px;color:#4caf50;font-size:12px;cursor:pointer;">+ Proposal</button>
          <button onclick="pinItemToDeferred(${tnJs}, ${questionHintJs}, 'ticket')"
            style="padding:6px 14px;background:transparent;border:1px solid var(--border);border-radius:4px;color:var(--text-dim);font-size:12px;cursor:pointer;">&#128204; Pin</button>
          <button onclick="deleteTicketWithConfirm(${tnJs}, this)"
            style="padding:6px 14px;background:#f443361a;border:1px solid #f4433644;border-radius:4px;color:#f44336;font-size:12px;cursor:pointer;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M3 4h10M4.5 4l.5 9a1 1 0 001 1h4a1 1 0 001-1l.5-9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Delete</button>
          <button onclick="document.getElementById('ticket-detail-modal').classList.remove('open')"
                  style="padding:6px 14px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;cursor:pointer;">Close</button>
        </div>`;
      // Seven sees — propose-only insight panel.
      try {
        if (window.SevenPanel) {
          window.SevenPanel.mount(document.getElementById('tdet-body'),
            { kind: 'ticket', id: ticketNumber });
        }
      } catch (e) { /* noop */ }
    })
    .catch(e => {
      document.getElementById('tdet-body').innerHTML = `<div style="color:#f77;padding:20px;">Error loading ticket: ${e.message}</div>`;
    });
}

function closeTicketFromModal(ticketNumber) {
  if (!confirm(`Close ${ticketNumber}?`)) return;
  fetch(`/api/tickets/${ticketNumber}/close`, { method: 'POST' })
    .then(r => r.json())
    .then(() => { openTicketDetail(ticketNumber); showToast(`${ticketNumber} closed`, 'success'); })
    .catch(e => showToast('Error: ' + e.message, 'error'));
}

function reopenTicketFromModal(ticketNumber) {
  fetch(`/api/tickets/${ticketNumber}/reopen`, { method: 'POST' })
    .then(r => r.json())
    .then(() => { openTicketDetail(ticketNumber); showToast(`${ticketNumber} reopened`, 'success'); })
    .catch(e => showToast('Error: ' + e.message, 'error'));
}

function createProposalFromTicket(ticketNumber, questionHint) {
  // Prompt Ghost to fill in a title and description, then POST to /api/queue
  const title = prompt(`Proposal title for ${ticketNumber}:`, questionHint ? `Fix: ${questionHint}` : '');
  if (!title || !title.trim()) return;
  const description = prompt('Brief description of the change:', '');
  if (description === null) return;  // cancelled

  fetch('/api/queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: description || title,
      sender_email: 'ghost@swarm',
      source_type: 'dashboard',
      tags: `ticket:${ticketNumber}`,
      title,
      description: description || title,
    })
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) { showToast(data.error, 'error'); return; }
      // Link proposal back to ticket
      const propId = data.proposal_id || (data.work_proposal && data.work_proposal.proposal_id);
      if (propId) {
        fetch(`/api/work-proposals/${encodeURIComponent(propId)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'pending', ticket_number: ticketNumber })
        });
      }
      showToast('Proposal created — review it in Studio', 'success');
      document.getElementById('ticket-detail-modal')?.classList.remove('open');
    })
    .catch(e => showToast('Error: ' + e.message, 'error'));
}

function openStudioSection(section) {
  const studioContent = document.getElementById('studio-content');
  
  if (section === 'agents') {
    studioContent.innerHTML = '<div style="padding: 16px; color: var(--text-dim); font-size: 12px;">Loading agents...</div>';
    
    fetch('/api/agents')
      .then(r => r.json())
      .then(data => {
        const agents = Array.isArray(data) ? data : (data.agents || []);
        
        if (agents.length === 0) {
          studioContent.innerHTML = '<div style="padding: 16px; color: var(--text-dim);">No agents online</div>';
          return;
        }
        
        let html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; padding: 12px;">';
        
        agents.forEach(agent => {
          const agentKey = agent.name.toLowerCase();
          const _studioAgentSvg = {
            'gemma':     '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.3"/><path d="M8 5v3l2 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
            'llama':     '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M5 13V9c0-2.5 6-2.5 6 0v4M5 13h6M8 6.5c0-1.1-.9-2-2-2s-2 .9-2 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            'mistral':   '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M8 2.5l5.5 9.5H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
            'eight':     '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M8 2C6.3 2 5 3.1 5 4.5S6.3 7 8 7s3 1.1 3 2.5S9.7 12 8 12s-3-1-3-2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M8 2v2M8 12v2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
            'nine':      '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M8 2l1.5 4h4L10 8.5l1.5 4L8 10l-3.5 2.5 1.5-4-3.5-2.5h4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
            'ten':       '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M4 8h8M10 5l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 5l-3 3 3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            'eleven':    '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M9 2L5 9h4l-2 5 6-8H9z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            'twelve':    '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M8 3C5.5 3 4 5 4 7c0 1.5 1 2.5 2 3l-.5 3h5L10 10c1-.5 2-1.5 2-3 0-2-1.5-4-4-4z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6.5 10.5h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
            'librarian': '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M4.5 3.5v9M4.5 3.5h5a2 2 0 010 4h-5M4.5 7.5h5.5a2 2 0 010 4H4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            'duck':      '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M4 9.5c0 2 1.8 3 4 3s4-1 4-3c0-1.5-1-2.5-3-2.5H8c1 0 2-1 2-2S9 3 8 3C6.5 3 5.5 4 5.5 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M12 7.5l2 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
            'sniffles':  '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M6 2h4M5.5 2v4.5L3 11.5a1 1 0 00.9 1.5h8.2a1 1 0 00.9-1.5L10.5 6.5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            'sniffer':   '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><path d="M6 2h4M5.5 2v4.5L3 11.5a1 1 0 00.9 1.5h8.2a1 1 0 00.9-1.5L10.5 6.5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
          };
          const agentSvg = _studioAgentSvg[agentKey] || '<svg viewBox="0 0 16 16" width="22" height="22" fill="none"><circle cx="8" cy="5.5" r="2.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>';
          const statusDot = agent.status === 'online'
            ? '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#4caf50;"></span>'
            : '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#f44336;"></span>';
          
          html += `
            <div style="background: var(--card); padding: 10px; border-radius: 6px; border: 1px solid var(--border); cursor: pointer; transition: all 0.2s;" onclick="showAgentDetails('${agent.name}')">
              <div style="display:flex;align-items:center;justify-content:center;height:32px;color:var(--accent);">${agentSvg}</div>
              <div style="font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top:4px;">${agent.name}</div>
              <div style="font-size: 10px; color: var(--text-dim); margin-top: 4px; display:flex; align-items:center; gap:4px;">${statusDot} ${agent.status || 'unknown'}</div>
              <div style="font-size: 9px; color: var(--text-dim); margin-top: 2px;">${agent.type || 'agent'}</div>
            </div>
          `;
        });
        
        html += '</div>';
        studioContent.innerHTML = html;
      })
      .catch(e => {
        studioContent.innerHTML = `<div style="padding: 16px; color: #f77;">Error loading agents: ${e.message}</div>`;
      });
  } else if (section === 'queue') {
    studioContent.innerHTML = `<div style="padding:16px;"><h4>Task Queue</h4><div id="studio-queue-body" style="font-size:12px;color:var(--text-dim);">Loading…</div></div>`;
    fetch('/api/chat/jobs/status').then(r => r.json()).then(data => {
      const jobs = (data && data.jobs) || [];
      const body = document.getElementById('studio-queue-body');
      if (!body) return;
      if (!jobs.length) { body.textContent = 'No active jobs.'; return; }
      body.innerHTML = jobs.map(j => `<div style="padding:4px 0;border-bottom:1px solid var(--border);">${j.agent || '?'} · ${j.status || '?'} · ${j.job_id || ''}</div>`).join('');
    }).catch(e => {
      const body = document.getElementById('studio-queue-body');
      if (body) body.textContent = 'Queue unavailable: ' + (e && e.message || e);
    });
  } else if (section === 'logs') {
    studioContent.innerHTML = `<div style="padding:16px;"><h4>Recent Episodes</h4><div id="studio-logs-body" style="font-size:12px;color:var(--text-dim);">Loading…</div></div>`;
    fetch('/api/seven/episodes?limit=20').then(r => r.json()).then(data => {
      const eps = (data && data.episodes) || [];
      const body = document.getElementById('studio-logs-body');
      if (!body) return;
      if (!eps.length) { body.textContent = 'No episodes recorded yet.'; return; }
      body.innerHTML = eps.map(e => `<div style="padding:4px 0;border-bottom:1px solid var(--border);">${e.ts || ''} · ${e.kind || ''} · ${(e.summary || e.text || '').slice(0,80)}</div>`).join('');
    }).catch(e => {
      const body = document.getElementById('studio-logs-body');
      if (body) body.textContent = 'Episodes unavailable: ' + (e && e.message || e);
    });
  } else if (section === 'config') {
    studioContent.innerHTML = `<div style="padding:16px;"><h4>Agent Health</h4><div id="studio-config-body" style="font-size:12px;color:var(--text-dim);">Loading…</div></div>`;
    fetch('/api/chat/agents/health').then(r => r.json()).then(data => {
      const agents = (data && data.agents) || {};
      const names = Object.keys(agents);
      const body = document.getElementById('studio-config-body');
      if (!body) return;
      if (!names.length) { body.textContent = 'No agents tracked yet.'; return; }
      body.innerHTML = names.map(n => {
        const a = agents[n] || {};
        return `<div style="padding:4px 0;border-bottom:1px solid var(--border);">${n} · count=${a.count||0} · stalled=${a.stalled||0} · p95=${a.p95_ms||0}ms</div>`;
      }).join('');
    }).catch(e => {
      const body = document.getElementById('studio-config-body');
      if (body) body.textContent = 'Agent health unavailable: ' + (e && e.message || e);
    });
  }
}

function showAgentDetails(agentName) {
  if (typeof openWindow === 'function') {
    try { openWindow('agents-config', `Agent · ${agentName}`, 'view-agents-config', { multi: false }); return; } catch (_) { /* fall through */ }
  }
  if (typeof showToast === 'function') showToast(`Agent: ${agentName}`, 'info');
}

function addCustomCard() {
  const name = prompt('Card title:');
  if (!name) return;
  const emoji = prompt('Emoji/Icon:');
  const desc = prompt('Description:');
  
  const card = document.createElement('div');
  card.className = 'home-card';
  card.innerHTML = `
    <div class="card-icon">${emoji || '<svg viewBox="0 0 16 16" width="16" height="16" fill="none"><path d="M9.5 2.5l4 4-6 6H4v-3.5l6-6z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M7 10v3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>'}</div>
    <div class="card-title">${name}</div>
    <div class="card-desc">${desc || 'Custom card'}</div>
  `;
  
  document.getElementById('quick-cards').appendChild(card);
}

function openWindowHelp(windowId) {
  // B15: Single-source manual — fetch from /api/manual/<key>; fall back to
  // the inline dict below if the fetch fails (offline, route missing, etc).
  const helpText = {
    home: {
      title: 'Fridays Home',
      body: 'Landing dashboard for quick access. Open tiles to use specific swarm tools. Use Settings for theme and transparency controls.\n\nQuick chat relay guide:\n1) Agents can request another agent using @agent, AGENT:, or route/ask language.\n2) If Auto Relay is ON, detected relay routes are queued automatically.\n3) Route buttons still appear for manual control when you want to review first.\n4) Relay temporarily targets the requested agent for that turn.'
    },
    chat: {
      title: 'Chat Window',
      body: 'Review conversation history, open full transcripts, and manage conversation titles. Use this for swarm dialogue and message context.\n\nHow to relay:\n- Write @gemma (or another agent) followed by a request.\n- You can also use: "ask gemma ..." or "Gemma, ...".\n- Turn on Auto Relay in Chat controls for automatic chaining.\n- Keep Auto Relay off when you want explicit human approval per hop.'
    },
    terminal: {
      title: 'Fridays Native Terminal',
      body: 'This is the Fridays native terminal, not your host shell. Commands are routed through API controls and ALM proposal governance, and are intended for swarm operations (services, health checks, diagnostics). For unrestricted host access, use an external terminal session.'
    },
    files: {
      title: 'Workspace Files',
      body: 'Browse the workspace tree, preview files, run file-scoped terminal actions, and edit text files with ALM-governed save operations.'
    },
    memory: {
      title: 'Memory Browser',
      body: 'Search and inspect swarm memory entries across agents. Use this to audit what was learned and when.'
    },
    monitor: {
      title: 'System Monitor',
      body: 'View system health, queue depth, and ALM governance status in one place.'
    },
    docs: {
      title: 'Documentation Center',
      body: 'Browse docs plus ALM history evidence. Use Docs tab for references and ALM History for proposal lifecycle traceability.'
    },
    skills: {
      title: 'Skills',
      body: 'See available skill commands and usage examples to trigger specific workflows.'
    },
    tickets: {
      title: 'Tickets',
      body: 'Inspect ticket lifecycle details, notes, and outcomes. Use this for task-level operational tracking.'
    },
    studio: {
      title: 'Studio',
      body: 'Proposal governance cockpit: review pending approvals and inspect full proposal history.'
    },
    'time-wizard': {
      title: 'Vortex',
      body: 'Decision timeline and architecture checkpoints. Use it to track state changes across sessions inside the Swarm boundary.'
    },
    'ghost-brief': {
      title: 'Ghost Brief',
      body: 'Summarized intelligence feed generated from current swarm state and recent activity.'
    }
  };

  const data = helpText[windowId] || {
    title: 'Window Help',
    body: 'This window is part of Fridays. Use controls in the header to resize, pin, fullscreen, or close.'
  };

  const relayTipsHtml = (windowId === 'home' || windowId === 'chat')
    ? `<div style="margin-top:12px;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--card);font-size:11px;color:var(--text-dim);">
         <div style="font-weight:600;color:var(--text);margin-bottom:6px;">Relay Tips</div>
         <div>Use @agent for the most reliable relay trigger.</div>
         <div>Enable Auto Relay to process "Route to Agent" handoffs automatically.</div>
         <div>If an action needs human confirmation, keep Auto Relay off and click the route button manually.</div>
       </div>`
    : '';

  let modal = document.getElementById('window-help-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'window-help-modal';
    modal.className = 'modal';
    modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = `
      <div class="modal-content" style="width:90%;max-width:680px;max-height:80vh;display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--border);flex-shrink:0;">
          <h3 id="win-help-title" style="margin:0;font-size:14px;">Window Help</h3>
          <button onclick="document.getElementById('window-help-modal').classList.remove('open')"
                  style="background:none;border:none;color:var(--text);font-size:18px;cursor:pointer;">✕</button>
        </div>
        <div id="win-help-body" style="overflow-y:auto;padding:16px;line-height:1.6;font-size:12px;"></div>
      </div>`;
    document.body.appendChild(modal);
  }

  document.getElementById('win-help-title').textContent = `❓ ${data.title}`;
  document.getElementById('win-help-body').innerHTML = `
    <div style="margin-bottom:12px;color:var(--text);white-space:pre-wrap;">${_escHtml(data.body)}</div>
    <div style="padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--card);font-size:11px;color:var(--text-dim);">
      Header controls: ? Help · ⬚ Maximize · _ Minimize · Pin · ⛶ Fullscreen · ✕ Close
    </div>
    ${relayTipsHtml}`;
  modal.classList.add('open');

  // B15: refresh from single-source manual endpoint
  fetch(`/api/manual/${encodeURIComponent(windowId)}`)
    .then(r => r.ok ? r.json() : null)
    .then(j => {
      if (!j || !j.ok) return;
      const titleEl = document.getElementById('win-help-title');
      const bodyEl = document.getElementById('win-help-body');
      if (titleEl && j.title) titleEl.textContent = `❓ ${j.title}`;
      if (bodyEl && j.body) {
        bodyEl.innerHTML = `
          <div style="margin-bottom:12px;color:var(--text);white-space:pre-wrap;">${_escHtml(j.body)}</div>
          <div style="padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--card);font-size:11px;color:var(--text-dim);">
            Header controls: ? Help · ⬚ Maximize · _ Minimize · Pin · ⛶ Fullscreen · ✕ Close
          </div>
          ${relayTipsHtml}`;
      }
    })
    .catch(() => { /* keep fallback render */ });
}

function closeTopModal() {
  const modalOrder = [
    'command-palette',
    'shortcuts-help-modal',
    'window-help-modal',
    'chat-detail-modal',
    'proposal-detail-modal',
    'ticket-detail-modal',
    'memory-detail-modal',
    'doc-detail-modal',
    'timezone-picker-modal',
    'settings-modal'
  ];
  for (const id of modalOrder) {
    const el = document.getElementById(id);
    if (!el) continue;
    if (id === 'command-palette' && el.classList.contains('open')) {
      el.classList.remove('open');
      return true;
    }
    if (id !== 'command-palette' && el.classList.contains('open')) {
      el.classList.remove('open');
      return true;
    }
  }
  return false;
}

function closeTopWindow() {
  const windows = Array.from(winManager.windows.values());
  if (windows.length > 0) {
    const topmost = windows.reduce((a, b) =>
      parseInt(a.el.style.zIndex || 0) > parseInt(b.el.style.zIndex || 0) ? a : b
    );
    if (topmost?.id) {
      if (topmost.fullscreen && typeof winManager.fullscreen === 'function') {
        winManager.fullscreen(topmost.id);
        return true;
      }
      winManager.close(topmost.id);
      return true;
    }
  }

  // DOM fallback in case manager state drifts
  const domWindows = Array.from(document.querySelectorAll('.floating-window'));
  if (!domWindows.length) return false;
  const topEl = domWindows.reduce((a, b) =>
    parseInt(a.style.zIndex || '0', 10) > parseInt(b.style.zIndex || '0', 10) ? a : b
  );
  if (!topEl?.id?.startsWith('win-')) return false;
  winManager.close(topEl.id.replace(/^win-/, ''));
  return true;
}


function sendTicketToChat(ticketNumber, questionHint) {
  // Close ticket modal
  const modal = document.getElementById('ticket-detail-modal');
  if (modal) modal.classList.remove('open');

  // Open or focus the Chat window
  if (typeof openWindow === 'function') {
    openWindow('chat', 'Chat', 'view-chat');
  }

  // Populate chat input with ticket context
  const populate = () => {
    const input = document.getElementById('question-input');
    if (!input) return;
    const prefix = `[Ticket ${ticketNumber}] `;
    const hint = String(questionHint || '').trim();
    input.value = hint ? prefix + hint : prefix;
    input.focus();
    input.dispatchEvent(new Event('input'));
    // Scroll input into view
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  // Small delay to let the chat window finish rendering
  setTimeout(populate, 300);
}

// Open the Chat window and navigate to a specific conversation thread
function openConversation(convId) {
  if (!convId) return;
  // Close proposal modal so chat is visible
  const propModal = document.getElementById('proposal-detail-modal');
  if (propModal) propModal.classList.remove('open');

  if (typeof openWindow === 'function') {
    openWindow('chat', 'Chat', 'view-chat');
  }

  // Give the window time to render before switching the active thread
  setTimeout(() => {
    if (typeof _setActiveThreadId === 'function') {
      _setActiveThreadId(convId);
    } else {
      window.__fridaysChatConversationId = convId;
    }
    if (typeof loadConversationMessages === 'function') {
      loadConversationMessages(convId);
    }
  }, 300);
}

// TEMPORARY INTAKE FIX - added 2026-04-09 for manual pipeline test
// This makes /api/queue work even if the backend intake_internal is missing
window.tempIntakeFix = true;

// MD-FEATURE-485CDCA789E8 — universal "?" tab help.
// Maps each studio tab to a short blurb + KC manual link. The button in the
// toolbar reads window._studioTab and surfaces a small modal anchored to the
// active tab so users can learn what each tab does without leaving Studio.
const _STUDIO_TAB_HELP = {
  projects:    { title: 'Projects', blurb: 'Agile / Waterfall / Prince2 plans with Seven as owner. Shows steps, packets, evidence, and the active filter (Active / All / Archived).', kc: '/knowledge?topic=studio-projects' },
  testlab:     { title: 'Test Lab', blurb: 'Run the 7-tier audit hierarchy + any registered test script against a change. Captures runs in the Records tab.', kc: '/knowledge?topic=studio-testlab' },
  pending:     { title: 'Proposed', blurb: 'New proposals awaiting review. Approve / reject / request-changes routes through the governance ALM.', kc: '/knowledge?topic=studio-proposals' },
  in_progress: { title: 'In Progress', blurb: 'Approved proposals under UAT or actively executing. Tracks queue depth and per-proposal stage.', kc: '/knowledge?topic=studio-proposals' },
  all:         { title: 'History', blurb: 'Rejected, closed, and done proposals. Read-only audit trail for governance review.', kc: '/knowledge?topic=studio-proposals' },
  media:       { title: 'Media', blurb: 'Linked music/video production projects, interests, feeds, and spine activity.', kc: '/knowledge?topic=studio-media' },
  git:         { title: 'Git', blurb: 'Git proposal queue — branch/diff/checks for ghost-coder and other agent-authored PRs.', kc: '/knowledge?topic=studio-git' },
  records:     { title: 'Records', blurb: 'Universal viewer for projects, steps, cases, runs, proposals, tickets, emails, notes, docs, threads (Platinum file layer).', kc: '/knowledge?topic=studio-records' },
};

function studioShowTabHelp() {
  const tab = window._studioTab || 'projects';
  const meta = _STUDIO_TAB_HELP[tab] || { title: tab, blurb: 'No help blurb registered for this tab yet.', kc: '/knowledge' };
  let modal = document.getElementById('studio-tab-help-modal');
  if (modal) modal.remove();
  modal = document.createElement('div');
  modal.id = 'studio-tab-help-modal';
  modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;';
  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 20px;width:min(440px,90vw);box-shadow:0 14px 40px rgba(0,0,0,.4);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div style="font-size:13px;font-weight:700;display:inline-flex;align-items:center;gap:8px;color:var(--accent);">
          <span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:color-mix(in srgb,var(--accent) 18%,transparent);border:1px solid var(--accent);font-size:13px;">?</span>
          <span>Studio — ${(meta.title || tab).replace(/[<>]/g,'')}</span>
        </div>
        <button onclick="document.getElementById('studio-tab-help-modal').remove()" aria-label="Close" style="background:transparent;border:none;color:var(--text-dim);font-size:18px;cursor:pointer;">×</button>
      </div>
      <div style="font-size:12px;line-height:1.55;color:var(--text);margin-bottom:12px;">${(meta.blurb || '').replace(/[<>]/g,'')}</div>
      <div style="display:flex;gap:6px;justify-content:flex-end;">
        <a href="${meta.kc}" onclick="event.preventDefault();openWindow('knowledge','Knowledge','view-knowledge');document.getElementById('studio-tab-help-modal').remove();" style="background:var(--accent);color:#000;border:none;border-radius:6px;padding:6px 12px;font-size:11px;font-weight:700;cursor:pointer;text-decoration:none;">Open KC manual →</a>
        <button onclick="document.getElementById('studio-tab-help-modal').remove()" style="background:transparent;border:1px solid var(--border);border-radius:6px;padding:6px 12px;color:var(--text-dim);font-size:11px;cursor:pointer;">Close</button>
      </div>
      <div style="margin-top:10px;font-size:9px;color:var(--text-dim);text-align:right;">Press <kbd style="padding:0 5px;border:1px solid var(--border);border-radius:3px;background:var(--bg);">Esc</kbd> to close</div>
    </div>`;
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
  const escH = (e) => { if (e.key === 'Escape') { const m = document.getElementById('studio-tab-help-modal'); if (m) m.remove(); document.removeEventListener('keydown', escH); } };
  document.addEventListener('keydown', escH);
  document.body.appendChild(modal);
}
window.studioShowTabHelp = studioShowTabHelp;
