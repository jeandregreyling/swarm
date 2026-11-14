"""Owner 13 Nov: one master protocol for every agent in HB (DOES replaces DEOS), built from a versioned pack, not hard-coded.

for_role(role)        -> the prompt text for that agent (shared protocol + its role section), or a compact form for small models.
reasoning_blocks(txt) -> the four thinking blocks found in a reply ([KC & Git State] ... [Final Verdict & Action]).
record(conn, task, agent, text, message_id) -> saves the blocks as a 'reasoning' task record (the thinking is kept, not only the
                         one-line verdict) and turns a [Prompt change proposal] into a plan step for the owner.
Claude Code is exempt for now (owner 13 Nov: it is making this foundational change).
"""
import json
import re
import time
from functools import lru_cache
from pathlib import Path

PACK = Path(__file__).resolve().parent / 'capability_packs' / 'hb.master.protocol.v1.json'
PLAN = 'P-2AB8250A87'
BLOCKS = ('KC & Git State', 'Pragmatic Analysis', 'Evolution & Alternative', 'Final Verdict & Action')
ROLE_OF = {'apex': 'apex', 'fred': 'fred', 'fred-cpu:24b': 'fred', 'nanny': 'nanny', 'codex-instructor': 'codex-instructor',
           'codex': 'codex-instructor', 'gemini-advisor': 'gemini-advisor', 'gemini': 'gemini-advisor'}
EXEMPT = {'claude-code'}


@lru_cache(maxsize=4)
def _pack(mtime):
    data = json.loads(PACK.read_text())
    if data.get('id') != 'hb.master.protocol' or 'shared' not in data or 'roles' not in data:
        raise ValueError('Invalid HB master protocol pack')
    return data


def pack():
    return _pack(PACK.stat().st_mtime)


def version():
    return pack()['version']


def for_role(agent, *, compact=False):
    """Prompt text for an agent; '' for exempt agents. Re-read automatically when the pack file changes."""
    if agent in EXEMPT:
        return ''
    data = pack()
    role = data['roles'].get(ROLE_OF.get(agent, agent)) or data['roles']['default']
    if compact:
        return f"{data['compact']} {role} (HB master protocol v{data['version']})"
    return f"HB master protocol v{data['version']}:\n" + '\n'.join(data['shared']) + '\n' + role


def reasoning_blocks(text):
    """The four thinking blocks in a reply, in order; {} when the reply has none."""
    text = str(text or '')
    marks = [(m.start(), m.end(), name) for name in BLOCKS for m in [re.search(r'\[' + re.escape(name) + r'\]\s*:?', text)] if m]
    marks.sort()
    out = {}
    for i, (start, end, name) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[end:stop]
        cut = body.find('[Prompt change proposal]')
        out[name] = (body[:cut] if cut >= 0 else body).strip()[:2000]
    return out


def proposal(text):
    m = re.search(r'\[Prompt change proposal\]\s*:?\s*(.+)', str(text or ''), re.S)
    return m.group(1).strip()[:3000] if m else ''


def record(conn, task, agent, text, message_id=None):
    """Save the thinking of a reply as a task record; a prompt change proposal becomes a plan step for the owner.
    Returns {'blocks': n, 'proposal_step': step_id or None}."""
    from core import hb_tasks
    blocks = reasoning_blocks(text)
    if blocks and task:
        hb_tasks.event(conn, task, agent, 'reasoning', {'protocol_version': version(), 'blocks': blocks},
                       **({'message_id': message_id} if message_id else {}))
    suggestion = proposal(text)
    step_id = None
    if suggestion:
        step_id = _proposal_step(conn, agent, suggestion, task)
    return {'blocks': len(blocks), 'proposal_step': step_id}


def _proposal_step(conn, agent, suggestion, task):
    import hashlib
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'project_steps' not in tables:
        return None
    digest = hashlib.sha256(suggestion.encode()).hexdigest()[:10].upper()
    step_id = 'S-' + digest
    if conn.execute('SELECT 1 FROM project_steps WHERE step_id=?', (step_id,)).fetchone():
        return step_id
    title = f'Prompt change proposal from {agent}: ' + ' '.join(suggestion.split())[:90]
    description = (f'A model proposed a change to its instructions (HB master protocol v{version()}). JD decides; nothing changes until approved.\n'
                   f'From: {agent}' + (f", task {task['task_id']}" if task else '') + f'\nProposal:\n{suggestion}')
    now = time.time()
    columns = {r[1] for r in conn.execute('PRAGMA table_info(project_steps)')}
    values = {'step_id': step_id, 'project_id': PLAN, 'title': title, 'description': description, 'status': 'todo',
              'owner': 'jd', 'order_idx': 16.994, 'created_at': now, 'updated_at': now,
              'residual_risk': 'Waits for JD: approve, change or reject this prompt change'}
    values = {k: v for k, v in values.items() if k in columns}
    conn.execute(f"INSERT INTO project_steps({', '.join(values)}) VALUES({', '.join('?' * len(values))})", tuple(values.values()))
    return step_id
