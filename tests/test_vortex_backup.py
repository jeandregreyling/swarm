import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core import time_machine, vortex_backup


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    from core import spine

    monkeypatch.setattr(spine, 'log', lambda *args, **kwargs: None)
    source = tmp_path / 'live.sqlite'
    with sqlite3.connect(source) as conn:
        conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE memory(id INTEGER PRIMARY KEY, content TEXT);
            CREATE TABLE agent_private_memory(id INTEGER PRIMARY KEY, content TEXT);
            CREATE TABLE queue(id INTEGER PRIMARY KEY, status TEXT);
            INSERT INTO memory VALUES (1, 'verified memory');
            INSERT INTO agent_private_memory VALUES (1, 'private lesson');
            INSERT INTO queue VALUES (1, 'pending');
        """)
    monkeypatch.setenv('SWARM_VORTEX_BACKUP_ROOT', str(tmp_path / 'backups'))
    return source


def test_backup_and_restore_preserve_all_tables_and_wal(memory_db, tmp_path):
    with sqlite3.connect(memory_db) as writer:
        writer.execute("INSERT INTO memory VALUES (2, 'committed WAL memory')")
        writer.commit()
        saved = vortex_backup.create_backup(memory_db, 'manual')
        writer.execute("UPDATE memory SET content='changed after backup' WHERE id=1")
        writer.commit()
        output = tmp_path / 'recovered.sqlite'
        result = vortex_backup.restore_backup(Path(saved['manifest_path']), output, live_database=memory_db)
    assert result['integrity_check'] == 'ok'
    with sqlite3.connect(output) as recovered:
        assert recovered.execute('SELECT * FROM memory ORDER BY id').fetchall() == [
            (1, 'verified memory'), (2, 'committed WAL memory')]
        assert recovered.execute('SELECT * FROM agent_private_memory').fetchall() == [(1, 'private lesson')]
        assert recovered.execute('SELECT * FROM queue').fetchall() == [(1, 'pending')]
    assert output.stat().st_mode & 0o777 == 0o600
    assert Path(saved['manifest_path']).stat().st_mode & 0o777 == 0o600
    assert Path(saved['manifest_path']).parent.stat().st_mode & 0o777 == 0o700


def test_recovery_rejects_live_database_existing_output_and_corruption(memory_db, tmp_path):
    saved = vortex_backup.create_backup(memory_db, 'manual')
    manifest = Path(saved['manifest_path'])
    with pytest.raises(ValueError, match='live database'):
        vortex_backup.restore_backup(manifest, memory_db, live_database=memory_db)
    existing = tmp_path / 'existing.sqlite'
    existing.write_bytes(b'keep me')
    with pytest.raises(FileExistsError):
        vortex_backup.restore_backup(manifest, existing, live_database=memory_db)
    assert existing.read_bytes() == b'keep me'
    (manifest.parent / 'memory.sqlite').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum mismatch'):
        vortex_backup.restore_backup(manifest, tmp_path / 'new.sqlite', live_database=memory_db)
    assert not (tmp_path / 'new.sqlite').exists()


def test_failed_backup_is_not_published(memory_db, monkeypatch):
    monkeypatch.setattr(vortex_backup, '_integrity', lambda conn: (_ for _ in ()).throw(ValueError('bad integrity')))
    with pytest.raises(ValueError, match='bad integrity'):
        vortex_backup.create_backup(memory_db, 'broken')
    assert list(vortex_backup.backup_root().iterdir()) == []


def test_manual_backup_failure_does_not_create_success_checkpoint(memory_db, monkeypatch):
    monkeypatch.setattr(time_machine, 'DB_PATH', memory_db)
    tm = time_machine.TimeMachine()
    monkeypatch.setattr(tm, 'capture_workflow_state', lambda: {'captured_at': 'now', 'counts': {}})
    monkeypatch.setattr(vortex_backup, 'create_backup', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError, match='disk full'):
        tm.create_workflow_checkpoint('failed-manual', backup_memory=True)
    assert tm.list_checkpoints() == []


def test_retention_expires_at_30_days_and_keeps_newest(memory_db):
    now = datetime.now(UTC)
    paths = []
    for age in (31, 29, 0):
        saved = vortex_backup.create_backup(memory_db, f'age-{age}')
        path = Path(saved['manifest_path'])
        saved['created_at'] = (now - timedelta(days=age)).isoformat()
        path.write_text(json.dumps(saved))
        paths.append(path)
    assert vortex_backup.prune_backups(now=now) == 1
    assert not paths[0].exists()
    assert paths[1].exists() and paths[2].exists()
    assert vortex_backup.prune_backups(now=now + timedelta(days=90)) == 1
    assert paths[2].exists()


def test_manual_checkpoint_has_full_backup_automatic_checkpoint_does_not(memory_db, monkeypatch):
    monkeypatch.setattr(time_machine, 'DB_PATH', memory_db)
    tm = time_machine.TimeMachine()
    monkeypatch.setattr(tm, 'capture_workflow_state', lambda: {'captured_at': 'now', 'counts': {}})
    monkeypatch.setattr(tm, 'record_event', lambda **kwargs: None)
    monkeypatch.setattr(tm, '_write_activity_log', lambda *args: None)
    git_calls = []
    monkeypatch.setattr(time_machine, '_git_cmd', lambda *args, **kwargs: git_calls.append(args) or ('', 0))
    automatic = tm.create_workflow_checkpoint('proposal-done')
    manual = tm.create_workflow_checkpoint('manual', backup_memory=True)
    assert automatic['memory_backup'] is None
    assert manual['memory_backup']['integrity_check'] == 'ok'
    assert git_calls == []
    assert len(list(vortex_backup.backup_root().glob('*/manifest.json'))) == 1
    assert tm.get_checkpoint(manual['checkpoint_name'])['full_state']['memory_backup'] == manual['memory_backup']
    assert tm.list_checkpoints()[0]['checkpoint_kind'] == 'memory'
    preview = tm.preview_restore(manual['checkpoint_name'])
    assert preview['restore_mode'] == 'offline-memory'
    assert preview['summary']['restorable'] is True
    assert preview['summary']['online_restore_allowed'] is False


def test_legacy_truncated_workflow_restore_never_deletes_live_rows(memory_db, monkeypatch):
    monkeypatch.setattr(time_machine, 'DB_PATH', memory_db)
    tm = time_machine.TimeMachine()
    monkeypatch.setattr(tm, 'capture_workflow_state', lambda: {'captured_at': 'now', 'counts': {}})
    tm.create_checkpoint('legacy-limited', 'vortex', full_state={'queue': [{'id': 999, 'status': 'done'}]})
    with pytest.raises(RuntimeError, match='Online step-back is disabled'):
        tm.restore_workflow_state('legacy-limited', dry_run=False)
    with sqlite3.connect(memory_db) as conn:
        assert conn.execute('SELECT * FROM queue').fetchall() == [(1, 'pending')]


def test_registry_local_alias_paths_exist_and_do_not_use_old_machine():
    import yaml
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / 'ops' / 'llm_registry.yaml').read_text())
    entries = {entry['name']: entry for entry in config['models']}
    for name in ('gemma-direct:3', 'llama-direct:3.2'):
        assert entries[name]['path'].startswith('/mnt/archive/models/blobs/')
    assert entries['gemma-direct:3']['ram_gb'] >= 3.9
    assert 'mmproj' in entries['gemma-direct:3']['options']
