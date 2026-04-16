// Files view — file browser, preview, edit, diff, code ops
// Extracted from terminal_base.html

function loadFilesData(win) {
  const listEl = win.el.querySelector('#files-list');
  const pathInput = win.el.querySelector('#files-path-input');
  const findInput = win.el.querySelector('#files-find-input');
  const replaceInput = win.el.querySelector('#files-replace-input');
  const splitter = win.el.querySelector('#files-preview-splitter');
  const previewEl = win.el.querySelector('#files-preview');
  const breadcrumbEl = win.el.querySelector('#files-breadcrumb');
  if (!listEl || !pathInput) return;
  
  window.__filesWin = win;
  window.__filesCurrentPath = '';
  window.__filesCurrentEntries = [];
  window.__filesPreviewState = null;
  window.__filesReplacePlan = null;

  const filesPreviewDefaultWidth = 320;
  const savedWidth = parseInt(localStorage.getItem('fridays-files-preview-width') || '', 10);
  if (previewEl && Number.isFinite(savedWidth) && savedWidth >= 240 && savedWidth <= 760) {
    previewEl.style.flex = `0 0 ${savedWidth}px`;
  }

  if (splitter && previewEl) {
    splitter.onmousedown = (e) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = previewEl.getBoundingClientRect().width;
      const onMove = (ev) => {
        const delta = startX - ev.clientX;
        const nextWidth = Math.max(240, Math.min(760, startWidth + delta));
        previewEl.style.flex = `0 0 ${Math.round(nextWidth)}px`;
      };
      const onUp = () => {
        const finalWidth = Math.round(previewEl.getBoundingClientRect().width);
        if (finalWidth >= 240 && finalWidth <= 760) {
          localStorage.setItem('fridays-files-preview-width', String(finalWidth));
        }
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    };

    splitter.ondblclick = () => {
      previewEl.style.flex = `0 0 ${filesPreviewDefaultWidth}px`;
      localStorage.setItem('fridays-files-preview-width', String(filesPreviewDefaultWidth));
    };
  }
  
  pathInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const path = pathInput.value.trim();
      if (path.toLowerCase().startsWith('find ')) {
        filesSearchByPattern(path.slice(5).trim() || '*');
      } else {
        filesNavigateTo(path || '');
      }
    }
  });

  [findInput, replaceInput].forEach((el) => {
    if (!el) return;
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') filesReplacePreview();
    });
  });
  
  // Load default path
  filesNavigateTo('');
}

