"""system.py — System & Monitoring routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

system_bp = Blueprint('system', __name__)

@system_bp.route('/api/health')
def api_health():
    """Lightweight health check endpoint. Returns 200 if server is up."""
    return jsonify({'ok': True, 'status': 'up', 'service': 'swarm-terminal'})



@system_bp.route('/')
def index():
    """Render themed terminal. Theme engine handles CSS injection."""
    html = get_themed_html()
    return Response(html, mimetype='text/html')




@system_bp.route('/api/system/time')
def api_system_time():
    """Return current system time in multiple formats for UI clock"""
    return jsonify({
        'timestamp': get_timestamp(),           # "2026-03-26 14:45:33"
        'iso': get_timestamp_iso(),             # ISO 8601 with timezone
        'full_string': get_full_time_string(),  # "Wed, March 26 • 2:45:33 PM UTC"
        'unix': int(__import__('time').time())  # Unix timestamp for JS
    })



@system_bp.route('/api/system')
def api_system():
    """Return full system status for System tab"""
    return jsonify(get_system_status())



@system_bp.route('/api/monitor/stats')
def api_monitor_stats():
    """System snapshot + API usage counts for Monitor tab."""
    import subprocess
    conn = get_connection()

    # System snapshot (live)
    try:
        import psutil
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu  = psutil.cpu_percent(interval=0.2)
        sys_snap = {
            'ram_used_gb':   round(mem.used  / 1e9, 1),
            'ram_total_gb':  round(mem.total / 1e9, 1),
            'ram_percent':   mem.percent,
            'swap_used_gb':  round(swap.used  / 1e9, 1),
            'swap_total_gb': round(swap.total / 1e9, 1),
            'swap_percent':  swap.percent,
            'cpu_percent':   cpu,
        }
    except Exception:
        sys_snap = {}

    # Claude usage
    claude_today = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_used),0) FROM claude_log WHERE date(created_at)=date('now')"
    ).fetchone()
    claude_total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_used),0) FROM claude_log"
    ).fetchone()

    # Serper usage
    serper_today = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='serper' AND event='search' AND date(created_at)=date('now')"
    ).fetchone()[0]
    serper_total = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='serper' AND event='search'"
    ).fetchone()[0]

    # Tavily usage
    tavily_today = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='tavily' AND event='search' AND date(created_at)=date('now')"
    ).fetchone()[0]
    tavily_total = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='tavily' AND event='search'"
    ).fetchone()[0]

    # Service health (systemctl)
    services = {
        'swarm-listener':  'Listener',
        'swarm-telegram':  'Telegram',
        'swarm-discord':   'Discord',
        'swarm-scheduler': 'Scheduler',
        'swarm-terminal-prod':  'Terminal',
        'swarm-skills':    'Skills',
    }
    health = {}
    for svc, label in services.items():
        try:
            r = subprocess.run(['systemctl', 'is-active', svc],
                               capture_output=True, text=True, timeout=3)
            health[svc] = {'label': label, 'state': r.stdout.strip()}
        except Exception:
            health[svc] = {'label': label, 'state': 'unknown'}

    return jsonify({
        'system': sys_snap,
        'claude': {
            'calls_today': claude_today[0],
            'tokens_today': claude_today[1],
            'calls_total': claude_total[0],
            'tokens_total': claude_total[1],
        },
        'serper': {'calls_today': serper_today, 'calls_total': serper_total},
        'tavily': {'calls_today': tavily_today, 'calls_total': tavily_total},
        'services': health,
    })



@system_bp.route('/api/tailscale')
def api_tailscale():
    """Return Tailscale peer list from cached status."""
    import subprocess, json
    try:
        r = subprocess.run(['tailscale', 'status', '--json'],
                           capture_output=True, text=True, timeout=5)
        data = json.loads(r.stdout)
        peers = []
        self_node = data.get('Self', {})
        peers.append({
            'name':   self_node.get('HostName', 'self'),
            'ip':     (self_node.get('TailscaleIPs') or [''])[0],
            'online': True,
            'self':   True,
            'os':     self_node.get('OS', ''),
        })
        for key, peer in (data.get('Peer') or {}).items():
            peers.append({
                'name':   peer.get('HostName', key[:8]),
                'ip':     (peer.get('TailscaleIPs') or [''])[0],
                'online': peer.get('Online', False),
                'self':   False,
                'os':     peer.get('OS', ''),
            })
        return jsonify({'peers': peers, 'error': None})
    except Exception as e:
        return jsonify({'peers': [], 'error': str(e)})



@system_bp.route('/api/sandpits')
def api_sandpits():
    stats = get_sandpit_stats()
    # Normalise into agents list for VS Explorer + keep raw stats
    agents = [
        {'agent': k, 'file_count': v.get('files', 0), 'bytes': v.get('bytes', 0)}
        for k, v in stats.items()
        if k != '_total'
    ]
    return jsonify({
        'agents': agents,
        'stats':  stats,
        'log':    sandpit_log(50),
    })



@system_bp.route('/api/ghost_circle')
def api_ghost_circle():
    from database import get_ghost_circle_entries
    limit = int(request.args.get('limit', 50))
    rows = get_ghost_circle_entries(limit=limit)
    return jsonify([dict(r) for r in rows])



@system_bp.route('/api/monitor')
def api_monitor():
    """Monitor data for the home dashboard."""
    from monitor import get_system_status
    status = get_system_status()
    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        running_jobs = [
            _chat_job_public(j)
            for j in _CHAT_JOBS.values()
            if str(j.get('status', 'running')).lower() == 'running'
        ]
    running_jobs.sort(key=lambda j: j.get('agent') or '')

    active_models = status.get('active_models') or []
    vram_used_bytes = 0
    resident_bytes = 0
    for model in active_models:
        if not isinstance(model, dict):
            continue
        try:
            vram_used_bytes += max(0, int(model.get('size_vram') or 0))
        except Exception:
            pass
        try:
            resident_bytes += max(0, int(model.get('size') or 0))
        except Exception:
            pass

    vram_used_gb = round(vram_used_bytes / (1024 ** 3), 2)
    resident_models_gb = round(resident_bytes / (1024 ** 3), 2)
    if active_models and vram_used_bytes <= 0:
        inference_mode = 'cpu-only'
    elif active_models:
        inference_mode = 'gpu-accelerated'
    else:
        inference_mode = 'idle'

    cpu_pct = float(status.get('cpu_percent') or 0)
    ram_pct = float(status.get('ram_percent') or 0)
    swap_pct = float(status.get('swap_percent') or 0)
    insights = []

    if inference_mode == 'cpu-only' and active_models:
        insights.append('GPU VRAM unavailable: local inference is CPU-only; slowdowns under load are expected.')
    if cpu_pct >= 95 and len(running_jobs) >= 3:
        insights.append('High contention: CPU saturated with multiple active agent jobs.')
    if swap_pct >= 10:
        insights.append('Swap pressure is high: expect longer responses while memory pages move to NVMe swap.')
    elif swap_pct >= 3 and running_jobs:
        insights.append('Swap is active during runtime jobs: throughput may dip, but completion should continue.')
    if ram_pct >= 90:
        insights.append('RAM usage is very high: prefer fewer concurrent local agents for faster turnaround.')

    delayed_agents = []
    for j in running_jobs:
        eta = int(j.get('eta_seconds') or 0)
        elapsed = int(j.get('elapsed_ms') or 0)
        if eta > 0 and elapsed > int(eta * 1400):
            delayed_agents.append(j.get('agent') or 'agent')
    if delayed_agents:
        unique = ', '.join(sorted(set(delayed_agents)))
        insights.append(f'ETA drift detected for: {unique}. Jobs are still running; monitor live stage updates.')

    if not insights:
        insights.append('System stable: no immediate runtime pressure detected.')

    return jsonify({
        'agents_online':  status.get('open_tickets', 0),   # repurposed for display
        'last_activity':  status.get('timestamp', '—'),
        'pending_tasks':  status.get('queue_depth', 0),
        'system_load':    f"{status.get('cpu_percent', 0):.0f}%",
        'memory_usage':   f"{status.get('ram_percent', 0):.0f}%",
        # Rich fields for the Monitor window
        'cpu_percent':    status.get('cpu_percent', 0),
        'cpu_temp_c':     status.get('cpu_temp_c', 0),
        'ram_percent':    status.get('ram_percent', 0),
        'ram_used_gb':    status.get('ram_used_gb', 0),
        'ram_total_gb':   status.get('ram_total_gb', 0),
        'swap_percent':   status.get('swap_percent', 0),
        'active_model':   status.get('active_model', 'none'),
        'active_models':  active_models,
        'active_models_count': status.get('active_models_count', 0),
        'vram_used_gb':   vram_used_gb,
        'resident_models_gb': resident_models_gb,
        'inference_mode': inference_mode,
        'monitor_insights': insights,
        'open_tickets':   status.get('open_tickets', 0),
        'queue_depth':    status.get('queue_depth', 0),
        'queue_processing': status.get('queue_processing', 0),
        'consults_today': status.get('consults_today', 0),
        'disks':          status.get('disks', []),
        'memory_pools':   status.get('memory_pools', {}),
        'runtime_jobs':   running_jobs,
        'duck_flags_today': _get_duck_flags_today(),
    })



@system_bp.route('/api/alm/status')
def api_alm_status():
    """Return ALM governance status for UI visibility and audits."""
    require_approvals = os.environ.get('ALM_REQUIRE_APPROVALS', '1') == '1'
    time_wizard_active = _is_time_wizard_active()
    sniffles_enabled = 'Sniffles' not in DISABLED_AGENTS

    pending = 0
    approved = 0
    executed = 0
    total = 0
    legacy_pending_files = 0

    conn = get_connection()
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='work_proposals'"
        ).fetchone()
        if table:
            rows = conn.execute(
                "SELECT status, COUNT(*) as c FROM work_proposals GROUP BY status"
            ).fetchall()
            for r in rows:
                st = (r['status'] or '').lower()
                c = int(r['c'])
                total += c
                if st == 'pending':
                    pending += c
                elif st == 'approved':
                    approved += c
                elif st == 'executed':
                    executed += c
    finally:
        conn.close()

    try:
        from sandpits import list_proposals
        legacy_pending_files = len(list_proposals() or [])
    except Exception:
        legacy_pending_files = 0

    status = 'enforced' if (require_approvals and time_wizard_active) else 'warn'
    return jsonify({
        'ok': True,
        'status': status,
        'time_wizard_active': time_wizard_active,
        'alm_require_approvals': require_approvals,
        'sniffles_enabled': sniffles_enabled,
        'work_proposals': {
            'total': total,
            'pending': pending,
            'approved': approved,
            'executed': executed,
        },
        'legacy_pending_files': legacy_pending_files,
    })




@system_bp.route('/api/activity')
def api_activity():
    from database import get_activity_log
    since = int(request.args.get('since', 0))
    limit = int(request.args.get('limit', 100))
    logs = get_activity_log(limit=limit, since_id=since)
    
    # Format for frontend
    activities = []
    for log in logs:
        activities.append({
            'timestamp': log.get('created_at', '—')[:16],
            'message': f"{log.get('service', 'System')}: {log.get('event', '')} {log.get('detail', '')}".strip(),
            'level': 'info',  # Could be enhanced based on event type
        })
    
    return jsonify({'activities': activities})



@system_bp.route('/api/activity/stream')
def api_activity_stream():
    """SSE stream — sends new activity_log entries as they arrive."""
    from database import get_activity_log
    import time

    def generate():
        since_id = 0
        # Send last 20 entries on connect so the feed isn't empty
        rows = get_activity_log(limit=20)
        rows.reverse()
        for row in rows:
            yield f"data: {__import__('json').dumps(row)}\n\n"
            since_id = max(since_id, row['id'])

        while True:
            time.sleep(2)
            new_rows = get_activity_log(limit=50, since_id=since_id)
            new_rows.reverse()
            for row in new_rows:
                yield f"data: {__import__('json').dumps(row)}\n\n"
                since_id = max(since_id, row['id'])

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})



@system_bp.route('/api/swarm/globals')
def api_swarm_globals_get():
    conn = get_connection()
    rows = conn.execute("SELECT key, value, description FROM swarm_globals ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])



@system_bp.route('/api/swarm/globals', methods=['PUT'])
def api_swarm_globals_put():
    data = request.get_json() or {}
    key   = (data.get('key')   or '').strip()
    value = (data.get('value') or '').strip()
    if not key:
        return jsonify({'error': 'key required'}), 400
    conn = get_connection()
    conn.execute(
        "INSERT INTO swarm_globals (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
        (key, value)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



@system_bp.route('/api/swarm/status')
def api_swarm_status():
    """Quick swarm health snapshot — no LLM, pure DB. Used by VS tab dashboard."""
    from database import log_activity as _la
    import subprocess, datetime
    conn = get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    try:
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        closed_t   = conn.execute("SELECT COUNT(*) FROM tickets WHERE DATE(closed_at)=DATE('now')").fetchone()[0]
        duck_yes   = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES' AND DATE(created_at)=DATE('now')").fetchone()[0]
        duck_no    = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'  AND DATE(created_at)=DATE('now')").fetchone()[0]
        recent_act = conn.execute(
            "SELECT service, event, detail, created_at FROM activity_log ORDER BY id DESC LIMIT 8"
        ).fetchall()
        
        nine_mem = []
        if 'memory_nine' in tables:
            nine_mem = conn.execute("SELECT subject, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 5").fetchall()
        
        ten_mem = []
        if 'memory_ten' in tables:
            ten_mem = conn.execute("SELECT subject, created_at FROM memory_ten WHERE archived=0 ORDER BY created_at DESC LIMIT 5").fetchall()
        
        debates = []
        if 'debates' in tables:
            debates = conn.execute("SELECT topic, status, rounds FROM debates ORDER BY created_at DESC LIMIT 4").fetchall()
            
        proposals  = []
        try:
            from sandpits import list_proposals
            proposals = [p.get('agent','?') + ': ' + str(p.get('filename',''))[:60] for p in list_proposals()[:4]]
        except Exception:
            pass
    finally:
        conn.close()

    # Service health via systemctl
    svcs = {}
    for svc in ('swarm-listener', 'swarm-telegram', 'swarm-discord', 'swarm-terminal-prod'):
        try:
            r = subprocess.run(['systemctl', 'is-active', svc], capture_output=True, text=True, timeout=2)
            svcs[svc] = r.stdout.strip()
        except Exception:
            svcs[svc] = 'unknown'

    return jsonify({
        'ts':         datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'queue':      {'queued': queued, 'processing': processing},
        'tickets':    {'open': open_t, 'closed_today': closed_t},
        'duck':       {'yes': duck_yes, 'no': duck_no},
        'services':   svcs,
        'activity':   [{'service': r[0], 'event': r[1], 'detail': str(r[2] or '')[:80], 'ts': str(r[3] or '')[:16]} for r in recent_act],
        'nine_memory': [{'subject': r[0], 'ts': str(r[1] or '')[:16]} for r in nine_mem],
        'ten_memory': [{'subject': r[0], 'ts': str(r[1] or '')[:16]} for r in ten_mem],
        'debates':    [{'topic': r[0][:60], 'status': r[1], 'rounds': r[2]} for r in debates],
        'proposals':  proposals,
    })



