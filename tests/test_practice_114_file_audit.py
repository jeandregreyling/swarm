"""Practice 114 (owner 16 Nov 2026): "one of the bigger models can actually start going through all the files, there's a lot of files with
things that don't work really well, look weird, the old icons still show". HB's reviewer model audits the interface files block by block;
only findings on a real line are kept; a finished file with findings becomes one Studio step (homework then specs it for APEX)."""
import json
import sqlite3

from core import hb_file_audit as a


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'go through all the files')")
    return c


def _repo(tmp_path, n=10):
    d = tmp_path / 'frontend' / 'static' / 'js'
    d.mkdir(parents=True)
    (d / 'x.js').write_text('\n'.join(f"const a{i} = '{'🌺' if i == 3 else i}';" for i in range(1, n + 1)) + '\n')
    return tmp_path


def test_practice_114_a_file_is_audited_and_real_findings_become_one_studio_step(tmp_path):
    root, c, steps = _repo(tmp_path), _db(), []
    model = lambda messages: {'findings': [
        {'line': 3, 'kind': 'old-icon', 'problem': 'A coloured emoji is used as an icon here.', 'fix': "Use HBIcons.svg('flower')."},
        {'line': 99, 'kind': 'cannot-work', 'problem': 'This line does not exist in the block.', 'fix': 'x'}]}
    add = lambda project, title, description, owner: steps.append((title, description, owner)) or 'S-AUDIT00001'
    assert a.audit_block(c, root, model=model, add_step=add) == ('frontend/static/js/x.js', 1)
    assert steps and steps[0][0] == 'Audit fix: frontend/static/js/x.js (1 finding)' and steps[0][2] == 'claude-code'
    assert 'line 3 (old-icon)' in steps[0][1] and 'line 99' not in steps[0][1]
    said = c.execute("SELECT conversation_id, content FROM messages WHERE from_agent='hummingbird'").fetchone()
    assert said[0] == 2845 and said[1].startswith('🔎 File audit: frontend/static/js/x.js - 1 thing(s) to fix')
    assert a.audit_block(c, root, model=model, add_step=add) is None          # unchanged: not again


def test_practice_114_a_changed_file_is_audited_again_and_big_files_go_block_by_block(tmp_path):
    root, c = _repo(tmp_path, n=a.CHUNK + 5), _db()
    calls = []
    model = lambda messages: calls.append(messages[1]['content'].splitlines()[0]) or {'findings': []}
    assert a.audit_block(c, root, model=model, add_step=lambda *x, **k: None)[0] == 'frontend/static/js/x.js'
    assert a.audit_block(c, root, model=model, add_step=lambda *x, **k: None)[0] == 'frontend/static/js/x.js'
    assert a.audit_block(c, root, model=model, add_step=lambda *x, **k: None) is None
    assert calls == [f'File: frontend/static/js/x.js (lines 1-{a.CHUNK} of {a.CHUNK + 5})',
                     f'File: frontend/static/js/x.js (lines {a.CHUNK + 1}-{a.CHUNK + 5} of {a.CHUNK + 5})']
    (root / 'frontend/static/js/x.js').write_text('let changed = 1;\n')
    assert a.audit_block(c, root, model=model, add_step=lambda *x, **k: None)[0] == 'frontend/static/js/x.js'


def test_practice_114_audit_command():
    c = _db()
    assert a.command(c, ['off']) == 'File audit is off.' and not a.enabled(c)
    assert a.command(c, ['on']).startswith('File audit is on.') and a.enabled(c)
