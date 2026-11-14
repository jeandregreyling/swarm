"""Practice 75 (owner 15 Nov): "let me edit and approve and move it" - every board row has pause / continue, cancel, and approve when a
finished step waits; the clicks run the same owner commands as typing them."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_practice_75_rows_have_task_controls():
    js = (ROOT / 'frontend/static/js/views/hb-queue.js').read_text()
    for piece in ('data-task="pause"', 'data-task="continue"', 'data-task="cancel"', 'data-task="accept"', 'JSON.stringify({ task: args })', "window.confirm('Cancel this task?"):
        assert piece in js, piece
    assert "if (i.state === 'now') return `<span class=\"hb-clip-edit\">${taskHtml(i)}</span>`;" in js      # the running step can be paused or cancelled
    done = subprocess.run(['node', '--check', str(ROOT / 'frontend/static/js/views/hb-queue.js')], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-300:]


def test_practice_75_route_runs_the_owner_commands_and_their_follow_up():
    src = (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
    i = src.index("isinstance(body.get('task'),list)")
    block = src[i:i + 1300]
    assert "args[0] in ('pause','continue','cancel')" in block and "args[0]=='accept'" in block
    assert "hb_commands.run(conn,2834,args[0],[args[1]],current_user['username']+' via the task board',after)" in block
    assert 'for job in after:' in block                                   # pause and cancel really stop the running turn
    assert "@require_owner\ndef hb_queue_status" in src and src.index('Sec-Fetch-Site') < i
