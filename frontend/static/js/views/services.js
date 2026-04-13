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
  // Position relative to viewport so it clears any overflow:hidden parent
  const rect = btn.getBoundingClientRect();
  menu.style.top  = (rect.bottom + 6) + 'px';
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
      // Update header dot: green if all active, amber if some down, red if most down
      const activeCount = services.filter(s => s.active).length;
      const dot = document.getElementById('services-dropdown-dot');
      if (dot) {
        dot.style.color = activeCount === services.length ? '#4caf50'
          : activeCount >= services.length / 2 ? '#ffb366'
          : '#ff6b6b';
      }

      panel.innerHTML = services.map(svc => {
        const dotColor = svc.active ? '#4caf50' : svc.status === 'activating' ? '#ffb366' : '#ff6b6b';
        const dotTitle = svc.status;
        return `<div style="display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:5px;transition:background 0.12s;"
            onmouseover="this.style.background='rgba(255,255,255,0.04)'"
            onmouseout="this.style.background='none'">
          <span style="color:${dotColor};font-size:9px;line-height:1;" title="${dotTitle}">●</span>
          <span style="font-size:12px;color:var(--text);flex:1;">${svc.label}</span>
          <button onclick="serviceRestart('${svc.id}','${svc.label}',this)"
            title="Restart ${svc.label}"
            style="background:var(--bg);border:1px solid var(--border);color:var(--text-dim);border-radius:4px;cursor:pointer;font-size:12px;line-height:1;padding:3px 7px;transition:all 0.15s;"
            onmouseover="this.style.color='var(--text)';this.style.borderColor='var(--text-dim)'"
            onmouseout="this.style.color='var(--text-dim)';this.style.borderColor='var(--border)'">↺</button>
        </div>`;
      }).join('');
    })
    .catch(() => {
      const panel = document.getElementById('services-panel');
      if (panel) panel.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:6px;">Status unavailable</div>';
    });
}

function serviceRestart(serviceId, label, btn) {
  if (btn) { btn.textContent = '…'; btn.style.pointerEvents = 'none'; btn.style.color = '#ffb366'; }
  const isSelf = serviceId === 'swarm-terminal-prod';

  fetch(`/api/services/${encodeURIComponent(serviceId)}/restart`, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        showToast(`${label} restarted`, 'success');
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