function filesNavigateTo(path) {
  const listEl = window.__filesWin?.el?.querySelector('#files-list');
  const pathInput = window.__filesWin?.el?.querySelector('#files-path-input');
  const breadcrumbEl = window.__filesWin?.el?.querySelector('#files-breadcrumb');
  if (!listEl || !pathInput) return;
  
  listEl.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">Loading directory...</div>';
  
  fetch(`/api/workspace/dir?path=${encodeURIComponent(path || '/home/seven/swarm')}`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) {
        listEl.innerHTML = `<div style="padding:12px;color:var(--error);font-size:11px;">Error: ${_escHtml(data.error || 'unknown error')}</div>`;
        return;
      }

      window.__filesCurrentPath = data.path;
      window.__filesCurrentEntries = data.entries || [];
      
      // Update breadcrumb
      const parts = data.path.split('/').filter(p => p);
      let breadcrumb = '<a href="#" data-path="" style="color:var(--accent);text-decoration:none;">swarm</a>';
      let accumulated = '';
      for (const part of parts) {
        accumulated = accumulated + '/' + part;
        breadcrumb += ` / <a href="#" data-path="${_escHtml(accumulated)}" style="color:var(--accent);text-decoration:none;">${_escHtml(part)}</a>`;
      }
      if (breadcrumbEl) {
        breadcrumbEl.innerHTML = breadcrumb;
        breadcrumbEl.querySelectorAll('a').forEach(link => {
          link.onclick = (e) => {
            e.preventDefault();
            filesNavigateTo(link.dataset.path);
          };
        });
      }
      
      // Update path input
      pathInput.value = data.path;
      
      // Render list
      listEl.innerHTML = '';
      if (!data.entries || data.entries.length === 0) {
        listEl.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">Directory is empty</div>';
        return;
      }

      // Parent directory row (.. ) — shown when not at workspace root
      const parentPath = data.path && data.path.includes('/') ? data.path.split('/').slice(0, -1).join('/') : '';
      if (parentPath) {
        const upRow = document.createElement('div');
        upRow.style.cssText = 'padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:11px;transition:background 0.15s;user-select:none;color:var(--text-dim);';
        upRow.onmouseover = () => upRow.style.background = 'rgba(255,255,255,0.05)';
        upRow.onmouseout = () => upRow.style.background = '';
        upRow.innerHTML = '<span style="min-width:20px;"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M2 4h5l1.5 1.5H14v8H2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg></span><span style="flex:1;">.. (parent)</span>';
        upRow.onclick = () => filesNavigateTo(parentPath);
        listEl.appendChild(upRow);
      }

      data.entries.forEach(entry => {
        const row = document.createElement('div');
        row.style.cssText = 'padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:11px;transition:background 0.15s;user-select:none;';
        row.onmouseover = () => row.style.background = 'rgba(255,255,255,0.05)';
        row.onmouseout = () => row.style.background = '';
        
        const icon = entry.type === 'dir' ? '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M2 4h5l1.5 1.5H14v8H2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>' : '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><rect x="3" y="2" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>';
        const sizeStr = entry.type === 'dir' ? '' : ` (${entry.size < 1024 ? '< 1' : Math.round(entry.size / 1024)}KB)`;
        
        let actionBtns = '';
        if (entry.type === 'file') {
          actionBtns = `<button title="Preview" class="file-btn-preview" data-path="${_escHtml(entry.path)}" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8s-2.5 4.5-6.5 4.5S1.5 8 1.5 8z" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.3"/></svg></button>
            <button title="Open in terminal" class="file-btn-terminal" data-path="${_escHtml(entry.path)}" data-isdir="false" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="1.5" y="3" width="13" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M4 7l2 1.5L4 10M8 10h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
            <button title="Search in file" class="file-btn-grep" data-path="${_escHtml(entry.path)}" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><circle cx="7" cy="7" r="4" stroke="currentColor" stroke-width="1.3"/><path d="M10 10l3.5 3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg></button>
            <button title="Copy path" class="file-btn-copy" data-path="${_escHtml(entry.path)}" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="4" y="4" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M4 7H3.5A1.5 1.5 0 012 5.5v-2A1.5 1.5 0 013.5 2h5A1.5 1.5 0 0110 3.5V4" stroke="currentColor" stroke-width="1.3"/></svg></button>`;
        } else {
          actionBtns = `<button title="Open in terminal" class="file-btn-terminal" data-path="${_escHtml(entry.path)}" data-isdir="true" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="1.5" y="3" width="13" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M4 7l2 1.5L4 10M8 10h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
            <button title="Copy path" class="file-btn-copy" data-path="${_escHtml(entry.path)}" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="4" y="4" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M4 7H3.5A1.5 1.5 0 012 5.5v-2A1.5 1.5 0 013.5 2h5A1.5 1.5 0 0110 3.5V4" stroke="currentColor" stroke-width="1.3"/></svg></button>`;
        }
        
        row.innerHTML = `<span style="min-width:20px;">${icon}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(entry.name)}</span><span style="color:var(--text-dim);font-size:10px;white-space:nowrap;">${sizeStr}</span><span style="display:flex;gap:4px;align-items:center;">${actionBtns}</span>`;
        
        if (entry.type === 'dir') {
          row.onclick = () => filesNavigateTo(entry.path);
        } else {
          row.onclick = () => filesPreviewFile(entry);
        }
        
        // Wire up action buttons
        row.querySelectorAll('.file-btn-preview').forEach(btn => {
          btn.onclick = (e) => {
            e.stopPropagation();
            filesPreviewFileByPath(btn.dataset.path);
          };
        });
        row.querySelectorAll('.file-btn-terminal').forEach(btn => {
          btn.onclick = (e) => {
            e.stopPropagation();
            const isDir = btn.dataset.isdir === 'true';
            filesOpenInTerminal(btn.dataset.path, isDir);
          };
        });
        row.querySelectorAll('.file-btn-grep').forEach(btn => {
          btn.onclick = (e) => {
            e.stopPropagation();
            filesGrepInFile(btn.dataset.path);
          };
        });
        row.querySelectorAll('.file-btn-copy').forEach(btn => {
          btn.onclick = (e) => {
            e.stopPropagation();
            filesCopyPath(btn.dataset.path);
          };
        });
        
        listEl.appendChild(row);
      });
    })
    .catch(e => {
      listEl.innerHTML = `<div style="padding:12px;color:var(--error);font-size:11px;">Error: ${e.message}</div>`;
    });
}

