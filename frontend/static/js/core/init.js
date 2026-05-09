// Boot sequence — DOMContentLoaded, intervals, SSE

// ── Settings modal: drag by h2, resize by CSS `resize: both` ─────────────
function _initSettingsDragResize() {
  // Legacy modal dragging is disabled now that Settings opens through the
  // shared floating-window manager.
}

// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// GOVERNANCE PANEL (Studio → 🛡 Governance button)
// ═══════════════════════════════════════════════════════════════════════════
async function openGovernancePanel() {
  let existing = document.getElementById('governance-panel-modal');
  if (existing) { existing.remove(); }
  const modal = document.createElement('div');
  modal.id = 'governance-panel-modal';
  modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;';
  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 20px;width:min(520px,92vw);box-shadow:0 14px 40px rgba(0,0,0,.4);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <div style="font-size:14px;font-weight:700;">🛡 Governance Controls</div>
        <button onclick="document.getElementById('governance-panel-modal').remove()" style="background:transparent;border:none;color:var(--text-dim);font-size:18px;cursor:pointer;">×</button>
      </div>
      <div id="gov-panel-body" style="font-size:12px;color:var(--text-dim);">Loading…</div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
  await refreshGovernancePanel();
}

async function refreshGovernancePanel() {
  const body = document.getElementById('gov-panel-body');
  if (!body) return;
  try {
    const r = await fetch('/api/governance/state');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'failed');
    const pill = (label, on, color) => `<span style="padding:2px 8px;border-radius:999px;background:color-mix(in srgb, ${color} 18%, transparent);color:${color};border:1px solid ${color};font-size:10px;font-weight:700;">${label}: ${on ? 'ON' : 'OFF'}</span>`;
    body.innerHTML = `
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
        ${pill('ALM', d.alm_status === 'enforced', 'var(--accent)')}
        ${pill('Vortex active', !!d.vortex_active, 'var(--info)')}
        ${pill('Sniffles', !!d.sniffles_enabled, 'var(--success,#4caf50)')}
        ${pill('Governance paused', !!d.paused, 'var(--warning)')}
        ${pill('Vortex paused', !!d.vortex_paused, 'var(--warning)')}
      </div>
      <div style="line-height:1.55;color:var(--text);margin-bottom:14px;">
        Governance is the Swarm's state-machine guarding proposal transitions.
        Pausing it lets operators bypass strict guards temporarily (changes still audited).
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button onclick="toggleGovernance('governance')" style="flex:1;padding:8px 12px;background:${d.paused ? 'var(--accent)' : 'var(--warning)'};color:#000;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:12px;">${d.paused ? '▶ Resume Governance' : '⏸ Pause Governance'}</button>
        <button onclick="toggleGovernance('vortex')" style="flex:1;padding:8px 12px;background:${d.vortex_paused ? 'var(--info)' : 'var(--warning)'};color:#000;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:12px;">${d.vortex_paused ? '▶ Resume Vortex' : '⏸ Pause Vortex'}</button>
      </div>
      <div style="margin-top:10px;font-size:10px;color:var(--text-dim);">Status persists in repository flag files; takes effect immediately.</div>
    `;
  } catch (e) {
    body.innerHTML = `<div style="color:var(--error,#ff6161);">Failed to load governance state: ${e.message}</div>`;
  }
}

async function toggleGovernance(target) {
  try {
    await fetch('/api/governance/toggle', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target })
    });
    await refreshGovernancePanel();
    if (typeof showToast === 'function') showToast(`${target === 'vortex' ? 'Vortex' : 'Governance'} toggled`, 'info');
  } catch (e) {
    if (typeof showToast === 'function') showToast('Toggle failed: ' + e.message, 'error');
  }
}

window.openGovernancePanel = openGovernancePanel;
window.refreshGovernancePanel = refreshGovernancePanel;
window.toggleGovernance = toggleGovernance;

// ═══════════════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════════════

let __vortexGitSyncToastKey = '';

async function checkVortexGitSyncDrift() {
  try {
    const resp = await fetch('/api/git/status?check_remote=1');
    const data = await resp.json().catch(() => ({}));
    if (!data || !data.ok) return;
    const remote = data.remote_check || {};
    if (!remote.checked || !remote.ok) return;
    const sync = data.out_of_sync || {};
    if (!sync.needs_pull) return;
    const key = `${data.environment || 'prod'}:${data.branch || ''}:${data.upstream || ''}:${data.behind || 0}`;
    if (key === __vortexGitSyncToastKey) return;
    __vortexGitSyncToastKey = key;
    const msg = sync.summary || `Local Git is behind by ${data.behind || 0} commit(s). Pull before continuing.`;
    if (typeof showToast === 'function') showToast(`Vortex Git sync: ${msg}`, 'warning');
  } catch (_) { /* remote drift check is best-effort */ }
}

