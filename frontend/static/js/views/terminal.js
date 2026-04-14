// Terminal view — shell commands, history, shortcuts
// Extracted from terminal_base.html

function loadTerminalData(win) {
  const output = win.el.querySelector('#terminal-output');
  const btnContainer = win.el.querySelector('#terminal-buttons');
  const panel = win.el.querySelector('#terminal-shortcuts-panel');
  if (output) {
    _terminalResetOutput(output);
  }
  if (btnContainer) {
    renderTerminalQuickButtons(btnContainer, win);
  }
  if (panel) {
    const collapsed = sessionStorage.getItem('fridays-terminal-shortcuts-collapsed') === '1';
    applyTerminalShortcutsState(win, collapsed);
  }
  _terminalSyncControls();
  _terminalSyncHistoryUi();
  _loadDbShortcuts(); // load custom shortcuts from DB (async, refreshes buttons when done)

  // Inject agent-commands panel below output if not present
  const existingAgentPanel = win.el.querySelector('#terminal-agent-cmds-wrap');
  if (!existingAgentPanel && output) {
    const wrap = document.createElement('div');
    wrap.id = 'terminal-agent-cmds-wrap';
    wrap.style.cssText = 'margin-top:10px;padding:8px 10px;border-top:1px solid var(--border);';
    wrap.innerHTML = `<div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-dim);letter-spacing:0.05em;margin-bottom:6px;">Agent Shell Commands</div>
      <div id="terminal-agent-cmds" style="font-size:11px;"><div style="color:var(--text-dim);font-size:11px;">Loading…</div></div>`;
    output.parentElement.appendChild(wrap);
  }
  startAgentCmdPolling();
}

function _terminalWindow() {
  return winManager && winManager.windows ? winManager.windows.get('terminal') : null;
}

const TERMINAL_HISTORY_MAX = 80;

function _terminalFind(selector) {
  const terminalWin = _terminalWindow();
  return terminalWin && terminalWin.el ? terminalWin.el.querySelector(selector) : null;
}

function _terminalStreamState() {
  if (!window.__terminalStreamState) {
    let history = [];
    try {
      const raw = JSON.parse(localStorage.getItem('fridays-terminal-history') || '[]');
      history = Array.isArray(raw) ? raw.filter(item => typeof item === 'string') : [];
    } catch {
      history = [];
    }
    window.__terminalStreamState = {
      running: false,
      controller: null,
      commandId: null,
      proposalId: null,
      autoScroll: true,
      history: history.slice(-TERMINAL_HISTORY_MAX),
      historyIndex: -1,
      draft: '',
      copyStore: {},
      actionStore: {},
      historyOpen: false,
    };
  }
  return window.__terminalStreamState;
}

function _terminalStoreActionValue(value, prefix) {
  const state = _terminalStreamState();
  const store = state.actionStore || {};
  const actionId = `${prefix || 'term-action'}-${Math.random().toString(36).slice(2, 10)}`;
  store[actionId] = String(value || '');
  state.actionStore = store;
  const keys = Object.keys(store);
  if (keys.length > 240) {
    delete store[keys[0]];
  }
  return actionId;
}

function _terminalReadActionValue(actionId) {
  const state = _terminalStreamState();
  return String(((state.actionStore || {})[actionId]) || '');
}

function _terminalHistoryPanel() {
  return _terminalFind('#terminal-history-panel');
}

function _terminalSyncHistoryUi() {
  const state = _terminalStreamState();
  const panel = _terminalHistoryPanel();
  const btn = _terminalFind('#terminal-history-btn');
  if (btn) {
    const count = Array.isArray(state.history) ? state.history.length : 0;
    btn.textContent = count ? `History (${count})` : 'History';
    btn.style.color = state.historyOpen ? 'var(--accent)' : 'var(--text)';
    btn.style.borderColor = state.historyOpen ? 'var(--accent)' : 'var(--border)';
  }
  if (panel) {
    panel.style.display = state.historyOpen ? 'block' : 'none';
  }
}