function filesSearchByPattern(pattern) {
  const listEl = window.__filesWin?.el?.querySelector('#files-list');
  const breadcrumbEl = window.__filesWin?.el?.querySelector('#files-breadcrumb');
  if (!listEl) return;

  listEl.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">Searching files...</div>';
  if (breadcrumbEl) breadcrumbEl.textContent = `Search: ${pattern}`;

  fetch(`/api/workspace/search?pattern=${encodeURIComponent(pattern)}&max_results=200`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) {
        listEl.innerHTML = `<div style="padding:12px;color:var(--error);font-size:11px;">Error: ${_escHtml(data.error || 'unknown error')}</div>`;
        return;
      }

      const matches = data.matches || [];
      if (!matches.length) {
        listEl.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">No files matched this pattern</div>';
        return;
      }

      listEl.innerHTML = '';
      matches.forEach(entry => {
        const row = document.createElement('div');
        row.style.cssText = 'padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:11px;transition:background 0.15s;user-select:none;';
        row.onmouseover = () => row.style.background = 'rgba(255,255,255,0.05)';
        row.onmouseout = () => row.style.background = '';
        const icon = entry.type === 'dir' ? '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><path d="M2 4h5l1.5 1.5H14v8H2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>' : '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" style="vertical-align:-2px;"><rect x="3" y="2" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>';
        const relPath = entry.path || entry.name;
        const pathToken = encodeURIComponent(relPath || '');
        row.innerHTML = `<span style="min-width:20px;">${icon}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(relPath)}</span><button title="Open in terminal" onclick="event.stopPropagation(); filesOpenInTerminal(decodeURIComponent('${pathToken}'), ${entry.type === 'dir' ? 'true' : 'false'})" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="1.5" y="3" width="13" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M4 7l2 1.5L4 10M8 10h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button><button title="Copy path" onclick="event.stopPropagation(); filesCopyPath(decodeURIComponent('${pathToken}'))" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="4" y="4" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M4 7H3.5A1.5 1.5 0 012 5.5v-2A1.5 1.5 0 013.5 2h5A1.5 1.5 0 0110 3.5V4" stroke="currentColor" stroke-width="1.3"/></svg></button>`;

        if (entry.type === 'dir') {
          row.onclick = () => filesNavigateTo(relPath);
        } else {
          row.onclick = () => filesPreviewFileByPath(relPath);
        }
        listEl.appendChild(row);
      });
    })
    .catch(e => {
      listEl.innerHTML = `<div style="padding:12px;color:var(--error);font-size:11px;">Error: ${e.message}</div>`;
    });
}

