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

  return `
    <div class="terminal-result-card" data-terminal-entry-id="${_escHtml(entryId)}" data-terminal-command="${_escHtml(cmd)}" data-terminal-output="${_escHtml((output||'').slice(0,2000))}" style="margin-top:0;">
      <pre style="margin:0;padding:2px 0 2px;font-family:'SF Mono','Courier New',monospace;font-size:12px;white-space:pre-wrap;word-break:break-word;line-height:1.45;color:${ok ? 'var(--text, #0f9)' : 'var(--danger, #f77)'};">${_escHtml(displayOutput)}</pre>
      <div style="display:flex;align-items:center;gap:8px;padding:2px 0 4px;border-bottom:1px solid var(--border);font-size:10px;color:var(--text-dim);">
        <span style="color:${statusColor};font-weight:600;">${statusLabel}</span>
        <span>${Math.round(elapsed * 100) / 100}s</span>
        <span>${lines} line${lines === 1 ? '' : 's'}${truncated ? ' · truncated' : ''}</span>
        <span style="flex:1;"></span>
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
  liveWrap.innerHTML = `
    <pre style="margin:0;padding:2px 0 2px;font-family:'SF Mono','Courier New',monospace;font-size:12px;white-space:pre-wrap;word-break:break-word;line-height:1.45;color:var(--text, #0f9);min-height:1.4em;"></pre>
    <div style="font-size:10px;color:var(--accent, #f7b84b);padding:2px 0 4px;">● running…</div>
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
          pre.textContent = combined;
          if (state.autoScroll) outputEl.scrollTop = outputEl.scrollHeight;
        } else if (evt.type === 'error') {
          finalStatus = { ok: false };
          combined += (combined ? '\n' : '') + `Error: ${evt.error || 'stream error'}`;
          pre.textContent = combined;
        } else if (evt.type === 'done') {
          finalStatus = { ok: !!evt.ok };
          if (evt.truncated) {
            combined += (combined ? '\n' : '') + '[… output truncated]';
            pre.textContent = combined;
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
      pre.textContent = combined;
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

