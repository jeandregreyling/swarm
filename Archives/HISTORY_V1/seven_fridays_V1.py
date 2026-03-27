"""
seven_fridays.py — Seven+Fridays Local Operator
═══════════════════════════════════════════════════════════════════════════════
The local command loop that actually runs the swarm.

Not a dashboard. Not a web UI. A local operator process with:
  - Direct SQLite access (no HTTP round-trips)
  - Real gate checks (waits for actual DB state changes)
  - Nine (Claude) embedded as architectural partner
  - Full tool access: skills, agents, proposals, housekeeping
  - Session memory logged to sandpits/nine/session_YYYY-MM-DD.log

Usage:
  python3 seven_fridays.py

Requires:
  - ANTHROPIC_API_KEY in environment or /etc/environment (for Nine)
  - sudo NOPASSWD for systemctl restart swarm-* (for service restart)
    add to /etc/sudoers: seven ALL=(ALL) NOPASSWD: /bin/systemctl restart swarm-*

Ghost Layer: Ghost (operator) + Nine (architect) + Duck (checker) + Sniffles (auditor)
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time
import subprocess
import textwrap
import re
import readline
import atexit
from datetime import datetime, date

sys.path.insert(0, '/home/seven/swarm')

from database       import get_connection, log_activity
from queue_manager  import get_queue_depth
from sandpits       import list_proposals, read_proposal, delete_proposal
from config         import NINE_SYSTEM_PROMPT, GHOST_EMAIL

try:
    import anthropic
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False


# ── Constants ─────────────────────────────────────────────────────────────────

VERSION       = '1.0.0'
HISTORY_FILE  = '/home/seven/swarm/sandpits/nine/.fridays_history'
SESSION_DIR   = '/home/seven/swarm/sandpits/nine'
PROMPT        = 'seven> '

VALID_SERVICES = {
    'listener':     'swarm-listener',
    'terminal':     'swarm-terminal',
    'monitor':      'swarm-monitor',
    'telegram':     'swarm-telegram',
    'discord':      'swarm-discord',
    'sniffer':      'swarm-sniffer',
    'housekeeping': 'swarm-housekeeping',
}

AGENT_TABLES = {
    'llama':  'memory_llama',
    'qwen':   'memory_qwen',
    'gemma':  'memory_gemma',
    'eight':  'memory_eight',
    'nine':   'memory_nine',
}


# ── Session logging ────────────────────────────────────────────────────────────

def _session_log_path():
    return os.path.join(SESSION_DIR, f'session_{date.today().isoformat()}.log')

def slog(line):
    try:
        with open(_session_log_path(), 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%H:%M:%S")}] {line}\n')
    except Exception:
        pass


# ── Readline setup ─────────────────────────────────────────────────────────────

def setup_readline():
    readline.set_history_length(500)
    if os.path.exists(HISTORY_FILE):
        try:
            readline.read_history_file(HISTORY_FILE)
        except Exception:
            pass
    atexit.register(_save_history)

def _save_history():
    try:
        readline.write_history_file(HISTORY_FILE)
    except Exception:
        pass


# ── Gate check ────────────────────────────────────────────────────────────────

def _activity_watermark():
    """Return the current MAX id from activity_log — used as a 'since' marker."""
    conn = get_connection()
    row  = conn.execute("SELECT MAX(id) FROM activity_log").fetchone()
    conn.close()
    return row[0] or 0

def gate_wait(service_match, event_prefix, since_id=None, timeout=120, poll=1.5):
    """
    Poll activity_log until a matching row appears after since_id, or timeout.
    Returns (True, row) on match, (False, None) on timeout.
    """
    if since_id is None:
        since_id = _activity_watermark()
    deadline = time.time() + timeout
    while time.time() < deadline:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, service, event, detail, created_at FROM activity_log "
            "WHERE id > ? ORDER BY id ASC LIMIT 50",
            (since_id,)
        ).fetchall()
        conn.close()
        for r in rows:
            s_ok = (service_match is None) or (r[1] == service_match)
            e_ok = (event_prefix is None) or r[2].startswith(event_prefix)
            if s_ok and e_ok:
                return True, dict(zip(['id','service','event','detail','created_at'], r))
        time.sleep(poll)
    return False, None


# ── System state helpers ───────────────────────────────────────────────────────

def _svc_status(svc_name):
    try:
        r = subprocess.run(
            ['systemctl', 'is-active', svc_name],
            capture_output=True, text=True, timeout=3
        )
        return r.stdout.strip() == 'active'
    except Exception:
        return None

def _queue_info():
    conn = get_connection()
    queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
    processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
    conn.close()
    return queued, processing

def _open_tickets():
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
    conn.close()
    return n

def _pending_proposals():
    try:
        return len(list_proposals())
    except Exception:
        return 0

def build_swarm_context():
    """Assemble a brief plain-text swarm state snapshot — injected into Nine calls."""
    queued, processing = _queue_info()
    lines = [
        f'=== Swarm state: {datetime.now().strftime("%Y-%m-%d %H:%M")} ===',
        f'Queue:       {queued} queued, {processing} processing',
        f'Open tickets: {_open_tickets()}',
        f'Proposals:   {_pending_proposals()} pending',
    ]
    # Last 5 activity entries
    conn = get_connection()
    recent = conn.execute(
        "SELECT service, event, detail, created_at FROM activity_log "
        "ORDER BY id DESC LIMIT 5"
    ).fetchall()
    conn.close()
    if recent:
        lines.append('Recent activity:')
        for r in recent:
            lines.append(f'  {r[3][11:16]}  {r[0]:<12} {r[1]:<20} {(r[2] or "")[:60]}')
    return '\n'.join(lines)


# ── Output helpers ─────────────────────────────────────────────────────────────

def _dot(active):
    return '●' if active else '○'

def _wrap(text, width=80, indent='  '):
    return '\n'.join(
        textwrap.fill(line, width=width, subsequent_indent=indent) if line.strip() else line
        for line in text.splitlines()
    )


# ── Banner ────────────────────────────────────────────────────────────────────

def print_banner():
    queued, processing = _queue_info()
    open_t   = _open_tickets()
    props    = _pending_proposals()
    svcs     = {k: _svc_status(v) for k, v in VALID_SERVICES.items()}

    print()
    print(f'  Seven+Fridays  v{VERSION}  ●  seven-potato  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('  ' + '─' * 68)

    # Queue + tickets
    print(f'  Queue       {queued} queued  {processing} processing   '
          f'Tickets  {open_t} open   Proposals  {props} pending')
    print()

    # Services
    svc_line = '  Services    '
    for short, full in VALID_SERVICES.items():
        state = svcs.get(short)
        dot   = _dot(state) if state is not None else '?'
        svc_line += f'{dot} {short}  '
    print(svc_line.rstrip())
    print()

    # System
    if _PSUTIL_OK:
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu  = psutil.cpu_percent(interval=0.2)
        print(f'  RAM  {mem.used/1e9:.1f}/{mem.total/1e9:.1f}GB  '
              f'Swap  {swap.used/1e9:.1f}/{swap.total/1e9:.1f}GB  '
              f'CPU  {cpu:.0f}%')
        print()

    print('  ' + '─' * 68)
    print("  Type 'help' for commands.  Nine is available via 'ask nine <question>'.")
    print()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_status(parts):
    """Show full swarm state."""
    queued, processing = _queue_info()
    open_t  = _open_tickets()
    props   = _pending_proposals()

    print()
    print(f'  SWARM STATUS  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('  ' + '─' * 50)
    print(f'  Queue:     {queued} queued, {processing} processing')
    print(f'  Tickets:   {open_t} open')
    print(f'  Proposals: {props} pending')
    print()

    print('  Services:')
    for short, full in VALID_SERVICES.items():
        active = _svc_status(full)
        dot    = _dot(active) if active is not None else '?'
        status = 'active' if active else ('inactive' if active is False else 'unknown')
        print(f'    {dot}  {full:<28} {status}')
    print()

    if _PSUTIL_OK:
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu  = psutil.cpu_percent(interval=0.5)
        try:
            temps = psutil.sensors_temperatures()
            temp_list = temps.get('coretemp', temps.get('k10temp', []))
            temp_c = f'{temp_list[0].current:.0f}°C' if temp_list else '—'
        except Exception:
            temp_c = '—'
        print(f'  RAM:   {mem.used/1e9:.1f}GB used / {mem.total/1e9:.1f}GB  ({mem.percent:.0f}%)')
        print(f'  Swap:  {swap.used/1e9:.1f}GB / {swap.total/1e9:.1f}GB nvme0  ({swap.percent:.0f}%)')
        print(f'  CPU:   {cpu:.0f}%  {temp_c}')
        print()

    # Recent activity
    conn = get_connection()
    recent = conn.execute(
        "SELECT service, event, detail, created_at FROM activity_log ORDER BY id DESC LIMIT 8"
    ).fetchall()
    conn.close()
    if recent:
        print('  Recent activity:')
        for r in recent:
            ts  = str(r[3] or '')[11:16]
            det = (str(r[2] or ''))[:55]
            print(f'    {ts}  {r[0]:<12} {r[1]:<20} {det}')
    print()


def cmd_queue(parts):
    """Show last N queue entries. Usage: queue [N]"""
    n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, from_addr, subject, status, priority, created_at FROM queue "
        "ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    if not rows:
        print('  No queue entries.')
        return
    print(f'\n  Last {n} queue entries:')
    print(f'  {"ID":<6} {"Status":<12} {"Pri":<4} {"From":<28} {"Subject":<35} Time')
    print('  ' + '─' * 100)
    for r in rows:
        ts = str(r[5] or '')[5:16]
        subj = (str(r[2] or ''))[:34]
        frm  = (str(r[1] or ''))[:27]
        print(f'  {r[0]:<6} {r[3]:<12} {r[4]:<4} {frm:<28} {subj:<35} {ts}')
    print()


def cmd_tickets(parts):
    """Show last N tickets. Usage: tickets [N]"""
    n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
    conn = get_connection()
    rows = conn.execute(
        "SELECT ticket_number, status, duck_result, question, created_at FROM tickets "
        "ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    if not rows:
        print('  No tickets.')
        return
    print(f'\n  Last {n} tickets:')
    print(f'  {"Ticket":<12} {"Status":<10} {"Duck":<8} Question')
    print('  ' + '─' * 80)
    for r in rows:
        duck = (str(r[2] or '—'))[:6]
        q    = (str(r[3] or ''))[:55]
        print(f'  {str(r[0]):<12} {str(r[1]):<10} {duck:<8} {q}')
    print()


def cmd_log(parts):
    """Show last N activity log entries. Usage: log [N]"""
    n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 20
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, service, event, detail, created_at FROM activity_log "
        "ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    if not rows:
        print('  No activity entries.')
        return
    print(f'\n  Last {n} activity entries:')
    for r in rows:
        ts  = str(r[4] or '')[5:16]
        det = (str(r[3] or ''))[:60]
        print(f'  {ts}  {r[1]:<14} {r[2]:<22} {det}')
    print()


def cmd_memory(parts):
    """Search memory pools. Usage: memory search <query> [agent]"""
    if len(parts) < 3 or parts[1] != 'search':
        print('  Usage: memory search <query> [agent]')
        print('  Agents: gemma llama qwen eight nine')
        return
    query = ' '.join(parts[2:])
    agent = ''
    # If last token is a known agent name, use as filter
    if parts[-1].lower() in AGENT_TABLES:
        agent = parts[-1].lower()
        query = ' '.join(parts[2:-1])
    if not query:
        print('  No query provided.')
        return

    like = f'%{query}%'
    conn = get_connection()
    if agent and agent in AGENT_TABLES:
        tbl = AGENT_TABLES[agent]
        arch = "AND archived=0" if agent != 'gemma' else ""
        rows = conn.execute(
            f"SELECT '{tbl}' source, agent, subject, content, importance, created_at FROM {tbl} "
            f"WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?) AND importance >= 3 {arch} "
            f"ORDER BY importance DESC, created_at DESC LIMIT 15",
            (like, like, like)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT source_table, agent, subject, content, importance, created_at FROM (
               SELECT 'memory'       source_table, agent, subject, content, tags, importance, created_at FROM memory       WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?) AND importance>=3 AND archived=0
               UNION ALL
               SELECT 'memory_llama' source_table, agent, subject, content, tags, importance, created_at FROM memory_llama WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?) AND importance>=3 AND archived=0
               UNION ALL
               SELECT 'memory_qwen'  source_table, agent, subject, content, tags, importance, created_at FROM memory_qwen  WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?) AND importance>=3 AND archived=0
               UNION ALL
               SELECT 'memory_gemma' source_table, agent, subject, content, tags, importance, created_at FROM memory_gemma WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?) AND importance>=3
               UNION ALL
               SELECT 'memory_eight' source_table, agent, subject, content, tags, importance, created_at FROM memory_eight WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?) AND importance>=3 AND archived=0
               UNION ALL
               SELECT 'memory_nine'  source_table, agent, subject, content, tags, importance, created_at FROM memory_nine  WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?) AND importance>=3 AND archived=0
            ) ORDER BY importance DESC, created_at DESC LIMIT 15""",
            (like,like,like, like,like,like, like,like,like, like,like,like, like,like,like, like,like,like)
        ).fetchall()
    conn.close()

    if not rows:
        print(f'  No memories matching "{query}".')
        return
    print(f'\n  Memory search: "{query}"  ({len(rows)} results)')
    print('  ' + '─' * 70)
    for r in rows:
        pool = str(r[0]).replace('memory_', '').replace('memory', 'shared')
        subj = (str(r[2] or ''))[:50]
        body = (str(r[3] or ''))[:80].replace('\n', ' ')
        print(f'  [{pool:<6} imp:{r[4]}]  {subj}')
        print(f'    {body}')
    print()


