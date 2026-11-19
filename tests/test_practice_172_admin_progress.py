"""Practice 172 (owner 19 Nov 2026: "is it really that difficult to show me in HB when these things are running and downloading?"): a running
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
