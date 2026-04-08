// Git view — status, diff, stage, commit, proposals
// Extracted from terminal_base.html

function _gitState() {
  if (!window.__gitState) {
    window.__gitState = {
      selectedPath: '',
      selectedStaged: false,
      status: null,
      filter: '',
    };
  }
  return window.__gitState;
}

function loadGitData(win) {
  window.__gitWin = win;
  const state = _gitState();
  const filterInput = win.el.querySelector('#git-filter-input');
  const commitInput = win.el.querySelector('#git-commit-message');
  if (filterInput && !filterInput.dataset.bound) {
    filterInput.dataset.bound = '1';
    filterInput.addEventListener('input', (e) => {
      state.filter = String(e.target.value || '');
      gitRenderStatus();
    });
  }
  if (commitInput && !commitInput.dataset.bound) {
    commitInput.dataset.bound = '1';
    commitInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') gitCommitChanges();
    });
  }
  gitRefreshStatus({ preserveSelection: true });
  gitLoadProposals();
}

async function gitRefreshStatus(options = {}) {
  const state = _gitState();
  const preserveSelection = options.preserveSelection !== false;
  const listEl = window.__gitWin?.el?.querySelector('#git-files-list');
  const diffBody = window.__gitWin?.el?.querySelector('#git-diff-body');
  if (listEl) listEl.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">Loading repository status...</div>';
  if (diffBody && !preserveSelection) diffBody.textContent = 'Loading diff...';

  try {
    const resp = await fetch('/api/git/status');
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) throw new Error(data.error || 'git status failed');
    state.status = data;

    const files = Array.isArray(data.files) ? data.files : [];
    if (!preserveSelection || !files.some(entry => entry.path === state.selectedPath)) {
      const first = files[0] || null;
      state.selectedPath = first ? first.path : '';
      state.selectedStaged = first ? !!(first.staged && !first.unstaged) : false;
    }

    gitRenderStatus();
    if (state.selectedPath) {
      await gitLoadDiff(state.selectedPath, state.selectedStaged, { silent: true });
    } else if (diffBody) {
      diffBody.textContent = 'Working tree is clean.';
      const titleEl = window.__gitWin?.el?.querySelector('#git-diff-title');
      const actionsEl = window.__gitWin?.el?.querySelector('#git-diff-actions');
      if (titleEl) titleEl.textContent = 'No changed files';
      if (actionsEl) actionsEl.innerHTML = '';
    }
  } catch (e) {
    if (listEl) listEl.innerHTML = `<div style="padding:12px;color:#f77;font-size:11px;">Error: ${_escHtml(e.message || e)}</div>`;
    showToast(`Git status failed: ${e.message || e}`, 'error');
  }
}

