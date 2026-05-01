"""
monitor.py — Seven's Swarm system monitor
═══════════════════════════════════════════════════════════════════════════════
Records system stats every 5 minutes. Sends daily email report.
Librarian calls get_system_status() to answer health questions.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
from database import get_connection
from config import GHOST_EMAIL
from email_handler import send_reply
import psutil
from core import llm as _llm
from datetime import datetime
import time

def get_active_model():
    try:
        running = _llm.ps()
        if running and hasattr(running, 'models') and running.models:
            return running.models[0].model
        return 'none'
    except Exception:
        return 'unknown'

def get_consultations_today():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM conversations WHERE created_at > date('now')")
    count = c.fetchone()[0]
    c.execute("SELECT MAX(created_at) FROM conversations")
    last = c.fetchone()[0]
    conn.close()
    return count, last

def record_stats():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu = psutil.cpu_percent(interval=1)
    try:
        temps = psutil.sensors_temperatures()
        cpu_temp = temps.get('coretemp', temps.get('k10temp', []))
        cpu_temp = round(cpu_temp[0].current, 1) if cpu_temp else 0
    except Exception:
        cpu_temp = 0
    active = get_active_model()
    consult_count, last_consult = get_consultations_today()

    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO system_stats
        (ram_total_gb, ram_used_gb, ram_available_gb, cpu_percent,
         swap_used_gb, active_model, consultations_today, last_consultation, cpu_temp_c)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        round(mem.total / 1e9, 1),
        round(mem.used / 1e9, 1),
        round(mem.available / 1e9, 1),
        cpu,
        round(swap.used / 1e9, 1),
        active,
        consult_count,
        last_consult,
        cpu_temp
    ))
    conn.commit()
    conn.close()
    return {
        'ram_used': round(mem.used / 1e9, 1),
        'ram_available': round(mem.available / 1e9, 1),
        'cpu': cpu,
        'active_model': active,
        'consultations_today': consult_count,
        'cpu_temp': cpu_temp
    }

def get_current_stats():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM system_stats ORDER BY recorded_at DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if not row:
        return 'No stats recorded yet.'
    return (
        f'RAM: {row["ram_used_gb"]}GB used / {row["ram_total_gb"]}GB total | '
        f'CPU: {row["cpu_percent"]}% | '
        f'Active model: {row["active_model"]} | '
        f'Consultations today: {row["consultations_today"]}'
    )


def get_disk_info():
    """Return disk usage for the active storage paths."""
    disks = []
    for path, label in [('/', 'nvme1 — OS / Swarm code / Ollama models'), ('/mnt/swarm_drive', 'nvme0 — Linux data')]:
        try:
            usage = psutil.disk_usage(path)
            disks.append({
                'path':       path,
                'label':      label,
                'total_gb':   round(usage.total / 1e9, 1),
                'used_gb':    round(usage.used / 1e9, 1),
                'free_gb':    round(usage.free / 1e9, 1),
                'percent':    usage.percent,
            })
        except Exception:
            pass
    return disks


def get_ollama_models():
    """Return list of locally available Ollama models."""
    try:
        models = _llm.list_models()
        return [m.model for m in models.models] if hasattr(models, 'models') else []
    except Exception:
        return []


# Cache for get_model_details — model metadata is static, so we cache for 5 min.
# Prevents /api/monitor polling from storming ollama with /api/show calls per loaded model.
_MODEL_DETAILS_CACHE = {}
_MODEL_DETAILS_TTL = 300  # seconds


def get_model_details(model):
    """
    Return rich metadata for a single model via ollama.show().
    Cached for 5 minutes — model metadata does not change at runtime.
    Fields: family, parameter_size, quantization, format, capabilities, parameters.
    """
    now = time.time()
    cached = _MODEL_DETAILS_CACHE.get(model)
    if cached and (now - cached[0]) < _MODEL_DETAILS_TTL:
        return cached[1]
    try:
        result  = _llm.show(model)
        details = getattr(result, 'details', None)
        payload = {
            'model':          model,
            'family':         (getattr(details, 'family', '') or '') if details else '',
            'parameter_size': (getattr(details, 'parameter_size', '') or '') if details else '',
            'quantization':   (getattr(details, 'quantization_level', '') or '') if details else '',
            'format':         (getattr(details, 'format', '') or '') if details else '',
            'capabilities':   list(getattr(result, 'capabilities', None) or []),
            'parameters':     (getattr(result, 'parameters', '') or ''),
        }
        _MODEL_DETAILS_CACHE[model] = (now, payload)
        return payload
    except Exception:
        return {'model': model}


# Short TTL cache for get_system_status() — collapses concurrent pollers
# (monitor tile + home stats + ollama panel + chat relay) into one computation.
# 3s matches the frontend pulse cadence: every UI poll gets fresh data, but
# concurrent subscribers share a single snapshot.
_SYSTEM_STATUS_CACHE = {'ts': 0.0, 'payload': None}
_SYSTEM_STATUS_TTL = 3.0


def get_system_status():
    """
    Full system status dict — called by Librarian to answer health questions
    and by the terminal /api/system endpoint.
    Cached for 5 seconds so multiple UI tiles share one snapshot.
    """
    now = time.time()
    if _SYSTEM_STATUS_CACHE['payload'] is not None \
            and (now - _SYSTEM_STATUS_CACHE['ts']) < _SYSTEM_STATUS_TTL:
        return _SYSTEM_STATUS_CACHE['payload']

    mem  = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu  = psutil.cpu_percent(interval=1)

    try:
        temps = psutil.sensors_temperatures()
        cpu_temp_list = temps.get('coretemp', temps.get('k10temp', []))
        cpu_temp = round(cpu_temp_list[0].current, 1) if cpu_temp_list else 0
    except Exception:
        cpu_temp = 0

    # Memory pools from DB
    pool_counts = {}
    try:
        conn = get_connection()
        for pool in ['memory', 'memory_llama', 'memory_qwen', 'memory_gemma', 'memory_eight', 'memory_nine']:
            pool_counts[pool] = conn.execute(
                f"SELECT COUNT(*) FROM {pool} WHERE archived=0"
            ).fetchone()[0]
        consults_today = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE created_at > date('now')"
        ).fetchone()[0]
        open_tickets = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE status='open'"
        ).fetchone()[0]
        queue_depth = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE status='queued'"
        ).fetchone()[0]
        queue_processing = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE status='processing'"
        ).fetchone()[0]
        try:
            from sandpits import list_proposals
            pending_proposals = len(list_proposals())
        except Exception:
            pending_proposals = 0
        conn.close()
    except Exception:
        pool_counts = {}
        consults_today = 0
        open_tickets = 0
        queue_depth = 0
        queue_processing = 0
        pending_proposals = 0

    # Active Ollama models — basic fields only (name/size/vram/expiry).
    # Rich metadata (family/quantisation/capabilities) is served on demand by
    # /api/ollama/show/<model> which is cached for 5 minutes. Fanning out
    # ollama.show() per loaded model on every poll tick was the root cause of
    # the April 2026 CPU runaway — do NOT re-introduce it here.
    active_models = []
    try:
        running = _llm.ps()
        if hasattr(running, 'models') and running.models:
            for m in running.models:
                name = getattr(m, 'model', '') or ''
                active_models.append({
                    'name':       name,
                    'size':       int(getattr(m, 'size', 0) or 0),
                    'size_vram':  int(getattr(m, 'size_vram', 0) or 0),
                    'expires_at': str(getattr(m, 'expires_at', '') or ''),
                })
        active_model = active_models[0]['name'] if active_models else 'none'
    except Exception:
        active_model = 'unknown'
        active_models = []

    payload = {
        'ram_total_gb':    round(mem.total / 1e9, 1),
        'ram_used_gb':     round(mem.used / 1e9, 1),
        'ram_available_gb':round(mem.available / 1e9, 1),
        'ram_percent':     mem.percent,
        'swap_used_gb':    round(swap.used / 1e9, 1),
        'swap_total_gb':   round(swap.total / 1e9, 1),
        'swap_percent':    swap.percent,
        'cpu_percent':     cpu,
        'cpu_temp_c':      cpu_temp,
        'cpu_cores':       psutil.cpu_count(logical=False),
        'cpu_threads':     psutil.cpu_count(logical=True),
        'active_model':    active_model,
        'active_models':   active_models,
        'active_models_count': len(active_models),
        'disks':           get_disk_info(),
        'memory_pools':      pool_counts,
        'consults_today':    consults_today,
        'open_tickets':      open_tickets,
        'queue_depth':       queue_depth,
        'queue_processing':  queue_processing,
        'pending_proposals': pending_proposals,
        'timestamp':         datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    _SYSTEM_STATUS_CACHE['ts'] = now
    _SYSTEM_STATUS_CACHE['payload'] = payload
    return payload


def librarian_health_summary():
    """
    Plain-text system health summary Librarian can include in responses.
    Called by orchestrator when question routing detects is_system=True.
    """
    s = get_system_status()
    lines = [
        f"System status as of {s['timestamp']}:",
        f"  RAM: {s['ram_used_gb']}GB used / {s['ram_total_gb']}GB total ({s['ram_percent']}%)",
        f"  CPU: {s['cpu_percent']}% | Temp: {s['cpu_temp_c']}°C | Cores: {s['cpu_cores']} physical / {s['cpu_threads']} threads",
        f"  Active model: {s['active_model']}",
        f"  Consultations today: {s['consults_today']} | Open tickets: {s['open_tickets']}",
    ]
    if s.get('disks'):
        for d in s['disks']:
            lines.append(f"  Disk [{d['label']}]: {d['used_gb']}GB / {d['total_gb']}GB ({d['percent']}% used)")
    if s.get('memory_pools'):
        pools = s['memory_pools']
        lines.append(
            f"  Memory: shared={pools.get('memory',0)} "
            f"LLaMA={pools.get('memory_llama',0)} "
            f"Qwen={pools.get('memory_qwen',0)} "
            f"Gemma={pools.get('memory_gemma',0)} "
            f"Eight={pools.get('memory_eight',0)} "
            f"Nine={pools.get('memory_nine',0)}"
        )
    return '\n'.join(lines)

def send_daily_report():
    stats = record_stats()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM memory")
    shared_mem = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memory_llama")
    llama_mem = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memory_qwen")
    qwen_mem = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memory_gemma")
    gemma_mem = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM conversations WHERE created_at > date('now')")
    today_consults = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM trusted_senders")
    trusted = c.fetchone()[0]
    conn.close()

    report = (
        f'=== Seven Swarm Daily Report {datetime.now().strftime("%Y-%m-%d")} ===\r\n\r\n'
        f'System:\r\n'
        f'  RAM used: {stats["ram_used"]}GB / available: {stats["ram_available"]}GB\r\n'
        f'  CPU: {stats["cpu"]}% | Temp: {stats.get("cpu_temp",0)}°C\r\n'
        f'  Active model: {stats["active_model"]}\r\n\r\n'
        f'Activity:\r\n'
        f'  Consultations today: {today_consults}\r\n'
        f'  Trusted senders: {trusted}\r\n\r\n'
        f'Memory:\r\n'
        f'  Shared verified: {shared_mem} entries\r\n'
        f'  LLaMA personal: {llama_mem} entries\r\n'
        f'  Qwen personal: {qwen_mem} entries\r\n'
        f'  Gemma verdicts: {gemma_mem} entries\r\n\r\n'
        f'Sent by Seven\'s Swarm Monitor'
    )
    send_reply(
        to_address=GHOST_EMAIL,
        subject=f'[Swarm] Daily report {datetime.now().strftime("%Y-%m-%d")}',
        body=report
    )
    print('[Monitor] Daily report sent.')

def run_forever(interval=300):
    print(f'\n=== Seven Swarm System Monitor ===')
    print(f'Recording stats every {interval} seconds.')
    print('Press Ctrl+C to stop.\n')
    while True:
        try:
            stats = record_stats()
            print(f'[Monitor] {datetime.now().strftime("%H:%M")} | RAM: {stats["ram_used"]}GB used | CPU: {stats["cpu"]}% | Temp: {stats.get("cpu_temp",0)}°C | Model: {stats["active_model"]} | Consults today: {stats["consultations_today"]}')
        except Exception as e:
            print(f'[Monitor] Error: {str(e)}')
        time.sleep(interval)

if __name__ == '__main__':
    run_forever()