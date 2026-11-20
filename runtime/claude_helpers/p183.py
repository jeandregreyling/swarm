"""Prepare Practice 183: backlog sweep - six old Bug steps fixed in one change set (stale references and stale tests)."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
edits = [
    # Bug: fred course paths - the module was renamed watchdog_deos -> watchdog_does
    {'path': 'docs/fred_course/08-finding-things.md', 'old': '`utils/watchdog_deos.py`', 'new': '`utils/watchdog_does.py`'},
    {'path': 'docs/fred_course/02-seven-and-watchdog.md', 'old': '(watchdog_deos_cycle)', 'new': '(watchdog_does_cycle)'},
    # Bug: model runtime gateway - fred-cpu:24b is now a registered direct model; the test is about the HTTP backup transport
    {'path': 'tests/test_model_runtime_gateway.py', 'old': '''    monkeypatch.setattr(gateway.requests, 'post', post)
    result = gateway.chat('fred-cpu:24b',''', 'new': '''    monkeypatch.setattr(gateway.requests, 'post', post)
    # Backlog sweep 20 Nov: Fred is a registered direct llama-server model now; this test is about the HTTP backup transport itself
    monkeypatch.setattr(gateway, '_is_registered_direct_model', lambda model: False)
    monkeypatch.setattr(gateway, '_seven_runtime_enabled', lambda: False)
    result = gateway.chat('fred-cpu:24b','''},
    # Bug: interest identity frontend - /api/auth/me returns {ok: true, user}; the stub left out ok
    {'path': 'tests/test_interest_identity_frontend.py', 'old': 'return {user};', 'new': 'return {ok: true, user};   // as /api/auth/me (login_bp)'},
    # Bug: tool approval - 'missing' used a new_text already in the file, so the deliberate ALREADY APPLIED answer came first
    {'path': 'tests/test_tool_approval.py', 'old': 'patch_proposal(store, repository, exact_old_text=text)',
     'new': 'patch_proposal(store, repository, exact_old_text=text, new_text="value = 3")   # a change not already in the file'},
    # Bug: tool approval / test isolation - frontend/services is importable only after something imported frontend.terminal
    {'path': 'tests/conftest.py', 'old': "import os\nimport tempfile\n", 'new': '''import os
import sys
import tempfile

# Backlog sweep 20 Nov: frontend/terminal.py puts frontend/ on sys.path so 'services' imports; tests that import chat.py alone
# failed with "No module named 'services'" unless another test had imported terminal.py first.
_FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend')
if _FRONTEND not in sys.path:
    sys.path.append(_FRONTEND)
'''},
    # Bug: hb task manager - Fred only takes over planned steps (owner 15 Nov); the two tests used a task with no step
    {'path': 'tests/test_hb_task_manager.py', 'old': "\n\ndef test_going_round_in_circles_hands_the_step_to_fred_before_jd", 'new': '''


def _planned(conn,task):
    """Backlog sweep 20 Nov: the task carries a planned Studio step with a spec - Fred only takes over those (owner 15 Nov)."""
    conn.execute("CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, order_idx REAL, created_at REAL, updated_at REAL, residual_risk TEXT)")
    conn.execute("INSERT OR IGNORE INTO project_steps VALUES('S-FED0000001','P-2AB8250A87','Practice F','Change x.\\\\nDone when: python -m pytest tests/test_x.py passes','todo','apex',1,0,0,NULL)")
    conn.execute("UPDATE hb_tasks SET step_id='S-FED0000001',project_id='P-2AB8250A87' WHERE task_id=?",(task['task_id'],))
    return hb_tasks.get(conn,task['task_id'])


def test_going_round_in_circles_hands_the_step_to_fred_before_jd'''},
    {'path': 'tests/test_hb_task_manager.py', 'old': """    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    for _ in range(manager.MAX_REPEATED_FAILURES):""", 'new': """    conn,p=flow;rid=owner(conn,'apex');task=_planned(conn,hb_tasks.for_request(conn,rid))
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    for _ in range(manager.MAX_REPEATED_FAILURES):"""},
    {'path': 'tests/test_hb_task_manager.py', 'old': """    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    assert manager.local_help(conn,task)=='submitted'""", 'new': """    conn,p=flow;rid=owner(conn,'apex');task=_planned(conn,hb_tasks.for_request(conn,rid))
    manager.register(conn,task,request_id=rid)
    assert manager.local_help(conn,task)=='submitted'"""},
    # Bug: hive android worker - the leader moved to another Tailscale address; check the form, not one IP
    {'path': 'tests/test_hive_android_worker_static.py', 'old': 'from pathlib import Path\n', 'new': 'import re\nfrom pathlib import Path\n'},
    {'path': 'tests/test_hive_android_worker_static.py', 'old': """    assert 'DEFAULT_LEADER = "http://100.87.66.45:5050"' in main""",
     'new': """    assert re.search(r'DEFAULT_LEADER = "http://[0-9.]+:5050"', main)   # the Tailscale address changes; the form does not"""},
    # Bug: seven direct runtime (part) - Seven's GGUF files left the repo; tests get stand-in files instead of this machine's disks
    {'path': 'tests/test_seven_direct_runtime.py', 'old': "from core.seven_llm.prompt_profiles import get_profile\n", 'new': '''from core.seven_llm.prompt_profiles import get_profile

import pytest


@pytest.fixture(autouse=True)
def _seven_models_on_disk(monkeypatch, tmp_path):
    """Backlog sweep 20 Nov: Seven's GGUF files left the repo (agents/seven/models no longer exists). These tests check the code,
    not this machine's disks, so each test gets small stand-in files at the registry's paths."""
    root = tmp_path / "agents" / "seven" / "models"
    (root / "small").mkdir(parents=True)
    paths = {"_SEVEN_DAILY_GGUF": root / "small" / "qwen2.5-0.5b-instruct-q4_k_m.gguf",
             "_SEVEN_Q8_GGUF": root / "seven-7b-q8_0.gguf", "_SEVEN_FP16_GGUF": root / "seven-7b-fp16.gguf"}
    for name, path in paths.items():
        path.write_bytes(b"GGUF" + bytes(64))
        monkeypatch.setattr(registry, name, str(path))
    monkeypatch.setattr(registry, "REGISTRY_PATH", str(tmp_path / "no-registry.yaml"))   # not this machine's registry file
    monkeypatch.setattr(registry, "_ollama_store_entries", lambda: [])                   # nor its Ollama store
    seven = registry._optional_defaults()
    names = {m.name for m in seven}
    monkeypatch.setattr(registry, "DEFAULTS", [m for m in registry.DEFAULTS if m.name not in names] + seven)
    registry.reload()
    yield root
    monkeypatch.undo()
    registry.reload()
'''},
]