function gitRenderStatus() {
  const state = _gitState();
  const win = window.__gitWin;
  if (!win) return;
  const listEl = win.el.querySelector('#git-files-list');
  const summaryEl = win.el.querySelector('#git-summary');
  if (!listEl || !summaryEl) return;

  const status = state.status || { files: [], counts: {} };
  const files = Array.isArray(status.files) ? status.files : [];
  const filterNeedle = String(state.filter || '').trim().toLowerCase();
  const filtered = !filterNeedle
    ? files
    : files.filter(entry => `${entry.path} ${entry.status_label}`.toLowerCase().includes(filterNeedle));

  const branchLabel = status.branch || '(detached)';
  const aheadBehind = [];
  if (status.ahead) aheadBehind.push(`ahead ${status.ahead}`);
  if (status.behind) aheadBehind.push(`behind ${status.behind}`);
  summaryEl.textContent = `${branchLabel}${status.upstream ? ` -> ${status.upstream}` : ''} · ${status.clean ? 'clean tree' : `${status.counts.changed || 0} changed`} ${aheadBehind.length ? `· ${aheadBehind.join(', ')}` : ''}`;

  if (!filtered.length) {
    listEl.innerHTML = `<div style="padding:12px;color:var(--text-dim);font-size:11px;">${files.length ? 'No files match the current filter.' : 'No changed files in this repository.'}</div>`;
    return;
  }

  listEl.innerHTML = '';
  filtered.forEach((entry) => {
    const row = document.createElement('div');
    const selected = entry.path === state.selectedPath;
    row.style.cssText = `padding:10px 12px;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:6px;cursor:pointer;background:${selected ? 'rgba(255,255,255,0.04)' : 'transparent'};`;
    row.onclick = () => gitSelectFile(entry.path, entry.staged && !entry.unstaged);

    const head = document.createElement('div');
    head.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px;';

    const pathEl = document.createElement('div');
    pathEl.style.cssText = 'font-size:11px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    pathEl.textContent = entry.path;
    head.appendChild(pathEl);

    const badge = document.createElement('span');
    badge.style.cssText = 'font-size:10px;color:var(--accent);border:1px solid var(--border);border-radius:999px;padding:2px 8px;white-space:nowrap;';
    badge.textContent = entry.status_label;
    head.appendChild(badge);
    row.appendChild(head);

    const meta = document.createElement('div');
    meta.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;';

    const flags = document.createElement('div');
    flags.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;font-size:10px;color:var(--text-dim);';
    const labels = [];
    if (entry.staged) labels.push('staged');
    if (entry.unstaged) labels.push('unstaged');
    if (entry.untracked) labels.push('untracked');
    if (entry.conflicted) labels.push('conflict');
    flags.textContent = labels.join(' · ');
    meta.appendChild(flags);

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:6px;align-items:center;flex-wrap:wrap;';

    if (entry.unstaged || entry.untracked) {
      const stageBtn = document.createElement('button');
      stageBtn.textContent = 'Propose Stage';
      stageBtn.style.cssText = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:3px 8px;cursor:pointer;font-size:10px;';
      stageBtn.onclick = (ev) => {
        ev.stopPropagation();
        gitStagePath(entry.path);
      };
      actions.appendChild(stageBtn);
    }

    if (entry.staged) {
      const unstageBtn = document.createElement('button');
      unstageBtn.textContent = 'Propose Unstage';
      unstageBtn.style.cssText = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:3px 8px;cursor:pointer;font-size:10px;';
      unstageBtn.onclick = (ev) => {
        ev.stopPropagation();
        gitUnstagePath(entry.path);
      };
      actions.appendChild(unstageBtn);
    }

    meta.appendChild(actions);
    row.appendChild(meta);
    listEl.appendChild(row);
  });
}

async function gitSelectFile(path, preferStaged = false) {
  const state = _gitState();
  state.selectedPath = path;
  state.selectedStaged = !!preferStaged;
  gitRenderStatus();
  await gitLoadDiff(path, state.selectedStaged);
}

async function gitLoadDiff(path, staged = false, options = {}) {
  const state = _gitState();
  const win = window.__gitWin;
  if (!win || !path) return;
  const titleEl = win.el.querySelector('#git-diff-title');
  const bodyEl = win.el.querySelector('#git-diff-body');
  const actionsEl = win.el.querySelector('#git-diff-actions');
  if (!titleEl || !bodyEl || !actionsEl) return;

  state.selectedPath = path;
  state.selectedStaged = !!staged;
  const entry = (state.status?.files || []).find(item => item.path === path);

  titleEl.textContent = `${path} · ${staged ? 'staged diff' : 'working tree diff'}`;
  bodyEl.textContent = options.silent ? bodyEl.textContent : 'Loading diff...';
  actionsEl.innerHTML = '';

  const openBtn = document.createElement('button');
  openBtn.textContent = 'Open in Files';
  openBtn.style.cssText = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:4px 8px;cursor:pointer;font-size:10px;';
  openBtn.onclick = () => {
    openWindow('files', '📁 Files', 'view-files');
    setTimeout(() => filesPreviewFileByPath(path), 140);
  };
  actionsEl.appendChild(openBtn);

  if (entry?.unstaged || entry?.untracked) {
    const workingBtn = document.createElement('button');
    workingBtn.textContent = 'Working';
    workingBtn.style.cssText = `background:${!staged ? 'var(--accent)' : 'var(--card)'};border:1px solid ${!staged ? 'var(--accent)' : 'var(--border)'};color:${!staged ? '#000' : 'var(--text)'};border-radius:4px;padding:4px 8px;cursor:pointer;font-size:10px;`;
    workingBtn.onclick = () => gitLoadDiff(path, false);
    actionsEl.appendChild(workingBtn);
  }
  if (entry?.staged) {
    const stagedBtn = document.createElement('button');
    stagedBtn.textContent = 'Staged';
    stagedBtn.style.cssText = `background:${staged ? 'var(--accent)' : 'var(--card)'};border:1px solid ${staged ? 'var(--accent)' : 'var(--border)'};color:${staged ? '#000' : 'var(--text)'};border-radius:4px;padding:4px 8px;cursor:pointer;font-size:10px;`;
    stagedBtn.onclick = () => gitLoadDiff(path, true);
    actionsEl.appendChild(stagedBtn);
  }

  try {
    const resp = await fetch(`/api/git/diff?path=${encodeURIComponent(path)}&staged=${staged ? '1' : '0'}`);
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) throw new Error(data.error || 'git diff failed');
    bodyEl.textContent = data.diff || '(No diff in this view)';
  } catch (e) {
    bodyEl.textContent = `Error loading diff: ${e.message || e}`;
    showToast(`Git diff failed: ${e.message || e}`, 'error');
  }
}

