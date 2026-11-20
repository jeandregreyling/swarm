"""Prepare Practice 191: HB emails JD when it stops to ask him; Fred's turns show as Fred (not APEX) in HB Live."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
TM = 'core/hb_task_manager.py'
AT = 'core/apex_tools.py'

email = '''EMAIL_GAP_S = 6 * 3600    # Practice 191: at most one email per task per 6 hours


def email_owner(conn, task, text, send=None, now=None):
    """Practice 191 (owner 20 Nov 2026: "the system should run autonomously for the most part unless something is really stuck, send me an
    email, you know I'm not going to be watching over you all as a hawk"): when HB stops and asks JD, the question also goes to his email
    (utils.config.nine_email, the owner address in config), in the background, at most once per task per EMAIL_GAP_S. Never under pytest
    unless a test passes `send`. Returns True when an email was started."""
    import os
    import threading
    now = now or time.time()
    if send is None and os.environ.get('PYTEST_CURRENT_TEST'):
        return False
    last = conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='owner_emailed'", (task['task_id'],)).fetchone()
    if last and last[0] and now - last[0] < EMAIL_GAP_S:
        return False
    hb_tasks.event(conn, task, 'hummingbird', 'owner_emailed', {'at': now})
    subject = 'HB needs you: ' + ' '.join(str(task.get('title') or task['task_id']).split())[:90]
    body = (str(text) + '\\n\\nOpen HB main chat to answer - the question is pinned under Needs you.\\n'
            '(HB sends at most one email per task every 6 hours.)')

    def go():
        try:
            (send or __import__('utils.config', fromlist=['nine_email']).nine_email)(subject, body)
        except Exception:
            pass
    threading.Thread(target=go, name='hb-email-owner', daemon=True).start()
    return True


def ask_owner(conn,task,what,options,kind='halt'):
'''

edits = [
    {'path': TM, 'old': "def ask_owner(conn,task,what,options,kind='halt'):\n", 'new': email},
    {'path': TM, 'old': "    hb_tasks.event(conn,task,'hummingbird','owner_question',{'text':text,'message_id':mid,'kind':kind})\n    return mid\n",
     'new': "    hb_tasks.event(conn,task,'hummingbird','owner_question',{'text':text,'message_id':mid,'kind':kind})\n"
            "    if kind!='plan':\n        try:\n            email_owner(conn,task,text)       # Practice 191: stuck work reaches JD by email\n"
            "        except Exception:\n            pass\n    return mid\n"},
    # Fred's turns run through the same tool loop: name the worker from the model actually routed, not always APEX
    {'path': AT, 'old': "        actor, lane, device, real = live.who('apex')\n    except Exception:\n        lane, device, real = 'gpu', None, None",
     'new': "        from core.apex_routing import active_model      # Practice 191: Fred's turns show as Fred on the CPU lane\n"
            "        actor, lane, device, real = live.who(active_model())\n    except Exception:\n        actor, lane, device, real = 'apex', 'gpu', None, None"},
    {'path': AT, 'old': "    with live.run('apex', lane or 'gpu', 'APEX: ' + (' '.join(question.split())[:110] or 'turn'), model=real, device=device,",
     'new': "    who_name = 'Fred' if actor == 'fred' else 'APEX'\n"
            "    with live.run(actor if actor in ('apex', 'fred') else 'apex', lane or 'gpu', who_name + ': ' + (' '.join(question.split())[:110] or 'turn'), model=real, device=device,"},
]

test = '''"""Practice 191: HB emails JD when it stops to ask him (once per task per 6 h); Fred's turns are Fred's in HB Live."""
import sqlite3

from core import hb_task_manager as tm
from core import hb_activity_log as live


def _conn():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, agent TEXT, kind TEXT, message_id INTEGER, request_id INTEGER, payload TEXT, created_at REAL)')
    return c


def test_stuck_question_is_emailed_once_per_gap(monkeypatch):
    sent = []
    events = []
    monkeypatch.setattr(tm.hb_tasks, 'event', lambda conn, task, agent, kind, payload, **kw: (events.append(kind), conn.execute(
        "INSERT INTO hb_task_events(task_id, agent, kind, payload, created_at) VALUES (?,?,?,?,?)", (task['task_id'], agent, kind, '{}', payload.get('at', 0)))))
    monkeypatch.setattr('threading.Thread', lambda target, **kw: type('T', (), {'start': lambda self: target()})())
    c, task = _conn(), {'task_id': 'T-1', 'title': 'Bug: seven direct runtime', 'step_id': 'S-1'}
    assert tm.email_owner(c, task, 'APEX is stuck', send=lambda s, b: sent.append((s, b)), now=1000)
    assert not tm.email_owner(c, task, 'again', send=lambda s, b: sent.append((s, b)), now=1000 + 60)
    assert tm.email_owner(c, task, 'still stuck', send=lambda s, b: sent.append((s, b)), now=1000 + tm.EMAIL_GAP_S + 1)
    assert [s for s, _ in sent] == ['HB needs you: Bug: seven direct runtime'] * 2 and 'Needs you' in sent[0][1]


def test_never_emails_from_tests_by_default():
    assert tm.email_owner(_conn(), {'task_id': 'T-2'}, 'x') is False


def test_fred_turn_is_logged_as_fred(monkeypatch, tmp_path):
    import json
    import core.apex_tools as t
    path = tmp_path / 'l.db'
    monkeypatch.setattr(live, 'FORCE', True)
    monkeypatch.setattr(live, '_connect', lambda: sqlite3.connect(path))
    monkeypatch.setattr('core.apex_routing.active_model', lambda: 'fred-cpu:24b')
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    turns = [json.dumps({'tool_calls': [], 'answer': 'Fred: fixed it.'})] * 3
    t.run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'fix the bug'}], lambda: True, lambda _r: None,
                     t.ReadOnlyRepository(tmp_path))
    row = sqlite3.connect(path).execute("SELECT actor, lane, text FROM hb_activity_log WHERE kind='start' AND parent IS NULL").fetchone()
    assert row == ('fred', 'cpu', 'Fred: fix the bug')
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1500)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("Owner 20 Nov: \"the system should run autonomously for the most part unless something is really stuck, send me an "
                            "email\". core/hb_task_manager.ask_owner (the one place HB stops and asks JD) also emails him via "
                            "utils.config.nine_email, in the background, at most once per task per 6 h, never from tests. And the HB Live "
                            "wrapper of run_apex_tools names the worker from the routed model, so Fred's turns show as Fred on the CPU lane."),
                 edits=edits, new_files={'tests/test_practice_191_email_and_fred.py': test},
                 test={'tests': ['tests/test_practice_191_email_and_fred.py', 'tests/test_hb_task_manager.py', 'tests/test_hb_live_l1_activity_log.py',
                                 'tests/test_hb_live_l2_snapshot.py'], 'keyword': ''}, run=run)
print(out['verified'])
