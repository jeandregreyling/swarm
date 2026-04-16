// fridays.js — Fridays system banner: temperature, status, agent and skill panels

(function () {
  'use strict';

  // ── Temperature polling ───────────────────────────────────────────────────
  let _tempInterval = null;

    function _fetchAndRenderTemp() {
      // Temperature gauge moved to System Status panel in monitor.js
    }

  // ── Detail panel ─────────────────────────────────────────────────────────
  let _openPanel = null;
  let _openBtn = null;

  function _closePanel() {
    if (_openPanel) { _openPanel.remove(); _openPanel = null; }
    if (_openBtn) { _openBtn.classList.remove('fridays-banner-btn--active'); _openBtn = null; }
  }

  function _buildRows(rows) {
    return rows.map(([label, value]) =>
      `<div class="detail-row">
        <span class="detail-label">${label}</span>
        <span class="detail-value">${value}</span>
      </div>`
    ).join('');
  }

  function _showPanel(btn, title, contentFn) {
    if (_openBtn === btn) { _closePanel(); return; }
    _closePanel();
    _openBtn = btn;
    btn.classList.add('fridays-banner-btn--active');

    const panel = document.createElement('div');
    panel.className = 'fridays-detail-panel';
    panel.innerHTML = `
      <button class="detail-close" title="Close">&#x2715;</button>
      <h4>${title}</h4>
      <div class="detail-body">Loading…</div>`;
    document.body.appendChild(panel);
    _openPanel = panel;

    panel.querySelector('.detail-close').onclick = _closePanel;
    document.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { _closePanel(); document.removeEventListener('keydown', esc); }
    }, { once: true });

    contentFn(panel.querySelector('.detail-body'));
  }

  // ── Panel content loaders ─────────────────────────────────────────────────
  function _loadStatusPanel(body) {
    fetch('/api/monitor/stats')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) { body.innerHTML = '<span style="color:#f44336;">Unavailable</span>'; return; }
        const temp = data.cpu_temp != null ? data.cpu_temp.toFixed(1) + ' °C' : '—';
        const cpu  = data.cpu_percent != null ? data.cpu_percent.toFixed(1) + ' %' : '—';
        const ram  = (data.ram_used != null && data.ram_total != null)
          ? ((data.ram_used / data.ram_total) * 100).toFixed(1) + ' %'
          : '—';
        const disk = (data.disk_used != null && data.disk_total != null)
          ? ((data.disk_used / data.disk_total) * 100).toFixed(1) + ' %'
          : '—';
        const uptime = data.uptime_human || '—';
        body.innerHTML = _buildRows([
          ['CPU Temp', temp],
          ['CPU Usage', cpu],
          ['RAM Usage', ram],
          ['Disk Usage', disk],
          ['Uptime', uptime],
        ]);
      })
      .catch(() => { body.innerHTML = '<span style="color:#f44336;">Could not load</span>'; });
  }

  function _loadAgentsPanel(body) {
    fetch('/api/agents')
      .then(r => r.ok ? r.json() : null)
      .then(agents => {
        if (!Array.isArray(agents) || !agents.length) {
          body.innerHTML = '<span style="color:rgba(255,255,255,0.5);">No agents found</span>';
          return;
        }
        const enabled = agents.filter(a => a.enabled !== false);
        body.innerHTML = _buildRows(enabled.slice(0, 10).map(a => [
          a.label || a.name,
          a.tier === 'paid' ? 'Online' : a.tier === 'free' ? 'Free' : 'Local'
        ]));
      })
      .catch(() => { body.innerHTML = '<span style="color:#f44336;">Could not load</span>'; });
  }

  function _loadSkillsPanel(body) {
    fetch('/api/skills')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const skills = Array.isArray(data) ? data : (data && Array.isArray(data.skills) ? data.skills : null);
        if (!skills || !skills.length) {
          body.innerHTML = '<span style="color:rgba(255,255,255,0.5);">No skills registered</span>';
          return;
        }
        body.innerHTML = _buildRows(skills.slice(0, 10).map(s => [
          s.name || s,
          s.description ? s.description.slice(0, 30) + (s.description.length > 30 ? '…' : '') : '—'
        ]));
      })
      .catch(() => { body.innerHTML = '<span style="color:#f44336;">Could not load</span>'; });
  }

  // ── Banner render ─────────────────────────────────────────────────────────
  function renderFridaysBanner() {
    if (document.getElementById('fridays-banner')) return; // already mounted

    const banner = document.createElement('div');
    banner.className = 'fridays-banner fridays-banner--active';
    banner.id = 'fridays-banner';
    banner.innerHTML = `
      <span class="fridays-temp" id="fridays-system-temp">—</span>
      <div class="gauge">
        <div class="gauge-body">
          <div class="gauge-fill" id="gauge-fill"></div>
          <div class="gauge-cover"></div>
        </div>
      </div>
      <span class="fridays-banner-spacer"></span>
      <button class="fridays-banner-btn" id="fridays-btn-status" title="System status: CPU, RAM, disk, uptime">Status</button>
      <button class="fridays-banner-btn" id="fridays-btn-agents" title="Active agents and their tiers">Agents</button>
      <button class="fridays-banner-btn" id="fridays-btn-skills" title="Registered system skills">Skills</button>
    `;
    document.body.insertBefore(banner, document.body.firstChild);

    // Wire buttons
    document.getElementById('fridays-btn-status').addEventListener('click', function () {
      _showPanel(this, 'System Status', _loadStatusPanel);
    });
    document.getElementById('fridays-btn-agents').addEventListener('click', function () {
      _showPanel(this, 'Active Agents', _loadAgentsPanel);
    });
    document.getElementById('fridays-btn-skills').addEventListener('click', function () {
      _showPanel(this, 'Skills Registry', _loadSkillsPanel);
    });

    // Close panel on click outside
    document.addEventListener('click', function (e) {
      if (_openPanel && !_openPanel.contains(e.target) && !e.target.closest('.fridays-banner-btn')) {
        _closePanel();
      }
    });

    // Start temperature polling
    _fetchAndRenderTemp();
    _tempInterval = setInterval(_fetchAndRenderTemp, 15000);
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderFridaysBanner);
  } else {
    renderFridaysBanner();
  }

  // Expose for external calls
  window.renderFridaysBanner = renderFridaysBanner;
  window.fridaysBannerRefreshTemp = _fetchAndRenderTemp;
})();