def cmd_run(parts):
    """Execute a skill. Usage: run <skill> [args]"""
    if len(parts) < 2:
        from fridays.skills import REGISTRY
        print('  Available skills: ' + ', '.join(sorted(REGISTRY.keys())))
        return
    skill = parts[1].lower()
    args  = ' '.join(parts[2:])
    print(f'  Running skill: {skill}  args: {args!r}')
    slog(f'  run {skill} {args}')
    watermark = _activity_watermark()
    try:
        from fridays.skills import call as skill_call
        success, output = skill_call(skill, args=args, agent='ghost')
        marker = '✓' if success else '✗'
        print(f'  {marker}  {_wrap(output)}')
        slog(f'  {marker} {output[:200]}')
    except Exception as e:
        print(f'  ✗  Error: {e}')
        slog(f'  ✗ Error: {e}')


def cmd_proposals(parts):
    """List pending proposals."""
    try:
        props = list_proposals()
    except Exception as e:
        print(f'  ✗  Could not read proposals: {e}')
        return
    if not props:
        print('  No pending proposals.')
        return
    print(f'\n  {len(props)} pending proposal(s):')
    print('  ' + '─' * 60)
    for i, p in enumerate(props, 1):
        print(f'  {i}.  {p["filename"]}  [{p.get("agent","?")}]')
        preview = (p.get('preview') or '')[:100].strip()
        if preview:
            print(f'       {preview}')
    print()
    print("  Use 'approve <filename>' or 'reject <filename>'")
    print()


