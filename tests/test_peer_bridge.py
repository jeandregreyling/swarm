import importlib
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'frontend')]

from core import peer_bridge as peers  # noqa: E402

CHAT_SCHEMA = """
CREATE TABLE conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, source TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')), sender TEXT DEFAULT '');
CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL,
    from_agent TEXT NOT NULL, to_agent TEXT, content TEXT NOT NULL, message_type TEXT DEFAULT 'chat',
    created_at TEXT DEFAULT (datetime('now')), tokens_used INTEGER DEFAULT 0);
"""


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'peer.db'
    conn = sqlite3.connect(path)
    conn.executescript(CHAT_SCHEMA)
    peers.ensure_schema(conn)
    conn.execute("INSERT INTO conversations (title, source) VALUES ('t', 'terminal-ui')")
    conn.commit()
    conn.close()
    return path


def _conn(path):
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def test_tokens_are_hashed_scoped_and_rotated(db):
    conn = _conn(db)
    first = peers.issue_token(conn, 'copilot-instructor')
    second = peers.issue_token(conn, 'copilot-instructor')
    stored = [row[0] for row in conn.execute('SELECT token_sha256 FROM service_tokens')]
    assert first not in stored and second not in stored
    assert peers.authenticate(conn, first) is None
    principal = peers.authenticate(conn, second)
    assert principal['id'] == 'copilot-instructor'
    assert not any(scope.startswith('peer.relay:') for scope in principal['scopes'])
    assert peers.authenticate(conn, 'hbp_forged') is None
    peers.set_enabled(conn, 'copilot-instructor', False, 'ghost')
    assert peers.authenticate(conn, second) is None


def test_mentions_are_whole_word_and_deduplicated():
    assert peers.mentioned_peers('@instructor and @Gemini, also @copilot') == ['copilot-instructor', 'gemini-advisor']
    assert peers.mentioned_peers('mail me at me@gemini.com or @instructors') == []


def test_round_trip_relay_and_memory_pool(db):
    conn = _conn(db)
    instructor = peers.authenticate(conn, peers.issue_token(conn, 'copilot-instructor'))
    gemini = peers.authenticate(conn, peers.issue_token(conn, 'gemini-advisor'))
    ids = peers.enqueue(conn, 1, 1, 'hello both', ['copilot-instructor', 'gemini-advisor'], sender='ghost')
    inbox = peers.inbox(conn, instructor)
    assert [m['id'] for m in inbox] == [ids[0]]
    assert [m['id'] for m in peers.inbox(conn, gemini)] == [ids[1]]
    assert peers.acknowledge(conn, instructor, ids) == 1
    with pytest.raises(peers.PeerError):
        peers.post(conn, instructor, 1, 'forged relay', 'gemini-advisor')
    reply = peers.post(conn, gemini, 1, 'relayed answer')
    assert reply['from_agent'] == 'gemini-advisor'
    with pytest.raises(peers.PeerError) as exc:
        peers.post(conn, gemini, 1, 'impersonation', 'copilot-instructor')
    assert exc.value.status == 403
    with pytest.raises(peers.PeerError):
        peers.post(conn, instructor, 99, 'uninvited thread')
    kinds = {row[0] for row in conn.execute("SELECT kind FROM service_memory WHERE principal_id='gemini-advisor'")}
    assert {'inbound', 'outbound', 'audit'} <= kinds
    assert peers.thread(conn, instructor, 1)[-1]['content'] == 'relayed answer'
    assert 'hbp_' not in str(peers.audit(conn))


def test_disabled_principal_cannot_receive(db):
    conn = _conn(db)
    with pytest.raises(peers.PeerError) as exc:
        peers.enqueue(conn, 1, 1, 'hello', ['gemini-advisor'])
    assert exc.value.status == 409


