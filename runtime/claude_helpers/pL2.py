"""Prepare HB Live L2 (Practice 187): core/hb_live.snapshot - the one read model - and GET /api/peer/v1/hb/live."""
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
MODULE = Path('/tmp/claude-1000/-home-jd/12a48d48-c161-4f13-ab48-18ba6f3e4cde/scratchpad/hb_live.py').read_text()
PB = 'frontend/blueprints/peer_bridge.py'

route = '''_HB_LIVE_CACHE = {'at': 0.0, 'data': None}


@peer_bridge_bp.route('/api/peer/v1/hb/live',methods=['GET'])
@require_owner
def hb_live_view(current_user=None):
    """HB Live L2 (owner 20 Nov 2026, docs/spec-hb-live-dashboard.md): the one snapshot main chat's live strip and windows render from.
    Cached for 1.5 s so several open pages share one read."""
    import time as _time
    from contextlib import closing
    from core import hb_live
    if _HB_LIVE_CACHE['data'] is None or _time.time()-_HB_LIVE_CACHE['at']>1.5:
        with closing(get_connection()) as conn:
            _HB_LIVE_CACHE['data']=hb_live.snapshot(conn)
        _HB_LIVE_CACHE['at']=_time.time()
    return jsonify(ok=True,**_HB_LIVE_CACHE['data'])


@peer_bridge_bp.route('/api/peer/v1/hb/queue',methods=['GET','POST'])
'''

