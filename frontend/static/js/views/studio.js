// Studio view — proposals, pipeline, agent details, custom cards
// Extracted from terminal_base.html

function loadStudioData(win) {
  // Load proposals into the studio content area
  const content = win.el.querySelector('#studio-content');
  const gov = win.el.querySelector('#studio-governance');
  if (!content) return;
  if (gov) {
    gov.textContent = 'ALM status: loading...';
    fetch('/api/alm/status')
      .then(r => r.json())
      .then(alm => {
        gov.innerHTML = `ALM: <strong>${alm.status === 'enforced' ? 'enforced' : 'warn'}</strong> · ` +
          `Sniffles: <strong>${alm.sniffles_enabled ? 'enabled' : 'disabled'}</strong> · ` +
          `Pending: <strong>${alm.work_proposals?.pending || 0}</strong>`;
      })
      .catch(() => { gov.textContent = 'ALM status: unavailable'; });
  }
  window._studioTab = window._studioTab || 'pending';
  studioSetTab(window._studioTab);
}

// ── Studio status palette (shared) ──────────────────────────────────────────
const _PROPOSAL_STATUS = {
  pending:     { color: '#ffa500', bg: '#ffa50022', border: '#ffa50044', label: 'Pending',     step: 0 },
  approved:    { color: '#4caf50', bg: '#4caf5020', border: '#4caf5060', label: 'Approved',    step: 1 },
  in_progress: { color: '#29b6f6', bg: '#29b6f620', border: '#29b6f660', label: 'In Progress', step: 2 },
  done:        { color: '#ab47bc', bg: '#ab47bc20', border: '#ab47bc60', label: 'Done',        step: 3 },
  executed:    { color: '#2196f3', bg: '#2196f320', border: '#2196f360', label: 'Executed',    step: 4 },
  rejected:    { color: '#f44336', bg: '#f4433620', border: '#f4433660', label: 'Rejected',    step: -1 },
};

function studioSetTab(tab) {
  window._studioTab = tab;
  ['pending','in_progress','all'].forEach(t => {
    const btn = document.getElementById('studio-tab-' + t);
    if (!btn) return;
    const on = tab === t;
    btn.style.cssText = btn.style.cssText.replace(/background[^;]+;|color[^;]+;|border-color[^;]+;/g,'') +
      (on ? 'background:var(--accent);color:#000;border-color:var(--accent);'
          : 'background:transparent;color:var(--text-dim);border-color:var(--border);');
  });
  const container = document.getElementById('studio-content');
  if (container) loadProposals(container, tab);
}

function loadProposals(container, tab) {
  const mode = tab || window._studioTab || 'pending';
  const url = mode === 'all'
    ? '/api/work-proposals?status=done&status=executed&status=rejected&limit=400'
    : mode === 'in_progress'
      ? '/api/work-proposals?status=in_progress&status=approved&limit=200'
      : '/api/work-proposals?status=pending&limit=200';

  fetch(url)
    .then(r => r.json())
    .then(data => {
      const proposals = data.proposals || [];
      window._proposals = proposals;
      if (!proposals.length) {
        container.innerHTML = `
          <div style="text-align:center;padding:40px 20px;color:var(--text-dim);">
            <div style="font-size:32px;margin-bottom:12px;">${mode==='all'?'📋':'📭'}</div>
            <div style="font-size:14px;font-weight:600;">${mode==='all'?'No completed or rejected proposals yet':mode==='in_progress'?'No approved or in-progress proposals':'No pending proposals'}</div>
          </div>`;
        return;
      }
      const labels = { pending:'Pending Review', in_progress:'In Progress & Approved', all:'History' };
      container.innerHTML = `
        <div style="padding:12px 0 8px;font-size:11px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
          ${proposals.length} Proposal${proposals.length!==1?'s':''} — ${labels[mode]||mode}
        </div>
        ${proposals.map(p => _proposalCard(p)).join('')}`;
    })
    .catch(e => {
      container.innerHTML = `<div style="color:#f77;padding:20px;font-size:12px;">Error: ${e.message}</div>`;
    });
}