def cmd_approve(parts):
    """Approve a proposal. Usage: approve <filename>"""
    if len(parts) < 2:
        print('  Usage: approve <filename>')
        return
    filename = parts[1]
    content  = read_proposal(filename)
    if content is None:
        print(f'  ✗  Proposal not found: {filename}')
        return

    # Show preview
    lines = content.splitlines()
    preview = '\n  '.join(lines[:8])
    print(f'\n  Proposal: {filename}')
    print('  ' + '─' * 60)
    print(f'  {preview}')
    if len(lines) > 8:
        print(f'  ... ({len(lines) - 8} more lines)')
    print()

    confirm = input('  Approve and add to KB? [y/N]: ').strip().lower()
    if confirm != 'y':
        print('  Cancelled.')
        return

    # Extract agent from filename
    agent = filename.split('_')[0].lower() if '_' in filename else ''

    conn = get_connection()
    doc_name = f'Proposal: {filename.replace(".md", "")}'
    existing = conn.execute("SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
            (content, agent or 'all', existing[0])
        )
    else:
        conn.execute(
            "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
            (doc_name, content, agent or 'all')
        )

    # Write approval memory (per-pool column rules)
    note = f'My proposal "{filename}" was approved by Ghost and added to the KB.'
    if agent in ('gemma', 'eight'):
        try:
            conn.execute(
                f"INSERT INTO memory_{agent} (content, importance, source) VALUES (?,?,?)",
                (note, 7, 'proposal_approved')
            )
        except Exception:
            pass
    elif agent in ('llama', 'qwen'):
        try:
            conn.execute(
                f"INSERT INTO memory_{agent} (content, importance) VALUES (?,?)",
                (note, 7)
            )
        except Exception:
            pass
    elif agent == 'nine':
        try:
            conn.execute(
                "INSERT INTO memory_nine (content, importance, source) VALUES (?,?,?)",
                (note, 7, 'proposal_approved')
            )
        except Exception:
            pass

    conn.commit()
    conn.close()
    delete_proposal(filename)
    log_activity('seven_fridays', 'proposal_approved', filename)
    print(f'  ✓  Approved: {filename} → KB')
    slog(f'  approve {filename} → ✓')


