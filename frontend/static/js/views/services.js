// services.js — Service status dropdown + restart buttons

function toggleServicesDropdown() {
  const menu = document.getElementById('services-dropdown-menu');
  const btn  = document.getElementById('services-dropdown-btn');
  if (!menu || !btn) return;
  const open = menu.style.display !== 'none';
  if (open) {
    menu.style.display = 'none';
    return;
  }
  const rect = btn.getBoundingClientRect();
  // Open downward from the home header; upward if the button sits low on screen.
  const openUp = rect.top > window.innerHeight / 2;
  if (openUp) {
    menu.style.top = '';
    menu.style.bottom = (window.innerHeight - rect.top + 6) + 'px';
  } else {
    menu.style.bottom = '';
    menu.style.top = (rect.bottom + 6) + 'px';
  }
  menu.style.right = (window.innerWidth - rect.right) + 'px';
  menu.style.display = 'block';
  loadServicesPanel();
}

// Close dropdown when clicking outside
document.addEventListener('click', e => {
  const wrap = document.getElementById('services-dropdown-wrap');
  if (wrap && !wrap.contains(e.target)) {
    const menu = document.getElementById('services-dropdown-menu');
    if (menu) menu.style.display = 'none';
  }
});

function loadServicesPanel() {
  const panel = document.getElementById('services-panel');
  if (!panel) return;

  fetch('/api/services')
    .then(r => r.json())
    .then(services => {
      services = Array.isArray(services) ? services : [];
      // Update header dot: green if all active, amber if some down, red if most down
      // Only units that exist on this machine count towards the health dot.
      const installed = services.filter(s => s.installed !== false);
      const activeCount = installed.filter(s => s.active).length;
      const dot = document.getElementById('services-dropdown-dot');
      if (dot) {
        dot.style.color = activeCount === installed.length ? '#4caf50'
          : activeCount >= installed.length / 2 ? '#ffb366'
          : '#ff6b6b';
      }

      const envs = ['PROD', 'DEV', 'UAT', 'SHARED', 'RUNTIME'];
      panel.innerHTML = envs.map(env => {
        const rows = services.filter(s => (s.env || 'SHARED') === env);
        if (!rows.length) return '';
        const anyInstalled = rows.some(s => s.installed !== false && s.can_restart !== false);
        const restartAll = env === 'RUNTIME'
          ? `<button onclick="llamaStopModel('', this)" title="Unload every local model (they reload on next use)" style="${_serviceBtnStyle('danger')}">unload all</button>`
          : anyInstalled
            ? `<button onclick="serviceRestartAll('${env}', false, this)" title="Restart ${env}" style="${_serviceBtnStyle()}">↺ all</button>
               <button onclick="serviceRestartAll('${env}', true, this)" title="Hard restart ${env}" style="${_serviceBtnStyle('danger')}">⏻ all</button>`
            : '';
        // Installed units first; units that are not set up on this machine go last, dimmed.
        rows.sort((a, b) => (a.installed === false) - (b.installed === false));
        return `<div style="padding:5px 0;border-bottom:1px solid var(--border);">
          <div style="display:flex;align-items:center;gap:6px;padding:2px 4px 5px;">
            <span style="font-size:10px;color:var(--text-dim);font-weight:700;flex:1;">${env}</span>${restartAll}
          </div>
          ${rows.map(_serviceRowHtml).join('')}
        </div>`;
      }).join('') || '<div style="color:var(--text-dim);font-size:11px;padding:6px;">No services found</div>';
    })
    .catch(() => {
      const panel = document.getElementById('services-panel');
      if (panel) panel.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:6px;">Status unavailable</div>';
    });
}

function _serviceBtnStyle(kind) {
  const color = kind === 'danger' ? '#ffb366' : 'var(--text-dim)';
  return `background:var(--bg);border:1px solid var(--border);color:${color};border-radius:4px;cursor:pointer;font-size:10px;line-height:1;padding:3px 6px;transition:all 0.15s;`;
}