function _proposalCard(p) {
  const status = (p.status || 'pending').toLowerCase();
  const m = _PROPOSAL_STATUS[status] || _PROPOSAL_STATUS.pending;
  const pid = p.proposal_id || '';
  const pidJs = _jsStr(pid);
  const title = _escHtml(p.title || pid || 'Untitled');
  const created = (p.created_at || '').slice(0,16);
  const agent = _escHtml(p.agent || '?');
  const description = p.description || '';
  const descriptionPreview = _escHtml(description.slice(0,300));
  const ticketLink = p.ticket_number
    ? `<span style="padding:2px 6px;border-radius:8px;background:#2196f320;color:#2196f3;font-size:10px;border:1px solid #2196f340;cursor:pointer;" onclick='event.stopPropagation();openTicketDetail(${_jsStr(p.ticket_number)})'>🎫 ${_escHtml(p.ticket_number)}</span>`
    : '';

  // Pipeline mini-bar (only for non-rejected)
  const pipelineHtml = status !== 'rejected' ? `
    <div style="display:flex;gap:3px;margin-top:10px;align-items:center;">
      ${['Proposed','Approved','In Progress','Done','Executed'].map((label, i) => {
        const active = m.step === i;
        const done   = m.step > i;
        return `<div style="flex:1;text-align:center;font-size:9px;padding:3px 0;border-radius:3px;
          background:${done?m.bg:active?m.bg:'transparent'};
          color:${done||active?m.color:'var(--text-dim)'};
          border:1px solid ${done||active?m.border:'var(--border)'};">${done?'✓ ':''}${label}</div>`;
      }).join('<div style="color:var(--text-dim);font-size:9px;">›</div>')}
    </div>` : '';

  const actionBtns = status === 'pending' ? `
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"approved")'
        style="flex:1;padding:6px;background:#4caf5020;border:1px solid #4caf5060;border-radius:4px;color:#4caf50;font-size:11px;font-weight:600;cursor:pointer;">✓ Approve</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"rejected")'
        style="flex:1;padding:6px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;font-weight:600;cursor:pointer;">✗ Reject</button>
    </div>` :
  status === 'approved' ? `
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"in_progress")'
        style="flex:1;padding:6px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:11px;font-weight:600;cursor:pointer;">▶ Start</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"rejected")'
        style="flex:1;padding:6px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;font-weight:600;cursor:pointer;">✗ Reject</button>
    </div>` :
  status === 'in_progress' ? `
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"done")'
        style="flex:1;padding:6px;background:#ab47bc20;border:1px solid #ab47bc60;border-radius:4px;color:#ab47bc;font-size:11px;font-weight:600;cursor:pointer;">✓ Mark Done</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"rejected")'
        style="flex:1;padding:6px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;font-weight:600;cursor:pointer;">✗ Reject</button>
    </div>` :
  status === 'done' ? `
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"executed")'
        style="flex:1;padding:6px;background:#2196f320;border:1px solid #2196f360;border-radius:4px;color:#2196f3;font-size:11px;font-weight:600;cursor:pointer;">✓ Verify &amp; Close</button>
      <button onclick='event.stopPropagation();moveProposal(${pidJs},"in_progress")'
        style="flex:1;padding:6px;background:#29b6f620;border:1px solid #29b6f660;border-radius:4px;color:#29b6f6;font-size:11px;font-weight:600;cursor:pointer;">↩ Reopen</button>
    </div>` : '';
  const deleteBtn = `
    <button onclick='event.stopPropagation();deleteProposalSafe(${pidJs})'
      title="Delete proposal"
      aria-label="Delete proposal"
      style="margin-left:6px;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;background:#f4433620;border:1px solid #f4433660;border-radius:6px;color:#f44336;font-size:13px;font-weight:700;cursor:pointer;flex:0 0 auto;">🗑</button>`;

  return `<div style="background:var(--card);border:1px solid var(--border);border-left:3px solid ${m.color};border-radius:6px;padding:14px;margin-bottom:10px;opacity:${status==='rejected'?'0.6':'1'};cursor:pointer;" onclick='openProposalDetail(${pidJs})'>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
      <div style="flex:1;">
        <div style="font-weight:700;font-size:13px;margin-bottom:4px;">${title}</div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
          <span style="font-size:10px;color:var(--text-dim);">By ${agent} · ${created}</span>
          ${ticketLink}
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex:0 0 auto;">
        <span style="padding:2px 8px;border-radius:10px;background:${m.bg};color:${m.color};font-size:10px;font-weight:700;white-space:nowrap;border:1px solid ${m.border};">${m.label}</span>
        ${deleteBtn}
      </div>
    </div>
    ${description ? `<div style="margin-top:8px;font-size:11px;color:var(--text-dim);white-space:pre-wrap;max-height:60px;overflow:hidden;line-height:1.5;font-family:monospace;">${descriptionPreview}${description.length>300?'…':''}</div>` : ''}
    ${pipelineHtml}
    ${actionBtns}
  </div>`;
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
  const confirmed = confirm(`Delete proposal ${proposalId}? This cannot be undone.`);
  if (!confirmed) return;
  try {
    const result = await deleteProposal(proposalId, closeModal);
    console.log('Delete succeeded:', result);
  } catch (e) {
    const msg = e.message || String(e);
    console.error('Delete failed:', msg);
    showToast('Delete failed: ' + msg, 'error');
  }
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

  document.getElementById('pdet-title').textContent = title;
  document.getElementById('pdet-body').innerHTML = `
    ${_proposalPipelineBar(status)}

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;">
      <span style="padding:3px 10px;border-radius:12px;background:${m.bg};color:${m.color};font-size:11px;font-weight:700;border:1px solid ${m.border};">${m.label}</span>
      ${p.agent ? `<span style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;">Agent: ${safeAgent}</span>` : ''}
      ${p.ticket_number ? `<span onclick='openTicketDetail(${ticketJs})' style="padding:3px 10px;border-radius:12px;background:#2196f320;color:#2196f3;font-size:11px;cursor:pointer;border:1px solid #2196f340;">Ticket: ${safeTicketNumber}</span>` : ''}
      ${p.queue_id ? `<span style="padding:3px 10px;border-radius:12px;background:var(--card);color:var(--text-dim);font-size:11px;">Queue: ${_escHtml(String(p.queue_id))}</span>` : ''}
    </div>

    <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:16px;">
      <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;width:130px;">Proposal ID</td><td style="font-family:monospace;font-size:11px;">${safeProposalId}</td></tr>
      <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Created</td><td>${_escHtml(created||'—')}</td></tr>
      ${updated && updated !== created ? `<tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Updated</td><td>${_escHtml(updated)}</td></tr>` : ''}
    </table>

    ${p.description ? `
    <div style="margin-bottom:14px;">
      <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Description</div>
      <div style="background:var(--card);padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap;max-height:280px;overflow-y:auto;font-family:monospace;line-height:1.5;">${safeDescription}</div>
    </div>` : ''}

    <div style="margin-bottom:14px;">
      <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Documentation</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;">
        ${artifacts.map(a => `<button onclick="openDocDetail('${a.file}','${a.label}')" style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">${a.label}</button>`).join('')}
      </div>
    </div>

    <div style="padding-top:12px;border-top:1px solid var(--border);">
      <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">Actions</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        ${status==='pending' ? `
          <button onclick='moveProposal(${pidJs},"approved")'
            style="padding:8px 16px;background:#4caf5020;border:1px solid #4caf5060;border-radius:4px;color:#4caf50;font-size:12px;font-weight:600;cursor:pointer;">&#10003; Approve</button>
          <button onclick='moveProposal(${pidJs},"rejected")'
            style="padding:8px 16px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:12px;font-weight:600;cursor:pointer;">&#10007; Reject</button>` : ''}
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
          <button onclick='moveProposal(${pidJs},"executed")'
            style="padding:8px 16px;background:#2196f320;border:1px solid #2196f360;border-radius:4px;color:#2196f3;font-size:12px;font-weight:600;cursor:pointer;">&#10003; Verify &amp; Close</button>
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
          <h3 id="doc-det-title" style="margin:0;font-size:14px;">📄</h3>
          <button onclick="document.getElementById('doc-detail-modal').classList.remove('open')"
                  style="background:none;border:none;color:var(--text);font-size:18px;cursor:pointer;">✕</button>
        </div>
        <div id="doc-det-body" style="overflow-y:auto;padding:20px;flex:1;font-size:12px;line-height:1.7;white-space:pre-wrap;font-family:monospace;"></div>
      </div>`;
    document.body.appendChild(modal);
  }
  document.getElementById('doc-det-title').textContent = '📄 ' + (title || filename);
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

  document.getElementById('tdet-title').textContent = '🎫 ' + ticketNumber;
  document.getElementById('tdet-body').innerHTML = '<div style="color:var(--text-dim);padding:20px;text-align:center;">Loading…</div>';
  modal.classList.add('open');

  fetch(`/api/tickets/${ticketNumber}`)
    .then(r => r.json())
    .then(data => {
      // API returns {ticket: {...}, notes: [...], messages: [...], snoozes: [...]}
      const t = data.ticket || data;
      const notes = data.notes || t.notes || [];
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
          ${t.snooze_count ? `<span style="padding:3px 10px;border-radius:12px;background:#ff980022;color:#ff9800;font-size:11px;">💤 ${_escHtml(String(t.snooze_count))} snooze</span>` : ''}
        </div>

        <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:16px;">
          <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;width:120px;">From</td><td>${_escHtml(t.sender_email||'—')}</td></tr>
          <tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Created</td><td>${_escHtml((t.created_at||'').slice(0,16))}</td></tr>
          ${t.closed_at ? `<tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Closed</td><td>${_escHtml(t.closed_at.slice(0,16))}</td></tr>` : ''}
          ${t.gemma_routing ? `<tr><td style="color:var(--text-dim);padding:4px 8px 4px 0;">Routing</td><td style="font-size:10px;color:var(--text-dim);">${_escHtml(t.gemma_routing)}</td></tr>` : ''}
        </table>

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
          ${t.status !== 'closed'
            ? `<button onclick="closeTicketFromModal(${tnJs})" style="padding:6px 14px;background:#f443361a;border:1px solid #f4433644;border-radius:4px;color:#f44336;font-size:12px;cursor:pointer;">Close Ticket</button>`
            : `<button onclick="reopenTicketFromModal(${tnJs})" style="padding:6px 14px;background:#4caf501a;border:1px solid #4caf5044;border-radius:4px;color:#4caf50;font-size:12px;cursor:pointer;">Reopen</button>`}
          <button onclick="createProposalFromTicket(${tnJs}, ${questionHintJs})"
            style="padding:6px 14px;background:#4caf501a;border:1px solid #4caf5044;border-radius:4px;color:#4caf50;font-size:12px;cursor:pointer;">+ Proposal</button>
          <button onclick="pinItemToDeferred(${tnJs}, ${questionHintJs}, 'ticket')"
            style="padding:6px 14px;background:transparent;border:1px solid var(--border);border-radius:4px;color:var(--text-dim);font-size:12px;cursor:pointer;">&#128204; Pin</button>
          <button onclick="document.getElementById('ticket-detail-modal').classList.remove('open')"
                  style="padding:6px 14px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;cursor:pointer;">Close</button>
        </div>`;
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
          const emoji = {
            'gemma': '🟢',
            'llama': '🦙',
            'qwen': '📕',
            'eight': '8️⃣',
            'nine': '9️⃣',
            'ten': '🔟',
            'eleven': '1️⃣1️⃣',
            'grok': '🧠',
            'twelve': '⏰',
            'librarian': '📚',
            'duck': '🦆',
            'sniffer': '🐕'
          }[agent.name.toLowerCase()] || '🤖';
          
          const status = agent.status === 'online' ? '🟢' : '🔴';
          
          html += `
            <div style="background: var(--card); padding: 12px; border-radius: 6px; border: 1px solid var(--border); cursor: pointer; transition: all 0.2s;" onclick="showAgentDetails('${agent.name}')">
              <div style="font-size: 28px; margin-bottom: 4px; text-align: center;">${emoji}</div>
              <div style="font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${agent.name}</div>
              <div style="font-size: 10px; color: var(--text-dim); margin-top: 4px;">${status} ${agent.status || 'unknown'}</div>
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
    studioContent.innerHTML = `
      <div style="padding: 16px;">
        <h4>Task Queue</h4>
        <p style="font-size: 12px; color: var(--text-dim);">Queue management coming soon...</p>
      </div>
    `;
  } else if (section === 'logs') {
    studioContent.innerHTML = `
      <div style="padding: 16px;">
        <h4>Activity Logs</h4>
        <p style="font-size: 12px; color: var(--text-dim);">Logs coming soon...</p>
      </div>
    `;
  } else if (section === 'config') {
    studioContent.innerHTML = `
      <div style="padding: 16px;">
        <h4>Configuration</h4>
        <p style="font-size: 12px; color: var(--text-dim);">Config management coming soon...</p>
      </div>
    `;
  }
}

function showAgentDetails(agentName) {
  console.log('Showing details for agent:', agentName);
  // TODO: Open detailed agent info window
}

function addCustomCard() {
  const name = prompt('Card title:');
  if (!name) return;
  const emoji = prompt('Emoji/Icon:');
  const desc = prompt('Description:');
  
  const card = document.createElement('div');
  card.className = 'home-card';
  card.innerHTML = `
    <div class="card-icon">${emoji || '📌'}</div>
    <div class="card-title">${name}</div>
    <div class="card-desc">${desc || 'Custom card'}</div>
  `;
  
  document.getElementById('quick-cards').appendChild(card);
}

function openWindowHelp(windowId) {
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
    <div style="margin-bottom:12px;color:var(--text);">${_escHtml(data.body)}</div>
    <div style="padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--card);font-size:11px;color:var(--text-dim);">
      Header controls: ? Help · ⬚ Maximize · _ Minimize · 📌 Pin · ⛶ Fullscreen · ✕ Close
    </div>
    ${relayTipsHtml}`;
  modal.classList.add('open');
}

function closeTopModal() {
  const modalOrder = [
    'command-palette',
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

