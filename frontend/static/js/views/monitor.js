// Monitor view — system stats, home dashboard, attention panel
// Extracted from terminal_base.html

function loadMonitorData(win) {
  const content = win.el.querySelector('#monitor-content');
  if (!content) return;

  // Clear any previous timers on this win object
  if (win._monitorTimer)    { clearInterval(win._monitorTimer);    win._monitorTimer    = null; }
  if (win._monitorAlmTimer) { clearInterval(win._monitorAlmTimer); win._monitorAlmTimer = null; }

  window.__monitorWin = win;

  const H = _escHtml;  // local alias
  const bar = (pct, color) =>
    `<div style="background:var(--border);border-radius:3px;height:6px;margin-top:3px;"><div style="background:${color};height:6px;border-radius:3px;width:${Math.min(pct,100)}%;transition:width 0.4s;"></div></div>`;

  const renderMonitorAlm = () => {
    fetch('/api/alm/status')
      .then(r => r.json())
      .then(alm => {
        const el = win.el.querySelector('#monitor-alm-status');
        if (!el) return;
        const badge = alm.status === 'enforced'
          ? '<span style="padding:2px 8px;border-radius:10px;background:#4caf5020;color:#4caf50;border:1px solid #4caf5060;font-size:10px;font-weight:700;">ENFORCED</span>'
          : '<span style="padding:2px 8px;border-radius:10px;background:#ffa50022;color:#ffa500;border:1px solid #ffa50055;font-size:10px;font-weight:700;">WARN</span>';
        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <div style="font-weight:600;">ALM Governance</div>
            ${badge}
          </div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:6px;">
            Vortex: <strong>${alm.time_wizard_active ? 'active' : 'inactive'}</strong> ·
            Sniffles: <strong>${alm.sniffles_enabled ? 'enabled' : 'disabled'}</strong><br>
            Queue: <strong>${alm.work_proposals?.pending || 0}</strong> pending / <strong>${alm.work_proposals?.executed || 0}</strong> executed
          </div>`;
      })
      .catch(() => {
        const el = win.el.querySelector('#monitor-alm-status');
        if (el) el.innerHTML = '<div style="font-weight:600;">ALM Governance</div><div style="font-size:11px;color:#f77;">Failed to load status</div>';
      });
  };

  const renderMonitor = (data) => {
    const cpuColor  = data.cpu_percent > 70 ? '#f44' : data.cpu_percent > 50 ? '#ffa500' : '#4caf50';
    const ramColor  = data.ram_percent > 80 ? '#f44' : data.ram_percent > 60 ? '#ffa500' : '#4caf50';
    const tempColor = data.cpu_temp_c  > 75 ? '#f44' : data.cpu_temp_c > 60 ? '#ffa500' : '#4caf50';
    const swapColor = (data.swap_percent || 0) > 10 ? '#f44' : (data.swap_percent || 0) > 3 ? '#ffa500' : '#4caf50';

    const disks = (data.disks || []).map(d =>
      `<div style="margin-bottom:8px;"><div style="display:flex;justify-content:space-between;">
        <span>${H(d.label || d.mountpoint)}</span>
        <span style="color:var(--text-dim);">${H(String(d.used_gb))}GB / ${H(String(d.total_gb))}GB (${H(String(d.percent))}%)</span>
       </div>${bar(d.percent, d.percent>85?'#f44':d.percent>70?'#ffa500':'#4caf50')}</div>`
    ).join('');

    const pools = Object.entries(data.memory_pools || {}).map(([k, v]) =>
      `<span style="margin-right:10px;">${H(k.replace('memory_',''))}: <strong>${H(String(v))}</strong></span>`
    ).join('');

    const activeModels = (data.active_models || []).map(m => {
      const sizeGb = (Number(m.size || 0) / (1024 * 1024 * 1024)).toFixed(2);
      const vramGb = (Number(m.size_vram || 0) / (1024 * 1024 * 1024)).toFixed(2);
      return `<div style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--window-header);margin-bottom:6px;">
        <div style="font-size:11px;font-weight:600;">${H(m.name || 'unknown model')}</div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">Resident: ${sizeGb} GB · VRAM: ${vramGb} GB</div>
        <div style="font-size:10px;color:var(--text-dim);">Expires: ${H(m.expires_at || 'n/a')}</div>
      </div>`;
    }).join('');

    const runtimeJobs = (data.runtime_jobs || []).map(j => {
      const elapsed    = (Number(j.elapsed_ms || 0) / 1000).toFixed(1);
      const eta        = Number(j.eta_remaining_seconds || 0);
      const runtimeCls = j.runtime_class ? `[${H(j.runtime_class)}] ` : '';
      return `<div style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--window-header);margin-bottom:6px;">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
          <div style="font-size:11px;font-weight:600;">${H(j.agent || 'agent')}</div>
          <div style="font-size:10px;color:var(--text-dim);">${elapsed}s elapsed</div>
        </div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">${runtimeCls}${H(j.stage || j.status || 'running')}</div>
        <div style="font-size:10px;color:var(--text-dim);">ETA remaining: ${eta}s</div>
      </div>`;
    }).join('');

    const monitorInsights = (data.monitor_insights || []).map(line =>
      `<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">• ${H(line)}</div>`
    ).join('');

    content.innerHTML = `
      <div style="font-size:12px;line-height:1.6;padding:4px 0;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
            <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">CPU</div>
            <div style="font-size:18px;font-weight:700;color:${cpuColor};">${(data.cpu_percent||0).toFixed(0)}%</div>
            ${bar(data.cpu_percent||0, cpuColor)}
            <div style="color:var(--text-dim);font-size:10px;margin-top:4px;">Temp: <span style="color:${tempColor};">${data.cpu_temp_c||0}°C</span></div>
          </div>
          <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
            <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">RAM</div>
            <div style="font-size:18px;font-weight:700;color:${ramColor};">${(data.ram_percent||0).toFixed(0)}%</div>
            ${bar(data.ram_percent||0, ramColor)}
            <div style="color:var(--text-dim);font-size:10px;margin-top:4px;">${data.ram_used_gb||0}GB / ${data.ram_total_gb||0}GB</div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
            <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">Acceleration</div>
            <div style="font-size:16px;font-weight:700;color:var(--text);">${H(data.inference_mode || 'unknown')}</div>
            <div style="color:var(--text-dim);font-size:10px;margin-top:4px;">VRAM in use: ${(Number(data.vram_used_gb || 0)).toFixed(2)} GB</div>
            <div style="color:var(--text-dim);font-size:10px;">Model residency: ${(Number(data.resident_models_gb || 0)).toFixed(2)} GB</div>
          </div>
          <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
            <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">Swap</div>
            <div style="font-size:18px;font-weight:700;color:${swapColor};">${(data.swap_percent||0).toFixed(1)}%</div>
            ${bar(data.swap_percent||0, swapColor)}
            <div style="color:var(--text-dim);font-size:10px;margin-top:4px;">Tracks spillover memory pressure during fanout.</div>
          </div>
        </div>
        <div style="margin-bottom:12px;"><div style="font-weight:600;margin-bottom:6px;">Disks</div>${disks || '<span style="color:var(--text-dim);">No disk data</span>'}</div>
        <div style="margin-bottom:10px;"><div style="font-weight:600;margin-bottom:4px;">Pipeline</div>
          <div>Queue: <strong>${data.queue_depth||0}</strong> pending · <strong>${data.queue_processing||0}</strong> processing</div>
          <div>Open tickets: <strong>${data.open_tickets||0}</strong> · Consults today: <strong>${data.consults_today||0}</strong></div>
          <div>Active model: <strong>${H(data.active_model||'none')}</strong></div>
        </div>
        <div style="margin-bottom:12px;padding:10px;border-radius:6px;border:1px solid var(--border);background:var(--card);">
          <div style="font-weight:600;margin-bottom:6px;">Inference Intelligence</div>
          ${monitorInsights || '<span style="color:var(--text-dim);font-size:11px;">No advisory insights.</span>'}
        </div>
        <div style="margin-bottom:12px;"><div style="font-weight:600;margin-bottom:6px;">Agent Runtime (Live)</div>${runtimeJobs || '<span style="color:var(--text-dim);font-size:11px;">No active agent jobs.</span>'}</div>
        <div style="margin-bottom:12px;"><div style="font-weight:600;margin-bottom:6px;">Model Residency (${data.active_models_count || 0})</div>${activeModels || '<span style="color:var(--text-dim);font-size:11px;">No resident models reported.</span>'}</div>
        ${pools ? `<div style="margin-bottom:4px;"><div style="font-weight:600;margin-bottom:4px;">Memory Pools</div><div style="font-size:11px;color:var(--text-dim);">${pools}</div></div>` : ''}
        <div id="monitor-alm-status" style="margin-top:10px;padding:10px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
          <div style="font-weight:600;margin-bottom:4px;">ALM Governance</div>
          <div style="font-size:11px;color:var(--text-dim);">Loading governance status...</div>
        </div>
        <div style="color:var(--text-dim);font-size:10px;margin-top:8px;">Updated ${H(data.last_activity||data.timestamp||'—')}</div>
      </div>`;

    // Render ALM inline after main content is set (first render only or on demand)
    renderMonitorAlm();
  };

  const refreshMonitor = () => {
    // Guard: stop if window has been closed
    if (!winManager.windows.has(win.id)) {
      if (win._monitorTimer)    { clearInterval(win._monitorTimer);    win._monitorTimer    = null; }
      if (win._monitorAlmTimer) { clearInterval(win._monitorAlmTimer); win._monitorAlmTimer = null; }
      return;
    }
    fetch('/api/monitor')
      .then(r => r.json())
      .then(renderMonitor)
      .catch(e => {
        content.innerHTML = `<span style="color:#f77;">Error loading monitor: ${_escHtml(e.message)}</span>`;
      });
  };

  win._monitorRefreshFn = refreshMonitor;
  refreshMonitor();
  // Fast refresh for live stats (2.5s), slow refresh for ALM (30s)
  win._monitorTimer    = setInterval(refreshMonitor,    2500);
  win._monitorAlmTimer = setInterval(renderMonitorAlm, 30000);
}

