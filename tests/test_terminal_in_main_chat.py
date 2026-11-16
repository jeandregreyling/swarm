"""S-9B9907AF1F (owner 16 Nov 2026): "Have you integrated the terminal to main chat yet?" - asked on 12 Nov, lost in the clean slate.
JD runs "$ <command>" in main chat: whitelisted read/status commands only, never through a shell, saved in the chat with live output,
Stop, and an honest "interrupted by an HB restart"."""
import sqlite3
import time
from pathlib import Path

from core import hb_chat_terminal as t

ROOT = Path(__file__).resolve().parents[1]


def _db(tmp_path):
    path = tmp_path / 'm.db'
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.commit()
    c.close()
    return lambda: sqlite3.connect(path, timeout=10)


def _wait(command_id, connect, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        s = t.status(command_id, connect)
        if s and s['state'] != 'running':
            return s
        time.sleep(0.2)
    return t.status(command_id, connect)


def test_only_plain_whitelisted_read_commands():
    assert t.check('df -h') == (['df', '-h'], None)
    for bad in ('cat /var/log/syslog;id', 'ps aux | grep python', 'ls $HOME', 'rm -rf /tmp/x',
                'sudo systemctl restart apex-server.service', 'curl -s https://example.com'):
        argv, why = t.check(bad)
        assert argv is None and why, bad


def test_a_command_runs_and_is_saved_in_the_chat(tmp_path):
    connect = _db(tmp_path)
    out = t.start(2845, 'pwd', connect=connect, root=str(tmp_path))
    assert out['ok'] and out['state'] == 'running'
    s = _wait(out['command_id'], connect)
    assert s['state'] == 'completed' and s['returncode'] == 0 and str(tmp_path) in s['output']
    rows = connect().execute('SELECT conversation_id, from_agent, content, message_type FROM messages ORDER BY id').fetchall()
    assert rows[0] == (2845, 'user', '$ pwd', 'terminal')
    assert rows[1][1] == 'hummingbird' and rows[1][2].startswith('💻 $ pwd') and 'completed, exit 0' in rows[1][2]


def test_a_refused_command_runs_nothing(tmp_path):
    connect = _db(tmp_path)
    marker = tmp_path / 'should-not-exist'
    out = t.start(2845, f'cat /var/log/syslog;touch {marker}', connect=connect)
    assert not out['ok'] and out['state'] == 'refused'
    time.sleep(0.3)
    assert not marker.exists()
    assert '— refused:' in t.status(out['command_id'], connect)['content']


def test_stop_ends_a_running_command(tmp_path):
    connect = _db(tmp_path)
    out = t.start(2845, 'ping -c 30 127.0.0.1', connect=connect)
    assert out['ok']
    time.sleep(1.5)
    assert t.stop(out['command_id'])
    s = _wait(out['command_id'], connect)
    assert s['state'] == 'stopped' and 'stopped by JD' in s['content']


def test_a_command_cut_off_by_a_restart_says_so(tmp_path):
    connect = _db(tmp_path)
    c = connect()
    t.ensure_schema(c)
    mid = c.execute("INSERT INTO messages(conversation_id,from_agent,content,message_type) VALUES (2845,'hummingbird','x','terminal')").lastrowid
    c.execute("INSERT INTO hb_chat_terminal(command_id,conversation_id,message_id,command,state,pid,boot,output,started_at) "
              "VALUES ('c1',2845,?,'df -h','running',NULL,'an-earlier-hb','Filesystem',1)", (mid,))
    assert t.recover(c) == 1
    assert 'interrupted by an HB restart' in c.execute('SELECT content FROM messages WHERE id=?', (mid,)).fetchone()[0]
    assert t.recover(c) == 0


def test_main_chat_and_routes_are_wired():
    js = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    assert '/api/chat-terminal/run' in js and 'const terminalCommand = _hcTerminalCommand(text);' in js and '/api/chat-terminal/stop' in js
    py = (ROOT / 'frontend/blueprints/shell.py').read_text()
    for route in ('/api/chat-terminal/run', '/api/chat-terminal/stop', '/api/chat-terminal/<command_id>'):
        assert route in py
    assert py.count('_chat_terminal_owner()') >= 3
