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

  // ── In-place update helpers (avoid full innerHTML replacement) ────────────
  const mnEl   = id => win.el.querySelector('#' + id);
  const mnTxt  = (id, v)        => { const e = mnEl(id); if (e) e.textContent = v; };
  const mnHtml = (id, v)        => { const e = mnEl(id); if (e) e.innerHTML   = v; };
  const mnCss  = (id, prop, v)  => { const e = mnEl(id); if (e) e.style[prop] = v; };
  const mnBar  = (id, pct, col) => mnHtml(id,
    `<div style="background:var(--border);border-radius:3px;height:6px;margin-top:3px;">` +
    `<div style="background:${col};height:6px;border-radius:3px;width:${Math.min(pct,100)}%;transition:width 0.4s;"></div></div>`
  );

  const _buildDiskHtml = (disks) => (disks || []).map(d =>
    `<div style="margin-bottom:8px;"><div style="display:flex;justify-content:space-between;">
      <span>${H(d.label || d.mountpoint)}</span>
      <span style="color:var(--text-dim);">${H(String(d.used_gb))}GB / ${H(String(d.total_gb))}GB (${H(String(d.percent))}%)</span>
     </div>${bar(d.percent, d.percent>85?'#f44':d.percent>70?'#ffa500':'#4caf50')}</div>`
  ).join('') || '<span style="color:var(--text-dim);">No disk data</span>';

  const _buildPoolsHtml = (pools) => Object.entries(pools || {}).map(([k, v]) =>
    `<span style="margin-right:10px;">${H(k.replace('memory_',''))}: <strong>${H(String(v))}</strong></span>`
  ).join('');

  const _buildModelsHtml = (models) => (models || []).map(m => {
    const sizeGb = (Number(m.size || 0) / (1024**3)).toFixed(2);
    const vramGb = (Number(m.size_vram || 0) / (1024**3)).toFixed(2);
    return `<div style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--window-header);margin-bottom:6px;">
      <div style="font-size:11px;font-weight:600;">${H(m.name || 'unknown model')}</div>
      <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">Resident: ${sizeGb} GB · VRAM: ${vramGb} GB</div>
      <div style="font-size:10px;color:var(--text-dim);">Expires: ${H(m.expires_at || 'n/a')}</div>
    </div>`;
  }).join('') || '<span style="color:var(--text-dim);font-size:11px;">No resident models reported.</span>';

  const _buildRuntimeHtml = (jobs) => (jobs || []).map(j => {
    const elapsed = (Number(j.elapsed_ms || 0) / 1000).toFixed(1);
    const eta     = Number(j.eta_remaining_seconds || 0);
    const cls     = j.runtime_class ? `[${H(j.runtime_class)}] ` : '';
    return `<div style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--window-header);margin-bottom:6px;">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
        <div style="font-size:11px;font-weight:600;">${H(j.agent || 'agent')}</div>
        <div style="font-size:10px;color:var(--text-dim);">${elapsed}s elapsed</div>
      </div>
      <div style="font-size:10px;color:var(--text-dim);margin-top:3px;">${cls}${H(j.stage || j.status || 'running')}</div>
      <div style="font-size:10px;color:var(--text-dim);">ETA remaining: ${eta}s</div>
    </div>`;
  }).join('') || '<span style="color:var(--text-dim);font-size:11px;">No active agent jobs.</span>';

  const renderMonitor = (data) => {
    const cpuColor  = data.cpu_percent > 70 ? '#f44' : data.cpu_percent > 50 ? '#ffa500' : '#4caf50';
    const ramColor  = data.ram_percent > 80 ? '#f44' : data.ram_percent > 60 ? '#ffa500' : '#4caf50';
    const tempColor = data.cpu_temp_c  > 75 ? '#f44' : data.cpu_temp_c  > 60 ? '#ffa500' : '#4caf50';
    const swapColor = (data.swap_percent || 0) > 10 ? '#f44' : (data.swap_percent || 0) > 3 ? '#ffa500' : '#4caf50';
    const rotation  = Math.round(((data.cpu_temp_c || 0) / 100) * 180);

    if (!win._monitorInitialized) {
      // ── First render only: build the stable skeleton ─────────────────────
      win._monitorInitialized = true;
      content.innerHTML = `
        <div style="font-size:12px;line-height:1.6;padding:4px 0;">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
              <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">CPU</div>
              <div id="mn-cpu-bar"></div>
              <div style="color:var(--text-dim);font-size:10px;margin-top:4px;">Temp: <span id="mn-cpu-temp"></span></div>
              <div id="mn-cpu-gauge" style="width:28px;height:28px;border-radius:50%;border:3px solid var(--border);transform:rotate(90deg);margin:4px auto;"></div>
              <div id="mn-cpu-status" style="color:var(--text-dim);font-size:10px;margin-top:4px;"></div>
            </div>
            <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
              <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">RAM</div>
              <div id="mn-ram-pct" style="font-size:18px;font-weight:700;"></div>
              <div id="mn-ram-bar"></div>
              <div id="mn-ram-detail" style="color:var(--text-dim);font-size:10px;margin-top:4px;"></div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
              <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">Acceleration</div>
              <div id="mn-accel-mode" style="font-size:16px;font-weight:700;color:var(--text);"></div>
              <div id="mn-accel-vram" style="color:var(--text-dim);font-size:10px;margin-top:4px;"></div>
              <div id="mn-accel-res" style="color:var(--text-dim);font-size:10px;"></div>
            </div>
            <div style="background:var(--card);padding:10px;border-radius:6px;border:1px solid var(--border);">
              <div style="color:var(--text-dim);font-size:10px;text-transform:uppercase;margin-bottom:4px;">Swap</div>
              <div id="mn-swap-pct" style="font-size:18px;font-weight:700;"></div>
              <div id="mn-swap-bar"></div>
              <div style="color:var(--text-dim);font-size:10px;margin-top:4px;">Tracks spillover memory pressure during fanout.</div>
            </div>
          </div>
          <div style="margin-bottom:12px;"><div style="font-weight:600;margin-bottom:6px;">Disks</div><div id="mn-disks"></div></div>
          <div style="margin-bottom:10px;"><div style="font-weight:600;margin-bottom:4px;">Pipeline</div><div id="mn-pipeline"></div></div>
          <div style="margin-bottom:12px;padding:10px;border-radius:6px;border:1px solid var(--border);background:var(--card);">
            <div style="font-weight:600;margin-bottom:6px;">Inference Intelligence</div>
            <div id="mn-insights"></div>
          </div>
          <div style="margin-bottom:12px;"><div style="font-weight:600;margin-bottom:6px;">Agent Runtime (Live)</div><div id="mn-runtime"></div></div>
          <div style="margin-bottom:12px;"><div style="font-weight:600;margin-bottom:6px;">Model Residency (<span id="mn-models-count">0</span>)</div><div id="mn-models"></div></div>
          <div id="mn-pools-wrap" style="margin-bottom:4px;display:none;"><div style="font-weight:600;margin-bottom:4px;">Memory Pools</div><div id="mn-pools" style="font-size:11px;color:var(--text-dim);"></div></div>
          <div id="monitor-alm-status" style="margin-top:10px;padding:10px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
            <div style="font-weight:600;margin-bottom:4px;">ALM Governance</div>
            <div style="font-size:11px;color:var(--text-dim);">Loading...</div>
          </div>
          <div id="monitor-services" style="margin-top:10px;padding:10px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
            <div style="font-weight:600;margin-bottom:6px;">Service Health</div>
            <div style="font-size:11px;color:var(--text-dim);">Loading...</div>
          </div>
          <div id="monitor-activity" style="margin-top:10px;padding:10px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
            <div style="font-weight:600;margin-bottom:6px;">System Activity</div>
            <div id="mn-activity-body" style="max-height:200px;overflow-y:auto;">
              <div style="font-size:11px;color:var(--text-dim);">Loading...</div>
            </div>
          </div>
          <div id="mn-timestamp" style="color:var(--text-dim);font-size:10px;margin-top:8px;"></div>
        </div>`;
      // Trigger the slow-refresh sections once immediately after skeleton is ready
      renderMonitorAlm();
      _renderMonitorServices(win);
      _renderMonitorActivity(win);
    }

    // ── Every tick: update only the live-changing values in place ───────────
    mnBar('mn-cpu-bar', data.cpu_percent || 0, cpuColor);
    const tempEl = mnEl('mn-cpu-temp');
    if (tempEl) { tempEl.textContent = `${data.cpu_temp_c || 'N/A'}°C`; tempEl.style.color = tempColor; }
    const gaugeEl = mnEl('mn-cpu-gauge');
    if (gaugeEl) gaugeEl.style.background = `conic-gradient(var(--red,#f44) 0deg ${rotation}deg, var(--bg-tile,#eee) ${rotation}deg 180deg)`;
    mnTxt('mn-cpu-status', (data.cpu_temp_c || 0) > 80 ? 'High Temp Warning' : 'Temp OK');

    mnBar('mn-ram-bar', data.ram_percent || 0, ramColor);
    const ramPctEl = mnEl('mn-ram-pct');
    if (ramPctEl) { ramPctEl.textContent = `${(data.ram_percent||0).toFixed(0)}%`; ramPctEl.style.color = ramColor; }
    mnTxt('mn-ram-detail', `${data.ram_used_gb||0}GB / ${data.ram_total_gb||0}GB`);

    mnTxt('mn-accel-mode', H(data.inference_mode || 'unknown'));
    mnTxt('mn-accel-vram', `VRAM in use: ${(Number(data.vram_used_gb || 0)).toFixed(2)} GB`);
    mnTxt('mn-accel-res',  `Model residency: ${(Number(data.resident_models_gb || 0)).toFixed(2)} GB`);

    mnBar('mn-swap-bar', data.swap_percent || 0, swapColor);
    const swapPctEl = mnEl('mn-swap-pct');
    if (swapPctEl) { swapPctEl.textContent = `${(data.swap_percent||0).toFixed(1)}%`; swapPctEl.style.color = swapColor; }

    mnHtml('mn-disks', _buildDiskHtml(data.disks));
    mnHtml('mn-pipeline',
      `<div>Queue: <strong>${data.queue_depth||0}</strong> pending · <strong>${data.queue_processing||0}</strong> processing</div>` +
      `<div>Open tickets: <strong>${data.open_tickets||0}</strong> · Consults today: <strong>${data.consults_today||0}</strong></div>` +
      `<div>Active model: <strong>${H(data.active_model||'none')}</strong></div>`
    );
    const insights = (data.monitor_insights || []).map(l =>
      `<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">• ${H(l)}</div>`
    ).join('') || '<span style="color:var(--text-dim);font-size:11px;">No advisory insights.</span>';
    mnHtml('mn-insights', insights);
    mnHtml('mn-runtime', _buildRuntimeHtml(data.runtime_jobs));
    mnTxt('mn-models-count', String(data.active_models_count || 0));
    mnHtml('mn-models', _buildModelsHtml(data.active_models));

    const poolsHtml = _buildPoolsHtml(data.memory_pools);
    const poolsWrap = mnEl('mn-pools-wrap');
    if (poolsWrap) { poolsWrap.style.display = poolsHtml ? '' : 'none'; }
    if (poolsHtml) mnHtml('mn-pools', poolsHtml);

    mnTxt('mn-timestamp', `Updated ${H(data.last_activity||data.timestamp||'—')}`);
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
  // Refresh every 20s — this is a health indicator, not a thermal monitor.
  // Backend caches /api/monitor for 5s, so tiles sharing this endpoint don't
  // re-fan-out system calls on every tick.
  win._monitorTimer    = setInterval(refreshMonitor,    20000);
  win._monitorAlmTimer = setInterval(() => {
    if (!winManager.windows.has(win.id)) return;
    renderMonitorAlm();
    _renderMonitorServices(win);
    _renderMonitorActivity(win);
  }, 30000);
}