function monitorManualRefresh() {
  const win = window.__monitorWin;
  if (!win) return;
  const indicator = win.el.querySelector('#monitor-refresh-indicator');
  if (indicator) { indicator.textContent = 'refreshing…'; setTimeout(() => { indicator.textContent = 'auto-refresh 2.5s'; }, 800); }
  if (win._monitorRefreshFn) win._monitorRefreshFn();
}

function loadHomeStats() {
  fetch('/api/monitor')
    .then(r => r.json())
    .then(data => {
      // Parse stat values for color coding
      const parseStat = (val) => val ? parseFloat(val.toString().match(/\d+\.?\d*/)?.[0] || 0) : 0;
      const cpu = data.cpu_percent != null ? data.cpu_percent : parseStat(data.system_load);
      const mem = data.ram_percent  != null ? data.ram_percent  : parseStat(data.memory_usage);
      const agents = parseStat(data.open_tickets || data.agents_online);
      updateChatMiniSystemStats(cpu, mem);
      window.__fridaysChatRelayResource = {
        cpuPercent: Number.isFinite(Number(cpu)) ? Number(cpu) : null,
        ramPercent: Number.isFinite(Number(mem)) ? Number(mem) : null,
        sampledAt: Date.now(),
        source: 'home',
      };

      const activeModels = Array.isArray(data.active_models) ? data.active_models : [];
      const vramGb = activeModels.reduce((sum, model) => {
        const val = Number(model && model.size_vram ? model.size_vram : 0);
        return sum + (Number.isFinite(val) ? val : 0);
      }, 0) / (1024 * 1024 * 1024);
      const residencyGb = activeModels.reduce((sum, model) => {
        const val = Number(model && model.size ? model.size : 0);
        return sum + (Number.isFinite(val) ? val : 0);
      }, 0) / (1024 * 1024 * 1024);

      // Deterministic trend based on previous sample.
      const prev = window.__fridaysHomePrevStats || {};
      const trendFor = (key, current) => {
        if (typeof prev[key] !== 'number') return '→';
        if (current > prev[key] + 0.5) return '↑';
        if (current < prev[key] - 0.5) return '↓';
        return '→';
      };
      window.__fridaysHomePrevStats = {
        cpu,
        mem,
        disk: data.disks && data.disks.length ? Number(data.disks[0].percent || 0) : 0,
        vramGb,
      };
      
      // Determine health colors
      const getCpuHealth = (val) => val > 70 ? 'health-crit' : val > 50 ? 'health-warn' : 'health-good';
      const getMemHealth = (val) => val > 80 ? 'health-crit' : val > 60 ? 'health-warn' : 'health-good';
      const getAgentHealth = (val) => val > 0 ? 'health-good' : 'health-warn';
      const getVramHealth = (val) => val > 0 ? 'health-good' : 'health-warn';
      
      const diskPct = data.disks && data.disks.length ? data.disks[0].percent : null;
      document.getElementById('stat-cpu').innerHTML = `${cpu.toFixed(0)}% <span class="stat-trend">${trendFor('cpu', cpu)}</span>`;
      document.getElementById('stat-mem').innerHTML = `${mem.toFixed(0)}% <span class="stat-trend">${trendFor('mem', mem)}</span>`;
      document.getElementById('stat-disk').innerHTML = diskPct != null ? `${diskPct}% <span class="stat-trend">→</span>` : '—';
      document.getElementById('stat-agents').innerHTML = `${data.queue_depth || 0} <span class="status-dot"></span>`;
      const vramNode = document.getElementById('stat-vram');
      if (vramNode) {
        if (vramGb > 0) {
          vramNode.innerHTML = `${vramGb.toFixed(2)}GB <span class="stat-trend">${trendFor('vramGb', vramGb)}</span>`;
          vramNode.title = `Resident models: ${residencyGb.toFixed(2)} GB`;
        } else {
          vramNode.innerHTML = `CPU-only <span class="stat-trend">→</span>`;
          vramNode.title = `VRAM unavailable; model residency in RAM: ${residencyGb.toFixed(2)} GB`;
        }
      }
      const almNode = document.getElementById('stat-alm');
      if (almNode) almNode.innerHTML = '...';
      
      // Apply color classes to stat cards
      document.querySelector('[id="stat-cpu"]').closest('.stat-card').className = `stat-card ${getCpuHealth(cpu)}`;
      document.querySelector('[id="stat-mem"]').closest('.stat-card').className = `stat-card ${getMemHealth(mem)}`;
      document.querySelector('[id="stat-disk"]').closest('.stat-card').className = `stat-card health-good`;
      document.querySelector('[id="stat-agents"]').closest('.stat-card').className = `stat-card ${getAgentHealth(agents)}`;
      if (vramNode) {
        vramNode.closest('.stat-card').className = `stat-card ${getVramHealth(vramGb)}`;
      }

      fetch('/api/alm/status')
        .then(r => r.json())
        .then(alm => {
          const almNode = document.getElementById('stat-alm');
          if (!almNode) return;
          almNode.textContent = alm.status === 'enforced' ? 'ON' : 'WARN';
          const cls = alm.status === 'enforced' ? 'health-good' : 'health-warn';
          const card = almNode.closest('.stat-card');
          if (card) card.className = `stat-card ${cls}`;

          const studioGov = document.getElementById('studio-governance');
          if (studioGov) {
            studioGov.innerHTML = `ALM: <strong>${alm.status === 'enforced' ? 'enforced' : 'warn'}</strong> · ` +
              `Sniffles: <strong>${alm.sniffles_enabled ? 'enabled' : 'disabled'}</strong> · ` +
              `Pending: <strong>${alm.work_proposals?.pending || 0}</strong>`;
          }
        })
        .catch(() => {
          const almNode = document.getElementById('stat-alm');
          if (almNode) almNode.textContent = 'ERR';
        });
    })
    .catch(e => {
      updateChatMiniSystemStats(null, null);
      console.error('Failed to load home stats:', e);
    });
}


