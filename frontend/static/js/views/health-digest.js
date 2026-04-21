// Health Digest — Agent 20's one-stop-shop system visibility
// Shows every subsystem's status at a glance with live updates

function loadHealthDigest(win) {
  var content = win.el.querySelector('#health-content');
  if (!content) return;

  if (win._healthTimer) { clearInterval(win._healthTimer); win._healthTimer = null; }

  var H = typeof _escHtml === 'function' ? _escHtml : function(s){
    var d = document.createElement('div'); d.textContent = s; return d.innerHTML;
  };

  var STATUS_COLORS = {
    healthy:  '#4caf50',
    degraded: '#ffa500',
    error:    '#f44336',
    critical: '#ff1744',
    unknown:  '#9e9e9e'
  };

  var STATUS_ICONS = {
    healthy:  '●',
    degraded: '◐',
    error:    '▲',
    critical: '◆',
    unknown:  '○'
  };

  function dot(status) {
    var c = STATUS_COLORS[status] || STATUS_COLORS.unknown;
    var i = STATUS_ICONS[status] || STATUS_ICONS.unknown;
    return '<span style="color:' + c + ';font-size:14px;margin-right:6px;" title="' + H(status) + '">' + i + '</span>';
  }

  function badge(status) {
    var c = STATUS_COLORS[status] || STATUS_COLORS.unknown;
    return '<span style="padding:2px 8px;border-radius:10px;background:' + c + '20;color:' + c +
      ';border:1px solid ' + c + '60;font-size:10px;font-weight:700;text-transform:uppercase;">' +
      H(status) + '</span>';
  }

  function bar(value, max, color) {
    var pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
    return '<div style="background:var(--border);border-radius:3px;height:6px;margin-top:3px;">' +
      '<div style="background:' + color + ';height:6px;border-radius:3px;width:' + pct +
      '%;transition:width 0.4s;"></div></div>';
  }

  function card(title, status, body) {
    var c = STATUS_COLORS[status] || STATUS_COLORS.unknown;
    return '<div style="background:var(--bg-secondary);border:1px solid ' + c + '40;border-radius:8px;padding:12px;margin-bottom:8px;">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">' +
        '<div style="font-weight:600;font-size:13px;">' + dot(status) + H(title) + '</div>' +
        badge(status) +
      '</div>' +
      '<div style="font-size:12px;opacity:0.85;line-height:1.6;">' + body + '</div>' +
    '</div>';
  }

  function renderDigest(d) {
    var html = '';

    // Overall status banner
    var oc = STATUS_COLORS[d.overall_status] || STATUS_COLORS.unknown;
    html += '<div style="background:' + oc + '15;border:2px solid ' + oc + '60;border-radius:10px;padding:14px;margin-bottom:12px;text-align:center;">' +
      '<div style="font-size:20px;font-weight:700;color:' + oc + ';">' + STATUS_ICONS[d.overall_status] + ' SYSTEM ' + (d.overall_status || 'unknown').toUpperCase() + '</div>' +
      '<div style="font-size:11px;opacity:0.6;margin-top:4px;">Scanned: ' + H(d.scanned_at || '—') + '</div>' +
    '</div>';

    // Grid layout
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">';

    // Agents
    var a = d.agents || {};
    html += card('Agents', a.status,
      H(a.enabled || 0) + ' enabled / ' + H(a.total || 0) + ' total' +
      (a.disabled > 0 ? '<br>' + H(a.disabled) + ' disabled' : ''));

    // Queue
    var q = d.queue || {};
    html += card('Queue', q.status,
      '<b>' + H(q.depth || 0) + '</b> queued · ' + H(q.processing || 0) + ' processing' +
      (q.failed > 0 ? ' · <span style="color:#f44336;">' + H(q.failed) + ' failed</span>' : '') +
      (q.stuck_over_1h > 0 ? '<br><span style="color:#ffa500;">' + H(q.stuck_over_1h) + ' stuck &gt;1h</span>' : ''));

    // Errors
    var e = d.errors || {};
    var svcList = '';
    if (e.by_service) {
      var svcs = Object.keys(e.by_service);
      for (var si = 0; si < svcs.length; si++) {
        svcList += H(svcs[si]) + ': ' + H(e.by_service[svcs[si]]) + (si < svcs.length - 1 ? ', ' : '');
      }
    }
    html += card('Errors', e.status,
      '<b>' + H(e.last_hour || 0) + '</b> last hour · ' + H(e.last_24h || 0) + ' last 24h' +
      (svcList ? '<br>' + svcList : ''));

    // System
    var s = d.system || {};
    var cpuPct = s.cpu_percent || 0;
    var cpuColor = cpuPct > 90 ? '#ff1744' : cpuPct > 70 ? '#ffa500' : '#4caf50';
    html += card('System', s.status,
      'CPU ' + H(cpuPct.toFixed(0)) + '%' + bar(cpuPct, 100, cpuColor) +
      '<br>RAM ' + H((s.ram_available_gb || 0).toFixed(1)) + 'GB free / ' + H((s.ram_used_gb || 0).toFixed(1)) + 'GB used' +
      '<br>Temp ' + H((s.cpu_temp_c || 0).toFixed(0)) + '°C' +
      (s.problems && s.problems.length ? '<br><span style="color:#f44336;">' + s.problems.map(H).join(', ') + '</span>' : ''));

    // Tickets
    var t = d.tickets || {};
    html += card('Tickets', t.status,
      '<b>' + H(t.open || 0) + '</b> open / ' + H(t.total || 0) + ' total' +
      (t.aging_over_24h > 0 ? '<br><span style="color:#ffa500;">' + H(t.aging_over_24h) + ' aging &gt;24h</span>' : '') +
      (t.stale_over_72h > 0 ? '<br><span style="color:#f44336;">' + H(t.stale_over_72h) + ' stale &gt;72h</span>' : ''));

    // Council
    var c = d.council || {};
    var roleHtml = '';
    if (c.role_distribution) {
      var roles = Object.keys(c.role_distribution);
      for (var ri = 0; ri < roles.length; ri++) {
        roleHtml += '<span style="background:var(--bg-primary);padding:1px 6px;border-radius:8px;margin:2px;display:inline-block;font-size:10px;">' +
          H(roles[ri]) + ':' + H(c.role_distribution[roles[ri]]) + '</span>';
      }
    }
    html += card('Council (Agent 20)', c.status,
      '<b>' + H(c.active || 0) + '</b> active · ' + H(c.dismissed || 0) + ' dismissed · ' + H(c.expired || 0) + ' expired' +
      (roleHtml ? '<br>' + roleHtml : ''));

    // Proposals
    var p = d.proposals || {};
    html += card('Proposals', p.status,
      H(p.pending || 0) + ' pending · ' + H(p.approved || 0) + ' approved · ' + H(p.rejected || 0) + ' rejected');

    // Memory
    var m = d.memory || {};
    html += card('Memory', m.status,
      H(m.active_memories || 0) + ' active · ' + H(m.archived || 0) + ' archived' +
      '<br>' + H(m.patterns_tracked || 0) + ' patterns · ' + H(m.high_importance || 0) + ' high-importance');

    // Governance
    var g = d.governance || {};
    html += card('Governance', g.status,
      H(g.governance_entries || 0) + ' entries · ' + H(g.governance_last_24h || 0) + ' last 24h' +
      '<br>' + H(g.decisions_total || 0) + ' decisions · ' + H(g.decisions_pending || 0) + ' pending');

    // Emails
    var em = d.emails || {};
    html += card('Email Pipeline', em.status,
      H(em.backlog || 0) + ' in backlog');

    // Tasks
    var tk = d.tasks || {};
    html += card('Scheduled Tasks', tk.status,
      H(tk.enabled || 0) + ' enabled' +
      (tk.overdue > 0 ? ' · <span style="color:#ffa500;">' + H(tk.overdue) + ' overdue</span>' : '') +
      (tk.recent_failures_24h > 0 ? ' · <span style="color:#f44336;">' + H(tk.recent_failures_24h) + ' failed (24h)</span>' : ''));

    // Self-check
    var sc = d._self_check || {};
    if (sc.warning) {
      html += card('Self-Check', sc.status, '<span style="color:#ffa500;">' + H(sc.warning) + '</span>');
    } else if (sc.problems_found) {
      html += card('Self-Check', sc.status, H(sc.problems_found) + ' subsystem(s) reporting issues');
    }

    html += '</div>'; // close grid

    content.innerHTML = html;
  }

  function renderError(msg) {
    content.innerHTML = '<div style="padding:20px;text-align:center;color:#f44336;">' +
      '<div style="font-size:16px;margin-bottom:8px;">▲ Health Digest Unavailable</div>' +
      '<div style="font-size:12px;opacity:0.7;">' + H(msg) + '</div></div>';
  }

  function refresh() {
    fetch('/api/health/digest')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.error) { renderError(d.error); return; }
        renderDigest(d);
      })
      .catch(function(err) { renderError(String(err)); });
  }

  // Initial load
  content.innerHTML = '<div style="padding:20px;text-align:center;opacity:0.5;">Scanning system…</div>';
  refresh();

  // Auto-refresh every 30 seconds
  win._healthTimer = setInterval(refresh, 30000);
}

// Cleanup when view unmounts
function unloadHealthDigest(win) {
  if (win._healthTimer) { clearInterval(win._healthTimer); win._healthTimer = null; }
}
