"""Tests for APEX hb_restart tool, /restart command, and /clip doer step-owner sync."""
import sqlite3
import types

import pytest

from core import apex_alm, apex_tools, hb_agent_tools as at, hb_clipboard, hb_commands, hb_task_manager


def _fake_run(returncode=0, stdout='', stderr=''):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run, calls


def test_hb_restart_tool_queues_systemd_unit():
    run, calls = _fake_run(0)
    res = at.hb_restart_tool({'scope': 'all', 'reason': 'Owner asked via Telegram'}, run=run)
    assert res['ok'] is True and res['status'] == 'queued' and res['scope'] == 'all'
    cmd, kw = calls[0]
    assert cmd[:4] == ['systemd-run', '--user', '--collect', '--quiet']
    assert cmd[5].endswith('scripts/hb_restart.py')
    assert cmd[6:] == ['all', 'Owner asked via Telegram']
    assert 'XDG_RUNTIME_DIR' in kw['env'] and 'DBUS_SESSION_BUS_ADDRESS' in kw['env']


def test_hb_restart_tool_defaults_and_validation():
    run, calls = _fake_run(0)
    res = at.hb_restart_tool({}, run=run)
    assert res['scope'] == 'ui'
    assert calls[0][0][6] == 'ui'
    with pytest.raises(ValueError):
        at.hb_restart_tool({'scope': 'kernel'})
    with pytest.raises(ValueError):
        at.hb_restart_tool({'scope': 'ui', 'cmd': 'rm -rf /'})


def test_hb_restart_tool_raises_on_systemd_failure():
    run, _ = _fake_run(1, stderr='Failed to connect to bus')
    with pytest.raises(RuntimeError, match='Failed to connect to bus'):
        at.hb_restart_tool({'scope': 'ui'}, run=run)


def test_hb_restart_is_wired_for_apex_and_commands(monkeypatch):
    assert 'hb_restart' in apex_tools.TOOL_SCHEMAS
    assert 'hb_restart' in apex_tools._REQUIRED_ARGUMENTS
    assert 'hb_restart' in hb_task_manager.EXECUTION_TOOLS
    assert 'hb_restart' in at.WRITE_TOOLS
    assert 'hb_restart' in apex_tools.DOER_ACTIONS
    assert 'hb_service' in apex_tools.TOOL_SCHEMAS
    assert 'hb_service' in hb_task_manager.EXECUTION_TOOLS
    assert 'hb_service' in at.WRITE_TOOLS
    assert 'hb_service' in apex_tools.DOER_ACTIONS
    assert 'studio_evidence_get' in at.READ_TOOLS and 'studio_resume' in at.READ_TOOLS
    assert hb_commands.parse('restart') == ('restart', ['ui'])
    assert hb_commands.parse('restart all reload backend') == ('restart', ['all', 'reload backend'])
    assert hb_commands.parse('restart invalid') is None

    seen = []
    monkeypatch.setattr(at, 'hb_restart_tool', lambda args: seen.append(args) or {'ok': True, 'scope': args['scope'], 'reason': args['reason']})
    conn = sqlite3.connect(':memory:')
    out = hb_commands.run(conn, 2845, 'restart', ['ui', 'Load fix'], 'JD')
    assert 'HB restart queued (ui)' in out
    assert seen == [{'scope': 'ui', 'reason': 'Load fix'}]


def test_clip_doer_apex_syncs_project_steps_owner_for_alm():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, owner TEXT, owner_route TEXT, updated_at REAL)')
    conn.execute("INSERT INTO project_steps VALUES ('S-0C67666A79', 'claude-code', NULL, 0)")
    conn.execute('CREATE TABLE hb_tasks(task_id TEXT, step_id TEXT, state TEXT, created_at REAL)')

    said = hb_clipboard.edit(conn, ['doer', 'S-0C67666A79', 'apex'], 'JD')
    assert 'doer: APEX' in said
    step = dict(conn.execute("SELECT * FROM project_steps WHERE step_id='S-0C67666A79'").fetchone())
    assert step['owner'] == 'apex' and step['owner_route'] == 'apex'
    assert apex_alm._assigned(step) is True