function _terminalRenderHistoryPanel() {
  const panel = _terminalHistoryPanel();
  if (!panel) return;
  const state = _terminalStreamState();
  const history = Array.isArray(state.history) ? state.history.slice().reverse() : [];
  panel.innerHTML = '';

  if (!history.length) {
    panel.innerHTML = '<div style="font-size:11px;color:var(--text-dim);padding:4px 0;">No recent commands yet.</div>';
    return;
  }

  const header = document.createElement('div');
  header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;';
  header.innerHTML = '<div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;">Recent Commands</div>';
  const clearBtn = document.createElement('button');
  clearBtn.textContent = 'Forget';
  clearBtn.style.cssText = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:3px 8px;cursor:pointer;font-size:10px;';
  clearBtn.onclick = () => terminalClearHistory();
  header.appendChild(clearBtn);
  panel.appendChild(header);

  history.forEach((cmd) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 0;border-top:1px solid rgba(255,255,255,0.04);';

    const code = document.createElement('code');
    code.textContent = cmd;
    code.style.cssText = 'flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:var(--text);';
    row.appendChild(code);

    const fillBtn = document.createElement('button');
    fillBtn.textContent = 'Fill';
    fillBtn.style.cssText = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:3px 8px;cursor:pointer;font-size:10px;';
    fillBtn.onclick = () => terminalFillFromHistory(cmd);
    row.appendChild(fillBtn);

    const runBtn = document.createElement('button');
    runBtn.textContent = 'Run';
    runBtn.style.cssText = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:3px 8px;cursor:pointer;font-size:10px;';
    runBtn.onclick = () => terminalRunFromHistory(cmd);
    row.appendChild(runBtn);

    const favBtn = document.createElement('button');
    favBtn.textContent = '★';
    favBtn.title = 'Save to shortcuts';
    favBtn.style.cssText = 'background:transparent;border:1px solid var(--border);color:#f7b84b;border-radius:4px;padding:3px 7px;cursor:pointer;font-size:11px;';
    favBtn.onclick = () => _terminalSaveToShortcuts(cmd, favBtn);
    row.appendChild(favBtn);

    panel.appendChild(row);
  });
}

function _terminalResetOutput(outputEl) {
  if (!outputEl) return;
  outputEl.innerHTML = '<div class="terminal-system-line" style="color:var(--text-dim);margin-bottom:6px;">Terminal ready. Type commands or use quick buttons above. Use Up/Down for history.</div>';
}

function _terminalAllocEntryId() {
  const state = _terminalStreamState();
  state.nextEntryId = Number(state.nextEntryId || 0) + 1;
  return 'term-entry-' + state.nextEntryId;
}

function _terminalCurrentFilter() {
  const filterInput = _terminalFind('#terminal-filter-input');
  return String(filterInput ? filterInput.value : '').trim().toLowerCase();
}

function terminalFilterOutput(value) {
  const output = _terminalFind('#terminal-output');
  if (!output) return;
  const needle = String(value || '').trim().toLowerCase();
  const cards = Array.from(output.querySelectorAll('.terminal-result-card'));
  const prompts = Array.from(output.querySelectorAll('.terminal-prompt-line'));
  const visibleEntryIds = new Set();

  cards.forEach((card) => {
    const haystack = `${card.dataset.terminalCommand || ''}\n${card.dataset.terminalOutput || ''}`.toLowerCase();
    const visible = !needle || haystack.includes(needle);
    const container = card.parentElement && card.parentElement !== output ? card.parentElement : card;
    container.style.display = visible ? '' : 'none';
    if (visible && card.dataset.terminalEntryId) {
      visibleEntryIds.add(card.dataset.terminalEntryId);
    }
  });

  prompts.forEach((prompt) => {
    const entryId = prompt.dataset.terminalEntryId || '';
    const text = (prompt.textContent || '').toLowerCase();
    const visible = !needle || visibleEntryIds.has(entryId) || text.includes(needle);
    prompt.style.display = visible ? '' : 'none';
  });

  output.querySelectorAll('.terminal-system-line').forEach((line) => {
    line.style.display = needle ? 'none' : '';
  });
}

function _terminalAppendPromptLine(output, cmd, entryId) {
  const line = document.createElement('div');
  line.className = 'terminal-prompt-line';
  line.dataset.terminalEntryId = entryId;
  line.style.color = '#5c9bd6';
  line.textContent = '❯ ' + cmd;
  output.appendChild(line);
  return line;
}

function _persistTerminalHistory() {
  const state = _terminalStreamState();
  try {
    localStorage.setItem('fridays-terminal-history', JSON.stringify((state.history || []).slice(-TERMINAL_HISTORY_MAX)));
  } catch {}
  if (state.historyOpen) {
    _terminalRenderHistoryPanel();
  }
  _terminalSyncHistoryUi();
}

function _terminalPushHistory(cmd) {
  const clean = String(cmd || '').trim();
  if (!clean) return;
  const state = _terminalStreamState();
  const history = Array.isArray(state.history) ? state.history : [];
  if (history[history.length - 1] !== clean) {
    history.push(clean);
    state.history = history.slice(-TERMINAL_HISTORY_MAX);
    _persistTerminalHistory();
  }
  state.historyIndex = -1;
  state.draft = '';
}

function _terminalStepHistory(direction, inputEl) {
  const state = _terminalStreamState();
  const history = Array.isArray(state.history) ? state.history : [];
  if (!inputEl || !history.length) return;

  if (direction < 0) {
    if (state.historyIndex === -1) {
      state.draft = inputEl.value || '';
      state.historyIndex = history.length - 1;
    } else if (state.historyIndex > 0) {
      state.historyIndex -= 1;
    }
    inputEl.value = history[state.historyIndex] || '';
  } else {
    if (state.historyIndex === -1) return;
    if (state.historyIndex < history.length - 1) {
      state.historyIndex += 1;
      inputEl.value = history[state.historyIndex] || '';
    } else {
      state.historyIndex = -1;
      inputEl.value = state.draft || '';
    }
  }

  const len = inputEl.value.length;
  inputEl.setSelectionRange(len, len);
}