def cmd_reject(parts):
    """Reject a proposal. Usage: reject <filename> [feedback]"""
    if len(parts) < 2:
        print('  Usage: reject <filename> [feedback message]')
        return
    filename = parts[1]
    feedback = ' '.join(parts[2:]) if len(parts) > 2 else ''

    content = read_proposal(filename)
    if content is None:
        print(f'  ✗  Proposal not found: {filename}')
        return

    agent = filename.split('_')[0].lower() if '_' in filename else ''

    if feedback and agent:
        try:
            from sandpits import write_file as sandpit_write
            reject_note = f'# Proposal Rejected\n\n**File:** {filename}\n**Feedback:** {feedback}\n**Date:** {date.today().isoformat()}\n'
            sandpit_write(agent, f'rejected_{filename}', reject_note)
            print(f'  Feedback written to {agent}/rejected_{filename}')
        except Exception as e:
            print(f'  Warning: could not write feedback: {e}')

    delete_proposal(filename)
    log_activity('seven_fridays', 'proposal_rejected', filename)
    print(f'  ✓  Rejected: {filename}')
    slog(f'  reject {filename} feedback={feedback!r}')


def cmd_housekeeping(parts):
    """Run Librarian housekeeping cycle."""
    print('  Running housekeeping...')
    slog('  housekeeping start')
    watermark = _activity_watermark()
    try:
        from fridays.skills import call as skill_call
        success, output = skill_call('housekeeping', args='', agent='ghost')
        marker = '✓' if success else '✗'
        print(f'  {marker}  {output}')
        slog(f'  housekeeping {marker}: {output[:150]}')
    except Exception as e:
        print(f'  ✗  Error: {e}')
        slog(f'  housekeeping ✗: {e}')


