"""Practice 236: a test that cannot fail proves nothing - it neither finishes a test-first chunk nor makes a step ready."""
import inspect
import json
import sqlite3
import time

from core import hb_chunks as ch, hb_tasks
from core import hb_task_manager as tm

DESC = ('Do: write tests/test_x_feature.py first, then add core/x_feature.py, then run the test.\n'
        'Done when: python -m pytest tests/test_x_feature.py passes')
TASK = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': DESC, 'title': 'X feature', 'conversation_id': 2845}


def _db():
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    c.execute('CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT, title TEXT, description TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, '
              'message_type TEXT, tokens_used INT)')
    c.execute("INSERT INTO project_steps VALUES ('S-1', 'X feature', ?)", (DESC,))
    ch.focus(c, TASK)
    c.execute('INSERT INTO hb_task_events(task_id, agent, kind, payload, created_at) VALUES (?,?,?,?,?)',
              ('T-1', 'apex', 'mutation', json.dumps({}), time.time()))
    return c


def _write(tmp_path, monkeypatch, body):
    (tmp_path / 'tests').mkdir(exist_ok=True)
    (tmp_path / 'tests' / 'test_x_feature.py').write_text(body)
    monkeypatch.setattr(ch, 'ROOT', tmp_path)


PLACEHOLDER = 'def test_placeholder():\n    assert True\n'
REAL = 'from core import x_feature\n\ndef test_it():\n    assert x_feature.total([1, 2]) == 3\n'


def test_assert_true_does_not_finish_the_chunk_and_hb_says_why_once(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, PLACEHOLDER)
    c = _db()
    assert ch.advance(c, TASK) is None and ch.advance(c, TASK) is None
    lines = [r[0] for r in c.execute("SELECT content FROM messages WHERE content LIKE '%NOT done%'")]
    assert len(lines) == 1 and 'chunk 1 is NOT done' in lines[0] and 'no real check' in lines[0]


def test_import_only_test_does_not_finish_the_chunk(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, "import importlib\n\ndef test_import():\n    importlib.import_module('core.x_feature')\n")
    assert ch.advance(_db(), TASK) is None


def test_a_skipped_test_does_not_count(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, 'import pytest\n\n@pytest.mark.skip(reason="later")\ndef test_it():\n    assert 1 + 1 == 3\n')
    assert 'skips itself' in ch.weak_test('write tests/test_x_feature.py first')


def test_missing_test_file_does_not_finish_the_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, 'ROOT', tmp_path)
    assert 'does not exist' in ch.weak_test('write tests/test_x_feature.py first')


def test_a_real_assertion_finishes_the_chunk(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, REAL)
    assert ch.advance(_db(), TASK) == 1


def test_pytest_raises_counts_and_other_chunks_are_untouched(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, 'import pytest\n\ndef test_it():\n    with pytest.raises(KeyError):\n        {}["a"]\n')
    assert ch.weak_test('write tests/test_x_feature.py first') is None
    assert ch.weak_test('add core/x_feature.py') is None


def test_a_placeholder_done_test_blocks_approval_and_the_flower(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, PLACEHOLDER)
    assert 'no real check' in ch.weak_done(TASK)
    _write(tmp_path, monkeypatch, REAL)
    assert ch.weak_done(TASK) is None
    assert ch.weak_done(dict(TASK, objective='Answer the question.')) is None


def test_the_task_manager_checks_it_before_approving():
    src = inspect.getsource(tm.tick)
    assert src.index('weak=weak_done(task)') < src.index("if phase=='review' and ready:")