async function gitStagePath(path) {
  let proposalId = null;
  try {
    proposalId = await _createALMProposal(
      'Git stage file',
      `Stage repository path via Git panel: ${path}`,
      3,
      { autoApprove: false }
    );
    showToast('Stage proposal created. Approve in Studio or Git ALM section, then Execute.', 'info');
    await gitLoadProposals();
  } catch (e) {
    await _rejectALMProposal(proposalId);
    showToast(`Stage proposal failed: ${e.message || e}`, 'error');
  }
}

async function gitUnstagePath(path) {
  let proposalId = null;
  try {
    proposalId = await _createALMProposal(
      'Git unstage file',
      `Unstage repository path via Git panel: ${path}`,
      3,
      { autoApprove: false }
    );
    showToast('Unstage proposal created. Approve in Studio or Git ALM section, then Execute.', 'info');
    await gitLoadProposals();
  } catch (e) {
    await _rejectALMProposal(proposalId);
    showToast(`Unstage proposal failed: ${e.message || e}`, 'error');
  }
}

async function gitCommitChanges() {
  const commitInput = window.__gitWin?.el?.querySelector('#git-commit-message');
  const message = String(commitInput?.value || '').trim();
  if (!message) {
    showToast('Commit message is required', 'error');
    return;
  }

  let proposalId = null;
  try {
    proposalId = await _createALMProposal(
      'Git commit staged changes',
      `Commit staged repository changes via Git panel: ${message.slice(0, 240)}`,
      3,
      { autoApprove: false }
    );
    if (commitInput) commitInput.value = '';
    showToast('Commit proposal created. Approve in Studio or Git ALM section, then Execute.', 'info');
    await gitLoadProposals();
  } catch (e) {
    await _rejectALMProposal(proposalId);
    showToast(`Commit proposal failed: ${e.message || e}`, 'error');
  }
}