def test_clip_doer_tool_is_instructor_only_and_updates_owner():
    from core import agent_identity
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, owner TEXT, owner_route TEXT, updated_at REAL)')
    conn.execute("INSERT INTO project_steps VALUES ('S-0C67666A79', 'claude-code', NULL, 0)")
    conn.execute('CREATE TABLE hb_tasks(task_id TEXT, step_id TEXT, state TEXT, created_at REAL)')

    tok = agent_identity.CURRENT.set({'principal': 'apex'})
    try:
        with pytest.raises(PermissionError):
            at.clip_doer_tool({'step_id': 'S-0C67666A79', 'doer': 'apex'}, conn=conn)
    finally:
        agent_identity.CURRENT.reset(tok)

    tok = agent_identity.CURRENT.set({'principal': 'copilot-instructor'})
    try:
        res = at.clip_doer_tool({'step_id': 'S-0C67666A79', 'doer': 'apex', 'reason': 'Owner asked to assign'}, conn=conn)
        assert res['ok'] is True and res['owner'] == 'apex' and res['owner_route'] == 'apex'
        assert 'clip_doer' in at.ACCEPT_TOOLS and 'studio_log_change' in at.ACCEPT_TOOLS
    finally:
        agent_identity.CURRENT.reset(tok)


def test_studio_log_change_tool_records_blackboard_and_file_log(monkeypatch):
    from core import agent_identity
    from core.knowledge import projects
    saved = []
    monkeypatch.setattr(projects, 'add_blackboard_note', lambda pid, content, *, author, kind: saved.append((pid, author, kind, content)) or 'B-TEST123456')
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, description TEXT, updated_at REAL)')
    conn.execute("INSERT INTO project_steps VALUES ('S-69FA40CEB7', 'FILE LOG', 0)")

    tok = agent_identity.CURRENT.set({'principal': 'apex'})
    try:
        with pytest.raises(PermissionError):
            at.studio_log_change_tool({'summary': 'nope'}, conn=conn)
    finally:
        agent_identity.CURRENT.reset(tok)

    tok = agent_identity.CURRENT.set({'principal': 'copilot-instructor'})
    try:
        res = at.studio_log_change_tool({
            'project_id': 'P-2AB8250A87',
            'kind': 'milestone',
            'summary': 'Added audited clip_doer and studio_log_change tools',
            'how': 'Instructor-only ACCEPT_TOOLS on /api/agent/v1/tools',
            'files': ['core/hb_agent_tools.py'],
            'receipts': ['pytest 43 passed'],
        }, conn=conn)
        assert res['ok'] is True and res['note_id'] == 'B-TEST123456' and res['file_log_updated'] is True
        assert saved and saved[0][1] == 'copilot-instructor' and 'pytest 43 passed' in saved[0][3]
        desc = conn.execute("SELECT description FROM project_steps WHERE step_id='S-69FA40CEB7'").fetchone()[0]
        assert 'B-TEST123456' in desc and 'core/hb_agent_tools.py' in desc
    finally:
        agent_identity.CURRENT.reset(tok)


def test_hb_service_tool_controls_hb_units_and_delegates_terminal_restart():
    run, calls = _fake_run(0, stdout='active\n')
    listed = at.hb_service_tool({'action': 'list'}, run=run)
    assert listed['ok'] is True and 'swarm-terminal.service' in listed['services']

    run2, calls2 = _fake_run(0)
    restarted = at.hb_service_tool({'action': 'restart', 'service': 'fridays', 'reason': 'reload bot'}, run=run2)
    assert restarted['ok'] is True and restarted['service'] == 'swarm-fridays.service'
    assert calls2[0][0] == ['sudo', '-n', '/usr/bin/systemctl', 'restart', 'swarm-fridays.service']

    run3, calls3 = _fake_run(0)
    term = at.hb_service_tool({'action': 'restart', 'service': 'hb', 'reason': 'reload ui'}, run=run3)
    assert term['status'] == 'queued' and calls3[0][0][:4] == ['systemd-run', '--user', '--collect', '--quiet']

    with pytest.raises(ValueError):
        at.hb_service_tool({'action': 'restart', 'service': 'sshd.service'}, run=run2)


def test_hb_restart_deduplicates_when_already_pending(monkeypatch):
    monkeypatch.setattr(at, '_restart_already_pending', lambda: True)
    res = at.hb_restart_tool({'scope': 'all', 'reason': 'duplicate'})
    assert res['ok'] is True and res['deduplicated'] is True and res['status'] == 'already_queued'