function terminalHandleInputKeydown(event) {
  if (!event) return;
  if (event.key === 'Escape') {
    const state = _terminalStreamState();
    if (state.historyOpen) {
      event.preventDefault();
      terminalToggleHistory(false);
    }
    return;
  }
  if (event.key === 'Enter') {
    event.preventDefault();
    runTerminalCmd();
    return;
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault();
    _terminalStepHistory(-1, event.target);
    return;
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    _terminalStepHistory(1, event.target);
  }
}

function terminalToggleHistory(force) {
  const state = _terminalStreamState();
  state.historyOpen = typeof force === 'boolean' ? force : !state.historyOpen;
  if (state.historyOpen) {
    _terminalRenderHistoryPanel();
  }
  _terminalSyncHistoryUi();
}

function terminalFillFromHistory(cmd) {
  const input = _terminalFind('#terminal-input');
  if (!input) return;
  input.value = String(cmd || '');
  const len = input.value.length;
  input.focus();
  input.setSelectionRange(len, len);
  terminalToggleHistory(false);
}

function terminalRunFromHistory(cmd) {
  if (_terminalStreamState().running) {
    showToast('Wait for the active command to finish first', 'error');
    return;
  }
  terminalFillFromHistory(cmd);
  runTerminalCmd();
}

function terminalClearHistory() {
  const state = _terminalStreamState();
  state.history = [];
  state.historyIndex = -1;
  state.draft = '';
  _persistTerminalHistory();
  _terminalRenderHistoryPanel();
  showToast('Terminal history cleared', 'success');
}

function terminalClearOutput() {
  const state = _terminalStreamState();
  if (state.running) {
    showToast('Stop the active command before clearing output', 'error');
    return;
  }
  const output = _terminalFind('#terminal-output');
  _terminalResetOutput(output);
}

async function terminalCopyResult(copyId) {
  const state = _terminalStreamState();
  const text = String((state.copyStore || {})[copyId] || '');
  if (!text) {
    showToast('Nothing to copy for this command', 'error');
    return;
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const temp = document.createElement('textarea');
      temp.value = text;
      temp.setAttribute('readonly', 'readonly');
      temp.style.position = 'fixed';
      temp.style.opacity = '0';
      document.body.appendChild(temp);
      temp.select();
      document.execCommand('copy');
      document.body.removeChild(temp);
    }
    showToast('Command output copied', 'success');
  } catch (e) {
    showToast('Copy failed: ' + (e.message || e), 'error');
  }
}

function terminalRerunCommand(actionId) {
  const cmd = _terminalReadActionValue(actionId);
  if (!cmd) {
    showToast('Command is no longer available to rerun', 'error');
    return;
  }
  if (_terminalStreamState().running) {
    showToast('Wait for the active command to finish first', 'error');
    return;
  }
  cmdTerminal(cmd);
}

function terminalPinCommand(actionId) {
  const cmd = _terminalReadActionValue(actionId);
  if (!cmd) {
    showToast('Command is no longer available to pin', 'error');
    return;
  }

  const custom = getCustomTerminalShortcuts();
  if (custom.some(item => String(item.cmd || '').trim() === cmd.trim())) {
    showToast('Command is already pinned in shortcuts', 'info');
    return;
  }

  const suggested = cmd.length > 28 ? cmd.slice(0, 28) + '…' : cmd;
  const label = prompt('Shortcut label for this command:', suggested);
  if (label == null) return;
  const cleanLabel = String(label || '').trim() || suggested;
  custom.push({ icon: '📌', label: cleanLabel, cmd });
  saveCustomTerminalShortcuts(custom);

  const terminalWin = winManager.windows.get('terminal');
  if (terminalWin) {
    const btnContainer = terminalWin.el.querySelector('#terminal-buttons');
    if (btnContainer) {
      renderTerminalQuickButtons(btnContainer, terminalWin);
    }
  }

  showToast('Pinned to terminal shortcuts', 'success');
}

function _terminalSyncControls() {
  const state = _terminalStreamState();
  const stopBtn = _terminalFind('#terminal-stop-btn');
  const autoBtn = _terminalFind('#terminal-autoscroll-toggle');
  if (stopBtn) {
    stopBtn.disabled = !state.running;
    stopBtn.style.cursor = state.running ? 'pointer' : 'not-allowed';
    stopBtn.style.opacity = state.running ? '1' : '0.55';
  }
  if (autoBtn) {
    autoBtn.textContent = `Auto-scroll: ${state.autoScroll ? 'On' : 'Off'}`;
    autoBtn.style.color = state.autoScroll ? 'var(--text)' : 'var(--text-dim)';
  }
}

