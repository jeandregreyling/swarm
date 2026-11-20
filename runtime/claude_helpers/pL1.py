"""Prepare HB Live L1 (Practice 186): hb_activity_log + the gateway and APEX-turn hooks + hbrun.py for Claude Code."""
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
MODULE = Path('/tmp/claude-1000/-home-jd/12a48d48-c161-4f13-ab48-18ba6f3e4cde/scratchpad/hb_activity_log.py').read_text()

gateway_wrapper = '''def chat_via_gateway(model: str, messages: list[dict], **kwargs) -> tuple[str, int]:
    """HB Live L1 (owner 20 Nov 2026, docs/spec-hb-live-dashboard.md): every local model call is one entry in hb_activity_log - start
    and finish (or error) with the real model, its lane and device, how long it took and the tokens - inside the run that made it
    (an APEX turn, a Fred job) when there is one. The call itself is _chat_via_gateway_impl, unchanged. Logging never breaks a call."""
    from core import hb_activity_log as live
    try:
        actor, lane, device, real = live.who(model)
        parent = live.current()
        call = live.begin(actor, lane, f'model call: {real}', model=real, device=device,
                          purpose=(parent.base.get('purpose') if parent else None) or 'model call')
    except Exception:
        call = None
    try:
        content, tokens = _chat_via_gateway_impl(model, messages, **kwargs)
    except BaseException as exc:
        if call:
            call.finish(False, f'{type(exc).__name__}: {exc}'[:160])
        raise
    if call:
        failed = isinstance(content, str) and content.startswith('[local runtime error')
        call.finish(not failed, (content[:160] if failed else f'{int(tokens or 0)} tokens'))
    return content, tokens


def _chat_via_gateway_impl(
'''

apex_wrapper = '''def run_apex_tools(call_model, messages: list[dict], authorize, emit_receipt, *args, **kwargs) -> tuple[str, int, list[dict]]:
    """HB Live L1: one APEX turn (main chat or workflow) is one run in hb_activity_log on the GPU lane; its model calls and step lines
    (Practice 176) are recorded inside it. The turn itself is _run_apex_tools, unchanged."""
    from core import hb_activity_log as live
    question = next((str(m.get('content') or '') for m in reversed(messages or []) if m.get('role') == 'user'
                     and not str(m.get('content') or '').startswith(('BACKEND', 'HB note', 'HB task reference'))), '')
    try:
        actor, lane, device, real = live.who('apex')
    except Exception:
        lane, device, real = 'gpu', None, None
    task = step_id = None
    try:
        from core.agent_identity import CURRENT
        actor_ctx = CURRENT.get() or {}
        task, step_id = actor_ctx.get('task_id'), actor_ctx.get('step_id')
    except Exception:
        pass
    with live.run('apex', lane or 'gpu', 'APEX: ' + (' '.join(question.split())[:110] or 'turn'), model=real, device=device,
                  task_id=task, step_id=step_id, purpose='workflow step' if task else 'main-chat turn') as r:
        result = _run_apex_tools(call_model, messages, authorize, emit_receipt, *args, **kwargs)
        try:
            r.finish(True, f'answered - {len(result[2])} tool call(s)')
        except Exception:
            pass
        return result


def _run_apex_tools(call_model, messages: list[dict], authorize, emit_receipt,
'''

hbrun = '''"""Claude Code's own work in HB's activity log (HB Live L1): it shows in main chat's Claude Code lane like any other worker.

  python hbrun.py start "<title>" [--task T-..] [--step S-..]   -> prints the run id
  python hbrun.py step R-... "<line>"
  python hbrun.py finish R-... [ok|error] ["<line>"]
"""
import sys
import time
sys.path.insert(0, '/home/jd/swarm')
from core import hb_activity_log as live

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
if args[0] == 'start':
    title = args[1]
    task = args[args.index('--task') + 1] if '--task' in args else None
    step = args[args.index('--step') + 1] if '--step' in args else None
    r = live.begin('claude', 'claude-code', title, model='claude-code', device='online', task_id=task, step_id=step, purpose='Claude Code')
    print(r.run_id)
elif args[0] == 'step':
    live.write({'run_id': args[1], 'lane': 'claude-code', 'actor': 'claude', 'kind': 'step', 'text': args[2]})
elif args[0] == 'finish':
    ok = len(args) < 3 or args[2] != 'error'
    live.write({'run_id': args[1], 'lane': 'claude-code', 'actor': 'claude', 'kind': 'finish' if ok else 'error',
                'text': args[3] if len(args) > 3 else ('done' if ok else 'failed')})
'''

