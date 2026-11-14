"""Practice 57 (owner 14 Nov): roles, not names - a role register with stand-ins; the CPU roles read their model from it."""
import sqlite3
from pathlib import Path
import core.hb_roles as r
import core.hb_commands as cmds

ROOT = Path(__file__).resolve().parents[1]
HERE = {'fred-cpu:24b', 'homework-cpu:7b', 'qwen2.5:14b-instruct', 'mistral-small:24b', 'qwen2.5:7b-instruct'}


def test_practice_57_default_then_register_then_stand_in():
    c = sqlite3.connect(':memory:')
    known = HERE.__contains__
    assert r.resolve('counsel', c, known) == ('fred-cpu:24b', 'the default for this role')
    assert r.assign(c, 'counsel', 'mistral-small:24b', 'jd', known).startswith('counsel (')
    assert r.resolve('counsel', c, known) == ('mistral-small:24b', 'set in the role register')
    assert r.assign(c, 'counsel', 'nope:1b', 'jd', known) == 'nope:1b is not a model on this machine.'
    assert r.assign(c, 'boss', 'fred-cpu:24b', 'jd', known).startswith('Roles: ')


def test_practice_57_a_missing_model_does_not_stop_the_role():
    c = sqlite3.connect(':memory:')
    gone = (HERE - {'fred-cpu:24b'}).__contains__
    assert r.resolve('deep', c, gone) == ('mistral-small:24b', 'fred-cpu:24b is not on this machine; mistral-small:24b stands in')
    assert r.resolve('homework', c, {'llama3.2:latest'}.__contains__)[0] == 'llama3.2:latest'
    assert 'no stand-in' in r.resolve('homework', c, lambda m: False)[1]
    r.assign(c, 'deep', 'qwen2.5:7b-instruct', 'jd', HERE.__contains__)
    assert r.resolve('deep', c, (HERE - {'qwen2.5:7b-instruct'}).__contains__)[0] == 'fred-cpu:24b'      # assigned one gone: back to the default


def test_practice_57_cpu_roles_read_the_register_and_roles_is_a_command():
    for rel, role in (('core/hb_counsel.py', 'counsel'), ('core/hb_homework.py', 'homework'), ('core/hb_local_review.py', 'review'), ('core/hb_model_switches.py', 'deep')):
        assert f"model_for('{role}')" in (ROOT / rel).read_text(), rel
    assert 'roles' in cmds.NAMES and cmds.parse('roles') == ('roles', []) and cmds.parse('roles set counsel mistral-small:24b') == ('roles', ['set', 'counsel', 'mistral-small:24b'])
    assert r.table(sqlite3.connect(':memory:')).startswith('Roles:\n- apex (')
