"""Practice 118 (monitoring 16 Nov 2026, 23:02): the audit's connection held its write while the model thought, so Studio's add_step hit
"database is locked" and returned None - three files were announced with "Studio step None" and never reached homework or APEX. Writes are
committed before the model call; a file whose step was never made gets it later; themed rgba(var(...)) is not a hard-coded colour."""
import json
import sqlite3

from core import hb_file_audit as a


def test_practice_118_the_database_is_free_while_the_model_thinks(tmp_path):
    db = tmp_path / 'm.db'
    c = sqlite3.connect(db)
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.commit()
    d = tmp_path / 'frontend' / 'static' / 'css'
    d.mkdir(parents=True)
    (d / 'x.css').write_text('.a { color: #000; }\n')
    seen = []

    def model(messages):
        other = sqlite3.connect(db, timeout=0.2)            # another HB connection writing while the model "thinks"
        other.execute("INSERT INTO messages(content) VALUES ('peer inbox poll')")
        other.commit()
        seen.append('wrote')
        return {'findings': [{'line': 1, 'kind': 'hard-coded-colour', 'problem': 'The colour #000 is hard-coded here.', 'fix': 'var(--text)'}]}
    steps = []
    a.audit_block(c, tmp_path, model=model, add_step=lambda p, t, description, owner: steps.append(t) or 'S-AUDIT00001')
    assert seen == ['wrote'] and steps == ['Audit fix: frontend/static/css/x.css (1 finding)']


def test_practice_118_a_missed_step_is_made_later_and_no_none_line(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'ROOT', tmp_path)
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    a.ensure_schema(c)
    (tmp_path / 'y.css').write_text('.b { color: #fff; }\n')
    found = [{'line': 1, 'kind': 'hard-coded-colour', 'problem': 'White is hard-coded here.', 'fix': 'var(--text)', 'code': '.b { color: #fff; }'}]
    c.execute("INSERT INTO hb_file_audit VALUES ('y.css', 'sha', 999, ?, 0, NULL)", (json.dumps(found),))
    assert a.missed(c, add_step=lambda *x, **k: None) == ('y.css', 0)          # Studio refused: nothing posted
    assert not c.execute("SELECT 1 FROM messages WHERE content LIKE '%Studio step None%'").fetchone()
    assert a.missed(c, add_step=lambda *x, **k: 'S-AUDIT00002') == ('y.css', 1)
    assert c.execute("SELECT step_id FROM hb_file_audit WHERE path='y.css'").fetchone()[0] == 'S-AUDIT00002'


def test_practice_118_themed_rgba_is_not_hard_coded():
    f = lambda code: {'line': 1, 'kind': 'hard-coded-colour', 'code': code}
    assert not a.verified(f('background: rgba(var(--accent-rgb, 96, 165, 250), 0.06);'))
    assert a.verified(f('background: rgba(138,26,43,0.40);'))
