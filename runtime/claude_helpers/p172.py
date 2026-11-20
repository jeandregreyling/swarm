"""Prepare Practice 172: a running admin step shows its progress live - in its main-chat message and on the live activity line."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
A = 'core/hb_admin.py'
LA = 'core/hb_live_activity.py'
edits = [
    {'path': A, 'old': '''    conn.execute("UPDATE hb_admin_requests SET state='running', updated_at=? WHERE id=?", (time.time(), rid))
    if watch:
''', 'new': '''    conn.execute("UPDATE hb_admin_requests SET state='running', updated_at=? WHERE id=?", (time.time(), rid))
    try:                                  # Practice 172: one main-chat message that updates itself while the step runs
        _progress_message(conn, rid)
    except Exception:
        pass                              # progress is a convenience; it never stops the admin step
    if watch:
'''},
    {'path': A, 'old': '''        sleep(5)
''', 'new': '''        sleep(5)
        if int(time.time() - start) % 10 < 5:   # Practice 172: refresh the live message about every 10 s
            try:
                with closing(get_connection()) as pc:
                    refresh(pc, rid, log, time.time() - start)
                    pc.commit()
            except Exception:
                pass
'''},
    {'path': A, 'old': "def _watch(rid, log, status, limit=4 * 3600, sleep=time.sleep, running=None):\n",
     'new': '''# Practice 172 (owner 19 Nov 2026: "is it really that difficult to show me in HB when these things are running and downloading?"): the ROCm
# step ran for 20+ minutes with nothing in main chat between "window is open" and the end. A running step now keeps one message current
# (elapsed time, packages fetched, last output lines) and shows on the live activity line under the chat.
def _progress_message(conn, rid):
    from core.hb_chat import owner_chat
    try:
        conn.execute('ALTER TABLE hb_admin_requests ADD COLUMN progress_mid INTEGER')
    except Exception:
        pass
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                       (owner_chat(conn), f'🔐 Admin step {rid} is starting - type your password in the "HB admin {rid}" window.')).lastrowid
    conn.execute('UPDATE hb_admin_requests SET progress_mid=? WHERE id=?', (mid, rid))
    return mid


def progress_text(rid, log_text, seconds, why=''):
    lines = [l.rstrip() for l in str(log_text or '').splitlines() if l.strip()]
    fetched = len(re.findall(r'^Get:\\d+ ', str(log_text or ''), re.M))
    setting = len(re.findall(r'^Setting up ', str(log_text or ''), re.M))
    phase = (f'{setting} packages set up' if setting else f'{fetched} packages downloaded' if fetched else 'waiting for your password' if not lines else 'working')
    tail = '\\n'.join(l[:160] for l in lines[-5:])
    return (f'🔐 Admin step {rid} running {int(seconds // 60)} min {int(seconds % 60)} s - {phase}' + (f' ({why})' if why else '') + '.'
            + (f"\\n```text\\n{tail.replace('```', '` ` `')}\\n```" if tail else ''))


def refresh(conn, rid, log, seconds):
    row = conn.execute('SELECT progress_mid, why FROM hb_admin_requests WHERE id=?', (rid,)).fetchone()
    if row and row[0]:
        text = log.read_text(errors='replace') if log.exists() else ''
        conn.execute('UPDATE messages SET content=? WHERE id=?', (progress_text(rid, text, seconds, row[1]), row[0]))


def live_lines(conn, now=None):
    """Lines for the live activity view: every admin step that is running."""
    now = now or time.time()
    try:
        rows = conn.execute("SELECT id, why, updated_at FROM hb_admin_requests WHERE state='running'").fetchall()
    except Exception:
        return []
    out = []
    for rid, why, started in rows:
        log = LOG_DIR / f'{rid}.log'
        text = log.read_text(errors='replace') if log.exists() else ''
        last = next((l for l in reversed(text.splitlines()) if l.strip()), 'waiting for your password in the HB admin window')
        out.append(f"ADMIN (sudo, your terminal) - {str(why)[:80]} - running {int((now - (started or now)) // 60)} min")
        out.append('  ' + last.strip()[:140])
    return out


def _watch(rid, log, status, limit=4 * 3600, sleep=time.sleep, running=None):
'''},
    {'path': LA, 'old': '''    return {'running': bool(lines), 'lines': lines}
''', 'new': '''    try:   # Practice 172: admin steps (sudo in JD's terminal) show here while they run
        from core.hb_admin import live_lines
        lines += live_lines(conn, now)
    except Exception:
        pass
    return {'running': bool(lines), 'lines': lines}
'''},
]

test = r'''"""Practice 172 (owner 19 Nov 2026: "is it really that difficult to show me in HB when these things are running and downloading?"): a running
admin step keeps a live main-chat message and shows on the live activity line."""
import sqlite3
import time

from core import hb_admin as a, hb_live_activity

LOG = 'Reading package lists...\nGet:1 https://repo.radeon.com x [1 kB]\nGet:2 https://repo.radeon.com y [122 MB]\n'


def test_practice_172_progress_text():
    t = a.progress_text('A-1', LOG, 125, 'install ROCm')
    assert t.startswith('🔐 Admin step A-1 running 2 min 5 s - 2 packages downloaded (install ROCm).') and 'Get:2' in t
    assert 'waiting for your password' in a.progress_text('A-1', '', 3)
    assert '1 packages set up' in a.progress_text('A-1', LOG + 'Setting up amdrocm (10.2)\n', 600)


def test_practice_172_live_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    (tmp_path / 'A-1.log').write_text(LOG)
    c = sqlite3.connect(':memory:')
    a.ensure_schema(c)
    c.execute("INSERT INTO hb_admin_requests VALUES ('A-1','[]','install ROCm','running',NULL,?,?,NULL,NULL)", (time.time(), time.time() - 300))
    lines = a.live_lines(c)
    assert lines[0].startswith('ADMIN (sudo, your terminal) - install ROCm - running 5 min') and 'Get:2' in lines[1]
    snap = hb_live_activity.snapshot(c, background=[])
    assert snap['running'] and any(l.startswith('ADMIN') for l in snap['lines'])
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 19 Nov (\"is it really that difficult to show me in HB when these things are running and downloading?\"): the ROCm "
                            "admin step ran 20+ minutes with nothing in main chat between start and end. core/hb_admin: a running step keeps one "
                            "main-chat message current about every 10 s (elapsed, packages downloaded / set up, last output lines) and live_lines() "
                            "adds it to the live activity view (core/hb_live_activity.snapshot)."),
                 edits=edits, new_files={'tests/test_practice_172_admin_progress.py': test},
                 test={'tests': ['tests/test_practice_172_admin_progress.py', 'tests/test_practice_171_admin_unattended.py',
                                 'tests/test_practice_170_admin_steps.py', 'tests/test_practice_164_activity_route.py'], 'keyword': ''}, run=run)
print(out['verified'])