def test_disabled_advisor_cannot_be_read_or_posted_through_relay(db):
    conn = _conn(db)
    instructor = peers.authenticate(conn, peers.issue_token(conn, 'copilot-instructor'))
    peers.set_enabled(conn, 'gemini-advisor', True, 'ghost')
    queued = _operator_says(conn, '@gemini check', ['gemini-advisor'])
    assert peers.inbox(conn, instructor) == []
    peers.set_enabled(conn, 'gemini-advisor', False, 'ghost')
    assert peers.inbox(conn, instructor) == []
    before = conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    with pytest.raises(peers.PeerError) as exc:
        peers.post(conn, instructor, 1, 'late relay', 'gemini-advisor')
    assert exc.value.status == 403
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == before


def test_disabled_recipient_does_not_discard_other_peer_reply(db):
    conn = _conn(db)
    instructor = peers.authenticate(conn, peers.issue_token(conn, 'apex'))
    _operator_says(conn, '@apex check', ['apex'])
    result = peers.post(conn, instructor, 1, 'review complete; question for @gemini')
    assert result['handoff']['queued'] == []
    assert result['handoff']['refused'] == ['gemini-advisor']
    assert conn.execute('SELECT content FROM messages WHERE id=?', (result['message_id'],)).fetchone()[0].startswith('review complete')
    assert any('not enabled' in row[0] for row in conn.execute(
        "SELECT content FROM service_memory WHERE kind='audit'"))


@pytest.fixture
def client(db, monkeypatch):
    bridge = importlib.import_module('frontend.blueprints.peer_bridge')
    monkeypatch.setattr(bridge, 'get_connection', lambda: _conn(db))
    published = []
    monkeypatch.setattr(bridge, '_publish', lambda *a, **k: published.append(a))
    app = Flask(__name__)
    app.register_blueprint(bridge.peer_bridge_bp)
    conn = _conn(db)
    token = peers.issue_token(conn, 'copilot-instructor')
    conn.commit()
    conn.close()
    return app.test_client(), token, bridge, published


def test_routes_require_loopback_and_token(client):
    http, token, _, _ = client
    assert http.get('/api/peer/v1/whoami', environ_base={'REMOTE_ADDR': '127.0.0.1'}).status_code == 401
    remote = http.get('/api/peer/v1/whoami', headers={'Authorization': f'Bearer {token}'},
                      environ_base={'REMOTE_ADDR': '192.168.1.5'})
    assert remote.status_code == 403
    ok = http.get('/api/peer/v1/whoami', headers={'Authorization': f'Bearer {token}'},
                  environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert ok.get_json()['principal'] == 'copilot-instructor'


def test_operator_dispatch_then_peer_reply(client, monkeypatch):
    http, token, bridge, published = client
    app = Flask(__name__)
    monkeypatch.setattr(bridge, 'get_current_user', lambda: {'username': 'ghost', 'role': 'owner'})
    with app.test_request_context():
        response = bridge.dispatch_operator_message({'conversation_id': 1}, '@instructor ping', ['copilot-instructor'])
    body = response.get_json()
    assert body['ok'] and body['conversation_id'] == 1 and body['mode'] == 'peer'
    assert body['peer_statuses'][0]['status'] == 'queued'
    assert body['peer_statuses'][0]['agent'] == 'copilot-instructor'
    assert 'waiting' in body['peer_statuses'][0]['stage'].lower()
    auth = {'Authorization': f'Bearer {token}'}
    loop = {'REMOTE_ADDR': '127.0.0.1'}
    inbox = http.get('/api/peer/v1/inbox?after=0', headers=auth, environ_base=loop).get_json()['messages']
    assert inbox[0]['body'] == '@instructor ping'
    posted = http.post('/api/peer/v1/messages', json={'conversation_id': 1, 'text': 'pong'},
                       headers=auth, environ_base=loop)
    assert posted.status_code == 201
    assert published and published[-1][1] == 'copilot-instructor'
    ack = http.post('/api/peer/v1/inbox/ack', json={'ids': [inbox[0]['id']]}, headers=auth, environ_base=loop)
    assert ack.get_json()['acknowledged'] == 1


def test_http_plain_reply_is_correlated_and_returned_to_apex(client,db):
    http,token,_,_=client
    with _conn(db) as conn:
        apex_token=peers.issue_token(conn,'apex')
        request_id=_operator_says(conn,'@instructor review this file list',['copilot-instructor'])[0]
    headers={'Authorization':f'Bearer {token}'};loop={'REMOTE_ADDR':'127.0.0.1'}
    first=http.post('/api/peer/v1/messages',headers=headers,environ_base=loop,json={
        'conversation_id':1,'text':'First part of the review','reply_to_request_id':request_id,'route_reply':False})
    assert first.status_code==201 and first.get_json()['handoff']['queued']==[]
    response=http.post('/api/peer/v1/messages',headers=headers,environ_base=loop,json={
        'conversation_id':1,'text':'The reviewed files are pending.','reply_to_request_id':request_id})
    assert response.status_code==201,response.get_json()
    routed=response.get_json()['handoff']['queued']
    assert len(routed)==1
    with _conn(db) as conn:
        row=conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(routed[0],)).fetchone()
        assert row[0]=='apex'
        from core import peer_turns
        assert peer_turns.route(conn,routed[0])['parent_request_id']==request_id
        assert peer_turns.current(conn,1)['turns']==2
    wrong=http.post('/api/peer/v1/messages',headers={'Authorization':f'Bearer {apex_token}'},environ_base=loop,json={
        'conversation_id':1,'text':'Forged reply','reply_to_request_id':request_id})
    assert wrong.status_code==403
    malformed=http.post('/api/peer/v1/messages',headers=headers,environ_base=loop,json={
        'conversation_id':1,'text':'Bad outcome','outcome':[]})
    assert malformed.status_code==400