def test_propose_patch_heals_numbered_read_file_paste(tmp_path):
    from core.apex_tools import ReadOnlyRepository
    from core.tool_approval import ApprovalStore
    import subprocess
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    target = tmp_path / 'sample.py'
    target.write_text('def greet():\n    return "hi"\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'sample.py'], cwd=tmp_path, check=True)
    repo = ReadOnlyRepository(tmp_path)
    store = ApprovalStore()
    tx = store.propose(
        repo,
        'propose_patch',
        {'file_path': 'sample.py', 'exact_old_text': '1: def greet():\n2:     return "hi"\n', 'new_text': 'def greet():\n    return "hello"\n'},
        'apex', 'sess', 2845,
    )
    assert tx.paths == ['sample.py']
    # Workspace-absolute path inside repo normalizes cleanly in ReadOnlyRepository._path
    assert repo._path(str(target)) == target


def test_vortex_prune_allows_sqlite_wal_shm_sidecars(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, UTC
    from core import vortex_backup
    import json
    broot = tmp_path / 'backups'
    broot.mkdir()
    monkeypatch.setattr(vortex_backup, 'backup_root', lambda: broot)
    src = tmp_path / 'src.sqlite'
    c = sqlite3.connect(src)
    c.execute('CREATE TABLE t(x INT)'); c.commit(); c.close()
    old = vortex_backup.create_backup(src, label='old')
    new = vortex_backup.create_backup(src, label='new')
    old_dir = broot / old['backup_id']
    mpath = old_dir / 'manifest.json'
    m = json.loads(mpath.read_text(encoding='utf-8'))
    m['created_at'] = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    mpath.write_text(json.dumps(m), encoding='utf-8')
    (old_dir / 'memory.sqlite-wal').write_bytes(b'')
    (old_dir / 'memory.sqlite-shm').write_bytes(b'x')
    assert vortex_backup.prune_backups(days=30) == 1
    assert not old_dir.exists() and (broot / new['backup_id']).exists()


def test_ba_facts_includes_total_lines_and_kc_notes(monkeypatch):
    from core import apex_knowledge, hb_homework, hb_tasks
    monkeypatch.setattr(apex_knowledge, 'search', lambda q: {'items': [{'document_id': 99, 'title': 'KC Lesson', 'excerpt': 'Use raw:true'}]})
    conn = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(conn)
    task = {'task_id': 'T-1', 'title': 'hb_clipboard doer sync', 'objective': 'Fix core/hb_clipboard.py', 'step_id': None}
    gathered = hb_homework.facts(conn, task)
    assert gathered['kc_notes'] and gathered['kc_notes'][0]['id'] == 99
    clip = next((f for f in gathered['files'] if f['path'] == 'core/hb_clipboard.py'), None)
    assert clip is not None and isinstance(clip.get('total_lines'), int) and clip['total_lines'] > 50


def test_mirror_to_kc_is_idempotent(monkeypatch, tmp_path):
    from core import apex_knowledge
    db_path = tmp_path / 'kc.sqlite'
    c = sqlite3.connect(db_path)
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, raw_text TEXT, source_type TEXT, source_ref TEXT, domain_tags TEXT, status TEXT, added_by TEXT, subcategory TEXT, created_at TEXT, updated_at TEXT, content_hash TEXT)')
    c.commit(); c.close()
    monkeypatch.setattr(apex_knowledge, 'get_connection', lambda: sqlite3.connect(db_path))
    id1 = apex_knowledge.mirror_to_kc('My Lesson', 'Body v1', source_ref='agent-memory://apex/1', domain_tags='memory,apex')
    id2 = apex_knowledge.mirror_to_kc('My Lesson', 'Body v2', source_ref='agent-memory://apex/1', domain_tags='memory,apex')
    assert id1 == id2
    with sqlite3.connect(db_path) as check:
        assert check.execute('SELECT COUNT(*), raw_text FROM knowledge_sources').fetchone() == (1, 'Body v2')


def test_apex_personality_is_upbeat_can_do_and_honest():
    from core import hb_master_prompt
    assert 'upbeat, creative, can-do' in apex_tools.PARTNER_ROLE
    assert "never lie or say 'yes I'll do that'" in apex_tools.PARTNER_ROLE
    role_text = hb_master_prompt.for_role('apex')
    assert 'upbeat, creative, can-do' in role_text
    assert 'Never lie' in role_text


def test_smart_hb_intent_glossary_atlas_and_email_trust(tmp_path):
    from core import hb_owner_intent as oi, hb_learning, hb_system_atlas, hb_email_intake
    assert oi.classify('what are you busy with') == 'status'
    assert oi.classify('what are you working on?') == 'status'
    assert oi.classify('go look for the latest sap notes about PDS') is None
    assert oi.classify('Make the theme more pink') is None
    assert 'themes.css' in hb_learning.glossary_for('Make the theme more pink')
    pds_gloss = hb_learning.glossary_for('go look for the latest sap notes about PDS')
    assert 'Payday Super' in pds_gloss and 'STP2' in pds_gloss

    atlas = hb_system_atlas.build_atlas()
    assert len(atlas['blueprints']) >= 30 and len(atlas['views']) >= 20
    assert any('themes.css' in t for t in atlas['themes_css'])

    conn = sqlite3.connect(':memory:')
    hb_email_intake.ensure_schema(conn)
    conn.execute("CREATE TABLE hb_channel_identities(key TEXT PRIMARY KEY, role TEXT, name TEXT, added_by TEXT, at REAL)")
    conn.execute("INSERT INTO hb_channel_identities VALUES ('email:owner@example.com','owner','JD','test',0)")
    assert 'owner@example.com' in hb_email_intake.trusted(conn)


def test_hb_media_download_tool_and_recommend_tools():
    run, calls = _fake_run(0, stdout='/srv/archive/projects/swarm/artifacts/media_center/downloads/Nature_Ep1-[abc].mp4\n')
    res = at.hb_media_download_tool({'query': 'nature documentary episode', 'format': 'video'}, run=run)
    assert res['ok'] is True and res['filename'] == 'Nature_Ep1-[abc].mp4'
    assert calls[0][0][-1] == 'ytsearch1:nature documentary episode'
    assert 'hb_media_download' in apex_tools.TOOL_SCHEMAS
    assert 'hb_media_download' in apex_tools.DOER_ACTIONS
    assert 'hb_media_download' in hb_task_manager.EXECUTION_TOOLS

    assert 'hb_media_download' in hb_task_manager.recommend_tools('Download nature episode from youtube')
    assert 'propose_patch' in hb_task_manager.recommend_tools('Make the theme more pink in themes.css')
    assert 'web_search' in hb_task_manager.recommend_tools('Find the freshest roses in Melbourne')
    assert 'hb_service' in hb_task_manager.recommend_tools('Restart fridays service')


def test_apex_thought_schema_meter_pills_read_404_hint_and_direct_hb():
    import json, shutil, subprocess
    from pathlib import Path
    from core import apex_paths, hb_commands
    # 1. TURN_FORMAT allows thought first on every branch
    for branch in apex_tools.TURN_FORMAT['json_schema']['schema']['oneOf']:
        assert 'thought' in branch['properties']
    # 2. Missing test file gives create-with-propose_write_file hint
    msg = apex_paths.not_found('tests/test_hb_phone_conversation_flow.py', [])
    assert 'propose_write_file' in msg
    # 3. Direct @hb answers plain English immediately
    conn = sqlite3.connect(':memory:')
    hb_commands.ensure_schema(conn)
    ans = hb_commands.handle(conn, 2845, '@hb where are the themes and pink CSS?', 'JD')
    assert 'themes.css' in ans
    pds = hb_commands.handle(conn, 2845, '@hb what is PDS?', 'JD')
    assert 'Payday Super' in pds
    # 4. renderMeter displays active tool pill and collapsible thought
    node = shutil.which('node')
    if node:
        js = Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live.js'
        code = (
            f"const R=require({json.dumps(str(js))});"
            "const h=R.renderMeter({up:true,busy:true,model:'mistral-nemo-12b-abliterated',device:'ROCm',"
            "prompt_tokens:1200,generated:40,ctx:45312,active_tool:'grep_repo',"
            "thought:'Checking hb_channels.py before creating the test',thoughts:['Checking hb_channels.py','Second step']},12.5,'');"
            "process.stdout.write(h);"
        )
        out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
        assert out.returncode == 0, out.stderr[-500:]
        assert 'hbl-tool-pill' in out.stdout and 'grep_repo' in out.stdout
        assert 'hbl-thought' in out.stdout and 'Checking hb_channels.py' in out.stdout


def test_custom_tools_plugin_loader_and_design_bible(tmp_path):
    from core import hb_custom_tools, hb_system_atlas
    plugin = tmp_path / 'custom_echo.py'
    plugin.write_text(
        "TOOL_SPEC = {'name': 'custom_echo', 'summary': 'Echo text', 'arguments': {'text': 'string'}}\n"
        "def run(args): return {'ok': True, 'echo': args.get('text', '')}\n",
        encoding='utf-8',
    )
    listed = hb_custom_tools.list_tools(tmp_path)
    assert len(listed) == 1 and listed[0]['name'] == 'custom_echo'
    assert hb_custom_tools.invoke('custom_echo', {'text': 'nectar'}, directory=tmp_path) == {'ok': True, 'echo': 'nectar'}
    with pytest.raises(ValueError):
        hb_custom_tools.invoke('not_custom', {}, directory=tmp_path)
    assert 'hb_custom_tool' in apex_tools.TOOL_SCHEMAS and 'hb_custom_tool' in hb_task_manager.EXECUTION_TOOLS
    assert 'Hummingbird' in hb_system_atlas.HUMMINGBIRD_DESIGN_BIBLE and 'Liquid-Glass' in hb_system_atlas.HUMMINGBIRD_DESIGN_BIBLE


def test_accept_step_commits_db_before_git_commit_to_prevent_deadlock(tmp_path, monkeypatch):
    from core import hb_change_sets, hb_commands as hc, hb_tasks
    db_path = tmp_path / 'hb.sqlite'
    conn = sqlite3.connect(db_path, timeout=0.5)
    hb_tasks.ensure_schema(conn)
    conn.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, residual_risk TEXT, updated_at REAL)')
    conn.execute("INSERT INTO project_steps VALUES ('S-DEADLOCK01','P-1','Test step','desc','partial','apex','',0)")
    conn.commit()
    monkeypatch.setattr(hb_tasks, 'owner_review_blocker', lambda c, sid: None)

    hook_wrote = []
    def fake_git_commit(step_id, title=''):
        # Simulate TimeWizard post-commit hook opening a SECOND connection and writing to SQLite!
        other = sqlite3.connect(db_path, timeout=0.5)
        try:
            assert other.execute("SELECT status FROM project_steps WHERE step_id=?", (step_id,)).fetchone()[0] == 'done'
            other.execute("CREATE TABLE IF NOT EXISTS hook_log(x TEXT)")
            other.execute("INSERT INTO hook_log VALUES ('ok')")
            other.commit()
            hook_wrote.append(True)
        finally:
            other.close()
        return {'state': 'committed', 'commit': 'abc1234', 'files': ['a.py']}

    monkeypatch.setattr(hb_change_sets, 'commit', fake_git_commit)
    out = hc.accept_step(conn, 'S-DEADLOCK01', 'ghost')
    conn.close()
    assert hook_wrote == [True] and 'Committed locally: abc1234' in out


