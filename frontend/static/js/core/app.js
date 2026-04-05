// Core app — window opening, home, navigation
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// WINDOW FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

function openWindow(id, title, templateId) {
  _troubleshootLog('info', 'openWindow requested', `id=${id} title=${title} template=${templateId}`);
  // Strip any existing emoji from title  
  const cleanTitle = title.replace(/^[^\w\s]+ /, '').trim();
  const icon = windowIcons[id] || '📦';
  const titleWithIcon = `${icon} ${cleanTitle}`;
  let windowKey = id;
  let windowTitle = titleWithIcon;
  const existing = winManager.windows.get(id);
  if (existing && !existing.minimized) {
    // Window is open — clicking again toggles it to minimized
    winManager.minimize(id);
    return;
  }
  if (existing && existing.minimized) {
    let n = 2;
    while (winManager.windows.has(`${id}__${n}`)) n += 1;
    windowKey = `${id}__${n}`;
    windowTitle = `${titleWithIcon} ${n}`;
  }
  const win = winManager.create(windowKey, windowTitle, templateId, { baseId: id });
  if (!win) {
    _troubleshootLog('error', 'winManager.create returned no window', `id=${id}`);
    return;
  }
  
  // Load data based on window type
  setTimeout(() => {
    try {
      if (id === 'chat') loadChatData(win);
      else if (id === 'terminal') loadTerminalData(win);
      else if (id === 'files') loadFilesData(win);
      else if (id === 'git') loadGitData(win);
      else if (id === 'memory') loadMemoryData(win);
      else if (id === 'monitor') loadMonitorData(win);
      else if (id === 'docs') loadDocsData(win);
      else if (id === 'skills') loadSkillsData(win);
      else if (id === 'tickets') loadTicketsData(win);
      else if (id === 'studio') loadStudioData(win);
      else if (id === 'time-wizard') initTimeWizard();
      else if (id === 'ghost-brief') initGhostBrief();
      else if (id === 'access') loadAccessData(win);
      else if (id === 'agents-config') loadAgentsConfigData(win);
      _troubleshootLog('info', 'Window opened', `id=${windowKey} base=${id}`);
    } catch (err) {
      _troubleshootLog('error', 'Window loader failed', `id=${windowKey} base=${id} error=${err?.message || err}`);
      throw err;
    }
  }, 100);
  
  showToast(`Opened ${cleanTitle}`, 'success');
}

function goHome() {
  // Close all open windows and return to home
  Array.from(winManager.windows.keys()).forEach(id => {
    winManager.close(id);
  });
}

function bindHomeLaunchClicks() {
  const launchNodes = Array.from(document.querySelectorAll('#quick-cards .home-card, #home-content .stat-card'));
  launchNodes.forEach((node) => {
    if (node.dataset.launchBound === '1') return;
    node.dataset.launchBound = '1';
    node.addEventListener('click', (event) => {
      // Primary path: data attributes. Fallback: legacy inline onclick parser.
      if (event.defaultPrevented) return;
      let winId = String(node.dataset.winId || '').trim();
      let winTitle = String(node.dataset.winTitle || '').trim();
      let winTemplate = String(node.dataset.winTemplate || '').trim();
      if (!winId || !winTitle || !winTemplate) {
        const inline = String(node.getAttribute('onclick') || '');
        const match = inline.match(/openWindow\('([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\)/);
        if (!match) return;
        winId = match[1];
        winTitle = match[2];
        winTemplate = match[3];
      }
      event.preventDefault();
      try {
        _troubleshootLog('info', 'Card click launch', `id=${winId} template=${winTemplate}`);
        openWindow(winId, winTitle, winTemplate);
        const afterOpen = String(node.dataset.afterOpen || '').trim();
        if (afterOpen.startsWith('docsSetTab:')) {
          const tab = afterOpen.split(':')[1] || 'all';
          setTimeout(() => {
            if (typeof docsSetTab === 'function') docsSetTab(tab);
          }, 120);
        }
      } catch (err) {
        _troubleshootLog('error', 'Card click launch failed', String(err?.message || err));
        showToast('Open window failed: ' + (err?.message || err), 'error');
      }
    }, { capture: true });
  });
}