def test_non_owner_cannot_address_peers(client, monkeypatch):
    _, _, bridge, _ = client
    monkeypatch.setattr(bridge, 'get_current_user', lambda: {'username': 'jeandre', 'role': 'viewer'})
    with Flask(__name__).test_request_context():
        response, status = bridge.dispatch_operator_message({}, '@instructor hi', ['copilot-instructor'])
    assert status == 403


def test_live_activity_is_owner_only_thread_scoped_and_read_only(client, db, monkeypatch):
    http, token, _, _ = client
    auth = importlib.import_module('services.auth')
    monkeypatch.setattr(auth, 'get_current_user', lambda: None)
    url = '/api/peer/v1/conversations/1/activity'
    assert http.get(url).status_code == 403
    monkeypatch.setattr(auth, 'get_current_user', lambda: {'username': 'ghost', 'role': 'owner'})
    calls = []
    from core import apex_studio
    monkeypatch.setattr(apex_studio, 'read_task_board', lambda *a, **kw:
                        calls.append((a, kw)) or {'tasks': [], 'total': 0})
    from core import hummingbird_status
    monkeypatch.setattr(hummingbird_status, 'runtime_stack_status', lambda: {
        'apex': {'state': 'online', 'model': 'qwen2.5:14b-instruct'},
        'archive': {'state': 'downloading'}, 'observed_at': 1000,
    })
    with _conn(db) as conn:
        peers.set_enabled(conn, 'gemini-advisor', True, 'ghost')
        peers.enqueue(conn, 1, 1, 'in this room', ['gemini-advisor'])
        conn.execute("INSERT INTO conversations (id,title) VALUES (2,'other')")
        peers.enqueue(conn, 2, 2, 'another room', ['gemini-advisor'])
        conn.execute("INSERT INTO messages (conversation_id,from_agent,content) VALUES (1,'apex','here')")
        conn.execute("INSERT INTO messages (conversation_id,from_agent,content) VALUES (2,'apex','private elsewhere')")
    data = http.get(url).get_json()
    assert data['ok'] and data['conversation_id'] == 1
    people = {p['id']: p for p in data['participants']}
    assert people['apex']['latest']['excerpt'] == 'here'
    assert people['gemini-advisor']['queued_for_delivery'] == 1
    assert data['runtime']['apex']['model'] == 'qwen2.5:14b-instruct'
    assert data['runtime']['archive']['state'] == 'downloading'
    with _conn(db) as conn:
        expected_principals = {row[0] for row in conn.execute('SELECT id FROM service_principals')}
    assert {agent['id'] for agent in data['runtime']['agents']} == expected_principals | {'apex'}
    assert 'private elsewhere' not in str(data) and token not in str(data)
    assert calls == [((1, 'ghost'), {'offset': 0, 'revision': None})]
    assert http.get('/api/peer/v1/conversations/99/activity').status_code == 404
    assert http.get(url + '?offset=-1').status_code == 400
    assert http.get(url, headers={'Authorization': f'Bearer {token}'}).status_code == 403


