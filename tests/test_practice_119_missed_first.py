"""Practice 119 (monitoring 16 Nov 2026, 23:32): the audit made a missed Studio step only after every file was audited, so three files
reported before Practice 118 still had none. A missed step is now made before the next block is read."""
import json
import sqlite3

from core import hb_file_audit as a


def test_practice_119_missed_step_first(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'ROOT', tmp_path)
    d = tmp_path / 'frontend' / 'static' / 'css'
    d.mkdir(parents=True)
    (d / 'done.css').write_text('.a { color: #000; }\n')
    (d / 'todo.css').write_text('.b { margin: 0; }\n')
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    a.ensure_schema(c)
    found = [{'line': 1, 'kind': 'hard-coded-colour', 'problem': 'Black is hard-coded here.', 'fix': 'var(--text)', 'code': '.a { color: #000; }'}]
    c.execute("INSERT INTO hb_file_audit VALUES ('frontend/static/css/done.css', ?, 999, ?, 0, NULL)",
              (a._sha((d / 'done.css').read_text()), json.dumps(found)))
    calls = []
    out = a.audit_block(c, tmp_path, model=lambda m: calls.append(1) or {'findings': []}, add_step=lambda *x, **k: 'S-AUDIT00003')
    assert out == ('frontend/static/css/done.css', 1) and calls == []          # the missed step first, no model call yet
    assert a.audit_block(c, tmp_path, model=lambda m: calls.append(1) or {'findings': []}, add_step=lambda *x, **k: 'S-X')[0] == 'frontend/static/css/todo.css'