edits = [
    {'path': 'core/llm.py', 'old': "def chat_via_gateway(\n    model: str,\n    messages: list[dict],\n    *,\n",
     'new': gateway_wrapper + "    model: str,\n    messages: list[dict],\n    *,\n"},
    {'path': 'core/apex_tools.py', 'old': "def run_apex_tools(call_model, messages: list[dict], authorize, emit_receipt,\n",
     'new': apex_wrapper},
    {'path': 'core/apex_tools.py', 'old': '''        report_model_progress({'stage': 'step', 'text': str(text)[:200]})
    except Exception:
        pass
''', 'new': '''        report_model_progress({'stage': 'step', 'text': str(text)[:200]})
    except Exception:
        pass
    try:                                          # HB Live L1: the same line in the turn's run in hb_activity_log
        from core import hb_activity_log
        hb_activity_log.step(str(text)[:200], 'check' if str(text).startswith('HB ') else 'step')
    except Exception:
        pass
'''},
]

test = '''"""HB Live L1: every model call and every APEX turn is recorded in hb_activity_log; Claude Code's work too."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import core.apex_tools as t
from core import hb_activity_log as live
from core import llm

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(monkeypatch, tmp_path):
    path = tmp_path / 'live.db'
    monkeypatch.setattr(live, 'FORCE', True)
    monkeypatch.setattr(live, '_connect', lambda: sqlite3.connect(path))
    monkeypatch.setattr(live, 'who', lambda model: ('apex', 'gpu', 'ROCm', 'swift-qwen3.8-27b') if 'fred' not in str(model)
                        else ('fred', 'cpu', 'CPU', 'fred-cpu:24b'))
    return lambda: sqlite3.connect(path)


def test_gateway_call_is_logged_inside_the_turn(db, monkeypatch):
    monkeypatch.setattr(llm, '_chat_via_gateway_impl', lambda model, messages, **kw: ('hello', 7))
    with live.run('apex', 'gpu', 'APEX: MCB question', purpose='main-chat turn') as r:
        assert llm.chat_via_gateway('gpt-oss:20b', [{'role': 'user', 'content': 'hi'}]) == ('hello', 7)
        live.step('searching our notes: "MCB"')
    c = db()
    rows = c.execute('SELECT run_id, parent, actor, model, device, kind, text FROM hb_activity_log ORDER BY id').fetchall()
    kinds = [(r[0] == r_id, r[5]) for r_id in [r.run_id] for r in rows]
    assert [k for _, k in kinds] == ['start', 'start', 'finish', 'step', 'finish']
    call = [x for x in rows if x[0] != r.run_id]
    assert call[0][1] == r.run_id and call[0][3] == 'swift-qwen3.8-27b' and call[0][4] == 'ROCm' and '7 tokens' in call[-1][6]
    assert live.open_runs(c) == []
    done = live.finished(c)
    assert done[0]['run_id'] == r.run_id and done[0]['steps'] >= 1 and done[0]['outcome'] == 'ok'


def test_failed_call_is_an_error_entry(db, monkeypatch):
    monkeypatch.setattr(llm, '_chat_via_gateway_impl', lambda model, messages, **kw: ('[local runtime error: model busy]', 0))
    llm.chat_via_gateway('fred-cpu:24b', [])
    rows = db().execute("SELECT actor, lane, kind, text FROM hb_activity_log WHERE kind IN ('finish','error')").fetchall()
    assert rows == [('fred', 'cpu', 'error', rows[0][3])] and 'model busy' in rows[0][3]


def test_apex_turn_is_one_run_with_its_steps(db, monkeypatch, tmp_path):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    turns = [json.dumps({'tool_calls': [], 'answer': 'A list is mutable; a tuple is not.'})] * 3
    t.run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'list vs tuple?'}], lambda: True, lambda _r: None,
                     t.ReadOnlyRepository(tmp_path))
    c = db()
    start = c.execute("SELECT run_id, actor, lane, text, purpose FROM hb_activity_log WHERE kind='start'").fetchone()
    assert start[1:] == ('apex', 'gpu', 'APEX: list vs tuple?', 'main-chat turn')
    assert c.execute("SELECT COUNT(*) FROM hb_activity_log WHERE run_id=? AND kind='step'", (start[0],)).fetchone()[0] >= 1
    assert c.execute("SELECT kind FROM hb_activity_log WHERE run_id=? ORDER BY id DESC LIMIT 1", (start[0],)).fetchone()[0] == 'finish'


def test_logging_never_breaks_work(monkeypatch):
    monkeypatch.setattr(live, 'FORCE', True)
    monkeypatch.setattr(live, '_connect', lambda: (_ for _ in ()).throw(OSError('disk gone')))
    assert live.write({'kind': 'start'}) is False
    with live.run('hb', 'hb', 'x') as r:
        r.step('still fine')


def test_off_under_pytest_by_default():
    assert live.enabled() is False


def test_claude_code_runs(tmp_path):
    db_path = tmp_path / 'cc.db'
    env = {'SWARM_DB_PATH': str(db_path), 'PATH': '/usr/bin:/bin'}
    script = ROOT / 'runtime/claude_helpers/hbrun.py'
    if not script.exists():
        pytest.skip('hbrun.py lives in runtime/claude_helpers (not part of a fresh checkout)')
    rid = subprocess.run([sys.executable, str(script), 'start', 'Backlog sweep'], env=env, capture_output=True, text=True).stdout.strip()
    subprocess.run([sys.executable, str(script), 'step', rid, 'fixed 6 bugs'], env=env)
    subprocess.run([sys.executable, str(script), 'finish', rid, 'ok'], env=env)
    rows = sqlite3.connect(db_path).execute('SELECT lane, actor, kind FROM hb_activity_log WHERE run_id=? ORDER BY id', (rid,)).fetchall()
    assert rows == [('claude-code', 'claude', 'start'), ('claude-code', 'claude', 'step'), ('claude-code', 'claude', 'finish')]
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1500)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


Path('/home/jd/swarm/runtime/claude_helpers/hbrun.py').write_text(hbrun)
out = cs.prepare(STEP, why=("HB Live L1 (owner 20 Nov: \"everything should always be visible in main chat\"; docs/spec-hb-live-dashboard.md). "
                            "New core/hb_activity_log (append-only log of runs: start/step/call/finish/error, lane, actor, real model, "
                            "device, task). core/llm.chat_via_gateway is now a thin wrapper that logs every local model call around the "
                            "unchanged _chat_via_gateway_impl; core/apex_tools.run_apex_tools makes each APEX turn one run (wrapper around "
                            "the unchanged _run_apex_tools) and say_step writes its lines into that run. Claude Code logs its own work with "
                            "runtime/claude_helpers/hbrun.py. Off under pytest unless a test sets FORCE."),
                 edits=edits, new_files={'core/hb_activity_log.py': MODULE, 'tests/test_hb_live_l1_activity_log.py': test},
                 test={'tests': ['tests/test_hb_live_l1_activity_log.py', 'tests/test_practice_176_see_apex_work.py',
                                 'tests/test_practice_174_out_of_tool_calls.py', 'tests/test_practice_175_web_allowance.py',
                                 'tests/test_apex_read_tools.py', 'tests/test_apex_grounding.py', 'tests/test_model_runtime_gateway.py',
                                 'tests/test_chat_continuity.py', 'tests/test_practice_143_reasked_questions.py'], 'keyword': 'not authenticated_apex_web_dispatch and not sse_chat_events_reach and not explicit_codex_address_bypasses'}, run=run)
print(out['verified'])