async function gitLoadProposals() {
  try {
    const resp = await fetch('/api/work-proposals?limit=120');
    const data = await resp.json();
    const proposals = data.proposals || [];
    const gitProposals = proposals;
    window.__gitProposals = gitProposals;

    const container = document.getElementById('git-proposals-list');
    if (!gitProposals.length) {
      container.innerHTML = '<div style="padding:8px;text-align:center;color:var(--text-dim);">No proposals</div>';
      return;
    }

    container.innerHTML = gitProposals.map(p => {
      const created = (p.created_at || '').slice(0, 16);
      const pid = p.proposal_id || '';
      const pidJs = JSON.stringify(pid);
      const title = _escHtml(p.title || 'Untitled');
      const status = String(p.status || 'pending').toLowerCase();
      const statusH = _escHtml(status);
      const createdH = _escHtml(created);
      const statusColor = status === 'approved' ? '#4caf50' : status === 'executed' ? '#29b6f6' : status === 'rejected' ? '#f44336' : 'var(--text-dim)';
      const isExecutable = status === 'approved';
      const canModerate = status === 'pending' || status === 'approved' || status === 'in_progress' || status === 'done';
      // Show Proposal-linked badge if created by git action
      const isGitLinked = /git (stage|unstage|commit)/i.test(p.title || '') || /via Git panel/i.test(p.description || '');
      return `
        <div style="background:var(--card);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:4px;padding:8px;margin-bottom:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:4px;">
            <div style="font-size:10px;font-weight:600;flex:1;word-break:break-word;">${title}</div>
            <span style="font-size:9px;color:${statusColor};white-space:nowrap;">${statusH}</span>
            ${isGitLinked ? '<span style="font-size:9px;background:#2196f320;color:#2196f3;border-radius:8px;padding:2px 8px;margin-left:6px;">Proposal-linked</span>' : ''}
          </div>
          <div style="font-size:9px;color:var(--text-dim);margin-bottom:6px;">${createdH}</div>
          <div style="display:flex;gap:4px;flex-wrap:wrap;">
            ${status === 'pending' ? `<button onclick="gitApproveProposal(${pidJs})" style="flex:1;min-width:60px;padding:3px 6px;background:#4caf5020;border:1px solid #4caf5060;border-radius:3px;color:#4caf50;font-size:9px;font-weight:600;cursor:pointer;">✓ Approve</button>` : ''}
            ${canModerate ? `<button onclick="gitRejectProposal(${pidJs})" style="flex:1;min-width:60px;padding:3px 6px;background:#f4433620;border:1px solid #f4433660;border-radius:3px;color:#f44336;font-size:9px;font-weight:600;cursor:pointer;">✗ Reject</button>` : ''}
            ${isExecutable ? `<button onclick="gitExecuteProposal(${pidJs})" style="flex:1;min-width:60px;padding:3px 6px;background:#29b6f620;border:1px solid #29b6f660;border-radius:3px;color:#29b6f6;font-size:9px;font-weight:700;cursor:pointer;">▶ Execute</button>` : ''}
            <button onclick="gitDeleteProposal(${pidJs})" style="flex:1;min-width:60px;padding:3px 6px;background:#f4433620;border:1px solid #f4433660;border-radius:3px;color:#f44336;font-size:9px;font-weight:600;cursor:pointer;">🗑 Delete</button>
            <button onclick="gitOpenVortex(${pidJs})" style="flex:1;min-width:60px;padding:3px 6px;background:var(--card);border:1px solid var(--border);border-radius:3px;color:var(--text-dim);font-size:9px;cursor:pointer;">🌀 Vortex</button>
            <button onclick="openWindow('studio','🎨 Studio','view-studio');setTimeout(() => studioSetTab('all'),150)" style="flex:1;min-width:60px;padding:3px 6px;background:var(--card);border:1px solid var(--border);border-radius:3px;color:var(--text-dim);font-size:9px;cursor:pointer;">Studio</button>
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    const container = document.getElementById('git-proposals-list');
    if (container) container.innerHTML = `<div style="padding:8px;color:#f77;font-size:10px;">Error: ${_escHtml(e.message)}</div>`;
  }
}

async function gitApproveProposal(proposalId) {
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ status: 'approved' })
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || 'approve failed');
    showToast('Proposal approved', 'success');
    await gitLoadProposals();
  } catch (e) {
    showToast('Approve failed: ' + e.message, 'error');
  }
}

async function gitRejectProposal(proposalId) {
  try {
    const resp = await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ status: 'rejected' })
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || 'reject failed');
    showToast('Proposal rejected', 'info');
    await gitLoadProposals();
  } catch (e) {
    showToast('Reject failed: ' + e.message, 'error');
  }
}

async function gitDeleteProposal(proposalId) {
  if (!confirm(`Delete proposal ${proposalId}? This cannot be undone.`)) return;
  try {
    await deleteProposal(proposalId);
    await gitLoadProposals();
  } catch (e) {
    showToast('Delete failed: ' + (e.message || e), 'error');
  }
}

function _gitParseProposalAction(proposal) {
  const title = String(proposal?.title || '').toLowerCase();
  const description = String(proposal?.description || '');

  if (title.includes('git stage file')) {
    const m = description.match(/Stage repository path via Git panel:\s*(.+)$/i);
    return m ? { action: 'stage', path: m[1].trim() } : null;
  }
  if (title.includes('git unstage file')) {
    const m = description.match(/Unstage repository path via Git panel:\s*(.+)$/i);
    return m ? { action: 'unstage', path: m[1].trim() } : null;
  }
  if (title.includes('git commit staged changes')) {
    const m = description.match(/Commit staged repository changes via Git panel:\s*(.+)$/i);
    return m ? { action: 'commit', message: m[1].trim() } : null;
  }
  return null;
}

async function gitExecuteProposal(proposalId) {
  const proposal = (window.__gitProposals || []).find(p => p.proposal_id === proposalId);
  if (!proposal) {
    showToast('Proposal not found in current list', 'error');
    return;
  }

  const parsed = _gitParseProposalAction(proposal);
  if (!parsed) {
    showToast('Unsupported or malformed Git proposal payload', 'error');
    return;
  }

  try {
    const checkpoint = await gitCreateVortexCheckpoint(`git-${proposalId.slice(0, 16)}-pre-exec`, true);
    let resp;
    if (parsed.action === 'stage') {
      resp = await fetch('/api/git/stage', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ paths: [parsed.path], proposal_id: proposalId })
      });
    } else if (parsed.action === 'unstage') {
      resp = await fetch('/api/git/unstage', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ paths: [parsed.path], proposal_id: proposalId })
      });
    } else {
      resp = await fetch('/api/git/commit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ message: parsed.message, proposal_id: proposalId })
      });
    }

    const data = await resp.json().catch(() => ({}));
    if (!data.ok) throw new Error(data.error || 'execution failed');
    await _finalizeALMProposal(proposalId);
    const cpName = checkpoint?.checkpoint_name || checkpoint?.name || '';
    showToast(`Executed ${parsed.action} proposal${cpName ? ` • snapshot ${cpName}` : ''}`, 'success');
    await gitRefreshStatus({ preserveSelection: true });
    await gitLoadProposals();
  } catch (e) {
    showToast(`Execute failed: ${e.message || e}`, 'error');
  }
}

async function gitCreateVortexCheckpoint(labelHint, silentOnError = false) {
  const safeLabel = String(labelHint || 'git-panel').trim().replace(/[^a-zA-Z0-9_-]+/g, '-').slice(0, 48) || 'git-panel';
  try {
    const res = await fetch('/api/time/checkpoints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        label: safeLabel,
        description: `Git ALM safety checkpoint before execution (${safeLabel})`,
        agent: 'terminal_ui',
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    if (!silentOnError) {
      showToast(`Vortex snapshot created: ${data.checkpoint?.checkpoint_name || safeLabel}`, 'success');
    }
    return data.checkpoint || null;
  } catch (e) {
    if (!silentOnError) {
      showToast(`Vortex snapshot failed: ${e.message || e}`, 'error');
    }
    return null;
  }
}

function gitOpenVortex(proposalId = '') {
  openWindow('time-wizard', '🌀 Vortex', 'view-time-wizard');
  setTimeout(() => {
    const search = document.getElementById('tw-search');
    if (!search) return;
    search.value = proposalId ? String(proposalId) : '';
    if (typeof applyTwFilters === 'function') applyTwFilters();
  }, 200);
}

function _filesAbsPath(relPath) {
  const clean = String(relPath || '').replace(/^\/+/, '');
  return `/home/seven/swarm/${clean}`;
}

function _filesShellQuote(value) {
  return `'${String(value || '').replace(/'/g, `'"'"'`)}'`;
}

async function filesCopyPath(path) {
  const value = _filesAbsPath(path);
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      const el = document.createElement('textarea');
      el.value = value;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    showToast('Copied path', 'success');
  } catch {
    showToast('Copy failed', 'error');
  }
}