function terminalToggleAutoScroll() {
  const state = _terminalStreamState();
  state.autoScroll = !state.autoScroll;
  _terminalSyncControls();
}

async function terminalStopActive() {
  const state = _terminalStreamState();
  if (!state.running) return;
  try {
    if (state.commandId) {
      await fetch('/api/terminal/stream/stop', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ command_id: state.commandId, proposal_id: state.proposalId || null })
      }).catch(() => {});
    }
    if (state.controller) {
      state.controller.abort();
    }
  } finally {
    showToast('Stopping command...', 'info');
  }
}

function applyTerminalShortcutsState(win, collapsed) {
  if (!win) return;
  const panel = win.el.querySelector('#terminal-shortcuts-panel');
  const btns = win.el.querySelector('#terminal-buttons');
  const header = win.el.querySelector('#terminal-shortcuts-header');
  const restoreBtn = win.el.querySelector('#terminal-shortcuts-restore');
  const headerToggle = win.el.querySelector('#terminal-shortcuts-toggle');
  const mainToggle = win.el.querySelector('#terminal-shortcuts-main-toggle');
  if (!panel || !btns || !headerToggle || !mainToggle || !header || !restoreBtn) return;

  panel.style.width = collapsed ? '42px' : '230px';
  panel.style.maxWidth = collapsed ? '42px' : '38%';
  panel.style.minWidth = collapsed ? '42px' : '180px';
  btns.style.display = collapsed ? 'none' : 'block';
  header.style.display = collapsed ? 'none' : 'flex';
  restoreBtn.style.display = collapsed ? 'inline-flex' : 'none';

  headerToggle.textContent = collapsed ? '⟨' : '⟩';
  headerToggle.title = collapsed ? 'Expand' : 'Collapse';

  mainToggle.textContent = collapsed ? '⚡ Show Shortcuts' : '⚡ Hide Shortcuts';
  mainToggle.title = collapsed ? 'Show shortcuts' : 'Hide shortcuts';
}

const DEFAULT_TERMINAL_SHORTCUTS = [
  { icon: '🔁', label: 'Hard Boot Terminal', cmd: 'sudo systemctl restart swarm-terminal' },
  { icon: '🎨', label: 'Theme Engine Check', cmd: 'head -n 80 /home/seven/swarm/themes/fridays.json' },
  { icon: '📡', label: 'ALM Status', cmd: 'curl -s http://localhost:5050/api/alm/status' },
  { icon: '💬', label: 'Restart Discord Bot', cmd: 'sudo systemctl restart swarm-discord' },
  { icon: '📨', label: 'Restart Telegram Bot', cmd: 'sudo systemctl restart swarm-telegram' },
  { icon: '✅', label: 'Terminal Service Status', cmd: 'systemctl status swarm-terminal' },
  { icon: '🧠', label: 'System Memory', cmd: 'free -h' },
];

// ── Terminal shortcuts (DB-backed) ───────────────────────────────────────────
// Custom shortcuts stored in terminal_shortcuts table via /api/terminal/shortcuts.
// DEFAULT_TERMINAL_SHORTCUTS are hardcoded and never stored in DB.

let _terminalDbShortcuts = []; // in-memory cache, loaded from DB on tile open
let _terminalSudoWhitelist = { built_in: [], custom: [], all: [] };

async function _loadDbShortcuts() {
  // One-time migration: move any localStorage custom shortcuts to DB
  try {
    const legacy = JSON.parse(localStorage.getItem('fridays-terminal-shortcuts-custom') || '[]');
    if (Array.isArray(legacy) && legacy.length > 0) {
      for (const item of legacy) {
        if (item.label && item.cmd) {
          await fetch('/api/terminal/shortcuts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ icon: item.icon || '⚡', label: item.label, cmd: item.cmd })
          }).catch(() => {});
        }
      }
      localStorage.removeItem('fridays-terminal-shortcuts-custom');
    }
  } catch {}

  try {
    const data = await fetch('/api/terminal/shortcuts').then(r => r.json());
    _terminalDbShortcuts = Array.isArray(data) ? data : [];
  } catch {
    _terminalDbShortcuts = [];
  }

  try {
    const whitelist = await fetch('/api/terminal/sudo-whitelist').then(r => r.json());
    _terminalSudoWhitelist = whitelist && typeof whitelist === 'object'
      ? {
          built_in: Array.isArray(whitelist.built_in) ? whitelist.built_in : [],
          custom: Array.isArray(whitelist.custom) ? whitelist.custom : [],
          all: Array.isArray(whitelist.all) ? whitelist.all : [],
        }
      : { built_in: [], custom: [], all: [] };
  } catch {
    _terminalSudoWhitelist = { built_in: [], custom: [], all: [] };
  }

  _terminalRefreshButtons();
  _scModalRenderList();
}