def cmd_seed(parts):
    """Seed KB from PROJECT.md. Usage: seed kb"""
    if len(parts) < 2 or parts[1] != 'kb':
        print('  Usage: seed kb')
        return

    project_path = '/home/seven/swarm/PROJECT.md'
    if not os.path.isfile(project_path):
        print('  ✗  PROJECT.md not found.')
        return

    with open(project_path, encoding='utf-8') as fh:
        text = fh.read()

    sections = re.split(r'\n(?=## )', text)
    print(f'  Found {len(sections)} sections in PROJECT.md.')
    confirm = input('  Seed all sections into KB (overwrites existing)? [y/N]: ').strip().lower()
    if confirm != 'y':
        print('  Cancelled.')
        return

    conn    = get_connection()
    seeded  = 0
    skipped = 0
    for section in sections:
        lines   = section.strip().splitlines()
        if not lines:
            continue
        heading = lines[0].lstrip('#').strip()
        content = section.strip()
        if len(content) < 40:
            skipped += 1
            continue
        tags     = 'eight' if any(k in heading for k in ('SAP', 'Eight')) else 'all'
        doc_name = f'[Swarm] {heading}'
        existing = conn.execute("SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                (content[:4000], tags, existing[0])
            )
        else:
            conn.execute(
                "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                (doc_name, content[:4000], tags)
            )
        print(f'  ✓  {doc_name[:60]}  ({len(content)} chars)')
        seeded += 1

    conn.commit()
    conn.close()
    log_activity('seven_fridays', 'kb_seeded', f'{seeded} sections')
    print(f'\n  Done. {seeded} sections seeded, {skipped} skipped.')
    slog(f'  seed kb → {seeded} sections')


