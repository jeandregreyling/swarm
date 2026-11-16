"""Practice 121 (monitoring 17 Nov 2026, 00:46): "UnboundLocalError: cannot access local variable 'closing'" in hb_model_bench.run_all.
Practice 105 imported closing inside the model loop, which makes it local to the whole function; when no model matched (a /bench with an
old name) the code after the loop crashed. The module-level import is used instead."""
import inspect

from core import hb_model_bench as mb


def test_practice_121_run_all_has_no_local_closing_import():
    assert 'from contextlib import closing' not in inspect.getsource(mb.run_all)


def test_practice_121_no_matching_model_does_not_crash(monkeypatch):
    import sqlite3
    from contextlib import closing  # noqa: F401
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')

    class Keep:
        def __enter__(self): return c
        def __exit__(self, *a): return False
        def close(self): pass
        def execute(self, *a, **k): return c.execute(*a, **k)
        def commit(self): c.commit()
    import utils.db._connection as conn_mod
    monkeypatch.setattr(conn_mod, 'get_connection', lambda: Keep())
    monkeypatch.setattr(mb, 'models', lambda: [])
    import core.hb_agents as agents
    monkeypatch.setattr(agents, 'onboard_local_models', lambda conn, actor='owner', say=None: [])
    mb.run_all(['no-such-model'])          # used to raise UnboundLocalError