function _terminalRefreshButtons() {
  const win = _terminalWindow();
  if (!win) return;
  const c = win.el.querySelector('#terminal-buttons');
  if (c) renderTerminalQuickButtons(c, win);
}

function renderTerminalQuickButtons(btnContainer, win) {
  if (!btnContainer) return;
  // All shortcuts come from DB — defaults were seeded server-side
  const all = _terminalDbShortcuts.length ? _terminalDbShortcuts : DEFAULT_TERMINAL_SHORTCUTS;

  btnContainer.innerHTML = '';
  all.forEach((item) => {
    const btn = document.createElement('button');
    btn.className = 'cmd-btn custom';
    const removeBtn = item.id
      ? `<button class="cmd-remove" title="Remove shortcut" onclick="event.stopPropagation(); _scDelete(${item.id})">✕</button>`
      : '';
    btn.innerHTML = `${removeBtn}<span>${item.icon || '⚡'}</span> ${_escHtml(item.label || 'Shortcut')}<span class="cmd-meta">${_escHtml((item.cmd || '').slice(0, 90))}${(item.cmd || '').length > 90 ? '…' : ''}</span>`;
    btn.onclick = () => cmdTerminal(item.cmd || '');
    btnContainer.appendChild(btn);
  });
}

// Open shortcut manager modal (replaces prompt() dialogs)
function addTerminalShortcut() {
  if (document.getElementById('terminal-shortcut-modal')) return;

  const inputStyle = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:5px 8px;font-size:12px;outline:none;';
  const btnStyle   = 'border:1px solid var(--border);border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px;';

  const overlay = document.createElement('div');
  overlay.id = 'terminal-shortcut-modal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div style="background:var(--bg,#12121a);border:1px solid var(--border);border-radius:10px;width:780px;max-width:96vw;max-height:84vh;display:flex;flex-direction:column;box-shadow:0 16px 48px rgba(0,0,0,0.6);">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-bottom:1px solid var(--border);flex-shrink:0;">
        <div style="font-weight:700;font-size:13px;">⚡ Terminal Controls</div>
        <button onclick="document.getElementById('terminal-shortcut-modal').remove()" style="background:transparent;border:none;color:var(--text-dim);cursor:pointer;font-size:18px;line-height:1;padding:0 2px;">✕</button>
      </div>
      <div style="overflow-y:auto;flex:1;padding:0;">
        <div id="sc-modal-list" style="padding:0;"></div>
        <div id="sudo-modal-list" style="padding:0;border-top:1px solid var(--border);"></div>
      </div>
      <div style="border-top:1px solid var(--border);padding:12px 16px;flex-shrink:0;display:grid;grid-template-columns:1fr;gap:12px;">
        <div>
          <div style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Add Shortcut</div>
          <div style="display:flex;gap:8px;align-items:center;">
            <input id="sc-new-icon" value="⚡" maxlength="4" style="${inputStyle}width:44px;text-align:center;font-size:16px;" title="Icon (emoji)">
            <input id="sc-new-label" placeholder="Label" style="${inputStyle}flex:1;" onkeydown="if(event.key==='Enter')_scAdd()">
            <input id="sc-new-cmd" placeholder="Command" style="${inputStyle}flex:2;font-family:monospace;" onkeydown="if(event.key==='Enter')_scAdd()">
            <button onclick="_scAdd()" style="${btnStyle}background:var(--accent,#7c5cfc);color:#fff;border-color:transparent;font-weight:600;">+ Add</button>
          </div>
        </div>
        <div>
          <div style="font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Add Sudo Whitelist Entry</div>
          <div style="display:flex;gap:8px;align-items:center;">
            <input id="sudo-new-command" placeholder="sudo systemctl restart my-service" style="${inputStyle}flex:2;font-family:monospace;" onkeydown="if(event.key==='Enter')_sudoWhitelistAdd()">
            <input id="sudo-new-note" placeholder="Optional note" style="${inputStyle}flex:1;" onkeydown="if(event.key==='Enter')_sudoWhitelistAdd()">
            <button onclick="_sudoWhitelistAdd()" style="${btnStyle}background:#c46b08;color:#fff;border-color:transparent;font-weight:600;">+ Allow</button>
          </div>
          <div style="margin-top:6px;font-size:10px;color:var(--text-dim);">Only exact <code>sudo ...</code> commands are accepted. Chaining like <code>&&</code>, pipes, semicolons, and substitutions are blocked.</div>
        </div>
      </div>
    </div>
  `;
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  _scModalRenderList();
  overlay.querySelector('#sc-new-label').focus();
}

function _scModalRenderList() {
  const list = document.getElementById('sc-modal-list');
  if (!list) return;
  const rowStyle = 'display:flex;align-items:center;gap:10px;padding:9px 16px;border-bottom:1px solid rgba(255,255,255,0.04);font-size:12px;';
  const btnStyle = 'border:1px solid var(--border);border-radius:3px;padding:2px 8px;cursor:pointer;font-size:10px;';

  let html = '<div style="padding:12px 16px 8px;font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.06em;">Shortcuts</div>';
  if (!_terminalDbShortcuts.length) {
    html += '<div style="padding:0 16px 16px;font-size:11px;color:var(--text-dim);">No shortcuts yet — add one below.</div>';
  } else {
    _terminalDbShortcuts.forEach(item => {
      html += `
        <div id="sc-row-${item.id}" style="${rowStyle}">
          <span style="font-size:16px;min-width:24px;">${_escHtml(item.icon || '⚡')}</span>
          <span style="flex:1;font-weight:500;">${_escHtml(item.label)}</span>
          <code style="flex:2;color:var(--text-dim);font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(item.cmd)}</code>
          <button onclick="_scEditRow(${item.id})" style="${btnStyle}background:var(--card);color:var(--text);">Edit</button>
          <button onclick="_scDelete(${item.id})" style="${btnStyle}background:transparent;color:#f44336;border-color:#f4433655;">✕</button>
        </div>`;
    });
  }
  list.innerHTML = html;

  const sudoList = document.getElementById('sudo-modal-list');
  if (!sudoList) return;

  const builtIn = Array.isArray(_terminalSudoWhitelist.built_in) ? _terminalSudoWhitelist.built_in : [];
  const custom = Array.isArray(_terminalSudoWhitelist.custom) ? _terminalSudoWhitelist.custom : [];

  let sudoHtml = '<div style="padding:12px 16px 8px;font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.06em;">Sudo Whitelist</div>';
  sudoHtml += '<div style="padding:0 16px 10px;font-size:11px;color:var(--text-dim);">Built-in rules are system defaults. Custom entries are exact commands you can add and remove here.</div>';

  if (!custom.length) {
    sudoHtml += '<div style="padding:0 16px 12px;font-size:11px;color:var(--text-dim);">No custom sudo whitelist entries yet.</div>';
  } else {
    custom.forEach((item) => {
      sudoHtml += `
        <div style="${rowStyle}">
          <span style="font-size:15px;min-width:24px;">🔐</span>
          <div style="flex:1;min-width:0;">
            <code style="display:block;color:var(--text);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(item.command || '')}</code>
            <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">${_escHtml(item.note || 'custom sudo whitelist entry')}</div>
          </div>
          <button onclick="_sudoWhitelistDelete(${item.id})" style="${btnStyle}background:transparent;color:#f44336;border-color:#f4433655;">Remove</button>
        </div>`;
    });
  }

  sudoHtml += '<div style="padding:10px 16px 6px;font-size:10px;color:var(--text-dim);font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">Built-in sudo rules</div>';
  if (!builtIn.length) {
    sudoHtml += '<div style="padding:0 16px 16px;font-size:11px;color:var(--text-dim);">No built-in sudo rules reported.</div>';
  } else {
    builtIn
      .filter(item => Number(item.trust_level) >= 4 && String(item.command || '').includes('sudo'))
      .forEach((item) => {
        sudoHtml += `
          <div style="${rowStyle}">
            <span style="font-size:15px;min-width:24px;">🧱</span>
            <div style="flex:1;min-width:0;">
              <code style="display:block;color:var(--text);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(item.command || '')}</code>
              <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">${_escHtml(item.description || 'built-in rule')} · regex rule</div>
            </div>
            <span style="font-size:10px;color:var(--text-dim);">fixed</span>
          </div>`;
      });
  }
  sudoList.innerHTML = sudoHtml;
}

function _scEditRow(id) {
  const item = _terminalDbShortcuts.find(s => s.id === id);
  if (!item) return;
  const row = document.getElementById('sc-row-' + id);
  if (!row) return;
  const inputStyle = 'background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:4px;padding:4px 7px;font-size:11px;outline:none;';
  row.innerHTML = `
    <input value="${_escHtml(item.icon||'⚡')}" maxlength="4" style="${inputStyle}width:44px;text-align:center;font-size:14px;" id="sc-edit-icon-${id}">
    <input value="${_escHtml(item.label)}" style="${inputStyle}flex:1;" id="sc-edit-label-${id}" onkeydown="if(event.key==='Enter')_scSave(${id})">
    <input value="${_escHtml(item.cmd)}" style="${inputStyle}flex:2;font-family:monospace;" id="sc-edit-cmd-${id}" onkeydown="if(event.key==='Enter')_scSave(${id})">
    <button onclick="_scSave(${id})" style="border:none;border-radius:3px;padding:3px 10px;cursor:pointer;font-size:10px;background:var(--accent,#7c5cfc);color:#fff;font-weight:600;">Save</button>
    <button onclick="_scModalRenderList()" style="border:1px solid var(--border);border-radius:3px;padding:3px 8px;cursor:pointer;font-size:10px;background:transparent;color:var(--text-dim);">Cancel</button>
  `;
  row.style.flexWrap = 'wrap';
  row.querySelector('#sc-edit-label-' + id).focus();
}

async function _scSave(id) {
  const icon  = (document.getElementById('sc-edit-icon-' + id)?.value || '⚡').trim().slice(0, 4) || '⚡';
  const label = (document.getElementById('sc-edit-label-' + id)?.value || '').trim();
  const cmd   = (document.getElementById('sc-edit-cmd-' + id)?.value || '').trim();
  if (!label || !cmd) { showToast('Label and command are required', 'error'); return; }
  try {
    await fetch(`/api/terminal/shortcuts/${id}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ icon, label, cmd })
    });
    const entry = _terminalDbShortcuts.find(s => s.id === id);
    if (entry) { entry.icon = icon; entry.label = label; entry.cmd = cmd; }
    _scModalRenderList();
    _terminalRefreshButtons();
    showToast('Shortcut updated', 'success');
  } catch (e) {
    showToast('Save failed: ' + e.message, 'error');
  }
}

