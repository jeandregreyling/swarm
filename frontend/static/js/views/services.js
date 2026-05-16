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
  // P4-S32: button now lives in the bottom-right env-switcher, so open
  // the menu UPWARD instead of below.
  const rect = btn.getBoundingClientRect();
  // If button is in the lower half of the screen, open upward; else downward
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
      const activeCount = services.filter(s => s.active).length;
      const dot = document.getElementById('services-dropdown-dot');
      if (dot) {
        dot.style.color = activeCount === services.length ? '#4caf50'
          : activeCount >= services.length / 2 ? '#ffb366'
          : '#ff6b6b';
      }

      const envs = ['PROD', 'DEV', 'UAT', 'SHARED', 'RUNTIME'];
      panel.innerHTML = envs.map(env => {
        const rows = services.filter(s => (s.env || 'SHARED') === env);
        if (!rows.length) return '';
        const restartAll = env !== 'RUNTIME'
          ? `<button onclick="serviceRestartAll('${env}', false, this)" title="Restart ${env}" style="${_serviceBtnStyle()}">↺ all</button>
             <button onclick="serviceRestartAll('${env}', true, this)" title="Hard restart ${env}" style="${_serviceBtnStyle('danger')}">⏻ all</button>`
          : `<button onclick="serviceRestart('ollama.service','Ollama Runtime',this,true)" title="Hard restart Ollama" style="${_serviceBtnStyle('danger')}">⏻ ollama</button>
             <button onclick="ollamaKillRunners(this)" title="Kill runaway Ollama runner processes" style="${_serviceBtnStyle('danger')}">kill runners</button>`;
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

function _pollUntilBack(btn, attempts) {
  attempts = attempts || 0;
  if (attempts > 20) {
    showToast('Terminal did not come back — check manually', 'error');
    return;
  }
  fetch('/api/services').then(r => {
    if (r.ok) {
      showToast('Terminal back online', 'success');
      if (btn) { btn.textContent = '✓'; btn.style.color = '#4caf50'; btn.style.pointerEvents = 'auto'; }
      loadServicesPanel();
    } else {
      setTimeout(() => _pollUntilBack(btn, attempts + 1), 1000);
    }
  }).catch(() => setTimeout(() => _pollUntilBack(btn, attempts + 1), 1000));
}