document.addEventListener('DOMContentLoaded', () => {
  // Load settings and apply time-of-day theme
  loadSettings();
  initClocks();
  bindHomeLaunchClicks();
  initHomeCardReorder();
  initHomeHeaderCollapse();
  initQuickAccessCollapse();
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
  _initSettingsDragResize();

  // Follow-up #5: per-tile hover ? buttons pull from single-source manual.
  // Injects a small help glyph into every .home-card[data-win-id]. Clicking
  // calls openWindowHelp(winId), which fetches /api/manual/<winId>.
  try {
    const _injectTileHelp = () => {
      document.querySelectorAll('.home-card[data-win-id]').forEach(card => {
        if (card.__tileHelpInjected) return;
        card.__tileHelpInjected = true;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'home-card-help-btn';
        btn.title = 'What is this?';
        btn.textContent = '?';
        btn.style.cssText = 'position:absolute;top:6px;right:8px;width:18px;height:18px;border-radius:50%;border:1px solid var(--border);background:var(--card);color:var(--text-dim);font-size:10px;font-weight:700;cursor:pointer;opacity:0;transition:opacity .15s;display:flex;align-items:center;justify-content:center;padding:0;line-height:1;z-index:2;';
        btn.addEventListener('mouseenter', () => { btn.style.opacity = '1'; });
        btn.addEventListener('mouseleave', () => { btn.style.opacity = '0.5'; });
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          const winId = card.getAttribute('data-win-id');
          if (winId && typeof openWindowHelp === 'function') openWindowHelp(winId);
        });
        if (getComputedStyle(card).position === 'static') card.style.position = 'relative';
        card.appendChild(btn);
        card.addEventListener('mouseenter', () => { btn.style.opacity = '0.5'; });
        card.addEventListener('mouseleave', () => { btn.style.opacity = '0'; });
      });
    };
    _injectTileHelp();
    // Re-run when new cards are added (Add-Tile flow)
    const _homeGrid = document.getElementById('home-tiles-grid') || document.querySelector('.home-tiles');
    if (_homeGrid && typeof MutationObserver === 'function') {
      new MutationObserver(_injectTileHelp).observe(_homeGrid, { childList: true });
    }
  } catch (_) { /* non-fatal */ }

  // Welcome modal: show-at-startup wiring
  try {
    const cb = document.getElementById('welcome-show-at-startup');
    const pref = localStorage.getItem('fridays-welcome-at-startup');
    // First-visit default: ON. Once user unticks, remember 'never'.
    const shouldShow = (pref === null) || pref === '1';
    if (cb) cb.checked = shouldShow;
    if (shouldShow) {
      setTimeout(() => {
        const m = document.getElementById('shortcuts-help-modal');
        if (m) m.classList.add('open');
        // First visit: persist so next boot knows user has seen it.
        if (pref === null) { try { localStorage.setItem('fridays-welcome-at-startup', '1'); } catch (e) {} }
      }, 600);
    }
  } catch (e) {}

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
  setInterval(loadHomeStats, 20000); // Update stats every 20 seconds (was 10s — this is a light dashboard, not a thermal monitor)
  loadServicesPanel(); // Load service status + restart buttons
  setInterval(loadServicesPanel, 30000); // Refresh every 30 seconds
  loadOllamaPanel(); // Load Ollama model panel
  setInterval(loadOllamaPanel, 20000); // Refresh every 20 seconds (was 15s — shares /api/monitor cache with home stats)
  loadAttentionPanel(); // Needs-attention summary → delegates to System Pulse
  setInterval(loadAttentionPanel, 30000); // Refresh every 30 seconds
  // Session 30 — Test Lab tile badge (latest run status)
  if (typeof paintHomeTestlabBadge === 'function') {
    paintHomeTestlabBadge();
    setInterval(paintHomeTestlabBadge, 30000);
  }
  // Sundial pulse runs on its own faster cadence (2s) — feels live without
  // hammering the DB thanks to the 2s server-side cache on /api/diamond/pulse.
  // Any other tile sharing this endpoint rides the same cache for free.
  if (typeof loadSystemPulse === 'function') {
    setInterval(loadSystemPulse, 2000);
  }
  // Home chat replaces activity log + ticket queue on the home page
  if (typeof initHomeChat === 'function') initHomeChat();
  loadAuthProfiles();
  _renderIdentityPill();
  initChatSpellHelper();
  populateRelayRuleTargetOptions();
  renderRelayRuleList();
  startChatLiveSyncService();
  _librarianStartWatchdog();
  checkVortexGitSyncDrift();
  setInterval(checkVortexGitSyncDrift, 5 * 60 * 1000);
  
  // Settings modal handlers
  document.querySelectorAll('[data-time]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('[data-time]').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
    });
  });
  
  const opacityControl = document.getElementById('opacity-slider');
  const handleOpacityControl = (e) => {
    const transparency = Math.max(0, Math.min(30, parseInt(e.target.value || '5', 10)));
    const actualOpacity = (100 - transparency) / 100;
    document.getElementById('opacity-value').textContent = transparency + '%';
    document.documentElement.style.setProperty('--glass-opacity', actualOpacity);
  };
  opacityControl.addEventListener('input', handleOpacityControl);
  opacityControl.addEventListener('change', handleOpacityControl);
  
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

    if ((e.ctrlKey || e.metaKey) && e.key === ' ') {
      e.preventDefault();
      if (typeof openSpotlight === 'function') openSpotlight();
      return;
    }

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

    // Ctrl+G — Open Studio > Git tab
    if ((e.ctrlKey || e.metaKey) && e.key === 'g' && !isInput) {
      e.preventDefault();
      if (typeof openWindow === 'function') openWindow('studio', 'Studio', 'view-studio');
      setTimeout(() => { if (typeof studioSetTab === 'function') studioSetTab('git'); }, 120);
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
      // Close spotlight
      const spotlight = document.getElementById('spotlight-overlay');
      if (spotlight?.classList.contains('open')) {
        if (typeof closeSpotlight === 'function') closeSpotlight();
        return;
      }
      // Close any dynamically-created overlay modals (terminal shortcuts, etc.)
      const dynModal = document.getElementById('terminal-shortcut-modal');
      if (dynModal) { dynModal.remove(); return; }
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
      { label: 'Files', onclick: 'openWindow("knowledge", "Knowledge", "view-knowledge"); setTimeout(()=>{ if (typeof knowledgeSetTab==="function") knowledgeSetTab("files"); }, 150)', hint: '' },
      { label: 'Git', onclick: 'openWindow("studio","Studio","view-studio"); setTimeout(()=>studioSetTab("git"),120)', hint: 'Ctrl+G' },
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
      { label: 'User Guide', onclick: 'openWindow("guide","User Guide","view-guide")', hint: '' },
      { label: 'Spotlight Search', onclick: 'openSpotlight()', hint: 'Ctrl+Space' },
    ];
    
    const filtered = commands.filter(c => c.label.toLowerCase().includes(query));
    results.innerHTML = filtered.map(c => `
      <div class="palette-item" onclick="${c.onclick}; document.getElementById('command-palette').classList.remove('open');">
        <span>${c.label}</span>${c.hint ? `<span style="font-size:10px;color:var(--text-dim);margin-left:auto;opacity:0.7;">${c.hint}</span>` : ''}
      </div>
    `).join('');
  });
  
  // Filter listeners (activity/ticket removed — now on home chat)
  // Activity log and ticket queue filters are available inside their tile windows
  
  // Close palette on click outside
  document.getElementById('command-palette').addEventListener('click', (e) => {
    if (e.target.id === 'command-palette') {
      e.target.classList.remove('open');
    }
  });
  
  // ESC key closes focused/topmost window (already handled above)
});

const QUICK_ACCESS_COLLAPSED_KEY = 'fridays-quick-access-collapsed';
function initQuickAccessCollapse() {
  const title = document.getElementById('quick-access-title');
  if (!title) return;
  const section = title.closest('.home-section');
  if (!section) return;
  // Restore saved state
  if (localStorage.getItem(QUICK_ACCESS_COLLAPSED_KEY) === '1') {
    section.classList.add('collapsed');
  }
  title.addEventListener('click', () => {
    section.classList.toggle('collapsed');
    localStorage.setItem(QUICK_ACCESS_COLLAPSED_KEY, section.classList.contains('collapsed') ? '1' : '0');
  });
}

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