def test_live_activity_reports_broken_task_evidence(client, monkeypatch):
    http, _, _, _ = client
    auth = importlib.import_module('services.auth')
    monkeypatch.setattr(auth, 'get_current_user', lambda: {'username': 'ghost', 'role': 'owner'})
    from core import apex_studio
    def broken(*args, **kwargs):
        raise RuntimeError('Studio snapshot checksum mismatch')
    monkeypatch.setattr(apex_studio, 'read_task_board', broken)
    response = http.get('/api/peer/v1/conversations/1/activity')
    assert response.status_code == 503
    assert response.get_json()['ok'] is False


def test_service_credentials_never_reach_legacy_or_owner_routes(client, monkeypatch):
    http, token, bridge, _ = client
    reached = []
    http.application.add_url_rule('/legacy-test', 'legacy_test', lambda: reached.append(True) or 'unsafe')
    monkeypatch.setattr(bridge, 'get_current_user', lambda: {'username': 'ghost', 'role': 'owner'})
    headers = {'Authorization': f'Bearer {token}'}
    for route in ('/legacy-test', '/api/peer/v1/principals'):
        response = http.get(route, headers=headers, environ_base={'REMOTE_ADDR': '127.0.0.1'})
        assert response.status_code == 403
        assert 'dedicated peer endpoints' in response.get_json()['error']
    assert reached == []
    assert http.get('/legacy-test').status_code == 200


def _operator_says(conn, text, recipients):
    cur = conn.execute("INSERT INTO messages (conversation_id, from_agent, to_agent, content) VALUES (1, 'user', ?, ?)",
                       (recipients[0], text))
    return peers.enqueue(conn, 1, cur.lastrowid, text, recipients, sender='ghost')


def test_apex_handoffs_are_paced_and_queue_a_decision_at_the_round_boundary(db, monkeypatch):
    monkeypatch.setattr(peers, 'MAX_PEER_CHAIN', 3)
    conn = _conn(db)
    clock = [1000.0]
    monkeypatch.setattr(peers.time, 'time', lambda: clock[0])
    instructor = peers.authenticate(conn, peers.issue_token(conn, 'copilot-instructor'))
    apex = peers.authenticate(conn, peers.issue_token(conn, 'apex'))
    first = _operator_says(conn, '@apex start; @instructor review', ['apex'])
    turn1 = peers.post(conn, apex, 1, 'over to you @instructor')
    assert turn1['handoff']['queued'] and not turn1['handoff']['locked']
    assert peers.inbox(conn, instructor) == []
    clock[0] += peers.HANDOFF_DELAY_S
    handoff = peers.inbox(conn, instructor)
    assert [m['recipient'] for m in handoff] == ['copilot-instructor']
    assert handoff[0]['sender'] == 'apex'
    turn2 = peers.post(conn, instructor, 1, 'back to @apex')
    assert turn2['handoff']['queued'] and turn2['handoff']['chain'] == 3
    turn3 = peers.post(conn, apex, 1, 'again @instructor')
    assert turn3['handoff']['queued'] and not turn3['handoff']['locked']
    from core import peer_turns
    assert peer_turns.route(conn,turn3['handoff']['queued'][0])['kind']=='decision'
    _operator_says(conn, '@apex carry on; @instructor review', ['apex'])
    resumed = peers.post(conn, apex, 1, 'resuming with @instructor')
    assert resumed['handoff']['queued'] and resumed['handoff']['chain'] == 2


