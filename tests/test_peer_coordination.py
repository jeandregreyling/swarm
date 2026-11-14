from contextlib import closing
from pathlib import Path
import sqlite3

import pytest
from core import peer_bridge as peers, peer_coordination as coordination, agent_identity

# These suites test HB after the owner's go-ahead. Since 11-12 Nov the owner's rules are: Continue off by default,
# online providers only when authorised, no automatic run without a definition of done. State them explicitly.
pytestmark = pytest.mark.usefixtures('owner_turned_continuation_on', 'online_providers_authorised', 'owner_defined_done')



@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_identity, 'STATE', tmp_path/'identities')
    monkeypatch.setattr(peers, 'HANDOFF_DELAY_S', 0)
    conn = sqlite3.connect(':memory:')
    conn.executescript('''CREATE TABLE conversations(id INTEGER PRIMARY KEY,title TEXT);
        INSERT INTO conversations VALUES (1,'Owner thread');
        CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id INTEGER,from_agent TEXT,to_agent TEXT,
        content TEXT,message_type TEXT,tokens_used INTEGER DEFAULT 0,created_at TEXT);''')
    peers.ensure_schema(conn)
    peers.issue_token(conn, 'codex-instructor')
    yield conn
    conn.close()


def test_failed_help_is_not_deduplicated_or_returned_to_worker(db):
    first = peers.request_help(db, 1, 'codex', 'Read step', 'Read failed')
    request = first['request_ids'][0]
    db.execute("UPDATE hb_peer_work SET state='failed',stage='Usage limit' WHERE request_id=?", (request,))
    second = peers.request_help(db, 1, 'codex', 'Read step', 'New request after failure')
    assert not second.get('deduplicated') and second['request_ids'] != [request]
    principal = {'id':'codex-instructor', 'scopes':{'peer.read'}}
    assert [r['id'] for r in peers.inbox(db, principal, pending_only=True)] == second['request_ids']
    # Failed receipts remain inspectable; not falsely acknowledged as delivered.
    assert db.execute('SELECT delivered_at FROM peer_messages WHERE id=?', (request,)).fetchone()[0] is None
    assert any(r['id'] == request for r in peers.inbox(db, principal))


def test_supervisor_starts_missing_worker_and_does_not_duplicate_live_worker(db):
    launches = []
    alive = [False]
    clock = [0]
    supervisor = coordination.Supervisor(launch=launches.append, alive=lambda _:alive[0], clock=lambda:clock[0])
    supervisor.tick(db)
    assert launches == ['codex-instructor']
    assert coordination.status(db)[0]['state'] == 'starting'
    clock[0] = 5
    supervisor.tick(db)
    assert len(launches) == 1
    alive[0] = True
    supervisor.tick(db)
    assert coordination.status(db)[0]['state'] == 'running' and len(launches) == 1


def test_supervisor_starts_gemini_with_a_fixed_no_tools_relay(db,monkeypatch):
    peers.issue_token(db,'gemini-advisor')
    folder=agent_identity.directory('gemini-advisor')
    (folder/'hb-pickup-boundary.json').write_text('{"after_request_id":614}')
    commands=[]
    monkeypatch.setattr(coordination.subprocess,'Popen',lambda command,**kwargs:commands.append(command))
    supervisor=coordination.Supervisor(alive=lambda agent:agent=='codex-instructor')
    supervisor.tick(db)
    assert len(commands)==1
    assert commands[0]==[coordination.sys.executable,str(coordination.ROOT/'scripts/hummingbird_gemini_peer.py'),'--after','614']
    states={r['agent']:r['state'] for r in coordination.status(db)}
    assert states['gemini-advisor']=='starting'


def test_startup_failure_is_bounded_and_request_gets_public_failure(db):
    request = peers.request_help(db, 1, 'codex', 'Need help', 'Evidence')['request_ids'][0]
    launches=[]; clock=[0]
    supervisor = coordination.Supervisor(launch=launches.append, alive=lambda _:False, clock=lambda:clock[0])
    for when in [0, 31, 62, 93, 124]:
        clock[0] = when
        supervisor.tick(db)
    assert len(launches) == 3
    assert coordination.status(db)[0]['state'] == 'unavailable'
    assert db.execute('SELECT state FROM hb_peer_work WHERE request_id=?', (request,)).fetchone()[0] == 'failed'
    messages=db.execute("SELECT content FROM messages WHERE from_agent='hummingbird'").fetchall()
    assert len(messages)==1 and str(request) in messages[0][0]


def test_disconnected_running_turn_requires_review_instead_of_reexecution(db):
    request = peers.request_help(db, 1, 'codex', 'Need help', 'Evidence')['request_ids'][0]
    db.execute("UPDATE hb_peer_work SET state='running' WHERE request_id=?", (request,))
    supervisor = coordination.Supervisor(launch=lambda _:None, alive=lambda _:False)
    supervisor.tick(db)
    assert db.execute('SELECT state FROM hb_peer_work WHERE request_id=?', (request,)).fetchone()[0] == 'needs_review'
    assert peers.inbox(db, {'id':'codex-instructor','scopes':{'peer.read'}}, pending_only=True) == []


def test_cutover_reconciles_old_failures_and_retires_unanswered_without_ack(db):
    failed = peers.request_help(db, 1, 'codex', 'Need help', 'Evidence')['request_ids'][0]
    folder=agent_identity.STATE/'codex-instructor';folder.mkdir(parents=True)
    with sqlite3.connect(folder/'hb-worker.sqlite') as worker:
        worker.execute('CREATE TABLE jobs(request_id INTEGER,state TEXT,error TEXT)')
        worker.execute("INSERT INTO jobs VALUES (?,'failed','usageLimitExceeded')", (failed,))
    # Simulate a second legacy request predating the duplicate guard.
    old = peers.enqueue(db, 1, 1, 'APEX asks Codex for help: old request', ['codex-instructor'], sender='apex')[0]
    coordination.retire_pending(db, old, 'Upgrade cutover; review old work')
    assert db.execute('SELECT state FROM hb_peer_work WHERE request_id=?', (failed,)).fetchone()[0] == 'failed'
    assert db.execute('SELECT state FROM hb_peer_work WHERE request_id=?', (old,)).fetchone()[0] == 'needs_review'
    assert db.execute('SELECT count(*) FROM peer_messages WHERE delivered_at IS NOT NULL').fetchone()[0] == 0
    new = peers.request_help(db, 1, 'codex', 'New help', 'New evidence')
    assert not new.get('deduplicated')