function monitorManualRefresh() {
  const win = window.__monitorWin;
  if (!win) return;
  const indicator = win.el.querySelector('#monitor-refresh-indicator');
  if (indicator) { indicator.textContent = 'refreshing…'; setTimeout(() => { indicator.textContent = 'auto-refresh 20s'; }, 800); }
  if (win._monitorRefreshFn) win._monitorRefreshFn();
}

function loadHomeStats() {
  // Slim version: just feeds chat mini-stats and resource cache.
  // System Pulse (diamond.js) handles the home dashboard vitals/graph.
  // Uses /api/pulse (the pulse bus) — compact payload, shared 3s cache.
  fetch('/api/pulse')
    .then(r => r.json())
    .then(data => {
      const cpu = (data && data.cpu != null) ? data.cpu : 0;
      const mem = (data && data.ram && data.ram.percent != null) ? data.ram.percent : 0;
      updateChatMiniSystemStats(cpu, mem);
      window.__fridaysChatRelayResource = {
        cpuPercent: Number.isFinite(Number(cpu)) ? Number(cpu) : null,
        ramPercent: Number.isFinite(Number(mem)) ? Number(mem) : null,
        sampledAt: Date.now(),
        source: 'home',
      };
    })
    .catch(e => {
      updateChatMiniSystemStats(null, null);
      console.error('Failed to load home stats:', e);
    });
}


