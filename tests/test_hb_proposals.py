"""Owner 14 Nov: advisors (Gemini, Codex, DeepSeek...) research read-only and write Studio proposals with real code; HB checks each proposal
by running its test; a passing one becomes APEX's task with a change set; nothing is changed by the advisor itself. Profiles, not names."""
import json
import sys

import pytest

from core import hb_proposals as hp, hb_change_sets as cs, hb_tasks
from core.hb_agent_profiles import tools_for, profile_for
from test_peer_turns import flow, reply  # noqa: F401
from test_hb_plan_workflow import plan, P  # noqa: F401


def _repo(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'mod.py').write_text('def value():\n    return 1\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_mod.py').write_text('import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n'
                                                    'from pkg.mod import value\n\ndef test_two():\n    assert value() == 2\n')
    return tmp_path


def test_profiles_decide_tools_not_names():
    assert profile_for('gemini-advisor')['name'] == 'advisor' and profile_for('deepseek')['name'] == 'advisor'
    tools = tools_for('gemini-advisor')
    assert 'studio_proposal' in tools and 'read_file' in tools and not {'propose_patch', 'propose_write_file', 'run_tests'} & set(tools)
    assert tools_for('someone-new') == []


def test_a_proposal_is_checked_by_hb_and_becomes_apex_work(plan, tmp_path, monkeypatch):
    conn, _, _ = plan
    root = _repo(tmp_path)
    monkeypatch.setattr(cs, 'ROOT', root)
    from core.knowledge import projects
    monkeypatch.setattr(projects, 'add_step', lambda project, title, description, owner: conn.execute(
        "INSERT INTO project_steps VALUES('S-0000000P01',?,?,?,'todo',?,99,0,0,NULL)", (project, title, description, owner)) and 'S-0000000P01')
    out = hp.create(conn, 'gemini-advisor', {'title': 'Make value two', 'why': 'value must be 2 for the report',
                                             'edits': [{'path': 'pkg/mod.py', 'old': '    return 1', 'new': '    return 2'}],
                                             'tests': ['tests/test_mod.py']})
    assert out['step_id'] == 'S-0000000P01' and (root / 'pkg/mod.py').read_text().endswith('return 1\n')    # nothing changed
    assert hp.pending(root) == ['S-0000000P01']
    result = hp.check(conn, 'S-0000000P01', root=root)
    assert result['verified'] and (root / 'pkg/mod.py').read_text().endswith('return 1\n')                   # proven, put back
    step = conn.execute("SELECT owner, description FROM project_steps WHERE step_id='S-0000000P01'").fetchone()
    assert step[0] == 'apex' and step[1].startswith('HB extra tools: change_set\nPREPARED (proposed by gemini-advisor')
    assert conn.execute("SELECT 1 FROM hb_tasks WHERE step_id='S-0000000P01'").fetchone()                      # in APEX's queue
    assert hp.pending(root) == []
    said = [r[0] for r in conn.execute("SELECT content FROM messages WHERE from_agent='hummingbird' ORDER BY id")]
    assert said[-2].startswith('📜 gemini-advisor proposed a change') and said[-1].startswith("✅ HB checked gemini-advisor's proposal")


def test_a_failing_or_untested_proposal_waits_for_review_and_secrets_are_refused(plan, tmp_path, monkeypatch):
    conn, _, _ = plan
    root = _repo(tmp_path)
    monkeypatch.setattr(cs, 'ROOT', root)
    from core.knowledge import projects
    ids = iter(['S-0000000P02', 'S-0000000P03'])
    def add(project, title, description, owner):
        sid = next(ids)
        conn.execute("INSERT INTO project_steps VALUES(?,?,?,?,'todo',?,99,0,0,NULL)", (sid, project, title, description, owner))
        return sid
    monkeypatch.setattr(projects, 'add_step', add)
    hp.create(conn, 'gemini-advisor', {'title': 'Wrong value', 'why': 'make it three for no reason',
                                       'edits': [{'path': 'pkg/mod.py', 'old': '    return 1', 'new': '    return 3'}], 'tests': ['tests/test_mod.py']})
    assert not hp.check(conn, 'S-0000000P02', root=root)['verified']
    assert conn.execute("SELECT owner FROM project_steps WHERE step_id='S-0000000P02'").fetchone()[0] == 'claude-code'
    hp.create(conn, 'gemini-advisor', {'title': 'An idea only', 'why': 'discuss splitting the module'})
    assert 'no code' in hp.check(conn, 'S-0000000P03', root=root)['why']
    with pytest.raises(PermissionError):
        hp.create(conn, 'gemini-advisor', {'title': 'Read the key', 'why': 'just to check it is set',
                                           'edits': [{'path': 'config.py', 'old': 'x', 'new': 'y'}]})
