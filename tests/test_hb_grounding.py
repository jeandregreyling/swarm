"""Practice 47 (owner 14 Nov): daily grounding - real day on the sundial, HB opens the day with a self-check and a checkpoint."""
import sqlite3
import time
from pathlib import Path
import core.hb_grounding as g
import core.hb_commands as cmds

ROOT = Path(__file__).resolve().parents[1]
NOW = time.mktime((2026, 11, 15, 9, 0, 0, 0, 0, -1))


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER, created_at TEXT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, project_id TEXT, title TEXT, status TEXT, updated_at REAL)')
    c.execute('CREATE TABLE hb_agents(agent_id TEXT, kind TEXT, status TEXT)')
    c.executemany('INSERT INTO project_steps VALUES (?,?,?,?,?)', [('S-1', g.PLAN, 'a', 'done', NOW - 60), ('S-2', g.PLAN, 'b', 'todo', NOW), ('S-3', g.PLAN, 'c', 'doing', NOW)])
    c.executemany('INSERT INTO hb_agents VALUES (?,?,?)', [('m1', 'local', 'active'), ('m2', 'local', 'provisional'), ('o1', 'online', 'active')])
    return c


def check(c):
    return g.self_check(c, NOW, memory={'MemAvailable': 32 * 1024 ** 3}, disk=200 * 1024 ** 3, listeners={8080: {'name': 'llama-server', 'pid': 1}})


def test_practice_47_self_check_reads_the_machine_and_the_queue():
    f = check(db())
    assert f['day'] == 'Sunday 15 November 2026' and f['ram_gb'] == 32.0 and f['disk_gb'] == 200
    assert f['model_server'] is True and f['models'] == 1 and f['open'] == 2 and f['done_24h'] == 1


def test_practice_47_opening_text_is_five_plain_lines():
    out = g.text(check(db()))
    lines = out.splitlines()
    assert len(lines) == 5 and lines[0] == '☀ Today is Sunday 15 November 2026.'
    assert 'APEX model server up' in lines[1] and '2 steps open, 1 finished' in lines[2] and lines[4].startswith('Checkpoint: one step at a time.')
    assert 'DOWN' in g.text({**check(db()), 'model_server': False})


def test_practice_47_posted_once_a_day_after_the_owner_arrives():
    c = db()
    assert g.tick(c, NOW) is None                                  # JD has not written today
    c.execute("INSERT INTO messages(conversation_id,from_agent,content,created_at) VALUES (?,'user','go',datetime(?, 'unixepoch'))", (g.MAIN_CHAT, NOW - 60))
    mid = g.tick(c, NOW)
    assert mid and c.execute('SELECT content FROM messages WHERE id=?', (mid,)).fetchone()[0].startswith('☀ Today is')
    assert g.tick(c, NOW + 3600) is None                           # once a day


def test_practice_47_sundial_shows_the_real_day_and_today_is_a_command():
    js = (ROOT / 'frontend/static/js/hb-day-anchor.js').read_text()
    assert "getElementById('sundial-title')" in js and "weekday: 'long'" in js
    assert '/static/js/hb-day-anchor.js' in (ROOT / 'frontend/templates/terminal_base.html').read_text()
    assert 'today' in cmds.NAMES and cmds.parse('today') == ('today', [])