function loadAttentionPanel() {
  // Replaced by System Pulse — delegate to diamond.js
  if (typeof loadSystemPulse === 'function') loadSystemPulse();
}

function _renderMonitorServices(win) {
  const el = win.el.querySelector('#monitor-services');
  if (!el) return;
  fetch('/api/services')
    .then(r => r.json())
    .then(services => {
      if (!services || !services.length) {
        el.innerHTML = '<div style="font-weight:600;margin-bottom:6px;">Service Health</div><div style="font-size:11px;color:var(--text-dim);">No services found.</div>';
        return;
      }
      const rows = services.map(s => {
        const color = s.active ? '#4caf50' : s.status === 'activating' ? '#ffb366' : '#ff6b6b';
        return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;"><span style="color:${color};font-size:8px;">●</span><span style="font-size:11px;flex:1;">${_escHtml(s.label)}</span><span style="font-size:9px;color:var(--text-dim);">${_escHtml(s.status || 'unknown')}</span></div>`;
      }).join('');
      el.innerHTML = `<div style="font-weight:600;margin-bottom:6px;">Service Health</div>${rows}`;
    })
    .catch(() => {
      el.innerHTML = '<div style="font-weight:600;margin-bottom:6px;">Service Health</div><div style="font-size:11px;color:#f77;">Failed to load</div>';
    });
}

function _renderMonitorActivity(win) {
  const body = win.el.querySelector('#mn-activity-body');
  if (!body) return;
  fetch('/api/activity')
    .then(r => r.json())
    .then(data => {
      const acts = (data.activities || []).slice(0, 15);
      if (!acts.length) {
        body.innerHTML = '<div style="font-size:11px;color:var(--text-dim);">No recent activity.</div>';
        return;
      }
      body.innerHTML = acts.map(a => {
        let color = 'var(--text)';
        if (a.level === 'error') color = '#f77';
        else if (a.level === 'warning') color = '#ffa500';
        else if (a.level === 'success') color = '#4caf50';
        return `<div style="font-size:11px;color:${color};padding:2px 0;"><span style="color:var(--text-dim);font-size:9px;">[${_escHtml(a.timestamp || '')}]</span> ${_escHtml(a.message || '')}</div>`;
      }).join('');
    })
    .catch(() => {
      body.innerHTML = '<div style="font-size:11px;color:#f77;">Failed to load</div>';
    });
}


