"""The real app must expose Media safely without overwriting Studio content."""
import sqlite3


def test_stage_falls_back_to_swarm_env_and_dev_does_not_clean_production_jobs(monkeypatch):
    monkeypatch.delenv('STAGE', raising=False)
    monkeypatch.setenv('SWARM_ENV', 'dev')
    monkeypatch.setenv('SWARM_VORTEX_LEDGER_DISABLED', '1')
    monkeypatch.setenv('SWARM_SECRET_KEY', 'test-only')
    import terminal
    assert terminal._runtime_stage() == 'DEV'
    calls = []
    monkeypatch.setattr(terminal, 'mark_orphaned_chat_jobs', lambda: calls.append('orphan cleanup'))
    terminal.create_app()
    assert calls == []
    monkeypatch.setenv('STAGE', 'UAT')
    assert terminal._runtime_stage() == 'UAT'
    monkeypatch.setenv('STAGE', 'PROD')
    assert terminal._runtime_stage() == 'PROD'


def test_real_factory_registers_media_owner_routes_and_preserves_studio(monkeypatch, tmp_path):
    monkeypatch.setenv('STAGE', 'UAT')
    monkeypatch.setenv('SWARM_VORTEX_LEDGER_DISABLED', '1')
    monkeypatch.setenv('SWARM_SECRET_KEY', 'test-only')
    from terminal import create_app
    import services.auth
    import blueprints.media_bp as media

    database = tmp_path / 'media.sqlite'
    def connect():
        c = sqlite3.connect(database)
        c.row_factory = sqlite3.Row
        return c

    with connect() as c:
        c.execute('CREATE TABLE project_docs (id INTEGER PRIMARY KEY, doc_name TEXT UNIQUE, content TEXT, tags TEXT, updated_at TEXT)')
        c.execute('INSERT INTO project_docs(doc_name,content,tags,updated_at) VALUES (?,?,?,?)',
                  ('MEDIA_CENTER_BOOTSTRAP.md', 'Owner-edited Studio document', 'custom', 'prior'))
        c.execute('CREATE TABLE user_profiles (username TEXT PRIMARY KEY, display_name TEXT, role TEXT, approved INTEGER, is_active INTEGER)')
        c.execute('CREATE TABLE user_sessions (username TEXT, session_token TEXT, expires_at TEXT, is_active INTEGER)')
        c.execute("INSERT INTO user_profiles VALUES ('owner', 'Owner', 'owner', 1, 1)")
        c.execute("INSERT INTO user_profiles VALUES ('guest', 'Guest', 'user', 1, 1)")
        c.execute("INSERT INTO user_sessions VALUES ('owner', 'owner-token', '2999-01-01 00:00:00', 1)")
        c.execute("INSERT INTO user_sessions VALUES ('guest', 'guest-token', '2999-01-01 00:00:00', 1)")
    monkeypatch.setattr(media, 'get_connection', connect)
    monkeypatch.setattr(services.auth, 'get_connection', connect)
    app = create_app()
    client = app.test_client()

    assert client.get('/api/media/state').status_code == 403
    assert client.post('/api/media/providers', json={'name': 'Test'}).status_code == 403

    client.set_cookie('friday_session', 'guest-token')
    assert client.get('/api/media/state').status_code == 403
    client.set_cookie('friday_session', 'owner-token')
    result = client.get('/api/media/state')
    assert result.status_code == 200 and result.get_json()['ok']
    with connect() as c:
        assert tuple(c.execute('SELECT content,tags,updated_at FROM project_docs WHERE doc_name=?',
                               ('MEDIA_CENTER_BOOTSTRAP.md',)).fetchone()) == ('Owner-edited Studio document', 'custom', 'prior')
    assert client.post('/api/media/providers', json={'name': 'Local'}).status_code == 200
    assert client.post('/api/media/providers', json={'name': 'Other'}, headers={'Origin': 'https://example.invalid'}).status_code == 403

    rules = {(r.rule, method) for r in app.url_map.iter_rules() for method in r.methods}
    for rule, method in [('/api/media/state', 'GET'), ('/api/media/providers', 'POST'),
                         ('/api/media/items', 'POST'), ('/api/media/seed-song', 'POST'),
                         ('/api/media/screenshot', 'POST'), ('/api/media/artifacts/<path:artifact_path>', 'GET'),
                         ('/api/media/remix', 'POST'), ('/api/media/mix-songs', 'POST'), ('/api/media/produce', 'POST')]:
        assert (rule, method) in rules