def test_self_mentions_do_not_handoff_and_thread_is_pruned(db):
    conn = _conn(db)
    instructor = peers.authenticate(conn, peers.issue_token(conn, 'copilot-instructor'))
    _operator_says(conn, '@instructor hi', ['copilot-instructor'])
    assert peers.post(conn, instructor, 1, 'I am @instructor')['handoff'] == {'queued': [], 'locked': False}
    peers.post(conn, instructor, 1, 'x' * (peers.THREAD_EXCERPT + 50))
    messages = peers.thread(conn, instructor, 1)
    assert len(messages) <= peers.THREAD_LIMIT
    assert messages[-1]['content'].endswith('…[truncated]')


def test_parse_dispatch_requires_strict_lines_outside_fences():
    text = '\n'.join([
        'Plan done.',
        '[DISPATCH: @instructor] verify receipt 42',
        '```',
        '[DISPATCH: @gemini] ignored inside a fence',
        '```',
        'inline [DISPATCH: @gemini] is not a line',
        '[DISPATCH: @gemini]',
        '  [DISPATCH: @gemini] choose the queue design  ',
    ])
    assert peers.parse_dispatch(text) == [
        ('copilot-instructor', 'verify receipt 42'),
        ('gemini-advisor', 'choose the queue design'),
    ]
    assert peers.parse_dispatch('[DISPATCH: @fred] nope') == []


def _apex_says(conn, text):
    cur = conn.execute("INSERT INTO messages (conversation_id, from_agent, to_agent, content) VALUES (1, 'apex', 'user', ?)",
                       (text,))
    return cur.lastrowid


def test_apex_dispatch_is_paced_capped_and_audited(db, monkeypatch):
    conn = _conn(db)
    clock = [2000.0]
    monkeypatch.setattr(peers.time, 'time', lambda: clock[0])
    instructor = peers.authenticate(conn, peers.issue_token(conn, 'copilot-instructor'))
    gemini = peers.authenticate(conn, peers.issue_token(conn, 'gemini-advisor'))
    conn.execute("INSERT INTO messages (conversation_id, from_agent, to_agent, content) VALUES (1, 'user', 'apex', '@instructor @gemini review')")
    text = '\n'.join(['Answer.', '[DISPATCH: @instructor] check the diff',
                      '[DISPATCH: @gemini] pick a schema', '[DISPATCH: @instructor] third is ignored'])
    message_id = _apex_says(conn, text)

    result = peers.dispatch_from_agent(conn, 1, message_id, 'apex', text)
    assert len(result['queued']) == 2 and result['chain'] == 1 and not result['locked']
    assert peers.inbox(conn, instructor) == []
    clock[0] += peers.HANDOFF_DELAY_S
    delivered = peers.inbox(conn, instructor) + peers.inbox(conn, gemini)
    assert [(m['sender'], m['recipient']) for m in delivered] == [
        ('apex', 'copilot-instructor'), ('apex', 'gemini-advisor')]
    assert delivered[0]['body'] == f'[APEX dispatch, message {message_id}] check the diff'
    audit = conn.execute("SELECT content FROM service_memory WHERE kind='audit'").fetchall()
    assert any('more than 2' in row[0] for row in audit)
    assert peers.post(conn, instructor, 1, 'diff verified')['message_id']


