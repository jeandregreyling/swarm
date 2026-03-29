"""
test_triage_queue_dryrun.py — Dry run for email + Telegram triage queue
═══════════════════════════════════════════════════════════════════════════════
Tests queue intake → ticket create → stage routing → close pipeline
without sending any real emails or loading Ollama models.

Run: SIMULATE=true python3 /home/seven/swarm/tests/test_triage_queue_dryrun.py

All sends are intercepted by listener.py's SIMULATE mode.
All model calls are stubbed so no Ollama is required.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time

# Set simulate mode before any imports
os.environ['SIMULATE'] = 'true'

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/lib/email')
sys.path.insert(0, '/home/seven/swarm/lib/system')
sys.path.insert(0, '/home/seven/swarm/agents/ghost')

# ── Stub out Ollama so we don't load any models ────────────────────────────
import types

_fake_ollama = types.ModuleType('ollama')

def _stub_chat(model, messages, options=None):
    prompt = messages[-1]['content'][:60].lower()
    # Routing stub
    if 'needs_web' in prompt or 'decide how to handle' in prompt or 'route this' in prompt.lower():
        return {'message': {'content': 'NEEDS_WEB: no\nNEEDS_BROWSER: no\nNEEDS_SHELL: no\nAGENTS: llama\nMODE: consult\nIS_IDENTITY: no\nIS_SAP: no\nIS_SYSTEM: no\nREASON: simple factual question'}}
    # Tag stub
    if 'tags only' in prompt:
        return {'message': {'content': 'test, dryrun, queue'}}
    # Duck stub
    if 'sanity' in prompt or 'verify' in prompt or 'yes or no' in prompt or 'does this answer' in prompt:
        return {'message': {'content': 'YES'}}
    # Triage stub
    if 'decide whether this email' in prompt or 'answer\n' in prompt:
        return {'message': {'content': 'ANSWER\nGenuine test question.'}}
    # Default — generic answer
    return {'message': {'content': f'[STUB] Answer for: {prompt[:50]}'}}

_fake_ollama.chat = _stub_chat
sys.modules['ollama'] = _fake_ollama

# Stub internet search
_fake_internet = types.ModuleType('internet')
_fake_internet.search_web = lambda q: f'[STUB] Web results for: {q[:50]}'
sys.modules['internet'] = _fake_internet

# Stub logging_bridge
_fake_lb = types.ModuleType('logging_bridge')
_fake_lb.log_action = lambda *a, **kw: None
_fake_lb.log_agent_thinking = lambda *a, **kw: None
_fake_lb.log_ticket_lifecycle = lambda *a, **kw: None
_fake_lb.batch_commit = lambda *a, **kw: None
sys.modules['logging_bridge'] = _fake_lb

# Stub email_cleaner
_fake_ec = types.ModuleType('email_cleaner')
_fake_ec.filter_non_english = lambda t: t
_fake_ec.extract_subject_question = lambda s, b: b.strip() or s
_fake_ec.clean_subject = lambda s: s.replace('Re: ', '').strip()
sys.modules['email_cleaner'] = _fake_ec

# Stub monitor
_fake_mon = types.ModuleType('monitor')
_fake_mon.librarian_health_summary = lambda: 'RAM: 28GB free / 32GB | CPU: 10%'
sys.modules['monitor'] = _fake_mon

# Stub system_clock (use real time)
from datetime import datetime as _dt
_fake_sc_mod = types.ModuleType('system_clock')
class _FakeClock:
    def now(self): return _dt.now()
    def timestamp_compact(self): return _dt.now().strftime('%Y-%m-%d %H:%M:%S')
_fake_sc_mod.get_system_clock = lambda: _FakeClock()
_fake_sc_mod.get_timestamp = lambda: _dt.now().strftime('%Y-%m-%d %H:%M:%S')
sys.modules['system_clock'] = _fake_sc_mod

# ── Imports ────────────────────────────────────────────────────────────────
import logging
logging.basicConfig(level=logging.WARNING)

from database import get_connection, log_activity
from queue_manager import intake as queue_intake, get_queue_depth, mark_processing, mark_completed, is_queue_quiet
from ticket import create as ticket_create, librarian_close, set_routing as ticket_set_routing

PASS = '✓'
FAIL = '✗'
results = []

def check(label, condition, detail=''):
    status = PASS if condition else FAIL
    results.append((status, label, detail))
    print(f'  {status} {label}' + (f' — {detail}' if detail else ''))
    return condition


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Email queue intake
# ══════════════════════════════════════════════════════════════════════════════
print('\n[Test 1] Email queue intake')

q_depth_before = get_queue_depth()
queue_id, position, tags = queue_intake('ghost@test.com', 'Test dry run', 'What is the capital of Australia?')

check('intake() returns queue_id', isinstance(queue_id, int) and queue_id > 0, f'id={queue_id}')
check('intake() returns position >= 1', position >= 1, f'pos={position}')
check('queue depth increased by 1', get_queue_depth() == q_depth_before + 1, f'depth={get_queue_depth()}')

# Verify queue row is in DB
conn = get_connection()
row = conn.execute("SELECT * FROM queue WHERE id=?", (queue_id,)).fetchone()
conn.close()
check('queue row exists in DB', row is not None)
check('queue status = queued', row and row['status'] == 'queued', f'status={row["status"] if row else "N/A"}')


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Ticket creation (Bug 1 & 2 regression)
# ══════════════════════════════════════════════════════════════════════════════
print('\n[Test 2] Ticket creation (regression: no unexpected kwargs)')

ticket_number = f'TEST-DRYRUN-{int(time.time())}'
try:
    ticket_create(ticket_number, 'ghost@test.com', 'What is the capital of Australia?',
                  tags=tags, queue_id=queue_id, email_message_id='<test@dryrun>')
    check('ticket_create() accepts correct kwargs only', True)
except TypeError as e:
    check('ticket_create() accepts correct kwargs only', False, str(e))

conn = get_connection()
trow = conn.execute("SELECT * FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
conn.close()
check('ticket row exists in DB', trow is not None)
check('ticket status = open', trow and trow['status'] == 'open', f'status={trow["status"] if trow else "N/A"}')


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Queue lifecycle: processing → completed
# ══════════════════════════════════════════════════════════════════════════════
print('\n[Test 3] Queue lifecycle: processing → completed')

mark_processing(queue_id)
conn = get_connection()
row = conn.execute("SELECT * FROM queue WHERE id=?", (queue_id,)).fetchone()
conn.close()
check('mark_processing() sets status=processing', row and row['status'] == 'processing', f'status={row["status"] if row else "N/A"}')

# Simulate routing decision
routing = {'needs_web': False, 'agents': 'llama', 'mode': 'consult',
           'is_identity': False, 'is_sap': False, 'is_system': False}
try:
    ticket_set_routing(ticket_number, routing)
    check('ticket_set_routing() works', True)
except Exception as e:
    check('ticket_set_routing() works', False, str(e))

# Librarian close (Duck runs inside, uses stubbed ollama)
try:
    librarian_close(ticket_number, 'What is the capital of Australia?',
                    'Canberra is the capital of Australia.',
                    queue_id=queue_id, sender_email='ghost@test.com')
    check('librarian_close() completes without error', True)
except Exception as e:
    check('librarian_close() completes without error', False, str(e))

conn = get_connection()
trow = conn.execute("SELECT * FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
qrow = conn.execute("SELECT * FROM queue WHERE id=?", (queue_id,)).fetchone()
conn.close()
check('ticket closed', trow and trow['status'] == 'closed', f'status={trow["status"] if trow else "N/A"}')
check('queue entry completed', qrow and qrow['status'] == 'completed', f'status={qrow["status"] if qrow else "N/A"}')


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Snooze datetime import (Bug 3 regression)
# ══════════════════════════════════════════════════════════════════════════════
print('\n[Test 4] _parse_snooze_time datetime import (regression)')

# Import from listener — triggers the datetime import path
try:
    from listener import _parse_snooze_time
    r1 = _parse_snooze_time('30m')
    r2 = _parse_snooze_time('2h')
    r3 = _parse_snooze_time('2026-04-01')
    r4 = _parse_snooze_time('2026-04-01 09:00')
    check('_parse_snooze_time("30m") parses', r1 is not None, str(r1))
    check('_parse_snooze_time("2h") parses', r2 is not None, str(r2))
    check('_parse_snooze_time("2026-04-01") parses', r3 is not None, str(r3))
    check('_parse_snooze_time("2026-04-01 09:00") parses', r4 is not None, str(r4))
except Exception as e:
    check('_parse_snooze_time imports and runs', False, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 — Telegram queue intake (same pipeline, telegram: key)
# ══════════════════════════════════════════════════════════════════════════════
print('\n[Test 5] Telegram queue intake (telegram:<chat_id> sender key)')

tg_sender = 'telegram:987654321'
tg_q_id, tg_pos, tg_tags = queue_intake(tg_sender, 'Telegram: testuser', 'Is Python faster than Java?')
check('Telegram intake returns queue_id', isinstance(tg_q_id, int) and tg_q_id > 0, f'id={tg_q_id}')

conn = get_connection()
tg_row = conn.execute("SELECT * FROM queue WHERE id=?", (tg_q_id,)).fetchone()
conn.close()
check('Telegram queue row from_addr = telegram:<chat_id>', tg_row and tg_row['from_addr'] == tg_sender,
      f'from_addr={tg_row["from_addr"] if tg_row else "N/A"}')

# Ticket + close
tg_ticket = f'TG-DRYRUN-{int(time.time())}'
ticket_create(tg_ticket, tg_sender, 'Is Python faster than Java?', tags=tg_tags, queue_id=tg_q_id)
mark_processing(tg_q_id)
librarian_close(tg_ticket, 'Is Python faster than Java?', 'It depends on the use case.',
                queue_id=tg_q_id, sender_email=tg_sender)

conn = get_connection()
tg_trow = conn.execute("SELECT * FROM tickets WHERE ticket_number=?", (tg_ticket,)).fetchone()
tg_qrow = conn.execute("SELECT * FROM queue WHERE id=?", (tg_q_id,)).fetchone()
conn.close()
check('Telegram ticket closed', tg_trow and tg_trow['status'] == 'closed')
check('Telegram queue entry completed', tg_qrow and tg_qrow['status'] == 'completed')


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6 — is_queue_quiet() works correctly
# ══════════════════════════════════════════════════════════════════════════════
print('\n[Test 6] is_queue_quiet() — queue depth and quiet state')

depth = get_queue_depth()
check('get_queue_depth() returns int >= 0', isinstance(depth, int) and depth >= 0, f'depth={depth}')

quiet = is_queue_quiet()
check('is_queue_quiet() returns bool', isinstance(quiet, bool), f'quiet={quiet}')


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7 — URGENT priority (jumps queue)
# ══════════════════════════════════════════════════════════════════════════════
print('\n[Test 7] URGENT priority intake')

# Add a regular item first
_, normal_pos, _ = queue_intake('user@test.com', 'Normal question', 'What time is it?', priority=5)
# Now add urgent — should get position 1
_, urgent_pos, _ = queue_intake('ghost@test.com', 'URGENT: production down', 'Server is down now!', priority=1)
check('URGENT priority gives position 1', urgent_pos == 1, f'pos={urgent_pos}')


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print('\n' + '═' * 60)
passed = sum(1 for s, _, _ in results if s == PASS)
failed = sum(1 for s, _, _ in results if s == FAIL)
print(f'Results: {passed} passed, {failed} failed out of {len(results)} checks')

if failed == 0:
    print('\n✓ Triage queue dry run — ALL CHECKS PASSED')
    print('  Email and Telegram queue pipelines are operational.')
else:
    print(f'\n✗ {failed} check(s) failed — review output above')
    for s, label, detail in results:
        if s == FAIL:
            print(f'  FAIL: {label}' + (f' — {detail}' if detail else ''))

# Log activity in DB
log_activity('test', 'dryrun_complete', f'triage_queue: {passed}/{len(results)} passed')
print('\n[Dry run logged to activity_log]')