function filesOpenInTerminal(path, isDir) {
  const abs = _filesAbsPath(path);
  const cmd = isDir
    ? `ls -la ${_filesShellQuote(abs)}`
    : `sed -n '1,120p' ${_filesShellQuote(abs)}`;

  if (!winManager.windows.get('terminal')) {
    showToast('Open Terminal window first', 'info');
    return;
  }
  cmdTerminal(cmd);
}

function filesGrepInFile(path) {
  const query = prompt('Search pattern in this file (regex supported):', 'TODO|FIXME');
  if (query == null) return;
  const trimmed = query.trim();
  if (!trimmed) return;

  const abs = _filesAbsPath(path);
  const cmd = `rg -n --color never -- ${_filesShellQuote(trimmed)} ${_filesShellQuote(abs)} | head -n 200`;

  if (!winManager.windows.get('terminal')) {
    showToast('Open Terminal window first', 'info');
    return;
  }
  cmdTerminal(cmd);
}

function filesNavigateHome() {
  filesNavigateTo('');
}

function _tableToAgent(table) {
  const map = { memory:'librarian', memory_llama:'llama', memory_qwen:'qwen', memory_gemma:'gemma',
                memory_eight:'eight', memory_nine:'nine', memory_ten:'ten', memory_grok:'grok',
                memory_twelve:'twelve', memory_eleven:'eleven', memory_mistral:'mistral' };
  return map[table] || 'librarian';
}