async function _scAdd() {
  const icon  = (document.getElementById('sc-new-icon')?.value  || '⚡').trim().slice(0, 4) || '⚡';
  const label = (document.getElementById('sc-new-label')?.value || '').trim();
  const cmd   = (document.getElementById('sc-new-cmd')?.value   || '').trim();
  if (!label || !cmd) { showToast('Label and command are required', 'error'); return; }
  try {
    const res  = await fetch('/api/terminal/shortcuts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ icon, label, cmd })
    }).then(r => r.json());
    _terminalDbShortcuts.push({ id: res.id, icon, label, cmd, sort_order: 0 });
    _scModalRenderList();
    _terminalRefreshButtons();
    if (document.getElementById('sc-new-label')) document.getElementById('sc-new-label').value = '';
    if (document.getElementById('sc-new-cmd'))   document.getElementById('sc-new-cmd').value   = '';
    if (document.getElementById('sc-new-icon'))  document.getElementById('sc-new-icon').value  = '⚡';
    showToast('Shortcut added', 'success');
  } catch (e) {
    showToast('Add failed: ' + e.message, 'error');
  }
}

async function _scDelete(id) {
  try {
    await fetch(`/api/terminal/shortcuts/${id}`, { method: 'DELETE' });
    _terminalDbShortcuts = _terminalDbShortcuts.filter(s => s.id !== id);
    _scModalRenderList();
    _terminalRefreshButtons();
    showToast('Shortcut removed', 'info');
  } catch (e) {
    showToast('Delete failed: ' + e.message, 'error');
  }
}