function _serviceRowHtml(svc) {
  if (svc.installed === false) {
    return `<div style="display:flex;align-items:center;gap:7px;padding:3px 6px;opacity:0.45;" title="${svc.id} is not installed on this machine">
      <span style="color:var(--text-dim);font-size:9px;line-height:1;">○</span>
      <span style="font-size:11px;color:var(--text-dim);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${svc.label}</span>
      <span style="font-size:9px;color:var(--text-dim);white-space:nowrap;">not installed</span>
    </div>`;
  }
  if (svc.can_stop_models) return _llamaRowHtml(svc);
  const dotColor = svc.active ? '#4caf50' : svc.status === 'activating' ? '#ffb366' : '#ff6b6b';
  const status = svc.status || 'unknown';
  const enabled = svc.enabled && svc.enabled !== 'enabled' ? ` · ${svc.enabled}` : '';
  const runners = Array.isArray(svc.runners) && svc.runners.length ? ` · ${svc.runners.length} pid` : '';
  const restart = svc.can_restart === false ? '' : `<button onclick="serviceRestart('${svc.id}','${svc.label}',this,false)" title="Restart ${svc.label}" style="${_serviceBtnStyle()}">↺</button>`;
  const hard = svc.can_hard_restart === false ? '' : `<button onclick="serviceRestart('${svc.id}','${svc.label}',this,true)" title="Hard restart ${svc.label}" style="${_serviceBtnStyle('danger')}">⏻</button>`;
  const kill = svc.can_kill ? `<button onclick="ollamaKillRunners(this)" title="Kill runaway Ollama runners" style="${_serviceBtnStyle('danger')}">kill</button>` : '';
  return `<div style="display:flex;align-items:center;gap:7px;padding:5px 6px;border-radius:5px;transition:background 0.12s;"
      onmouseover="this.style.background='rgba(255,255,255,0.04)'"
      onmouseout="this.style.background='none'">
    <span style="color:${dotColor};font-size:9px;line-height:1;" title="${status}">●</span>
    <span style="font-size:12px;color:var(--text);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${svc.id}">${svc.label}</span>
    <span style="font-size:9px;color:var(--text-dim);white-space:nowrap;">${status}${enabled}${runners}</span>
    ${restart}${hard}${kill}
  </div>`;
}

function serviceRestart(serviceId, label, btn, hard) {
  if (btn) { btn.textContent = '…'; btn.style.pointerEvents = 'none'; btn.style.color = '#ffb366'; }
  const isSelf = serviceId === 'swarm-terminal.service';

  fetch(`/api/services/${encodeURIComponent(serviceId)}/restart`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: hard ? 'hard' : 'restart' })
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok && isSelf) {
        // The restart was queued; this server goes down right after answering.
        showToast('Terminal restarting…', 'info');
        _pollUntilBack(btn);
        return;
      }
      if (data.ok) {
        showToast(`${label} ${hard ? 'hard restarted' : 'restarted'}`, 'success');
        if (btn) { btn.textContent = '✓'; btn.style.color = '#4caf50'; }
      } else {
        showToast(`${label}: ${data.output || 'restart failed'}`, 'error');
        if (btn) { btn.textContent = '↺'; btn.style.color = '#ff6b6b'; btn.style.pointerEvents = 'auto'; }
      }
      setTimeout(loadServicesPanel, 2000);
    })
    .catch(() => {
      if (isSelf) {
        // Server killed its own connection — that means it worked. Poll until back.
        showToast('Terminal restarting…', 'info');
        if (btn) { btn.textContent = '…'; btn.style.color = '#ffb366'; }
        _pollUntilBack(btn);
      } else {
        showToast(`${label}: restart failed`, 'error');
        if (btn) { btn.textContent = '↺'; btn.style.color = '#ff6b6b'; btn.style.pointerEvents = 'auto'; }
      }
    });
}

function serviceRestartAll(env, hard, btn) {
  if (btn) { btn.textContent = '…'; btn.style.pointerEvents = 'none'; btn.style.color = '#ffb366'; }
  fetch('/api/services/restart-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ env, hard: !!hard })
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) showToast(`${env} ${hard ? 'hard restarted' : 'restarted'}`, 'success');
      else showToast(`${env}: ${data.error || 'some services failed'}`, 'error');
      if (btn) { btn.textContent = hard ? '⏻ all' : '↺ all'; btn.style.pointerEvents = 'auto'; }
      setTimeout(loadServicesPanel, 2000);
    })
    .catch(() => {
      showToast(`${env}: restart request failed`, 'error');
      if (btn) { btn.textContent = hard ? '⏻ all' : '↺ all'; btn.style.pointerEvents = 'auto'; }
    });
}

