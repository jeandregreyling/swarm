"""Prepare Practice 185: clean baseline - this week's Practices broke older tests; fix each on the right side (code or test)."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
edits = [
    # Practice 179 always added 'last' and read a column older hb_executions tables lack -> only when known, tolerate old tables (code)
    {'path': 'core/hb_live_activity.py', 'old': '''    last = None
    if not lines and {'hb_executions', 'hb_tasks'} <= tables:   # Practice 179: when idle, what ran last and when it finished
        row = conn.execute("SELECT e.agent, t.title, e.updated_at FROM hb_executions e JOIN hb_tasks t ON t.task_id=e.task_id "
                           "WHERE e.state!='running' ORDER BY e.updated_at DESC LIMIT 1").fetchone()
        if row:
            last = {'agent': row[0], 'title': str(row[1])[:90], 'at': row[2]}
    return {'running': bool(lines), 'lines': lines, 'last': last}''', 'new': '''    out = {'running': bool(lines), 'lines': lines}
    if not lines and {'hb_executions', 'hb_tasks'} <= tables:   # Practice 179: when idle, what ran last and when it finished
        try:                                                     # Practice 185: older tables have no updated_at - then no 'last'
            row = conn.execute("SELECT e.agent, t.title, e.updated_at FROM hb_executions e JOIN hb_tasks t ON t.task_id=e.task_id "
                               "WHERE e.state!='running' ORDER BY e.updated_at DESC LIMIT 1").fetchone()
        except Exception:
            row = None
        if row:
            out['last'] = {'agent': row[0], 'title': str(row[1])[:90], 'at': row[2]}
    return out'''},
    # Practice 179 used classList.add/remove; toggle(name, bool) does the same and works on every element (code)
    {'path': 'frontend/static/js/views/home-chat.js', 'old': "      if (!away) btn.classList.remove('fresh');",
     'new': "      if (!away) btn.classList.toggle('fresh', false);"},
    {'path': 'frontend/static/js/views/home-chat.js', 'old': "> 120) btn.classList.add('fresh');   // Practice 179",
     'new': "> 120) btn.classList.toggle('fresh', true);   // Practice 179"},
    {'path': 'tests/test_practice_179_arrow_and_idle.py', 'old': '''"btn.classList.add('fresh')" in js''', 'new': '''"btn.classList.toggle('fresh', true)" in js'''},
    # Practice 182's watcher timers kept Node alive, so the translator's Node tests timed out; unref() is Node-only (code)
    {'path': 'frontend/static/js/hb-translate-bubble.js', 'old': '''  setInterval(watchServer, 30000);
  setTimeout(watchServer, 1500);''', 'new': '''  const watchTimers = [setInterval(watchServer, 30000), setTimeout(watchServer, 1500)];
  watchTimers.forEach((t) => { if (t && typeof t.unref === 'function') t.unref(); });   // Practice 185: never keeps Node alive'''},
    # Practice 174 deliberately trims an over-budget batch instead of refusing it (test)
    {'path': 'tests/test_apex_read_tools.py', 'old': '''def test_call_limit_rejects_batch_before_any_read(repository, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Excessive batch executed"))
    content = envelope(*[("git_status", {})] * 13)
    with pytest.raises(RuntimeError, match="excessive"):
        run_apex_tools(lambda *_: (content, 1), [], lambda: True, lambda _: None, repository)''',
     'new': '''def test_call_limit_rejects_batch_before_any_read(repository, monkeypatch):
    """Practice 174 (20 Nov): an over-budget batch is trimmed to MAX_CALLS - never run in full - so a turn still ends with an answer."""
    from core.apex_tools import MAX_CALLS
    ran = []

    def call(*args):
        ran.append(args)
        if len(ran) > MAX_CALLS:
            pytest.fail("ran past the call budget")
        return "clean"
    monkeypatch.setattr(repository, "call", call)
    content = envelope(*[("git_status", {})] * 13)
    try:
        run_apex_tools(lambda *_: (content, 1), [], lambda: True, lambda _: None, repository)
    except RuntimeError:
        pass
    assert len(ran) <= MAX_CALLS'''},
    # Practice 183's fixture stubbed the Ollama store for every test, including the one about the store (test)
    {'path': 'tests/test_seven_direct_runtime.py',
     'old': '    monkeypatch.setattr(registry, "_ollama_store_entries", lambda: [])                   # nor its Ollama store\n', 'new': ''},
    # A full run imports old test modules that put the retired root on sys.path several times; remove every copy (test)
    {'path': 'tests/test_swarm_root_priority_files.py', 'old': '''    if retired_root in sys.path:
        sys.path.remove(retired_root)''', 'new': '''    # Practice 185: old test modules add it at import, several times in a full run - remove every copy (restored afterwards)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != retired_root])'''},
]


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1200)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("Full test run 20 Nov after the sweep: 20 failed, about 11 of them this week's Practices breaking older tests (each "
                            "change set ran only nearby tests). Fixed on the right side: hb_live_activity adds 'last' only when known and "
                            "tolerates older tables (179); the jump arrow uses classList.toggle (179); the translator watcher timers no longer "
                            "keep Node alive (182); the call-limit test follows Practice 174's deliberate trimming; the Seven fixture no longer "
                            "stubs the Ollama store (183); the whitelist test removes every copy of the retired root."),
                 edits=edits, new_files={},
                 test={'tests': ['tests/test_hb_live_activity.py', 'tests/test_home_chat_layout.py', 'tests/test_practice_179_arrow_and_idle.py',
                                 'tests/test_hb_translate_bubble_static.py', 'tests/test_practice_182_translator_on_demand.py',
                                 'tests/test_apex_read_tools.py', 'tests/test_practice_174_out_of_tool_calls.py',
                                 'tests/test_seven_direct_runtime.py::test_registry_serves_ollama_store_models_directly',
                                 'tests/test_seven_direct_runtime.py::test_direct_registry_discovers_repo_local_seven_model',
                                 'tests/test_swarm_root_priority_files.py', 'tests/test_hb_peer_control.py'], 'keyword': ''}, run=run)
print(out['verified'])