def test_apex_dispatch_respects_disable_without_counting_chat_as_handoffs(db, monkeypatch):
    monkeypatch.setattr(peers, "MAX_PEER_CHAIN", 3)
    conn = _conn(db)
    conn.execute("INSERT INTO messages (conversation_id, from_agent, to_agent, content) VALUES (1, 'user', 'apex', 'go')")
    first = _apex_says(conn, '[DISPATCH: @gemini] advise')
    refused = peers.dispatch_from_agent(conn, 1, first, 'apex', '[DISPATCH: @gemini] advise')
    assert refused['queued'] == [] and refused['refused'] == ['gemini-advisor']

    _apex_says(conn, 'two')
    third = _apex_says(conn, '[DISPATCH: @instructor] three')
    refused = peers.dispatch_from_agent(conn, 1, third, 'apex', '[DISPATCH: @instructor] three')
    assert refused == {'queued': [], 'locked': False, 'chain': 0, 'refused':['copilot-instructor']}
    assert peers.dispatch_from_agent(conn, 1, third, 'apex', 'no routing here') == {'queued': [], 'locked': False}


def test_chat_hook_dispatches_latest_apex_reply(db, monkeypatch):
    chat = importlib.import_module('frontend.blueprints.chat')
    monkeypatch.setattr(chat, 'get_connection', lambda: _conn(db))
    conn = _conn(db)
    peers.set_enabled(conn, 'copilot-instructor', True, 'ghost')
    conn.execute("INSERT INTO messages (conversation_id, from_agent, to_agent, content) VALUES (1, 'user', 'apex', '@instructor @gemini review')")
    text = 'Done.\n[DISPATCH: @instructor] review receipt 7'
    message_id = _apex_says(conn, text)
    conn.commit()
    conn.close()

    result = chat._dispatch_apex_peers(1, 'apex', text)
    assert len(result['queued']) == 1
    conn = _conn(db)
    row = conn.execute("SELECT sender, recipient, message_id FROM peer_messages").fetchone()
    assert row == ('apex', 'copilot-instructor', message_id)


def test_team_copy_only_reaches_explicitly_addressed_peers(db):
    conn = _conn(db)
    for principal in peers.SCOPES:
        peers.issue_token(conn, principal)
    peers.set_enabled(conn, 'gemini-advisor', False, 'ghost')
    queued = peers.share_exchange(conn, 1, 7, 'fix the grep', 'apex', 'I ran grep_repo on tests.',
                                  receipts=[{'tool': 'grep_repo', 'status': 'succeeded'}],
                                  addressed=['copilot-instructor'], sender='ghost')
    assert set(queued) == {'copilot-instructor'}
    body = conn.execute("SELECT body, sender, not_before FROM peer_messages WHERE id=?",
                        (queued['copilot-instructor'][0],)).fetchone()
    assert body[0].startswith('[TEAM COPY, the operator addressed you: APEX answered message 7')
    assert 'Operator: fix the grep' in body[0] and 'APEX: I ran grep_repo on tests.' in body[0]
    assert 'grep_repo=succeeded' in body[0] and body[1] == 'ghost' and body[2] is None
    peers.set_enabled(conn, 'gemini-advisor', True, 'ghost')
    again = peers.share_exchange(conn, 1, 8, 'x' * 5000, 'apex', 'y' * 5000)
    assert again == {}
    assert conn.execute("SELECT count(*) FROM peer_messages").fetchone()[0] == 1



def test_structured_help_bundle_is_persisted_scoped_and_paced(db, monkeypatch):
    conn = _conn(db)
    codex = peers.authenticate(conn, peers.issue_token(conn, 'codex-instructor'))
    _operator_says(conn, 'Please repair the local loop', ['codex-instructor'])
    for _ in range(4):
        conn.execute("INSERT INTO messages (conversation_id,from_agent,to_agent,content,message_type) VALUES (1,'apex','user','read receipt','tool_result')")
    clock = [1000.0]
    monkeypatch.setattr(peers.time, 'time', lambda: clock[0])
    result = peers.request_help(conn, 1, 'codex', 'Which guard is appropriate?', 'A read repeated six times.')
    assert result['status'] == 'queued'
    assert 'not delivered or answered' in result['notice']
    clock[0] += peers.HANDOFF_DELAY_S
    messages = peers.inbox(conn, codex)
    request = next(m for m in messages if m['id'] in result['request_ids'])
    assert request['sender'] == 'apex' and 'Evidence and attempts:' in request['body']
    assert peers.thread(conn, codex, 1)[-1]['message_type'] == 'handoff'
    before = conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    with pytest.raises(peers.PeerError):
        peers.request_help(conn, 1, 'gemini', 'Review this?', '')
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == before


