// Boot sequence — DOMContentLoaded, intervals, SSE
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  // Load settings and apply time-of-day theme
  loadSettings();
  initClocks();
  bindHomeLaunchClicks();
  initHomeCardReorder();
  initHomeHeaderCollapse();
  _renderTroubleshootBadge();

  // Wire header buttons via JS (inline onclick may be suppressed)
  document.getElementById('troubleshoot-btn')?.addEventListener('click', () => toggleTroubleshootPanel());
  document.getElementById('auth-user-pill')?.addEventListener('click', () => openIdentityManager());
  document.getElementById('home-help-btn')?.addEventListener('click', () => openWindowHelp('home'));
  document.getElementById('home-settings-btn')?.addEventListener('click', () => toggleSettings());
  document.getElementById('troubleshoot-toggle-btn')?.addEventListener('click', () => toggleTroubleshootEnabled());
  document.getElementById('troubleshoot-close-btn')?.addEventListener('click', () => {
    const state = _troubleshootState();
    state.panelOpen = false;
    document.getElementById('troubleshoot-modal')?.classList.remove('open');
    _renderTroubleshootBadge();
  });
  document.getElementById('troubleshoot-clear-btn')?.addEventListener('click', () => clearTroubleshootLogs());
  document.getElementById('troubleshoot-copy-btn')?.addEventListener('click', () => copyTroubleshootLogs());
  _initTroubleshootDrag();

  // Clicking empty home background should minimize open windows to taskbar.
  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!target) return;
    if (!target.closest('#home-page')) return;
    if (target.closest('.floating-window, #taskbar, #settings-modal, #troubleshoot-modal, #command-palette')) return;
    if (target.closest('.home-card, .stat-card, .chat-action-btn, button, a, input, textarea, select, [role="button"], [onclick], [data-win-id]')) return;
    if (!winManager || !winManager.windows || winManager.windows.size === 0) return;
    winManager.minimizeAllToTaskbar();
  }, true);

  document.addEventListener('click', (event) => {
    const state = _troubleshootState();
    if (!state.enabled) return;
    const target = event.target;
    if (target?.closest?.('#troubleshoot-modal')) return;
    _troubleshootLog('info', 'Click', _troubleshootTargetLabel(target));
  }, true);

  window.addEventListener('error', (event) => {
    const msg = event?.message || 'Unknown script error';
    const where = `${event?.filename || 'unknown'}:${event?.lineno || 0}:${event?.colno || 0}`;
    _troubleshootLog('error', msg, where);
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event?.reason;
    const text = reason && reason.message ? reason.message : String(reason || 'Unhandled rejection');
    _troubleshootLog('error', 'Unhandled promise rejection', text);
  });
  
  // Update time-of-day theme every minute
  setInterval(() => {
    const selectedMode = String(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto').toLowerCase();
    if (selectedMode === 'auto') {
      applyTimeTheme('auto');
    }
  }, 60000);
  
  _loadAgentRegistry(); // Load agent numbers + labels from DB — updates CHAT_AGENT_OPTIONS
  loadHomeStats(); // Load system stats with colors and trends
  setInterval(loadHomeStats, 10000); // Update stats every 10 seconds
  loadServicesPanel(); // Load service status + restart buttons
  setInterval(loadServicesPanel, 30000); // Refresh every 30 seconds
  loadOllamaPanel(); // Load Ollama model panel
  setInterval(loadOllamaPanel, 15000); // Refresh every 15 seconds
  loadAttentionPanel(); // Needs-attention summary → delegates to System Pulse
  setInterval(loadAttentionPanel, 30000); // Refresh every 30 seconds
  updateActivityLog();
  setInterval(updateActivityLog, 5000);
  updateTicketQueue();
  setInterval(updateTicketQueue, 10000);
  loadAuthProfiles();
  _renderIdentityPill();
  initChatSpellHelper();
  populateRelayRuleTargetOptions();
  renderRelayRuleList();
  startChatLiveSyncService();
  _librarianStartWatchdog();
  
  // Settings modal handlers
  document.querySelectorAll('[data-time]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('[data-time]').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
    });
  });
  
  document.getElementById('opacity-slider').addEventListener('input', (e) => {
    const transparency = Math.max(0, Math.min(30, parseInt(e.target.value || '5', 10)));
    const actualOpacity = (100 - transparency) / 100;
    document.getElementById('opacity-value').textContent = transparency + '%';
    document.documentElement.style.setProperty('--glass-opacity', actualOpacity);
  });
  
  // (time-slider removed — themes are now applied directly from buttons)


  document.getElementById('close-settings').addEventListener('click', saveSettings);
  
  // Close settings on click outside
  document.getElementById('settings-modal').addEventListener('click', (e) => {
    if (e.target.id === 'settings-modal') {
      closeSettings();
    }
  });

  _renderTroubleshootPanel();
  
  // Show keyboard hints (auto-hide after 5 seconds)
  const hints = document.getElementById('keyboard-hints');
  hints.style.display = 'block';
  setTimeout(() => {
    hints.classList.add('fade-out');
    setTimeout(() => { hints.style.display = 'none'; }, 300);
  }, 5000);
  
  // Command palette + ESC + global shortcuts (capture phase for consistency)
  document.addEventListener('keydown', (e) => {
    // Skip shortcuts when typing in an input/textarea
    const tag = (e.target.tagName || '').toLowerCase();
    const isInput = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;

    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const palette = document.getElementById('command-palette');
      palette.classList.toggle('open');
      if (palette.classList.contains('open')) {
        document.getElementById('command-palette-input').focus();
      }
      return;
    }

    // Ctrl+T — Open Tickets
    if ((e.ctrlKey || e.metaKey) && e.key === 't' && !isInput) {
      e.preventDefault();
      if (typeof openWindow === 'function') openWindow('tickets', 'Tickets', 'view-tickets');
      return;
    }

    // Ctrl+P — Open Studio (proposals)
    if ((e.ctrlKey || e.metaKey) && e.key === 'p' && !isInput) {
      e.preventDefault();
      if (typeof openWindow === 'function') openWindow('studio', 'Studio', 'view-studio');
      return;
    }

    // Ctrl+H — Go Home
    if ((e.ctrlKey || e.metaKey) && e.key === 'h' && !isInput) {
      e.preventDefault();
      if (typeof goHome === 'function') goHome();
      return;
    }

    // Ctrl+J — Open Chat
    if ((e.ctrlKey || e.metaKey) && e.key === 'j' && !isInput) {
      e.preventDefault();
      if (typeof openWindow === 'function') openWindow('chat', 'Chat', 'view-chat');
      return;
    }

    // Ctrl+G — Open Git
    if ((e.ctrlKey || e.metaKey) && e.key === 'g' && !isInput) {
      e.preventDefault();
      if (typeof openWindow === 'function') openWindow('git', 'Git', 'view-git');
      return;
    }

    // Ctrl+E — Open Email
    if ((e.ctrlKey || e.metaKey) && e.key === 'e' && !isInput) {
      e.preventDefault();
      if (typeof openWindow === 'function') openWindow('email', 'Email', 'view-email');
      return;
    }

    // Ctrl+B — Open Knowledge
    if ((e.ctrlKey || e.metaKey) && e.key === 'b' && !isInput) {
      e.preventDefault();
      if (typeof openWindow === 'function') openWindow('knowledge', 'Knowledge', 'view-knowledge');
      return;
    }

    // ? — Show keyboard shortcuts help (only when not in input)
    if (e.key === '?' && !isInput && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      const modal = document.getElementById('shortcuts-help-modal');
      if (modal) modal.classList.toggle('open');
      return;
    }

    // ESC invariant: close top overlay first, else close top window.
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      // Close shortcuts help modal first
      const shortcutsModal = document.getElementById('shortcuts-help-modal');
      if (shortcutsModal?.classList.contains('open')) {
        shortcutsModal.classList.remove('open');
        return;
      }
      if (closeTopModal()) return;
      if (closeTopWindow()) return;
      const palette = document.getElementById('command-palette');
      if (palette?.classList.contains('open')) {
        palette.classList.remove('open');
      }
    }
  }, true);
  
  // Command palette search
  const paletteInput = document.getElementById('command-palette-input');
  paletteInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    const results = document.getElementById('command-palette-results');
    
    const commands = [
      { label: 'Chat', onclick: 'openWindow("chat", "Chat", "view-chat")', hint: 'Ctrl+J' },
      { label: 'Terminal', onclick: 'openWindow("terminal", "Terminal", "view-terminal")', hint: '' },
      { label: 'Knowledge', onclick: 'openWindow("knowledge", "Knowledge", "view-knowledge")', hint: 'Ctrl+B' },
      { label: 'Files', onclick: 'openWindow("files", "Files", "view-files")', hint: '' },
      { label: 'Git', onclick: 'openWindow("git", "Git", "view-git")', hint: 'Ctrl+G' },
      { label: 'Memory', onclick: 'openWindow("memory", "Memory", "view-memory")', hint: '' },
      { label: 'Monitor', onclick: 'openWindow("monitor", "Monitor", "view-monitor")', hint: '' },
      { label: 'Documents', onclick: 'openWindow("docs", "Documents", "view-docs")', hint: '' },
      { label: 'Skills', onclick: 'openWindow("skills", "Skills", "view-skills")', hint: '' },
      { label: 'Tickets', onclick: 'openWindow("tickets", "Tickets", "view-tickets")', hint: 'Ctrl+T' },
      { label: 'Studio', onclick: 'openWindow("studio", "Studio", "view-studio")', hint: 'Ctrl+P' },
      { label: 'Email', onclick: 'openWindow("email", "Email", "view-email")', hint: 'Ctrl+E' },
      { label: 'Library', onclick: 'openWindow("library", "Library", "view-library")', hint: '' },
      { label: 'Vortex', onclick: 'openWindow("time-wizard", "Vortex", "view-time-wizard")', hint: '' },
      { label: 'Feeds', onclick: 'openWindow("feeds", "Feeds", "view-feeds")', hint: '' },
      { label: 'VPN', onclick: 'openWindow("vpn", "VPN", "view-vpn")', hint: '' },
      { label: 'Home', onclick: 'goHome()', hint: 'Ctrl+H' },
    ];
    
    const filtered = commands.filter(c => c.label.toLowerCase().includes(query));
    results.innerHTML = filtered.map(c => `
      <div class="palette-item" onclick="${c.onclick}; document.getElementById('command-palette').classList.remove('open');">
        <span>${c.label}</span>${c.hint ? `<span style="font-size:10px;color:var(--text-dim);margin-left:auto;opacity:0.7;">${c.hint}</span>` : ''}
      </div>
    `).join('');
  });
  
  // Filter activity log
  document.getElementById('activity-filter').addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    document.querySelectorAll('#activity-log .activity-item').forEach(item => {
      item.style.display = item.textContent.toLowerCase().includes(query) ? 'block' : 'none';
    });
  });
  
  // Filter ticket queue
  document.getElementById('ticket-filter').addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    document.querySelectorAll('#ticket-queue .ticket-item').forEach(item => {
      item.style.display = item.textContent.toLowerCase().includes(query) ? 'flex' : 'none';
    });
  });
  
  // Close palette on click outside
  document.getElementById('command-palette').addEventListener('click', (e) => {
    if (e.target.id === 'command-palette') {
      e.target.classList.remove('open');
    }
  });
  
  // ESC key closes focused/topmost window (already handled above)
});

