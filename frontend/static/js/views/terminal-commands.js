// Terminal command execution — /api/exec calls
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// TERMINAL COMMANDS
// ═══════════════════════════════════════════════════════════════════════════

async function _createALMProposal(title, description, priority = 4, options = {}) {
  const almResp = await fetch('/api/alm/status').then(r => r.json()).catch(() => null);
  if (!almResp || almResp.status !== 'enforced') return null;
  const autoApprove = options?.autoApprove !== false;

  const createResp = await fetch('/api/queue', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      agent: 'terminal_ui',
      title,
      description,
      priority,
    })
  });
  const created = await createResp.json().catch(() => ({}));
  const proposalId = created.proposal_id;
  if (!proposalId) throw new Error('ALM proposal creation failed');

  if (autoApprove) {
    await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({status: 'approved'})
    });
  }

  return proposalId;
}

async function _createALMProposalForCommand(cmd) {
  return _createALMProposal(
    'Terminal command execution',
    `Auto-created ALM proposal for terminal command: ${cmd.slice(0, 240)}`,
    4
  );
}

async function _finalizeALMProposal(proposalId) {
  if (!proposalId) return;
  await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: 'executed'})
  }).catch(() => {});
}

async function _rejectALMProposal(proposalId) {
  if (!proposalId) return;
  await fetch(`/api/work-proposals/${encodeURIComponent(proposalId)}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: 'rejected'})
  }).catch(() => {});
}

// ANSI SGR palette for common 3/4-bit colors. Intentionally muted so colored
// output reads well against both light and dark themes.
const _TERM_ANSI_COLORS = {
  '30': '#4a4a4a', '31': '#e06666', '32': '#4caf50', '33': '#f7b84b',
  '34': '#6aa9ff', '35': '#c678dd', '36': '#56b6c2', '37': '#d8d8d8',
  '90': '#7a7a7a', '91': '#ff7b7b', '92': '#7fdc8c', '93': '#ffd07f',
  '94': '#8cb8ff', '95': '#d490e6', '96': '#7fd4dc', '97': '#ffffff',
};

// Convert raw terminal text (with possible ANSI escapes) into safe HTML:
// - parses SGR (color/bold/dim) codes into <span>s
// - highlights known semantic lines (ERROR/WARN/Traceback/PASS/FAIL)
// Everything else is HTML-escaped. Unrecognized escapes are stripped quietly.
function _terminalFormatOutput(text) {
  if (!text) return '';
  // Strip any non-SGR CSI sequences (cursor moves, clears) — they can't render
  // usefully in a <pre>, and leaking them as text is noisy.
  let src = String(text).replace(/\x1b\[[0-9;?]*[A-HJKSTfhlmnpsu]/g, (m) => {
    return /m$/.test(m) ? m : '';
  });
  // Also drop bare ESC chars that remain.
  src = src.replace(/\x1b/g, '');
  // Parse SGR segments: \u001b was already stripped above, but the earlier pass
  // preserved ...m sequences. Rebuild from the pre-strip copy via a matcher.
  const raw = String(text);
  let html = '';
  let openSpans = 0;
  let i = 0;
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  while (i < raw.length) {
    const nextEsc = raw.indexOf('\x1b[', i);
    if (nextEsc === -1) { html += esc(raw.slice(i)); break; }
    html += esc(raw.slice(i, nextEsc));
    const endM = raw.indexOf('m', nextEsc);
    if (endM === -1) { html += esc(raw.slice(nextEsc)); break; }
    const codeStr = raw.slice(nextEsc + 2, endM);
    i = endM + 1;
    // Non-SGR CSI (e.g. cursor moves) — skip silently.
    if (!/^[0-9;]*$/.test(codeStr)) continue;
    const codes = codeStr.split(';').filter(c => c !== '');
    if (codes.length === 0 || codes.includes('0')) {
      while (openSpans > 0) { html += '</span>'; openSpans--; }
      if (codes.length === 0 || (codes.length === 1 && codes[0] === '0')) continue;
    }
    const styles = [];
    for (const c of codes) {
      if (c === '0') continue;
      if (c === '1') styles.push('font-weight:600');
      else if (c === '2') styles.push('opacity:0.7');
      else if (c === '4') styles.push('text-decoration:underline');
      else if (_TERM_ANSI_COLORS[c]) styles.push(`color:${_TERM_ANSI_COLORS[c]}`);
    }
    if (styles.length) {
      html += `<span style="${styles.join(';')}">`;
      openSpans++;
    }
  }
  while (openSpans > 0) { html += '</span>'; openSpans--; }

  // Line-level semantic highlighting. Applied after ANSI parsing so it layers
  // on top of (not instead of) any server-sent colors.
  const lines = html.split('\n');
  const out = lines.map(line => {
    const plain = line.replace(/<[^>]+>/g, '');
    if (/^\s*(Traceback \(most recent call last\)|[A-Za-z_][A-Za-z0-9_.]*Error:|[A-Za-z_][A-Za-z0-9_.]*Exception:)/.test(plain)) {
      return `<span style="color:#ff8a8a;font-weight:600;">${line}</span>`;
    }
    if (/^\s*(ERROR|FATAL|CRITICAL|FAILED|FAIL)\b/i.test(plain) || /\bFAILED\b/.test(plain)) {
      return `<span style="color:#ff8a8a;">${line}</span>`;
    }
    if (/^\s*(WARN(ING)?|DEPRECAT)/i.test(plain)) {
      return `<span style="color:#f7b84b;">${line}</span>`;
    }
    if (/^\s*(PASSED|OK|SUCCESS)\b/i.test(plain) || /\b\d+ passed\b/.test(plain)) {
      return `<span style="color:#7fdc8c;">${line}</span>`;
    }
    return line;
  });
  return out.join('\n');
}

function terminalExpandOutput(copyId, btnId) {
  const state = _terminalStreamState();
  const full = (state.copyStore || {})[copyId];
  if (!full) return;
  const btn = document.getElementById(btnId);
  const card = btn ? btn.closest('.terminal-result-card') : null;
  const pre = card ? card.querySelector('pre') : null;
  if (!pre) return;
  pre.innerHTML = _terminalFormatOutput(full);
  if (btn) btn.remove();
}

async function _renderTerminalResultCard(cmd, output, statusEl, startTime) {
  const state = _terminalStreamState();
  const elapsed = Math.max(0, (Date.now() - startTime) / 1000);
  const ok = statusEl.ok !== false;
  const lines = (output || '').split('\n').filter(l => l.trim()).length;
  const truncated = (output || '').length > 4000;
  const displayOutput = truncated ? (output || '').slice(0, 4000) + '\n[… output truncated]' : (output || '');
  const copyId = 'term-copy-' + Math.random().toString(36).slice(2, 10);
  state.copyStore[copyId] = output || '';
  const copyKeys = Object.keys(state.copyStore || {});
  if (copyKeys.length > 160) delete state.copyStore[copyKeys[0]];
  const rerunId = _terminalStoreActionValue(cmd, 'term-rerun');
  const pinId   = _terminalStoreActionValue(cmd, 'term-pin');
  const entryId = statusEl.entryId || '';
  const statusColor = ok ? 'var(--success, #4caf50)' : 'var(--danger, #f44336)';
  const statusLabel = ok ? '✓' : '✕';
  const btnStyle = 'background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:3px;padding:1px 7px;cursor:pointer;font-size:10px;';
  const ts = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const expandBtnId = 'term-expand-' + Math.random().toString(36).slice(2, 10);
  const expandBtn = truncated
    ? `<button id="${expandBtnId}" onclick="terminalExpandOutput('${copyId}','${expandBtnId}')" style="${btnStyle}">Show full</button>`
    : '';

  return `
    <div class="terminal-result-card" data-terminal-entry-id="${_escHtml(entryId)}" data-terminal-command="${_escHtml(cmd)}" data-terminal-output="${_escHtml((output||'').slice(0,2000))}" style="margin:0;">
      <pre style="margin:0;padding:0;font-family:'SF Mono','Courier New',monospace;font-size:12px;white-space:pre;overflow-x:auto;line-height:1.4;color:${ok ? 'var(--text, #0f9)' : 'var(--danger, #f77)'};user-select:text;">${_terminalFormatOutput(displayOutput)}</pre>
      <div style="display:flex;align-items:center;gap:8px;padding:1px 0 2px;border-bottom:1px solid var(--border);font-size:10px;color:var(--text-dim);user-select:none;">
        <span style="color:${statusColor};font-weight:600;">${statusLabel}</span>
        <span>${Math.round(elapsed * 100) / 100}s</span>
        <span>${lines} line${lines === 1 ? '' : 's'}${truncated ? ' · truncated' : ''}</span>
        <span style="flex:1;"></span>
        ${expandBtn}
        <button onclick="terminalRerunCommand('${rerunId}')" style="${btnStyle}">↩ Rerun</button>
        <button onclick="terminalPinCommand('${pinId}')" style="${btnStyle}"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><path d="M9.5 2.5l4 4-6 6H4v-3.5l6-6z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M7 10v3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Pin</button>
        <button onclick="terminalCopyResult('${copyId}')" style="${btnStyle}">Copy</button>
        <span>${ts}</span>
      </div>
    </div>
  `;
}

async function _runTerminalCommandStream(cmd, outputEl, entryEl, startTime, proposalId, entryId) {
  const state = _terminalStreamState();
  if (state.running) {
    throw new Error('Another command is already running');
  }

  const controller = new AbortController();
  state.running = true;
  state.controller = controller;
  state.commandId = null;
  state.proposalId = proposalId || null;
  _terminalSyncControls();

  const liveWrap = document.createElement('div');
  liveWrap.dataset.terminalEntryId = entryId || '';
  liveWrap.style.cssText = 'margin-top:0;';
  // white-space:pre + overflow-x:auto preserves column alignment (ps aux,
  // git log, journalctl tables) instead of mangling ASCII columns with
  // mid-word wrapping. Long lines horizontally scroll per-entry.
  liveWrap.innerHTML = `
    <pre style="margin:0;padding:0;font-family:'SF Mono','Courier New',monospace;font-size:12px;white-space:pre;overflow-x:auto;line-height:1.4;color:var(--text, #0f9);min-height:1.4em;user-select:text;"></pre>
    <div style="font-size:10px;color:var(--accent, #f7b84b);padding:1px 0 2px;user-select:none;">● running…</div>
  `;
  (entryEl || outputEl).appendChild(liveWrap);
  const pre = liveWrap.querySelector('pre');

  let combined = '';
  let finalStatus = { ok: true };
  let streamError = null;
  let wasStopped = false;

  try {
    const res = await fetch('/api/terminal/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ command: cmd, proposal_id: proposalId }),
      signal: controller.signal,
    });

    if (!res.ok || !res.body) {
      const txt = await res.text().catch(() => 'stream unavailable');
      throw new Error(txt || 'stream unavailable');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let done = false;

    while (!done) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buffer += decoder.decode(value, { stream: true });

      let idx = buffer.indexOf('\n\n');
      while (idx !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        idx = buffer.indexOf('\n\n');

        const dataLine = frame.split('\n').find(line => line.startsWith('data: '));
        if (!dataLine) continue;

        let evt = null;
        try {
          evt = JSON.parse(dataLine.slice(6));
        } catch {
          continue;
        }

        if (evt.type === 'start') {
          state.commandId = evt.command_id || null;
        } else if (evt.type === 'chunk') {
          const txt = evt.text || '';
          combined += txt;
          pre.innerHTML = _terminalFormatOutput(combined);
          if (state.autoScroll) outputEl.scrollTop = outputEl.scrollHeight;
        } else if (evt.type === 'error') {
          finalStatus = { ok: false };
          combined += (combined ? '\n' : '') + `Error: ${evt.error || 'stream error'}`;
          pre.innerHTML = _terminalFormatOutput(combined);
        } else if (evt.type === 'done') {
          finalStatus = { ok: !!evt.ok };
          if (evt.truncated) {
            combined += (combined ? '\n' : '') + '[… output truncated]';
            pre.innerHTML = _terminalFormatOutput(combined);
          }
          done = true;
        }
      }
    }
  } catch (e) {
    if (e && e.name === 'AbortError') {
      wasStopped = true;
      finalStatus = { ok: false };
      combined += (combined ? '\n' : '') + '[stopped by user]';
      pre.innerHTML = _terminalFormatOutput(combined);
    } else {
      streamError = e;
    }
  } finally {
    state.running = false;
    state.controller = null;
    state.commandId = null;
    state.proposalId = null;
    _terminalSyncControls();
  }

  if (streamError) throw streamError;

  await _finalizeALMProposal(proposalId);
  liveWrap.innerHTML = await _renderTerminalResultCard(cmd, combined, { ...finalStatus, entryId }, startTime);
  terminalFilterOutput(_terminalCurrentFilter());
  if (state.autoScroll || wasStopped) outputEl.scrollTop = outputEl.scrollHeight;
}

async function runTerminalCmd() {
  const input = _terminalFind('#terminal-input');
  const output = _terminalFind('#terminal-output');
  if (!input || !output) return;
  const cmd = input.value.trim();
  
  if (!cmd) return;
  terminalToggleHistory(false);
  _terminalPushHistory(cmd);
  const entryId = _terminalAllocEntryId();
  const entryEl = _terminalAppendPromptLine(output, cmd, entryId);

  input.value = '';
  const startTime = Date.now();

  let proposalId = null;
  try {
    proposalId = await _createALMProposalForCommand(cmd);
  } catch (e) {
    // ALM proposal failure is non-fatal — log to output and continue without a proposal ID.
    const warn = document.createElement('div');
    warn.style.cssText = 'font-size:10px;color:var(--text-dim);padding:2px 0;';
    warn.textContent = '⚠ ALM proposal unavailable — command will still run.';
    entryEl.appendChild(warn);
  }

  _runTerminalCommandStream(cmd, output, entryEl, startTime, proposalId, entryId)
    .catch(async (e) => {
      // Fallback to non-stream endpoint if streaming is unavailable.
      try {
        const data = await fetch('/api/terminal/run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({command: cmd, proposal_id: proposalId})
        }).then(r => r.json());
        await _finalizeALMProposal(proposalId);
        const res = document.createElement('div');
        res.innerHTML = await _renderTerminalResultCard(cmd, data.output || '', { ok: data.ok, entryId }, startTime);
        entryEl.appendChild(res);
        terminalFilterOutput(_terminalCurrentFilter());
        output.scrollTop = output.scrollHeight;
      } catch (fallbackErr) {
        await _finalizeALMProposal(proposalId);
        const selfRestart = /^\s*sudo\s+systemctl\s+restart\s+swarm-terminal(\.service)?\s*$/i.test(cmd || '');
        const msg = selfRestart
          ? 'Connection dropped while restarting swarm-terminal. This is expected; wait a few seconds and refresh.'
          : 'Error: ' + (fallbackErr.message || e.message);
        const res = document.createElement('div');
        res.innerHTML = await _renderTerminalResultCard(cmd, msg, { ok: false, entryId }, startTime);
        entryEl.appendChild(res);
        terminalFilterOutput(_terminalCurrentFilter());
        output.scrollTop = output.scrollHeight;
      }
    });
}

// Quick command buttons
async function cmdTerminal(cmd) {
  if (_terminalStreamState().running) {
    showToast('Wait for the active command to finish first', 'error');
    return;
  }
  const output = _terminalFind('#terminal-output');
  if (!output) return;
  terminalToggleHistory(false);
  _terminalPushHistory(cmd);
  const entryId = _terminalAllocEntryId();
  const entryEl = _terminalAppendPromptLine(output, cmd, entryId);

  const startTime = Date.now();

  let proposalId = null;
  try {
    proposalId = await _createALMProposalForCommand(cmd);
  } catch (e) {
    // ALM proposal failure is non-fatal — log to output and continue without a proposal ID.
    const warn = document.createElement('div');
    warn.style.cssText = 'font-size:10px;color:var(--text-dim);padding:2px 0;';
    warn.textContent = '⚠ ALM proposal unavailable — command will still run.';
    entryEl.appendChild(warn);
  }

  _runTerminalCommandStream(cmd, output, entryEl, startTime, proposalId, entryId)
    .catch(async (e) => {
      try {
        const data = await fetch('/api/terminal/run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({command: cmd, proposal_id: proposalId})
        }).then(r => r.json());
        await _finalizeALMProposal(proposalId);
        const res = document.createElement('div');
        res.innerHTML = await _renderTerminalResultCard(cmd, data.output || '', { ok: data.ok, entryId }, startTime);
        entryEl.appendChild(res);
        terminalFilterOutput(_terminalCurrentFilter());
        output.scrollTop = output.scrollHeight;
      } catch (fallbackErr) {
        await _finalizeALMProposal(proposalId);
        const res = document.createElement('div');
        res.innerHTML = await _renderTerminalResultCard(cmd, 'Error: ' + (fallbackErr.message || e.message), { ok: false, entryId }, startTime);
        entryEl.appendChild(res);
        terminalFilterOutput(_terminalCurrentFilter());
        output.scrollTop = output.scrollHeight;
      }
    });
}