def test_coaching_context_includes_only_attributable_replies_from_this_room(db):
    conn=_conn(db)
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'codex-instructor','apex','Use the existing Access view and test its disconnected state.','response')")
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(2,'gemini-advisor','apex','Other-room private context','response')")
    text=peers.coaching_context(conn,1)
    assert 'codex-instructor' in text and 'Use the existing Access view' in text
    assert 'Other-room private context' not in text
    assert 'not permissions' in text
    assert peers.coaching_context(conn,3)==''


def test_online_peer_cannot_pull_in_another_online_peer(db):
    conn = _conn(db)
    codex = peers.authenticate(conn, peers.issue_token(conn,'codex-instructor'))
    peers.issue_token(conn,'gemini-advisor')
    _operator_says(conn,'@codex help',['codex-instructor'])
    reply=peers.post(conn,codex,1,'Ask @gemini about this')
    assert reply['handoff']['queued']==[]
    assert conn.execute("SELECT count(*) FROM peer_messages WHERE recipient='gemini-advisor'").fetchone()[0]==0


def test_old_automatic_observer_copies_do_not_invite_or_reach_online_agents(db):
    conn = _conn(db)
    codex = peers.authenticate(conn,peers.issue_token(conn,'codex-instructor'))
    peers.enqueue(conn,1,1,'[TEAM COPY, observe: APEX answered message 1; coach APEX]', ['codex-instructor'])
    assert peers.inbox(conn,codex)==[]
    with pytest.raises(peers.PeerError,match='addressed'):
        peers.thread(conn,codex,1)
    with pytest.raises(peers.PeerError,match='addressed'):
        peers.post(conn,codex,1,'unsolicited reply')


def test_only_apex_login_receives_an_apex_invitation(db):
    conn = _conn(db)
    codex=peers.authenticate(conn,peers.issue_token(conn,'codex-instructor'))
    apex=peers.authenticate(conn,peers.issue_token(conn,'apex'))
    ids=_operator_says(conn,'@apex hello',['apex'])
    assert peers.inbox(conn,codex)==[]
    assert [row['id'] for row in peers.inbox(conn,apex)]==ids


def test_instructor_help_reuses_pending_request_across_operator_turns(db):
    conn = _conn(db)
    peers.issue_token(conn, 'codex-instructor')
    peers.issue_token(conn, 'apex')
    _operator_says(conn, '@apex read the Studio step; @codex may help', ['apex'])
    first = peers.request_help(conn, 1, 'codex', 'How do I read the step?', 'HTTP request rejected.')
    before = conn.execute('SELECT count(*) FROM messages').fetchone()[0]
    # Rewording or a new local turn must not trigger another online request.
    _operator_says(conn, '@apex try the step again; @codex may help', ['apex'])
    second = peers.request_help(conn, 1, 'codex', 'Can you fix this?', 'Same unresolved blocker.')
    assert second['deduplicated'] is True
    assert second['request_ids'] == first['request_ids']
    assert second['message_id'] == first['message_id']
    assert conn.execute('SELECT count(*) FROM messages').fetchone()[0] == before + 1
    assert conn.execute("SELECT count(*) FROM peer_messages WHERE sender='apex' AND recipient='codex-instructor'").fetchone()[0] == 1
    # A reply has been handled; later help is allowed.
    conn.execute('UPDATE peer_messages SET delivered_at=1 WHERE id=?', (first['request_ids'][0],))
    third = peers.request_help(conn, 1, 'codex', 'Different issue after the reply', 'New evidence.')
    assert 'deduplicated' not in third
    assert third['request_ids'] != first['request_ids']
