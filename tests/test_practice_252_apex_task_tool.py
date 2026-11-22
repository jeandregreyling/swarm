"""Practice 252: APEX's hb_tasks tool lists, resumes, pauses and cancels HB tasks; JD's steps are off limits."""
import sqlite3
from contextlib import closing

import pytest

from core import hb_agent_tools, hb_commands, apex_tools, hb_task_manager, hb_tasks


@pytest.fixture
def db(monkeypatch):
    c = sqlite3.connect(':memory:', check_same_thread=False)
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, step_id TEXT, objective TEXT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, owner TEXT)')
    c.executemany('INSERT INTO hb_tasks VALUES (?,?,?)', [('T-0000000000AA', 'S-1', ''), ('T-0000000000BB', 'S-2', ''), ('T-0000000000CC', None, 'HB conversation: remarks and go-aheads from JD that are not new work.')])
    c.executemany('INSERT INTO project_steps VALUES (?,?)', [('S-1', 'apex'), ('S-2', 'jd')])
    class NoClose:
        def __getattr__(self, n): return getattr(c, n)
        def close(self): pass
    import utils.db._connection as dbc
    monkeypatch.setattr(dbc, 'get_connection', lambda: NoClose())
    calls = []
    monkeypatch.setattr(hb_commands, '_open_tasks', lambda *_: [
        {'task_id': 'T-0000000000AA', 'title': 'Real work', 'state': 'active', 'mode': 'on', 'status': 'queued'},
        {'task_id': 'T-0000000000CC', 'title': 'Chat with JD', 'state': 'active', 'mode': 'on', 'status': 'running'}])
    monkeypatch.setattr(hb_tasks, 'get', lambda _c, tid: {'step_id': None, 'objective': 'HB conversation: remarks and go-aheads from JD that are not new work.'} if tid.endswith('CC') else {'step_id': 'S-1', 'objective': 'Real work'})
    monkeypatch.setattr(hb_commands, 'handle', lambda conn, cid, text, actor: calls.append(text) or f'did {text}')
    monkeypatch.setattr(hb_commands, 'cancel_task', lambda conn, tid, actor, after=None: calls.append(('cancel', tid, actor)) or f'{tid} cancelled')
    return calls


def test_list_continue_pause(db):
    listing = hb_agent_tools.hb_tasks_tool({'action': 'list'})['tasks']
    assert 'Eligible APEX work:' in listing and 'Real work' in listing
    assert 'Chat with JD' not in listing and 'T-0000000000CC' not in listing
    hb_agent_tools.hb_tasks_tool({'action': 'continue', 'task_id': 'T-0000000000AA'})
    hb_agent_tools.hb_tasks_tool({'action': 'pause', 'task_id': 't-0000000000aa'})
    assert db[-2:] == ['/continue T-0000000000AA', '/pause T-0000000000AA']


def test_cancel_needs_a_reason_and_records_it(db):
    with pytest.raises(ValueError):
        hb_agent_tools.hb_tasks_tool({'action': 'cancel', 'task_id': 'T-0000000000AA'})
    hb_agent_tools.hb_tasks_tool({'action': 'cancel', 'task_id': 'T-0000000000AA', 'reason': 'duplicate of T-0000000000CC'})
    assert db[-1] == ('cancel', 'T-0000000000AA', 'APEX: duplicate of T-0000000000CC')


def test_jds_steps_and_invented_ids_are_refused(db):
    with pytest.raises(PermissionError):
        hb_agent_tools.hb_tasks_tool({'action': 'cancel', 'task_id': 'T-0000000000BB', 'reason': 'not needed anymore'})
    with pytest.raises(ValueError):
        hb_agent_tools.hb_tasks_tool({'action': 'continue', 'task_id': 'T-123'})


def test_apex_has_it_everywhere_he_needs_it():
    assert 'hb_tasks' in apex_tools.TOOL_SCHEMAS and 'hb_tasks' in hb_task_manager.EXECUTION_TOOLS
    assert 'hb_tasks' in hb_agent_tools.WRITE_TOOLS


def test_chat_record_cannot_be_continued_as_work(db):
    with pytest.raises(ValueError, match='not an actionable work task'):
        hb_agent_tools.hb_tasks_tool({'action': 'continue', 'task_id': 'T-0000000000CC'})
    assert '/continue T-0000000000CC' not in db
