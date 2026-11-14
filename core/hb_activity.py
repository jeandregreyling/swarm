"""Live activity in main chat (owner 14 Nov 2026): what APEX, Fred and the other agents are actually doing, in words a person reads.

  chains(conn)  one entry per task that has work running: its title and each agent working on it (a linked chain: APEX -> Fred ...),
                each with role, model, where it runs (GPU / RAM), and its last actions written as plain statuses by HB.
  requests      request id -> task id for the chat's recent requests, so the page can hand an old bubble over to the newest one
                of the same task instead of freezing it as "stalled".
"""
import json
import time
from pathlib import PurePosixPath

ROLE = {'apex': 'APEX', 'codex-instructor': 'Codex', 'gemini-advisor': 'Gemini', 'hummingbird': 'HB'}


def _where(model):
    if not model:
        return ''
    try:
        from core.seven_llm import registry
        entry = registry.get(model)
        if entry and entry.options.get('ngl') == 0:
            return 'RAM / CPU'
    except Exception:
        pass
    return 'RAM / CPU' if 'cpu' in model else 'GPU'


def _role(agent, model):
    if model and 'fred' in model:
        return 'Fred'
    return ROLE.get(agent, agent)


def _file(path):
    return PurePosixPath(str(path or '')).name or str(path or '')


def plain(kind, p):
    """One action as a short status a person reads. Returns None for noise."""
    if kind == 'progress':
        stage = str(p.get('stage') or '')
        if stage.startswith('Local model selected') or stage.endswith(': succeeded') or stage.endswith(': failed'):
            return None
        for old, new in (('Attached agent picked up', 'Started'), ('Agent answer saved', 'Answer written'), ('Request failed', '✘ Turn failed'),
                         ('Loading larger local', 'Loading Fred into memory'), ('Larger local24B review running', 'Fred is thinking'),
                         ('Queued', 'Waiting its turn')):
            if stage.startswith(old):
                return new
        return stage[:100] or None
    tool, a = p.get('tool'), p.get('arguments') or {}
    if kind == 'test_result':
        verdict = str(p.get('verdict') or '')
        return ('✔ Checks pass: ' if p.get('alm_run_status') == 'pass' else '✘ Checks fail: ') + verdict.split(';')[0].replace('PASS: ', '').replace('FAIL: ', '')[:70]
    if kind == 'mutation':
        out = str(p.get('output') or '')
        if 'patch completed:' in out:
            return '✔ Changed ' + _file(out.split('patch completed:')[1].split(';')[0].strip())
        if p.get('tool') == 'does_rename' or 'DOES rename' in out:
            return '✔ Applied the DOES rename in a file'
        if p.get('tool') == 'change_set':
            return '✔ Applied the prepared change'
        return '✔ Changed something (' + str(p.get('tool') or 'tool') + ')'
    if kind == 'tool_failure':
        err = str(p.get('error') or '')
        if err.startswith('ALREADY APPLIED'):
            return '↺ That change was already in - moving on'
        if 'matched 0 locations' in err:
            return f"✘ The change to {_file(a.get('file_path') or a.get('path'))} didn't fit the file"
        return f"✘ {tool} didn't work: {err[:70]}"
    words = {
        'read_file': lambda: f"Reading {_file(a.get('path'))}",
        'grep_repo': lambda: f"Searching the code for “{str(a.get('query', ''))[:40]}”",
        'knowledge_search': lambda: f"Looking up “{str(a.get('query', ''))[:40]}” in the KC",
        'knowledge_read': lambda: 'Reading a KC document',
        'propose_patch': lambda: f"Changing {_file(a.get('file_path'))}",
        'propose_write_file': lambda: f"Writing {_file(a.get('path'))}",
        'run_tests': lambda: 'Running the checks',
        'alm_step_get': lambda: 'Reading the Studio step',
        'task_context': lambda: 'Reading the task notes',
        'task_evidence': lambda: 'Reading earlier results',
        'task_plan': lambda: 'Saving the next step of the plan',
        'does_rename': lambda: f"Applying the DOES rename in {_file(a.get('path'))}" if a.get('action') == 'apply' else f"Rename tool: {a.get('action')}",
        'change_set': lambda: {'show': 'Reading the prepared change', 'apply': 'Applying the prepared change'}.get(a.get('action'), 'Checking the prepared change'),
        'git_status': lambda: 'Checking which files changed',
        'get_diff': lambda: f"Looking at the changes in {_file(a.get('path'))}",
        'memory_search': lambda: 'Checking its own notes',
        'local_review': lambda: 'Asking Fred for advice',
    }
    return words.get(tool, lambda: f'Using {tool}')()


def chains(conn, steps=6):
    out = {}
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_peer_work'").fetchone():
        return []
    for rid, agent, stage in conn.execute("SELECT w.request_id, p.recipient, w.stage FROM hb_peer_work w JOIN peer_messages p ON p.id=w.request_id "
                                          "WHERE w.state='running' ORDER BY w.request_id"):
        model, lines = None, []
        for kind, payload, at in conn.execute("SELECT kind, payload, created_at FROM hb_task_events WHERE request_id=? AND kind IN "
                                              "('progress','tool_result','tool_failure','mutation','test_result') ORDER BY event_id", (rid,)):
            p = json.loads(payload or '{}')
            if kind == 'progress' and str(p.get('stage', '')).startswith('Local model selected: '):
                model = p['stage'].split(': ', 1)[1]
            if kind == 'tool_result' and p.get('tool') == 'run_tests':
                continue                                   # its test_result line says it better
            line = plain(kind, p)
            if line and (not lines or lines[-1]['what'] != line):
                lines.append({'at': time.strftime('%H:%M', time.localtime(at)), 'what': line})
        task = conn.execute("SELECT t.task_id, t.title FROM hb_task_requests r JOIN hb_tasks t ON t.task_id=r.task_id WHERE r.request_id=?",
                            (rid,)).fetchone()
        key = task[0] if task else f'request-{rid}'
        chain = out.setdefault(key, {'task_id': task[0] if task else None, 'task': (task[1] if task else '')[:90], 'members': []})
        chain['members'].append({'request_id': rid, 'role': _role(agent, model), 'model': model or '', 'where': _where(model),
                                 'now': (lines[-1]['what'] if lines else plain('progress', {'stage': stage}) or 'starting'),
                                 'steps': lines[-steps:]})
    from core import hb_background
    for job in hb_background.snapshot():      # owner 14 Nov: the homework team and counsel show like any agent
        out.setdefault(job.get('task_id') or job['kind'], {'task_id': job.get('task_id'), 'task': job['task'], 'members': []})['members'].append(
            {'request_id': None, 'role': job['role'], 'model': job['model'], 'where': 'RAM / CPU' if job['model'] != 'tests' else 'CPU',
             'now': job['steps'][-1]['what'], 'steps': job['steps']})
    return list(out.values())


def requests(conn, conversation_id=2834, limit=80):
    rows = conn.execute("SELECT r.request_id, r.task_id FROM hb_task_requests r JOIN peer_messages p ON p.id=r.request_id "
                        "WHERE p.conversation_id=? ORDER BY r.request_id DESC LIMIT ?", (conversation_id, limit)).fetchall()
    return {str(rid): tid for rid, tid in rows}


def running(conn, limit=8):
    """Older flat shape (kept for callers): one entry per running request."""
    flat = []
    for c in chains(conn, steps=limit):
        for m in c['members']:
            flat.append({'request_id': m['request_id'], 'agent': m['role'], 'model': m['model'], 'where': m['where'], 'stage': m['now'],
                         'task': c['task'], 'steps': m['steps']})
    return flat
