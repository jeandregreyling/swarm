"""Practice 179: the jump arrow floats and glows; the HB-now line says what last ran when idle."""
import sqlite3
from pathlib import Path

from core import hb_live_activity

ROOT = Path(__file__).resolve().parents[1]


def test_jump_arrow_states():
    js = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    css = (ROOT / 'frontend/static/css/home-chat.css').read_text()
    assert "btn.classList.toggle('away', away)" in js and "btn.classList.toggle('fresh', true)" in js and "classList.toggle('locked', !auto)" in js
    assert 'Auto scroll LOCKED' in js and 'Auto scroll ON' in js
    assert '@keyframes hcJumpGlow' in css and '#hc-jump-bottom.fresh::before' in css and 'max-width: 40px' in css


def test_idle_line_names_what_ran_last():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, title TEXT)')
    c.execute('CREATE TABLE hb_executions(execution_id TEXT, task_id TEXT, request_id TEXT, agent TEXT, kind TEXT, identity TEXT, state TEXT, started_at REAL, updated_at REAL)')
    c.execute("INSERT INTO hb_tasks VALUES ('T-1', 'Practice 178 (owner): answers do not talk about drafts')")
    c.execute("INSERT INTO hb_executions VALUES ('E-1','T-1','R-1','apex','turn','x','completed',100,200)")
    s = hb_live_activity.snapshot(c, now=300, background=[])
    assert s['running'] is False and s['last'] == {'agent': 'apex', 'title': 'Practice 178 (owner): answers do not talk about drafts', 'at': 200}
    js = (ROOT / 'frontend/static/js/hb-live-activity.js').read_text()
    assert "'idle since '" in js and "last=live.get('last')" in (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()


def test_terminal_icon_urls_do_not_swallow_jump_arrow_rules():
    import re

    css = (ROOT / 'frontend/static/css/home-chat.css').read_text()
    declarations = [line.strip() for line in css.splitlines()
                    if 'mask: url("data:image/svg+xml,' in line]
    assert len(declarations) == 2
    for declaration in declarations:
        assert re.fullmatch(r"""(?:-webkit-)?mask: url\((["'])(.*?)\1\) no-repeat center;""",
                            declaration), declaration