test = '''"""HB Live L2: one snapshot of every lane, the master list, Needs you, history and telemetry."""
import sqlite3
from pathlib import Path

import pytest

from core import hb_activity_log as live
from core import hb_live

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def conn(monkeypatch, tmp_path):
    path = tmp_path / 'live.db'
    monkeypatch.setattr(live, 'FORCE', True)
    monkeypatch.setattr(live, '_connect', lambda: sqlite3.connect(path))
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE hb_admin_requests(id TEXT, argv TEXT, why TEXT, state TEXT, needs TEXT, created_at REAL, updated_at REAL, exit_code INTEGER, log TEXT, progress_mid INTEGER)")
    c.commit()
    return c


def _stubs(monkeypatch, peers=(), queue=None, waiting=()):
    from core import hb_activity, hb_queue, hb_commands
    monkeypatch.setattr(hb_activity, 'chains', lambda conn: list(peers))
    monkeypatch.setattr(hb_queue, 'status', lambda conn: queue or {'on': True, 'auto': False, 'items': []})
    monkeypatch.setattr(hb_commands, 'waiting_items', lambda conn: list(waiting))


def test_every_source_lands_in_its_lane(conn, monkeypatch):
    turn = live.begin('apex', 'gpu', 'APEX: MCB question', model='swift-qwen3.8-27b', device='ROCm', task_id='T-1', purpose='main-chat turn')
    turn.step('searching our notes: "MCB"')
    cc = live.begin('claude', 'claude-code', 'Backlog sweep', model='claude-code', device='online')
    conn.execute("INSERT INTO hb_admin_requests VALUES ('A-1', '[\\"apt-get\\", \\"update\\"]', 'refresh packages', 'running', NULL, 0, 5, NULL, NULL, NULL)")
    conn.commit()
    peers = [{'task_id': 'T-2', 'task': 'Bug: x', 'members': [{'request_id': 9, 'role': 'Fred', 'model': 'fred-cpu:24b', 'where': 'CPU',
                                                               'now': 'reading core/x.py', 'steps': [{'at': '10:00', 'what': 'reading core/x.py'}]}]},
             {'task_id': 'T-3', 'task': 'Review', 'members': [{'request_id': 10, 'role': 'Codex', 'model': 'codex', 'where': 'online',
                                                               'now': 'reviewing', 'steps': []}]}]
    queue = {'on': True, 'auto': True, 'items': [{'step_id': 'S-1', 'task_id': 'T-1', 'title': 'MCB', 'state': 'now', 'parked': False},
                                                 {'step_id': 'S-2', 'task_id': 'T-9', 'title': 'Old bug', 'state': 'waiting', 'parked': True}]}
    _stubs(monkeypatch, peers, queue, [{'kind': 'accept', 'label': 'Approve Studio S-1'}])
    s = hb_live.snapshot(conn, tele={'gpu': {'busy_pct': 80}, 'cpu': {}, 'ram': {}})
    lanes = {l['id']: l for l in s['lanes']}
    assert lanes['gpu']['state'] == 'busy' and lanes['gpu']['items'][0]['last_step'] == 'searching our notes: "MCB"'
    assert lanes['fred']['items'][0]['last_step'] == 'reading core/x.py' and lanes['online']['items'][0]['actor'] == 'Codex'
    assert lanes['admin']['items'][0]['title'] == 'sudo apt-get update' and lanes['claude-code']['items'][0]['title'] == 'Backlog sweep'
    assert s['master']['items'][0]['live']['lane'] == 'gpu' and s['master']['items'][1]['live'] is None and s['master']['items'][1]['parked']
    assert s['needs_you'] == [{'kind': 'accept', 'label': 'Approve Studio S-1'}] and s['unexplained'] == []
    turn.finish(True, 'answered')
    cc.finish(True)
    s2 = hb_live.snapshot(conn, tele={'gpu': {'busy_pct': 80}, 'cpu': {}, 'ram': {}})
    assert {h['title'] for h in s2['history']} == {'APEX: MCB question', 'Backlog sweep'}
    assert s2['unexplained'] == [] or s2['unexplained'][0]['lane'] == 'gpu'


def test_busy_gpu_with_nothing_recorded_is_unexplained(conn, monkeypatch):
    _stubs(monkeypatch)
    s = hb_live.snapshot(conn, tele={'gpu': {'busy_pct': 75}, 'cpu': {}, 'ram': {}})
    assert s['unexplained'] == [{'lane': 'gpu', 'evidence': 'GPU 75% busy and no APEX run is recorded'}]


def test_a_task_seen_twice_shows_once(conn, monkeypatch):
    live.begin('apex', 'gpu', 'APEX: step', task_id='T-5')
    _stubs(monkeypatch, [{'task_id': 'T-5', 'task': 'step', 'members': [{'request_id': 1, 'role': 'APEX', 'model': 'apex', 'where': 'GPU',
                                                                         'now': 'run_tests -> PASS', 'steps': [{'at': '1', 'what': 'run_tests -> PASS'}]}]}])
    gpu = [l for l in hb_live.snapshot(conn, tele={'gpu': {}, 'cpu': {}, 'ram': {}})['lanes'] if l['id'] == 'gpu'][0]
    assert len(gpu['items']) == 1 and gpu['items'][0]['last_step'] == 'run_tests -> PASS'


def test_telemetry_reads_sysfs(tmp_path):
    dev = tmp_path / 'card1' / 'device'
    (dev / 'hwmon' / 'hwmon4').mkdir(parents=True)
    (dev / 'gpu_busy_percent').write_text('42\\n')
    (dev / 'mem_info_vram_used').write_text(str(8 * 2 ** 30))
    (dev / 'mem_info_vram_total').write_text(str(16 * 2 ** 30))
    (dev / 'hwmon' / 'hwmon4' / 'temp1_input').write_text('51000')
    t = hb_live.telemetry(root=str(tmp_path))
    assert t['gpu'] == {'busy_pct': 42.0, 'vram_used_gb': 8.0, 'vram_total_gb': 16.0, 'temp_c': 51.0} and t['ram']['total_gb'] > 0


def test_route_is_registered():
    assert "/api/peer/v1/hb/live" in (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1500)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("HB Live L2 (owner 20 Nov, docs/spec-hb-live-dashboard.md): core/hb_live.snapshot is the one read model - lanes "
                            "(GPU APEX, CPU Fred, CPU small, Online, HB, Admin, Claude Code, System) from hb_activity_log open runs, "
                            "hb_activity.chains (peer requests + background jobs) and running admin steps; telemetry from sysfs/proc; "
                            "Needs you (waiting_items); the master list (hb_queue.status = the clipboard) joined with what is live per task; "
                            "finished runs as history; a busy GPU with nothing recorded as unexplained. GET /api/peer/v1/hb/live (1.5 s cache). "
                            "88 ms on the live database."),
                 edits=[{'path': PB, 'old': "@peer_bridge_bp.route('/api/peer/v1/hb/queue',methods=['GET','POST'])\n", 'new': route}],
                 new_files={'core/hb_live.py': MODULE, 'tests/test_hb_live_l2_snapshot.py': test},
                 test={'tests': ['tests/test_hb_live_l2_snapshot.py', 'tests/test_hb_live_l1_activity_log.py', 'tests/test_practice_164_activity_route.py',
                                 'tests/test_practice_180_parked_tasks.py'], 'keyword': ''}, run=run)
print(out['verified'])