function loadAttentionPanel() {
  const setVal = (id, text, cls) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    const card = el.closest('.stat-card');
    if (card && cls) card.className = 'stat-card ' + cls;
  };

  // /api/monitor has open tickets + duck flags
  fetch('/api/monitor')
    .then(r => r.json())
    .then(d => {
      const openT  = d.open_tickets ?? 0;
      const duckNo = d.duck_flags_today ?? 0;
      setVal('attn-open-tickets', openT, openT > 5 ? 'health-crit' : openT > 0 ? 'health-warn' : 'health-good');
      setVal('attn-duck', duckNo, duckNo > 0 ? 'health-crit' : 'health-good');
    }).catch(() => { setVal('attn-open-tickets','?',''); setVal('attn-duck','?',''); });

  // Active proposals
  fetch('/api/work-proposals')
    .then(r => r.json())
    .then(d => {
      const active = (d.proposals || []).filter(p => !['executed','rejected'].includes(p.status));
      const pending = active.filter(p => p.status === 'pending').length;
      const n = active.length;
      setVal('attn-proposals', n, pending > 0 ? 'health-warn' : n > 0 ? 'health-good' : '');
    }).catch(() => setVal('attn-proposals', '?', ''));

  // Pinned unresolved items
  fetch('/api/deferred')
    .then(r => r.json())
    .then(d => {
      const n = (d.items || []).length;
      setVal('attn-pinned', n, n > 0 ? 'health-warn' : 'health-good');
    }).catch(() => setVal('attn-pinned', '?', ''));

  // Ghost Brief freshness
  fetch('/api/brief')
    .then(r => r.json())
    .then(d => {
      if (!d.brief) { setVal('attn-brief', 'None', 'health-crit'); return; }
      const gen = new Date(d.brief.generated_at);
      const ageH = (Date.now() - gen.getTime()) / 3600000;
      let label, cls;
      if      (ageH < 1)  { label = '<1h ago';               cls = 'health-good'; }
      else if (ageH < 6)  { label = `${Math.floor(ageH)}h ago`; cls = 'health-good'; }
      else if (ageH < 24) { label = `${Math.floor(ageH)}h ago`; cls = 'health-warn'; }
      else                { label = `${Math.floor(ageH/24)}d ago`; cls = 'health-crit'; }
      setVal('attn-brief', label, cls);
    }).catch(() => setVal('attn-brief', '?', ''));
}