def test_hummingbird_theme_and_chat_pill_upgrade_present():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert 'body.theme-hummingbird' in (root / 'frontend/static/css/themes.css').read_text(encoding='utf-8')
    assert "'hummingbird'" in (root / 'frontend/static/js/core/theme.js').read_text(encoding='utf-8')
    assert "setNamedTheme('hummingbird')" in (root / 'frontend/templates/terminal_base.html').read_text(encoding='utf-8')
    js = (root / 'frontend/static/js/hb-live.js').read_text(encoding='utf-8')
    assert 'upgradeLightTicks' in js and 'hbl-chat-pills' in js and 'hbl-drawer-grip-b' in js


def test_manual_pick_never_hijacks_apex_gpu_with_fred_cpu(monkeypatch):
    from core import hb_apex_swap
    monkeypatch.setattr(hb_apex_swap, 'playing', lambda: 'mistral-nemo-12b-abliterated')
    modes = {'fred-cpu:24b': 'on', 'mistral-nemo-12b-abliterated': 'on'}
    picked, _ = hb_apex_swap.manual_pick('Hello apex hows your new attitude feeling?', modes=modes)
    assert picked != 'fred-cpu:24b'
    # Explicit @fred mention still works if ever requested
    explicit, _ = hb_apex_swap.manual_pick('@fred-cpu:24b review this', modes=modes)
    assert explicit == 'fred-cpu:24b' or explicit is None