async function _sudoWhitelistAdd() {
  const command = (document.getElementById('sudo-new-command')?.value || '').trim();
  const note = (document.getElementById('sudo-new-note')?.value || '').trim();
  if (!command) { showToast('Sudo command is required', 'error'); return; }
  try {
    const res = await fetch('/api/terminal/sudo-whitelist', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ command, note })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || 'Unable to add whitelist entry');
    }
    _terminalSudoWhitelist.custom = [...(_terminalSudoWhitelist.custom || []), data.item];
    _terminalSudoWhitelist.all = [
      ...(_terminalSudoWhitelist.built_in || []),
      ...(_terminalSudoWhitelist.custom || []),
    ];
    _scModalRenderList();
    if (document.getElementById('sudo-new-command')) document.getElementById('sudo-new-command').value = '';
    if (document.getElementById('sudo-new-note')) document.getElementById('sudo-new-note').value = '';
    showToast('Sudo whitelist entry added', 'success');
  } catch (e) {
    showToast('Whitelist add failed: ' + e.message, 'error');
  }
}

async function _sudoWhitelistDelete(id) {
  try {
    const res = await fetch(`/api/terminal/sudo-whitelist/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || 'Unable to remove whitelist entry');
    }
    _terminalSudoWhitelist.custom = (_terminalSudoWhitelist.custom || []).filter(item => item.id !== id);
    _terminalSudoWhitelist.all = [
      ...(_terminalSudoWhitelist.built_in || []),
      ...(_terminalSudoWhitelist.custom || []),
    ];
    _scModalRenderList();
    showToast('Sudo whitelist entry removed', 'info');
  } catch (e) {
    showToast('Whitelist delete failed: ' + e.message, 'error');
  }
}

// Save a command from history directly to shortcuts (no modal needed)
async function _terminalSaveToShortcuts(cmd, btnEl) {
  const already = _terminalDbShortcuts.some(s => s.cmd.trim() === cmd.trim());
  if (already) { showToast('Already in shortcuts', 'info'); return; }
  try {
    const label = cmd.length > 32 ? cmd.slice(0, 32) + '…' : cmd;
    const res = await fetch('/api/terminal/shortcuts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ icon: '⚡', label, cmd })
    }).then(r => r.json());
    _terminalDbShortcuts.push({ id: res.id, icon: '⚡', label, cmd, sort_order: 0 });
    _terminalRefreshButtons();
    if (btnEl) { btnEl.textContent = '★'; btnEl.style.color = '#4caf50'; btnEl.disabled = true; }
    showToast('Saved to shortcuts', 'success');
  } catch (e) {
    showToast('Save failed: ' + e.message, 'error');
  }
}

// ── Agent shell command panel ─────────────────────────────────────────────────
// Shows commands that Developer Agents (Grok, GPT, etc.) ran via SKILL shell.
// Polls /api/shell/agent-commands every 3s when the terminal tile is open.

let _agentCmdPollTimer = null;

function _agentCmdPanelEl() {
  const win = _terminalWindow();
  return win && win.el ? win.el.querySelector('#terminal-agent-cmds') : null;
}

function _agentCmdStatusStyle(status) {
  if (status === 'running')  return 'color:#ffa500;font-weight:700;';
  if (status === 'done')     return 'color:#4caf50;';
  if (status === 'timeout')  return 'color:#f44;';
  if (status === 'killed')   return 'color:#f44;';
  if (status === 'failed')   return 'color:#ff7043;';
  if (status === 'error')    return 'color:#f44;';
  return 'color:var(--text-dim);';
}

function _renderAgentCmds(cmds) {
  const el = _agentCmdPanelEl();
  if (!el) return;
  if (!cmds || !cmds.length) {
    el.innerHTML = '<div style="font-size:11px;color:var(--text-dim);padding:4px 0;">No recent agent shell commands.</div>';
    return;
  }
  const H = _escHtml;
  el.innerHTML = cmds.map(c => {
    const age = c.finished_at
      ? Math.round(Date.now() / 1000 - c.finished_at) + 's ago'
      : Math.round(Date.now() / 1000 - c.started_at) + 's running';
    const killBtn = c.status === 'running'
      ? `<button onclick="agentCmdKill('${H(c.cmd_id)}')"
           title="Kill this command"
           style="padding:2px 7px;font-size:10px;background:#f4433620;border:1px solid #f4433660;color:#f44;border-radius:4px;cursor:pointer;">✕ kill</button>`
      : '';
    const preview = c.output
      ? `<div style="font-size:10px;color:var(--text-dim);margin-top:3px;white-space:pre-wrap;max-height:60px;overflow:hidden;">${H(c.output.slice(0, 300))}</div>`
      : '';
    return `<div style="padding:6px 8px;border:1px solid var(--border);border-radius:5px;background:var(--card);margin-bottom:6px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
        <div style="font-size:10px;font-weight:700;${_agentCmdStatusStyle(c.status)}">${H(c.status.toUpperCase())}</div>
        <div style="font-size:10px;color:var(--text-dim);">${H(c.agent)} · ${age}</div>
        ${killBtn}
      </div>
      <code style="font-size:11px;color:var(--text);display:block;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${H(c.command)}</code>
      ${preview}
    </div>`;
  }).join('');
}

function _pollAgentCmds() {
  fetch('/api/shell/agent-commands')
    .then(r => r.json())
    .then(d => _renderAgentCmds(d.commands || []))
    .catch(() => {});
}

function agentCmdKill(cmdId) {
  fetch('/api/shell/agent-kill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cmd_id: cmdId }),
  })
    .then(r => r.json())
    .then(d => {
      showToast(d.killed ? 'Command killed' : 'Not found or already finished', d.killed ? 'success' : 'warning');
      _pollAgentCmds();
    })
    .catch(e => showToast('Kill failed: ' + e.message, 'error'));
}

function startAgentCmdPolling() {
  if (_agentCmdPollTimer) return;
  _pollAgentCmds();
  _agentCmdPollTimer = setInterval(_pollAgentCmds, 3000);
}

function stopAgentCmdPolling() {
  if (_agentCmdPollTimer) {
    clearInterval(_agentCmdPollTimer);
    _agentCmdPollTimer = null;
  }
}

// Legacy helpers kept so any old stored references don't throw
function getCustomTerminalShortcuts() { return []; }
function saveCustomTerminalShortcuts() {}
function removeTerminalShortcut() {}

function toggleTerminalShortcuts() {
  const termWin = winManager.windows.get('terminal');
  if (!termWin) return;
  const collapsed = sessionStorage.getItem('fridays-terminal-shortcuts-collapsed') === '1';
  const nextCollapsed = !collapsed;
  applyTerminalShortcutsState(termWin, nextCollapsed);
  sessionStorage.setItem('fridays-terminal-shortcuts-collapsed', nextCollapsed ? '1' : '0');
}