async function filesReplacePreview() {
  const listEl = window.__filesWin?.el?.querySelector('#files-list');
  const breadcrumbEl = window.__filesWin?.el?.querySelector('#files-breadcrumb');
  const findInput = window.__filesWin?.el?.querySelector('#files-find-input');
  const replaceInput = window.__filesWin?.el?.querySelector('#files-replace-input');
  const patternInput = window.__filesWin?.el?.querySelector('#files-replace-pattern');
  if (!listEl || !findInput || !replaceInput || !patternInput) return;

  const findText = findInput.value || '';
  const replaceText = replaceInput.value || '';
  const pattern = (patternInput.value || '*.py').trim() || '*.py';
  const scopePath = window.__filesCurrentPath || '';

  if (!findText.trim()) {
    showToast('Find text is required', 'error');
    return;
  }

  listEl.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">Preparing replacement preview...</div>';
  if (breadcrumbEl) breadcrumbEl.textContent = `Replace preview: "${findText}" -> "${replaceText}"`;

  try {
    const resp = await fetch('/api/workspace/replace/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        find_text: findText,
        replace_text: replaceText,
        pattern,
        scope_path: scopePath,
      })
    });
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) throw new Error(data.error || 'preview failed');

    window.__filesReplacePlan = {
      findText,
      replaceText,
      pattern,
      scopePath,
      preview: data,
    };

    const matches = data.matches || [];
    if (!matches.length) {
      listEl.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">No matches found in this scope</div>';
      showToast('No matches found', 'info');
      return;
    }

    listEl.innerHTML = '';
    matches.forEach((entry) => {
      const row = document.createElement('div');
      row.style.cssText = 'padding:10px 12px;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:4px;font-size:11px;';
      const sample = (entry.lines || []).map(n => `L${n}`).join(', ');
      row.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
          <span style="color:var(--text);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(entry.path)}</span>
          <span style="color:var(--accent);font-size:10px;white-space:nowrap;">${entry.occurrences} hit${entry.occurrences === 1 ? '' : 's'}</span>
        </div>
        <div style="color:var(--text-dim);font-size:10px;">${sample ? `lines ${_escHtml(sample)}` : 'line numbers unavailable'}</div>
      `;
      row.onclick = () => filesPreviewFileByPath(entry.path);
      listEl.appendChild(row);
    });

    showToast(`Preview ready: ${data.total_replacements} replacement${data.total_replacements === 1 ? '' : 's'} in ${data.matched_files} file${data.matched_files === 1 ? '' : 's'}`, 'success');
  } catch (e) {
    listEl.innerHTML = `<div style="padding:12px;color:var(--error);font-size:11px;">Error: ${_escHtml(e.message || e)}</div>`;
    showToast(`Replace preview failed: ${e.message || e}`, 'error');
  }
}

async function filesReplaceApply() {
  const plan = window.__filesReplacePlan;
  if (!plan) {
    showToast('Run Preview first', 'error');
    return;
  }

  if (!confirm(`Apply ${plan.preview?.total_replacements || 0} replacements across ${plan.preview?.matched_files || 0} files?`)) {
    return;
  }

  let proposalId = null;
  try {
    const alm = await fetch('/api/alm/status').then(r => r.json()).catch(() => null);
    if (alm && alm.status === 'enforced') {
      const createResp = await fetch('/api/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent: 'terminal_ui',
          title: 'Workspace bulk replace',
          description: `Replace "${plan.findText}" with "${plan.replaceText}" in ${plan.pattern}`,
          priority: 4,
        })
      });
      const created = await createResp.json().catch(() => ({}));
      proposalId = created.proposal_id;
      if (!proposalId) throw new Error('ALM proposal creation failed');

      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'approved' })
      });
    }

    const resp = await fetch('/api/workspace/replace/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        find_text: plan.findText,
        replace_text: plan.replaceText,
        pattern: plan.pattern,
        scope_path: plan.scopePath,
        proposal_id: proposalId,
      })
    });
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) throw new Error(data.error || 'replace apply failed');

    if (proposalId) {
      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'executed' })
      }).catch(() => {});
    }

    showToast(`Applied ${data.total_replacements} replacement${data.total_replacements === 1 ? '' : 's'} in ${data.changed_files} file${data.changed_files === 1 ? '' : 's'}`, 'success');
    window.__filesReplacePlan = null;
    filesNavigateTo(window.__filesCurrentPath || '');
  } catch (e) {
    if (proposalId) {
      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'rejected' })
      }).catch(() => {});
    }
    showToast(`Replace apply failed: ${e.message || e}`, 'error');
  }
}

function filesPreviewFile(entry) {
  const previewEl = window.__filesWin?.el?.querySelector('#files-preview');
  const splitterEl = window.__filesWin?.el?.querySelector('#files-preview-splitter');
  const bodyEl = window.__filesWin?.el?.querySelector('#files-preview-body');
  if (!previewEl || !bodyEl) return;
  
  bodyEl.textContent = 'Loading file...';
  previewEl.style.display = 'flex';
  if (splitterEl) splitterEl.style.display = 'block';
  
  fetch(`/api/workspace/file?path=${encodeURIComponent(entry.path)}&max_bytes=10000`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) {
        bodyEl.textContent = `Error: ${data.error}`;
        return;
      }

      window.__filesPreviewState = {
        path: data.path,
        content: data.content || '',
        originalContent: data.content || '',
        size: data.size || 0,
        truncated: !!data.truncated,
        editing: false,
      };
      filesRenderPreview();
    })
    .catch(e => {
      bodyEl.textContent = `Error: ${e.message}`;
    });
}

function filesHidePreview() {
  const previewEl = window.__filesWin?.el?.querySelector('#files-preview');
  const splitterEl = window.__filesWin?.el?.querySelector('#files-preview-splitter');
  if (previewEl) previewEl.style.display = 'none';
  if (splitterEl) splitterEl.style.display = 'none';
}

function filesRenderPreview() {
  const bodyEl = window.__filesWin?.el?.querySelector('#files-preview-body');
  const state = window.__filesPreviewState;
  if (!bodyEl || !state) return;

  const codeOpsPanel = window.__filesWin?.el?.querySelector('#files-code-ops');
  const isSupportedType = state.path && /\.(py|js|jsx|ts|tsx|yaml|yml|json)$/i.test(state.path);
  if (codeOpsPanel) {
    codeOpsPanel.style.display = (state.editing || !isSupportedType) ? 'none' : 'block';
  }

  const relPath = state.path || '';
  const sizeKb = Math.max(1, Math.round((state.size || 0) / 1024));
  const truncatedBadge = state.truncated
    ? '<span style="padding:2px 6px;border:1px solid #f7b84b88;border-radius:10px;color:#f7b84b;font-size:10px;">truncated</span>'
    : '';

  if (!state.editing) {
    const content = state.content || '';
    bodyEl.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:8px;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
          <div style="min-width:0;display:flex;flex-direction:column;gap:3px;">
            <div style="font-size:11px;color:var(--text);font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(relPath)}</div>
            <div style="font-size:10px;color:var(--text-dim);">${sizeKb} KB</div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;">${truncatedBadge}<button onclick="filesStartEdit()" style="background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:4px 8px;cursor:pointer;font-size:10px;">Edit</button></div>
        </div>
        <pre style="margin:0;white-space:pre-wrap;word-break:break-word;color:var(--text-dim);font-family:monospace;font-size:11px;line-height:1.45;max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:6px;padding:8px;background:rgba(0,0,0,0.15);">${_escHtml(content)}${state.truncated ? '\n\n[…file truncated, showing first 10KB]' : ''}</pre>
      </div>`;
    return;
  }

  bodyEl.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:8px;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <div style="min-width:0;display:flex;flex-direction:column;gap:3px;">
          <div style="font-size:11px;color:var(--text);font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(relPath)}</div>
          <div style="font-size:10px;color:var(--text-dim);">Editing mode</div>
        </div>
        <div style="display:flex;gap:6px;align-items:center;">
          <button onclick="filesCancelEdit()" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:4px 8px;cursor:pointer;font-size:10px;">Cancel</button>
          <button onclick="filesSaveEdit()" style="background:var(--accent);border:1px solid var(--accent);color:#000;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:10px;font-weight:700;">Save</button>
        </div>
      </div>
      <textarea id="files-editor" style="width:100%;min-height:360px;max-height:560px;resize:vertical;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-size:11px;font-family:monospace;line-height:1.45;outline:none;">${_escHtml(state.content || '')}</textarea>
    </div>`;
}

function filesStartEdit() {
  const state = window.__filesPreviewState;
  if (!state) return;
  if (state.truncated) {
    showToast('File preview is truncated; open in terminal for full edits', 'error');
    return;
  }
  state.editing = true;
  filesRenderPreview();
}

function filesCancelEdit() {
  const state = window.__filesPreviewState;
  if (!state) return;
  state.editing = false;
  state.content = state.originalContent;
  filesRenderPreview();
}

function _filesGenerateDiff(original, modified) {
  // Simple line-by-line diff with context
  const origLines = original.split('\n');
  const modLines = modified.split('\n');
  const maxLen = Math.max(origLines.length, modLines.length);
  const changes = [];
  
  for (let i = 0; i < maxLen; i++) {
    const origLine = origLines[i] || '';
    const modLine = modLines[i] || '';
    if (origLine !== modLine) {
      changes.push({
        lineNum: i + 1,
        type: origLine ? (modLine ? 'changed' : 'removed') : 'added',
        original: origLine,
        modified: modLine,
      });
    }
  }
  return changes;
}

function _filesShowDiffModal(filePath, originalContent, newContent) {
  // Create modal to show diff
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:10000;';
  modal.id = 'files-diff-modal';
  
  const changes = _filesGenerateDiff(originalContent, newContent);
  const changesSummary = {
    added: changes.filter(c => c.type === 'added').length,
    removed: changes.filter(c => c.type === 'removed').length,
    changed: changes.filter(c => c.type === 'changed').length,
  };
  
  let diffHtml = '<div style="display:flex;flex-direction:column;gap:4px;max-height:360px;overflow-y:auto;">';
  
  changes.forEach(change => {
    const bgColor = change.type === 'added' ? 'rgba(76,175,80,0.15)' 
                  : change.type === 'removed' ? 'rgba(244,67,54,0.15)'
                  : 'rgba(255,193,7,0.15)';
    const textColor = change.type === 'added' ? '#4caf50'
                    : change.type === 'removed' ? '#f44336'
                    : '#ffc107';
    
    const icon = change.type === 'added' ? '+ ' : change.type === 'removed' ? '- ' : '~ ';
    
    diffHtml += `
      <div style="background:${bgColor};border-left:3px solid ${textColor};padding:6px 8px;font-family:monospace;font-size:10px;line-height:1.4;color:var(--text-dim);">
        <div style="color:${textColor};font-weight:700;margin-bottom:3px;font-size:9px;">Line ${change.lineNum}</div>
        ${change.type !== 'added' ? `<div style="margin-bottom:2px;white-space:pre-wrap;word-break:break-all;opacity:0.7;"><span style="opacity:0.5;">${icon}</span>${_escHtml(change.original)}</div>` : ''}
        ${change.type !== 'removed' ? `<div style="white-space:pre-wrap;word-break:break-all;"><span style="opacity:0.5;">${icon}</span>${_escHtml(change.modified)}</div>` : ''}
      </div>
    `;
  });
  
  diffHtml += '</div>';
  
  const content = document.createElement('div');
  content.style.cssText = 'background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;max-width:600px;max-height:80vh;display:flex;flex-direction:column;gap:12px;box-shadow:0 10px 40px rgba(0,0,0,0.3);';
  
  content.innerHTML = `
    <div>
      <div style="font-size:12px;font-weight:700;color:var(--text);margin-bottom:8px;"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-1px;"><rect x="4" y="4" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M4 7H3.5A1.5 1.5 0 012 5.5v-2A1.5 1.5 0 013.5 2h5A1.5 1.5 0 0110 3.5V4" stroke="currentColor" stroke-width="1.3"/></svg> Review Changes</div>
      <div style="font-size:10px;color:var(--text-dim);margin-bottom:8px;">
        <span style="color:#4caf50;">+ ${changesSummary.added} added</span> · 
        <span style="color:#f44336;">- ${changesSummary.removed} removed</span> · 
        <span style="color:#ffc107;">~ ${changesSummary.changed} changed</span>
      </div>
    </div>
    <div style="flex:1;border:1px solid var(--border);border-radius:6px;padding:8px;overflow-y:auto;background:rgba(0,0,0,0.15);">
      ${diffHtml}
    </div>
    <div style="display:flex;gap:6px;justify-content:flex-end;">
      <button id="files-diff-cancel" style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:6px 12px;cursor:pointer;font-size:10px;">Cancel</button>
      <button id="files-diff-confirm" style="background:var(--accent);border:1px solid var(--accent);color:#000;border-radius:4px;padding:6px 12px;cursor:pointer;font-size:10px;font-weight:700;">Confirm & Save</button>
    </div>
  `;
  
  modal.appendChild(content);
  document.body.appendChild(modal);
  
  const cancelBtn = modal.querySelector('#files-diff-cancel');
  const confirmBtn = modal.querySelector('#files-diff-confirm');
  
  cancelBtn.onclick = () => modal.remove();
  confirmBtn.onclick = async () => {
    modal.remove();
    await filesSaveEditConfirmed(newContent);
  };
}

async function filesSaveEdit() {
  const state = window.__filesPreviewState;
  const bodyEl = window.__filesWin?.el?.querySelector('#files-preview-body');
  const editor = window.__filesWin?.el?.querySelector('#files-editor');
  if (!state || !editor || !bodyEl) return;

  const nextContent = editor.value;
  if (nextContent === state.originalContent) {
    showToast('No changes to save', 'error');
    return;
  }

  // Show diff preview modal
  _filesShowDiffModal(state.path, state.originalContent, nextContent);
}

async function filesSaveEditConfirmed(nextContent) {
  const state = window.__filesPreviewState;
  const bodyEl = window.__filesWin?.el?.querySelector('#files-preview-body');
  if (!state || !bodyEl) return;

  let proposalId = null;
  try {
    const alm = await fetch('/api/alm/status').then(r => r.json()).catch(() => null);
    if (alm && alm.status === 'enforced') {
      const createResp = await fetch('/api/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent: 'terminal_ui',
          title: 'Workspace file edit',
          description: `Edit file via Files panel: ${state.path}`,
          priority: 4,
        })
      });
      const created = await createResp.json().catch(() => ({}));
      proposalId = created.proposal_id;
      if (!proposalId) throw new Error('ALM proposal creation failed');

      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'approved' })
      });
    }

    bodyEl.innerHTML = '<div style="padding:10px;color:var(--text-dim);font-size:11px;">Saving file...</div>';
    const saveResp = await fetch('/api/workspace/file', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: state.path,
        content: nextContent,
        proposal_id: proposalId,
      })
    });
    const saved = await saveResp.json().catch(() => ({}));
    if (!saved.ok) throw new Error(saved.error || 'save failed');

    if (proposalId) {
      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'executed' })
      }).catch(() => {});
    }

    state.originalContent = nextContent;
    state.content = nextContent;
    state.editing = false;
    state.size = saved.size || state.size;
    showToast('File saved', 'success');
    filesRenderPreview();
  } catch (e) {
    showToast(`Save failed: ${e.message || e}`, 'error');
    if (proposalId) {
      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'rejected' })
      }).catch(() => {});
    }
    state.editing = true;
    filesRenderPreview();
  }
}

function filesPreviewFileByPath(path) {
  filesPreviewFile({ path, type: 'file', name: path.split('/').pop() || path });
}

async function codeOpRunTests() {
  const state = window.__filesPreviewState;
  if (!state) { showToast('No file selected', 'error'); return; }
  
  const statusEl = document.getElementById('files-op-status');
  const statusText = document.getElementById('files-op-status-text');
  statusEl.style.display = 'block';
  statusText.textContent = 'Running tests...';
  
  try {
    const resp = await fetch('/api/code-ops/pytest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: state.path })
    });
    const result = await resp.json().catch(() => ({}));
    if (!result.ok) {
      statusText.innerHTML = `<span style="color:#f44336;">❌ ${_escHtml(result.error || 'Test failed')}</span>`;
      showToast(`Tests failed: ${result.error || 'unknown error'}`, 'error');
    } else {
      const passed = result.passed || 0;
      const failed = result.failed || 0;
      const total = passed + failed;
      statusText.innerHTML = `<span style="color:#4caf50;">✓ Tests: ${passed}/${total} passed</span> ${result.duration ? `<span style="color:var(--text-dim);">(${result.duration.toFixed(2)}s)</span>` : ''}`;
      showToast(`Tests: ${passed}/${total} passed`, 'success');
    }
  } catch (e) {
    statusText.innerHTML = `<span style="color:#f44336;">Error: ${_escHtml(e.message || e)}</span>`;
  }
}

async function codeOpLintFile() {
  const state = window.__filesPreviewState;
  if (!state || !state.path.endsWith('.py')) { showToast('Only Python files supported', 'error'); return; }
  
  const statusEl = document.getElementById('files-op-status');
  const statusText = document.getElementById('files-op-status-text');
  statusEl.style.display = 'block';
  statusText.textContent = 'Linting...';
  
  try {
    const resp = await fetch('/api/code-ops/pylint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: state.path })
    });
    const result = await resp.json().catch(() => ({}));
    if (!result.ok) {
      const count = result.issues ? result.issues.length : 0;
      statusText.innerHTML = `<span style="color:#ffc107;">⚠ ${count} issue${count !== 1 ? 's' : ''} found</span>`;
      const msg = result.issues ? result.issues.slice(0, 3).map(i => `${i.line}: ${i.msg}`).join('; ') : result.error;
      showToast(`Lint issues: ${msg}`, 'info');
    } else {
      statusText.innerHTML = `<span style="color:#4caf50;">✓ No lint issues</span>`;
      showToast('No lint issues', 'success');
    }
  } catch (e) {
    statusText.innerHTML = `<span style="color:#f44336;">Error: ${_escHtml(e.message || e)}</span>`;
  }
}

async function codeOpFormatFile() {
  const state = window.__filesPreviewState;
  if (!state || !state.path.endsWith('.py')) { showToast('Only Python files supported', 'error'); return; }
  
  const statusEl = document.getElementById('files-op-status');
  const statusText = document.getElementById('files-op-status-text');
  statusEl.style.display = 'block';
  statusText.textContent = 'Formatting...';
  
  try {
    const resp = await fetch('/api/code-ops/format', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: state.path, content: state.content })
    });
    const result = await resp.json().catch(() => ({}));
    if (!result.ok) {
      statusText.innerHTML = `<span style="color:#f44336;">❌ ${_escHtml(result.error || 'Format failed')}</span>`;
      showToast(`Format failed: ${result.error}`, 'error');
    } else {
      state.content = result.formatted_content;
      state.originalContent = result.formatted_content;
      statusText.innerHTML = `<span style="color:#4caf50;">✓ Formatted (${result.lines_changed} lines)</span>`;
      showToast(`Code formatted (${result.lines_changed} lines changed)`, 'success');
      filesRenderPreview();
    }
  } catch (e) {
    statusText.innerHTML = `<span style="color:#f44336;">Error: ${_escHtml(e.message || e)}</span>`;
  }
}

async function codeOpCommit() {
  const state = window.__filesPreviewState;
  if (!state) { showToast('No file selected', 'error'); return; }
  
  const msg = prompt('Commit message:');
  if (!msg) return;
  
  const statusEl = document.getElementById('files-op-status');
  const statusText = document.getElementById('files-op-status-text');
  statusEl.style.display = 'block';
  statusText.textContent = 'Creating commit...';
  
  let proposalId = null;
  try {
    const alm = await fetch('/api/alm/status').then(r => r.json()).catch(() => null);
    if (alm && alm.status === 'enforced') {
      const createResp = await fetch('/api/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent: 'terminal_ui',
          title: 'Git commit',
          description: `Commit via Files panel: ${msg}`,
          priority: 3,
        })
      });
      const created = await createResp.json().catch(() => ({}));
      proposalId = created.proposal_id;
      if (!proposalId) throw new Error('ALM proposal creation failed');
      
      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'approved' })
      });
    }
    
    const resp = await fetch('/api/code-ops/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, proposal_id: proposalId })
    });
    const result = await resp.json().catch(() => ({}));
    if (!result.ok) {
      statusText.innerHTML = `<span style="color:#f44336;">❌ ${_escHtml(result.error || 'Commit failed')}</span>`;
      showToast(`Commit failed: ${result.error}`, 'error');
      if (proposalId) {
        await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: 'rejected' })
        }).catch(() => {});
      }
    } else {
      statusText.innerHTML = `<span style="color:#4caf50;">✓ Committed: ${_escHtml(result.commit_hash ? result.commit_hash.substring(0, 7) : 'done')}</span>`;
      showToast(`Changes committed (${result.files_changed} files)`, 'success');
      if (proposalId) {
        await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: 'executed' })
        }).catch(() => {});
      }
    }
  } catch (e) {
    statusText.innerHTML = `<span style="color:#f44336;">Error: ${_escHtml(e.message || e)}</span>`;
    if (proposalId) {
      await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'rejected' })
      }).catch(() => {});
    }
  }
}

