"""Swap the single local worker: park the current one (Fred by default) and plug in another agent.

    .venv/bin/python3 scripts/swap_worker.py <new_name> <ollama_model> [--label "Display Name"]
    .venv/bin/python3 scripts/swap_worker.py --back          # return to Fred

The new agent gets its own memory table, sandpit, skill grants (copied from the worker it replaces) and
the taught memories. Nothing is deleted: the old worker is only disabled. Restart PROD and the scheduler
afterwards so they read runtime/worker_agent.txt and runtime/worker_model.txt.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.db._connection import get_connection  # noqa: E402
from utils.worker import DEFAULT_WORKER, WORKER_AGENT  # noqa: E402

NAME_RE = re.compile(r'[a-z][a-z0-9_]{1,23}')
WRAPPER = '''"""agents/{name}/{name}_agent.py: {label}, the local worker. Same engine as Fred, own name, memory and sandpit."""
from agents.fred.fred_agent import chat as _worker_chat

AGENT_NAME = '{name}'


def chat(message, conversation_history=None, stage_cb=None):
    return _worker_chat(message, conversation_history, stage_cb, agent_name=AGENT_NAME)
'''


def _models():
    out = subprocess.run(['ollama', 'list'], capture_output=True, text=True).stdout
    return {line.split()[0] for line in out.splitlines()[1:] if line.strip()}


def _write(name, text):
    os.makedirs(os.path.join(ROOT, 'runtime'), exist_ok=True)
    with open(os.path.join(ROOT, 'runtime', name), 'w', encoding='utf-8') as handle:
        handle.write(text)


def plug_in(name, model, label):
    if not NAME_RE.fullmatch(name):
        sys.exit(f'bad name {name!r}: one lowercase word, 2-24 letters/digits/_')
    if model not in _models():
        sys.exit(f'model {model!r} is not installed (ollama list). Pull it first.')
    conn = get_connection()
    try:
        old = WORKER_AGENT
        src = conn.execute('SELECT * FROM agents WHERE name=?', (old,)).fetchone()
        if src is None:
            sys.exit(f'current worker {old!r} has no agents row')
        cols = [d[0] for d in conn.execute('SELECT * FROM agents LIMIT 0').description]
        row = dict(zip(cols, tuple(src)))
        exists = conn.execute('SELECT enabled FROM agents WHERE name=?', (name,)).fetchone()
        if exists is not None and exists[0] and name != old:
            sys.exit(f'{name!r} is an active agent already; choose a new name')

        row.update(name=name, model=model, label=label, display_label=label, memory_table=f'memory_{name}',
                   enabled=1, role='Local worker: system administrator, chat bot and coder',
                   roles=row.get('roles'), aliases='[]',
                   system_prompt=str(row.get('system_prompt') or '').replace('Fred', label).replace('FRED', label.upper()))
        number = conn.execute('SELECT COALESCE(MAX(number), 0) + 1 FROM agents').fetchone()[0]
        row['number'] = number
        if exists is None:
            use = [c for c in cols if c != 'id']
            conn.execute(f'INSERT INTO agents ({",".join(use)}) VALUES ({",".join("?" for _ in use)})',
                         [row[c] for c in use])
        else:
            conn.execute('UPDATE agents SET model=?, label=?, display_label=?, memory_table=?, enabled=1 WHERE name=?',
                         (model, label, label, f'memory_{name}', name))
        if name != old:
            conn.execute('UPDATE agents SET enabled=0 WHERE name=?', (old,))

        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='memory_fred'").fetchone()[0]
        conn.execute(ddl.replace('memory_fred', f'memory_{name}').replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1))
        mem_cols = [d[0] for d in conn.execute(f'SELECT * FROM memory_{name} LIMIT 0').description if d[0] != 'id']
        have = conn.execute(f'SELECT COUNT(*) FROM memory_{name}').fetchone()[0]
        if not have:
            conn.execute(
                f'INSERT INTO memory_{name} ({",".join(mem_cols)}) SELECT {",".join(mem_cols)} FROM memory_fred '
                "WHERE source='taught'")
        conn.execute(f'UPDATE memory_{name} SET agent=?', (name,))
        grants = conn.execute('SELECT skill_name, allowed FROM user_skill_permissions WHERE username=?', (old,)).fetchall()
        for skill, allowed in grants:
            conn.execute(
                'INSERT INTO user_skill_permissions (username, skill_name, allowed, created_by) VALUES (?,?,?,?) '
                'ON CONFLICT(username, skill_name) DO UPDATE SET allowed=excluded.allowed',
                (name, skill, allowed, 'ghost'))
        conn.execute("UPDATE scheduled_tasks SET action_data=REPLACE(action_data,'work_owner=fred','work_owner=worker') "
                     "WHERE action_data LIKE '%work_owner=fred%'")
        conn.commit()
        seeded = conn.execute(f'SELECT COUNT(*) FROM memory_{name}').fetchone()[0]
    finally:
        conn.close()

    pkg = os.path.join(ROOT, 'agents', name)
    os.makedirs(pkg, exist_ok=True)
    open(os.path.join(pkg, '__init__.py'), 'a').close()
    wrapper = os.path.join(pkg, f'{name}_agent.py')
    if not os.path.exists(wrapper):
        with open(wrapper, 'w', encoding='utf-8') as handle:
            handle.write(WRAPPER.format(name=name, label=label))
    os.makedirs(os.path.join(ROOT, 'sandpits', name), exist_ok=True)
    _write('worker_agent.txt', name + '\n')
    _write('worker_model.txt', model + '\n')
    print(f'plugged in {name} on {model}; parked {old}; {len(grants)} skill grants copied; '
          f'{seeded} memories seeded; sandpit sandpits/{name}/')
    print('Restart PROD (5050) and the scheduler so they pick it up.')


def go_back():
    conn = get_connection()
    try:
        conn.execute('UPDATE agents SET enabled=0 WHERE name=?', (WORKER_AGENT,))
        conn.execute('UPDATE agents SET enabled=1 WHERE name=?', (DEFAULT_WORKER,))
        conn.commit()
    finally:
        conn.close()
    for name in ('worker_agent.txt', 'worker_model.txt'):
        try:
            os.remove(os.path.join(ROOT, 'runtime', name))
        except OSError:
            pass
    print(f'back to {DEFAULT_WORKER}; {WORKER_AGENT} is parked, not deleted. Restart PROD and the scheduler.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('name', nargs='?')
    parser.add_argument('model', nargs='?')
    parser.add_argument('--label')
    parser.add_argument('--back', action='store_true')
    args = parser.parse_args()
    if args.back:
        go_back()
    elif args.name and args.model:
        plug_in(args.name.lower(), args.model, args.label or args.name.replace('_', ' ').title())
    else:
        parser.error('give <name> <model>, or --back')