function ollamaKillRunners(btn) {
  if (btn) { btn.textContent = '…'; btn.style.pointerEvents = 'none'; btn.style.color = '#ffb366'; }
  fetch('/api/services/ollama/kill-runners', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      const count = (data.killed || []).length;
      if (data.ok) showToast(`Killed ${count} Ollama runner${count === 1 ? '' : 's'}`, 'success');
      else showToast(`Ollama runner kill had errors`, 'error');
      if (btn) { btn.textContent = 'kill'; btn.style.pointerEvents = 'auto'; }
      setTimeout(loadServicesPanel, 1000);
    })
    .catch(() => {
      showToast('Ollama runner kill failed', 'error');
      if (btn) { btn.textContent = 'kill'; btn.style.pointerEvents = 'auto'; }
    });
}

function _pollUntilBack(btn, attempts, sawDown) {
  attempts = attempts || 0;
  if (attempts > 45) {
    showToast('Terminal did not come back — check manually', 'error');
    if (btn) { btn.textContent = '↺'; btn.style.color = '#ff6b6b'; btn.style.pointerEvents = 'auto'; }
    return;
  }
  const retry = down => setTimeout(() => _pollUntilBack(btn, attempts + 1, sawDown || down), 1000);
  fetch('/api/health', { cache: 'no-store' }).then(r => {
    // Wait until the old process has gone (or ~6s passed) before calling it back.
    if (r.ok && (sawDown || attempts >= 6)) {
      showToast('Terminal back online', 'success');
      if (btn) { btn.textContent = '✓'; btn.style.color = '#4caf50'; btn.style.pointerEvents = 'auto'; }
      loadServicesPanel();
    } else {
      retry(!r.ok);
    }
  }).catch(() => retry(true));
}

function _fmtIdle(seconds) {
  if (seconds === null || seconds === undefined) return '';
  if (seconds < 90) return `${seconds}s idle`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m idle`;
  return `${Math.round(seconds / 3600)}h idle`;
}

function _llamaRowHtml(svc) {
  const models = Array.isArray(svc.models) ? svc.models : [];
  const totalGb = models.reduce((sum, m) => sum + Number(m.ram_gb || 0), 0);
  const head = `<div style="display:flex;align-items:center;gap:7px;padding:5px 6px;">
    <span style="color:#4caf50;font-size:9px;line-height:1;">●</span>
    <span style="font-size:12px;color:var(--text);flex:1;">${svc.label}</span>
    <span style="font-size:9px;color:var(--text-dim);white-space:nowrap;">${models.length} loaded${models.length ? ` · ${totalGb.toFixed(1)} GB RAM` : ' · load on demand'}</span>
  </div>`;
  const rows = models.map(m => {
    const safe = String(m.model || '').replace(/[^A-Za-z0-9_.:\-]/g, '');
    const where = m.gpu === false ? 'cpu' : 'gpu';
    return `<div style="display:flex;align-items:center;gap:7px;padding:2px 6px 2px 22px;">
      <span style="font-size:11px;color:var(--text);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="pid ${m.pid} · port ${m.port}">${safe}</span>
      <span style="font-size:9px;color:var(--text-dim);white-space:nowrap;">${where} · ${Number(m.ram_gb || 0).toFixed(1)} GB · ${_fmtIdle(m.idle_seconds)}</span>
      <button onclick="llamaStopModel('${safe}', this)" title="Unload ${safe} (reloads on next use)" style="${_serviceBtnStyle('danger')}">■</button>
    </div>`;
  }).join('');
  return head + rows;
}

function llamaStopModel(model, btn) {
  if (btn) { btn.textContent = '…'; btn.style.pointerEvents = 'none'; btn.style.color = '#ffb366'; }
  fetch('/api/services/llama/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model ? { model } : {})
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) showToast(model ? `Unloaded ${model}` : `Unloaded ${data.stopped} model${data.stopped === 1 ? '' : 's'}`, 'success');
      else showToast(`Unload failed: ${data.error || 'unknown error'}`, 'error');
      loadServicesPanel();
    })
    .catch(() => {
      showToast('Unload request failed', 'error');
      loadServicesPanel();
    });
}