S7 = 'tests/test_seven_direct_runtime.py::'
out = None


BM = 'core/capability_packs/bugfix.method.v1.json'
LESSON = ("Decide which side is out of date: the code or the test. Backlog sweep 20 Nov 2026: 6 of 8 stuck bugs were stale tests - a "
          "renamed file (watchdog_deos -> watchdog_does), an owner rule the test predates (Fred only takes over planned steps), a stub "
          "missing a field the real endpoint returns (ok: true), a deliberate newer answer (ALREADY APPLIED), or this machine's state "
          "(model files that left the repo, a changed IP). When the code changed on purpose (a Practice, an owner note, git log), update "
          "the test to the deliberate behaviour or make it independent of this machine (stand-in files, monkeypatch), and say so in the "
          "report - that is not weakening a test. Change the code only when it is the code that is wrong.")
edits += [   # the lesson for APEX: bugfix.method 1.1.0
    {'path': BM, 'old': '"version": "1.0.0",', 'new': '"version": "1.1.0",'},
    {'path': BM, 'old': '    "Write a test that fails now and will pass after the fix',
     'new': '    ' + __import__('json').dumps(LESSON) + ',\n    "Write a test that fails now and will pass after the fix'},
]
LESSON_TEST = '''"""Practice 183: the bug method teaches APEX to decide whether the code or the test is out of date."""
from core import hb_learning


def test_bugfix_method_has_the_stale_test_step():
    m = hb_learning.bugfix_method()
    assert 'Decide which side is out of date: the code or the test' in m
    assert 'that is not weakening a test' in m and 'never weaken a test' in m
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("Owner 20 Nov: clear the old bug backlog in one sweep (APEX got stuck on these around 16 Nov). Each was a stale "
                            "reference or a stale test, not a product bug: Fred's course named watchdog_deos.py (renamed watchdog_does.py); "
                            "the gateway test hit Fred's new direct llama-server path instead of the HTTP backup transport it is about; the "
                            "auth stub left out ok:true; a tool-approval case collided with the deliberate ALREADY APPLIED answer; "
                            "frontend/services was importable only after terminal.py had been imported (now in conftest); Fred only takes "
                            "over planned steps (owner 15 Nov) and two tests used a task without one; the Android leader IP moved; Seven's "
                            "GGUFs left the repo (stand-in files). Left for a spec: Seven runtime launch/gatekeeper tests, the Android "
                            "shared-chat contract."),
                 edits=edits, new_files={'tests/test_practice_183_sweep_lesson.py': LESSON_TEST},
                 test={'tests': ['tests/test_fred_course_paths.py', 'tests/test_model_runtime_gateway.py', 'tests/test_interest_identity_frontend.py',
                                 'tests/test_tool_approval.py', 'tests/test_hb_task_manager.py', 'tests/test_practice_183_sweep_lesson.py',
                                 'tests/test_practice_166_bugfix_method.py',
                                 'tests/test_hive_android_worker_static.py::test_hive_worker_supports_dynamic_join_deep_link',
                                 S7 + 'test_direct_registry_discovers_repo_local_seven_model', S7 + 'test_gateway_routes_registered_direct_model_by_name'],
                       'keyword': ''}, run=run)
print(out['verified'])