def cmd_debate(parts):
    """Open and run an autonomous agent debate. Usage: debate <topic>"""
    if len(parts) < 2:
        print('  Usage: debate <topic text>')
        return
    topic = ' '.join(parts[1:])
    print(f'\n  Opening debate: {topic}')
    print('  LLaMA + Qwen will argue. Gemma arbitrates.')
    print('  CONSENSUS → auto-proposal   ESCALATE → Ghost review\n')
    try:
        from debate import run_and_resolve
        result = run_and_resolve(topic, initiator='ghost')
        status = result.get('status', 'unknown')
        if status == 'consensus':
            print(f'\n  ✓  CONSENSUS after {result["rounds"]} rounds')
            print(f'  Consensus: {result["consensus"]}')
            print(f'  Proposal written: {result.get("proposal_file","?")}')
        elif status == 'escalated':
            print(f'\n  ⚠  ESCALATED — needs Ghost review')
            print(f'  Issue: {result["consensus"]}')
        else:
            print(f'\n  Result: {result}')
        slog(f'  debate: {topic[:60]} → {status}')
    except Exception as e:
        print(f'  ✗  {e}')


def cmd_debates(parts):
    """List recent debates."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, topic, status, consensus, rounds, created_at FROM debates ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    if not rows:
        print('  No debates yet.')
        return
    print()
    for r in rows:
        icon = '✓' if r[1] == 'consensus' else '⚠' if r[1] == 'escalated' else '…'
        print(f'  #{r[0]} [{icon} {r[2]}] {r[3][:50]}')
        print(f'       {r[1][:60]} ({r[4]} rounds) · {str(r[5] or "")[:16]}')
    print()


def cmd_restart(parts):
    """Restart a swarm service. Usage: restart <service>"""
    if len(parts) < 2:
        print('  Usage: restart <service>')
        print('  Services: ' + ', '.join(VALID_SERVICES.keys()))
        return
    short = parts[1].lower()
    svc   = VALID_SERVICES.get(short)
    if not svc:
        print(f'  Unknown service: {short!r}')
        print('  Valid: ' + ', '.join(VALID_SERVICES.keys()))
        return

    # Check if sudo works without password for this service
    test = subprocess.run(
        ['sudo', '-n', 'systemctl', 'is-active', svc],
        capture_output=True, text=True
    )
    if test.returncode not in (0, 3):  # 3 = inactive, but sudo worked
        print('  Warning: sudo may require a password — command may hang.')

    confirm = input(f'  Restart {svc}? [y/N]: ').strip().lower()
    if confirm != 'y':
        print('  Cancelled.')
        return

    result = subprocess.run(
        ['sudo', 'systemctl', 'restart', svc],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        time.sleep(1)
        active = _svc_status(svc)
        dot    = _dot(active)
        print(f'  {dot}  {svc} restarted — now {("active" if active else "inactive")}')
        log_activity('seven_fridays', 'service_restarted', svc)
        slog(f'  restart {svc} → active={active}')
    else:
        print(f'  ✗  {result.stderr.strip() or "restart failed"}')


def cmd_ask(parts):
    """Ask an agent a question. Usage: ask <agent> <question>"""
    if len(parts) < 3:
        print('  Usage: ask <agent> <question>')
        print('  Agents: gemma llama qwen eight nine')
        return
    agent_name = parts[1].lower()
    question   = ' '.join(parts[2:])

    if agent_name == 'nine':
        _ask_nine(question)
    elif agent_name in ('gemma', 'llama', 'qwen', 'eight'):
        _ask_ollama(agent_name, question)
    else:
        print(f'  Unknown agent: {agent_name!r}. Valid: gemma llama qwen eight nine')


def _ask_nine(question):
    """Call Nine via Claude API with swarm context + session memory."""
    from claude_api import _load_api_key, CLAUDE_MODEL

    if not _ANTHROPIC_OK:
        print('  ✗  anthropic SDK not installed. Run: pip install anthropic')
        return
    api_key = _load_api_key()
    if not api_key:
        print('  ✗  ANTHROPIC_API_KEY not set. Add to /etc/environment and restart.')
        return

    # Swarm state context
    ctx = build_swarm_context()

    # Nine's recent session memory for continuity
    conn = get_connection()
    nine_mem = conn.execute(
        "SELECT subject, content, created_at FROM memory_nine "
        "WHERE archived=0 ORDER BY created_at DESC LIMIT 8"
    ).fetchall()
    conn.close()

    mem_block = ''
    if nine_mem:
        mem_block = '\n=== Nine session memory ===\n'
        for m in nine_mem:
            mem_block += f'[{str(m[2] or "")[:16]}] {m[0]}: {(str(m[1] or ""))[:180]}\n'

    full_prompt = ctx + mem_block + f'\n=== Ghost asks ===\n{question}'

    print('  Calling Nine (Claude API)...')
    slog(f'  ask nine: {question[:100]}')

    try:
        client   = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=NINE_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': full_prompt}]
        )
        answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        print()
        print(_wrap(answer, width=80, indent='  '))
        print()
        print(f'  [{tokens} tokens]')

        # Persist to memory_nine
        conn = get_connection()
        conn.execute(
            "INSERT INTO memory_nine (subject, content, tags, importance, source) VALUES (?,?,?,?,?)",
            (question[:100], answer[:600], 'session,repl', 8, 'repl_session')
        )
        conn.commit()
        conn.close()

        log_activity('seven_fridays', 'nine_consulted', f'tokens={tokens} | {question[:80]}')
        slog(f'  nine response: {answer[:150]}')

    except Exception as e:
        print(f'  ✗  Nine error: {e}')
        slog(f'  nine error: {e}')


def _ask_ollama(agent_name, question):
    """Ask a local Ollama agent directly via orchestrator."""
    print(f'  Calling {agent_name.capitalize()} (Ollama)...')
    slog(f'  ask {agent_name}: {question[:100]}')
    try:
        from orchestrator import ask_agent, build_shared_context
        ctx    = build_shared_context(question)
        prompt = ctx + f'\n\n=== Ghost asks (direct Seven+Fridays) ===\n{question}'
        answer = ask_agent(agent_name.capitalize(), prompt)
        print()
        print(_wrap(str(answer), width=80, indent='  '))
        print()
        log_activity('seven_fridays', f'{agent_name}_consulted', question[:80])
        slog(f'  {agent_name} response: {str(answer)[:150]}')
    except Exception as e:
        print(f'  ✗  Error calling {agent_name}: {e}')
        slog(f'  {agent_name} error: {e}')


def cmd_help(parts):
    """Show available commands."""
    print("""
  Seven+Fridays — Command Reference
  ──────────────────────────────────────────────────────────────
  status              Full swarm state: queue, services, system, activity
  queue [N]           Last N queue entries  (default 10)
  tickets [N]         Last N tickets  (default 10)
  log [N]             Last N activity log entries  (default 20)

  memory search <q>   Search all memory pools  (append agent name to filter)
                      e.g.  memory search retro accounting eight

  run <skill> [args]  Execute a skill directly with real completion output
                      e.g.  run shell df -h
                            run search latest Ollama release notes
                            run memory_search SAP wage types

  ask <agent> <q>     Ask an agent a question directly (no email pipeline)
                      Agents: gemma  llama  qwen  eight  nine
                      Nine calls Claude API and reads/writes session memory.

  proposals           List pending agent proposals
  approve <file>      Approve a proposal → KB + agent memory  (confirms first)
  reject <file> [msg] Reject a proposal  (optional feedback to agent sandpit)

  debate <topic>      Run autonomous debate: LLaMA+Qwen argue, Gemma arbitrates
                      CONSENSUS → auto-proposal  |  ESCALATE → Ghost review
  debates             List recent debates and their outcomes

  housekeeping        Run Librarian cycle: archive, dedup, play time
  seed kb             Parse PROJECT.md sections → KB  (confirms first)

  restart <service>   Restart a swarm service  (confirms first)
                      Services: listener  terminal  monitor  telegram
                                discord   sniffer   housekeeping

  help                This screen
  exit / quit         Exit Seven+Fridays
  ──────────────────────────────────────────────────────────────
  Session log:  sandpits/nine/session_{today}.log
  Nine memory:  memory_nine table (persists across sessions)
