"""Practice 71 (owner 15 Nov): "the system should have a task board and let me edit and move it" - the board's rows can be moved
and given an importance by clicking; the clicks use the same rules as /clip."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_practice_71_board_rows_have_move_and_importance_controls():
    js = (ROOT / 'frontend/static/js/views/hb-queue.js').read_text()
    for piece in ('data-clip="top"', 'data-clip="up"', 'data-clip="down"', 'select data-importance=', "JSON.stringify({ clip: args })", "clip(['importance', s.dataset.importance, s.value])"):
        assert piece in js, piece
    assert "i.state === 'now' || i.state === 'blocked'" in js          # the running step and blocked ones are not movable
    done = subprocess.run(['node', '--check', str(ROOT / 'frontend/static/js/views/hb-queue.js')], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_practice_71_route_takes_clip_edits_with_the_same_rules_as_the_command():
    src = (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
    i = src.index("isinstance(body.get('clip'),list)")
    block = src[i:i + 900]
    assert "hb_clipboard.edit(conn,args,current_user['username']+' via the task board')" in block
    assert "('up','down','top','importance','doer','impact','clear')" in block
    assert src.index("Sec-Fetch-Site") < i                                # the cross-site guard still runs first
    assert "@require_owner\ndef hb_queue_status" in src                   # owner only