function initHomeHeaderCollapse() {
  const homePage = document.getElementById('home-page');
  const homeContent = document.getElementById('home-content');
  if (!homePage || !homeContent) return;

  const syncHeaderState = () => {
    homePage.classList.toggle('header-collapsed', homeContent.scrollTop > 24);
  };

  homeContent.addEventListener('scroll', syncHeaderState, { passive: true });
  syncHeaderState();
}

function updateActivityLog() {
  const log = document.getElementById('activity-log');
  if (!log) return;
  
  fetch('/api/activity')
    .then(r => r.json())
    .then(data => {
      if (data.activities && data.activities.length > 0) {
        log.innerHTML = data.activities.slice(0, 10).map(act => {
          let color = 'var(--text)';
          if (act.level === 'error') color = '#f77';
          else if (act.level === 'warning') color = '#ffa500';
          else if (act.level === 'success') color = '#4caf50';
          return `<div class="activity-item" style="color: ${color};"><span style="color: var(--text-dim); font-size: 9px;">[${act.timestamp}]</span> ${act.message}</div>`;
        }).join('');
      }
    })
    .catch(e => {
      log.innerHTML = '<div style="padding: 12px; color: var(--text-dim);">Activity log unavailable</div>';
    });
}

function updateTicketQueue() {
  const queue = document.getElementById('ticket-queue');
  if (!queue) return;

  fetch('/api/tickets?status=open')
    .then(r => r.json())
    .then(data => {
      const all = Array.isArray(data) ? data : (data.tickets || []);
      // Belt-and-braces: filter client-side in case API doesn't support ?status
      const open = all.filter(t => t.status !== 'closed').slice(0, 8);
      if (open.length > 0) {
        queue.innerHTML = open.map(t => {
          const num   = t.number || t.ticket_number || '?';
          const title = (t.title || t.question || 'Untitled').slice(0, 60);
          const st    = t.status || 'unknown';
          const stColor = st === 'open' ? '#4caf50' : st === 'in_progress' ? '#ffa500' : '#888';
          const stBg    = st === 'open' ? 'rgba(76,175,80,0.15)' : st === 'in_progress' ? 'rgba(255,165,0,0.15)' : 'rgba(136,136,136,0.15)';
          return `<div class="ticket-item" style="display:flex;justify-content:space-between;align-items:center;" onclick='openTicketDetail(${JSON.stringify(num)})'>
            <span style="flex:1;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">#${_escHtml(num)} — ${_escHtml(title)}</span>
            <span style="font-size:9px;padding:3px 8px;border-radius:3px;background:${stBg};color:${stColor};white-space:nowrap;margin-left:8px;font-weight:600;">${_escHtml(st)}</span>
          </div>`;
        }).join('');
      } else {
        queue.innerHTML = '<div style="padding: 12px; color: var(--text-dim);">✓ No open tickets</div>';
      }
    })
    .catch(() => {
      queue.innerHTML = '<div style="padding: 12px; color: var(--text-dim);">Ticket queue unavailable</div>';
    });
}