""".format(today=date.today().isoformat()))


# ── Command dispatch ───────────────────────────────────────────────────────────

DISPATCH = {
    'status':       cmd_status,
    'queue':        cmd_queue,
    'tickets':      cmd_tickets,
    'log':          cmd_log,
    'memory':       cmd_memory,
    'run':          cmd_run,
    'ask':          cmd_ask,
    'proposals':    cmd_proposals,
    'approve':      cmd_approve,
    'reject':       cmd_reject,
    'housekeeping': cmd_housekeeping,
    'seed':         cmd_seed,
    'restart':      cmd_restart,
    'debate':       cmd_debate,
    'debates':      cmd_debates,
    'help':         cmd_help,
}


# ── REPL ──────────────────────────────────────────────────────────────────────

def repl():
    setup_readline()
    print_banner()
    slog(f'=== Seven+Fridays session started ===')

    while True:
        try:
            raw = input(PROMPT).strip()
        except (KeyboardInterrupt, EOFError):
            print('\n  Session ended.')
            slog('=== session ended ===')
            break

        if not raw:
            continue

        slog(f'> {raw}')
        parts = raw.split()
        cmd   = parts[0].lower()

        if cmd in ('exit', 'quit', 'q'):
            print('  Session ended.')
            slog('=== session ended ===')
            break

        handler = DISPATCH.get(cmd)
        if handler is None:
            # Friendly suggestion
            close = [k for k in DISPATCH if k.startswith(cmd[:2])]
            hint  = f'  Did you mean: {", ".join(close[:3])}?' if close else ''
            print(f'  Unknown command: {cmd!r}.  Type \'help\' for commands.{hint}')
            continue

        try:
            handler(parts)
        except KeyboardInterrupt:
            print('\n  Interrupted.')
        except Exception as e:
            msg = f'  Error in {cmd}: {e}'
            print(msg)
            slog(msg)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    repl()

