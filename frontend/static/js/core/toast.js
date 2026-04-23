// Toast notifications & troubleshoot diagnostics
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════════════════════

// Always-on glitch log — captures errors regardless of trace state
// Max 100 entries, persists until page reload
window.__systemGlitches = window.__systemGlitches || [];

function _glitchLog(source, message) {
  const entry = {
    ts: new Date().toISOString(),
    source: String(source || 'unknown'),
    message: String(message || ''),
  };
  window.__systemGlitches.push(entry);
  if (window.__systemGlitches.length > 100) window.__systemGlitches.shift();
  _renderGlitchSection();
  // Also pipe into trace log if active
  _troubleshootLog('error', `[${entry.source}]`, entry.message);
}

function _renderGlitchSection() {
  const el = document.getElementById('troubleshoot-glitches');
  if (!el) return;
  const glitches = window.__systemGlitches || [];
  if (!glitches.length) {
    el.textContent = 'No glitches recorded.';
    const badge = document.getElementById('troubleshoot-glitch-badge');
    if (badge) badge.style.display = 'none';
    return;
  }
  el.textContent = glitches.slice(-50).map(g => {
    const d = new Date(g.ts);
    const ts = d.toLocaleTimeString('en-AU', {hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false});
    return `[${ts}] [${g.source}] ${g.message}`;
  }).join('\n');
  el.scrollTop = el.scrollHeight;
  // Show red badge on tracer button
  const badge = document.getElementById('troubleshoot-glitch-badge');
  if (badge) { badge.textContent = glitches.length; badge.style.display = 'inline'; }
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  // Always log errors/warnings to glitch log
  const t = String(type || 'info').toLowerCase();
  if (t === 'error' || t === 'warning') {
    _glitchLog('toast', message);
  }

  // Pipe UI toasts into troubleshoot trace while tracing is enabled.
  const logLevel = t === 'error' ? 'error' : 'info';
  _troubleshootLog(logLevel, 'Toast', `${type}: ${message}`);

  setTimeout(() => {
    toast.classList.add('remove');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function _troubleshootState() {
  if (!window.__fridaysTroubleshoot) {
    window.__fridaysTroubleshoot = {
      logs: [],
      max: 250,
      enabled: false,
      panelOpen: false,
      panelX: null,
      panelY: null,
    };
  }
  return window.__fridaysTroubleshoot;
}

function _troubleshootTimestamp() {
  try {
    return new Date().toISOString();
  } catch {
    return String(Date.now());
  }
}

function _troubleshootLog(level, message, details) {
  const state = _troubleshootState();
  if (!state.enabled) return;
  state.logs.push({
    ts: _troubleshootTimestamp(),
    level: String(level || 'info').toLowerCase(),
    message: String(message || ''),
    details: details == null ? '' : String(details),
  });
  if (state.logs.length > state.max) {
    state.logs.splice(0, state.logs.length - state.max);
  }
  _renderTroubleshootBadge();
  _renderTroubleshootPanel();
}

function _renderTroubleshootBadge() {
  const btn = document.getElementById('troubleshoot-btn');
  if (!btn) return;
  const _tIcon = '<svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px"><path d="M6 2h4M5.5 2v4.5L3 11.5a1 1 0 00.9 1.5h8.2a1 1 0 00.9-1.5L10.5 6.5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const state = _troubleshootState();
  if (!state.panelOpen) {
    btn.innerHTML = state.enabled ? `${_tIcon} Trace: ON` : `${_tIcon} Trace`;
    btn.style.color = state.enabled ? '#72e6a6' : 'var(--text-dim)';
    btn.style.borderColor = state.enabled ? '#22c55e66' : 'var(--border)';
    return;
  }
  if (!state.enabled) {
    btn.innerHTML = `${_tIcon} Trace: OFF`;
    btn.style.color = 'var(--text-dim)';
    btn.style.borderColor = 'var(--border)';
    return;
  }
  const errors = state.logs.filter(item => item.level === 'error').length;
  const warns = state.logs.filter(item => item.level === 'warn').length;
  if (errors > 0) {
    btn.innerHTML = `${_tIcon} Trace: ON (${errors})`;
    btn.style.color = '#f77';
    btn.style.borderColor = '#f4433666';
  } else if (warns > 0) {
    btn.innerHTML = `${_tIcon} Trace: ON (${warns})`;
    btn.style.color = '#ffb366';
    btn.style.borderColor = '#f59e0b66';
  } else {
    btn.innerHTML = `${_tIcon} Trace: ON`;
    btn.style.color = '#72e6a6';
    btn.style.borderColor = '#22c55e66';
  }
  // M9: mirror error/warning counts onto the Trace tile pills.
  try {
    const errEl = document.getElementById('trace-tile-errors');
    const warnEl = document.getElementById('trace-tile-warnings');
    if (errEl) {
      if (errors > 0) { errEl.textContent = String(errors); errEl.style.display = ''; }
      else errEl.style.display = 'none';
    }
    if (warnEl) {
      if (warns > 0) { warnEl.textContent = String(warns); warnEl.style.display = ''; }
      else warnEl.style.display = 'none';
    }
  } catch (e) {}
}

function _renderTroubleshootToggleBtn() {
  const toggleBtn = document.getElementById('troubleshoot-toggle-btn');
  if (!toggleBtn) return;
  const state = _troubleshootState();
  if (state.enabled) {
    toggleBtn.textContent = 'Stop Trace';
    toggleBtn.style.color = '#72e6a6';
    toggleBtn.style.borderColor = '#22c55e66';
  } else {
    toggleBtn.textContent = 'Start Trace';
    toggleBtn.style.color = 'var(--text)';
    toggleBtn.style.borderColor = 'var(--border)';
  }
}

function _renderTroubleshootPanel() {
  const body = document.getElementById('troubleshoot-log-body');
  const summary = document.getElementById('troubleshoot-summary');
  if (!body || !summary) return;
  const state = _troubleshootState();
  _renderTroubleshootToggleBtn();
  if (!state.enabled) {
    summary.textContent = 'Tracing is OFF';
    body.textContent = 'Click the Trace button to start recording UI actions and runtime errors.';
    return;
  }
  const rows = state.logs.slice(-180);
  const errors = state.logs.filter(item => item.level === 'error').length;
  const warns = state.logs.filter(item => item.level === 'warn').length;
  summary.textContent = `${rows.length} shown · ${errors} errors · ${warns} warnings`;
  if (!rows.length) {
    body.textContent = 'No client errors captured yet.';
    return;
  }
  body.textContent = rows.map((item) => {
    const head = `[${item.ts}] [${item.level.toUpperCase()}] ${item.message}`;
    return item.details ? `${head}\n  ${item.details}` : head;
  }).join('\n\n');
  body.scrollTop = body.scrollHeight;
}

function toggleTroubleshootPanel(forceOpen) {
  const modal = document.getElementById('troubleshoot-modal');
  if (!modal) return;
  const state = _troubleshootState();
  const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : !state.panelOpen;
  state.panelOpen = shouldOpen;
  modal.classList.toggle('open', state.panelOpen);
  _renderTroubleshootBadge();
  _renderTroubleshootPanel();
  _renderGlitchSection();
}

function toggleTroubleshootEnabled(forceEnabled) {
  const state = _troubleshootState();
  const shouldEnable = typeof forceEnabled === 'boolean' ? forceEnabled : !state.enabled;
  state.enabled = shouldEnable;
  if (state.enabled) {
    state.logs.push({
      ts: _troubleshootTimestamp(),
      level: 'info',
      message: 'Trace started',
      details: 'User enabled troubleshoot tracing',
    });
    if (state.logs.length > state.max) {
      state.logs.splice(0, state.logs.length - state.max);
    }
    state.panelOpen = true;
    document.getElementById('troubleshoot-modal')?.classList.add('open');
  }
  _renderTroubleshootBadge();
  _renderTroubleshootPanel();
}

function _initTroubleshootDrag() {
  const modal = document.getElementById('troubleshoot-modal');
  const handle = document.getElementById('troubleshoot-drag-handle');
  if (!modal || !handle || handle.dataset.dragBound === '1') return;
  handle.dataset.dragBound = '1';

  // SE resize grip
  const grip = document.getElementById('troubleshoot-resize-grip');
  if (grip) {
    grip.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const startX = e.clientX;
      const startY = e.clientY;
      const startW = modal.offsetWidth;
      const startH = modal.offsetHeight;
      const onMove = (ev) => {
        const newW = Math.max(280, startW + ev.clientX - startX);
        const newH = Math.max(200, startH + ev.clientY - startY);
        modal.style.width = newW + 'px';
        modal.style.height = newH + 'px';
      };
      const onUp = () => {
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
  }

  handle.addEventListener('mousedown', (event) => {
    if (event.target.closest('button')) return;
    const rect = modal.getBoundingClientRect();
    const offsetX = event.clientX - rect.left;
    const offsetY = event.clientY - rect.top;
    const onMove = (e) => {
      const minX = 8;
      const minY = 8;
      const maxX = Math.max(minX, window.innerWidth - rect.width - 8);
      const maxY = Math.max(minY, window.innerHeight - rect.height - 8);
      const left = Math.min(maxX, Math.max(minX, e.clientX - offsetX));
      const top = Math.min(maxY, Math.max(minY, e.clientY - offsetY));
      modal.style.left = left + 'px';
      modal.style.top = top + 'px';
      modal.style.right = 'auto';
      modal.style.bottom = 'auto';
      const state = _troubleshootState();
      state.panelX = left;
      state.panelY = top;
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  });
}

function clearTroubleshootLogs() {
  const state = _troubleshootState();
  state.logs = [];
  _renderTroubleshootBadge();
  _renderTroubleshootPanel();
  showToast('Troubleshoot log cleared', 'info');
}

async function copyTroubleshootLogs() {
  const state = _troubleshootState();
  const text = state.logs.map((item) => {
    const head = `[${item.ts}] [${item.level.toUpperCase()}] ${item.message}`;
    return item.details ? `${head}\n  ${item.details}` : head;
  }).join('\n\n');
  if (!text) {
    showToast('No troubleshoot logs to copy', 'info');
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast('Troubleshoot logs copied', 'success');
  } catch (e) {
    showToast('Copy failed: ' + (e?.message || e), 'error');
  }
}

function _troubleshootTargetLabel(node) {
  if (!node || !node.tagName) return 'unknown';
  const tag = String(node.tagName).toLowerCase();
  const id = node.id ? `#${node.id}` : '';
  const cls = node.classList && node.classList.length ? '.' + Array.from(node.classList).slice(0, 3).join('.') : '';
  const text = (node.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 64);
  return `${tag}${id}${cls}${text ? ` :: ${text}` : ''}`;
}

