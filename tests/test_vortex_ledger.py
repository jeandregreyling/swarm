import gzip
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import vortex_ledger as ledger


def _set_root(monkeypatch, tmp_path):
    root = tmp_path / 'vortex'
    monkeypatch.setattr(ledger, 'LEDGER_ROOT', root)
    return root


def test_write_event_records_fields_and_redacts_content(monkeypatch, tmp_path):
    root = _set_root(monkeypatch, tmp_path)
    event = {
        'id': 'event-1',
        'ts': datetime(2025, 5, 1, tzinfo=timezone.utc).timestamp(),
        'kind': 'chat',
        'source': 'fridays.tool',
        'agent': 'gemma',
        'message': 'private user message',
        'payload': {
            'source_agent': 'gemma',
            'target_agent': 'search',
            'action_type': 'tool_call',
            'execution_status': 'completed',
            'prompt': 'private prompt',
            'api_key': 'sensitive-key',
        },
    }

    record = ledger.write_event(event)
    daily_file = root / 'ledger' / '2025-05-01.jsonl'
    snapshot_file = root / record['snapshot']
    persisted = json.loads(daily_file.read_text(encoding='utf-8'))
    snapshot = json.loads(snapshot_file.read_text(encoding='utf-8'))

    assert record['source_agent'] == 'gemma'
    assert record['target_agent'] == 'search'
    assert record['action_type'] == 'tool_call'
    assert record['execution_status'] == 'completed'
    assert len(record['payload_context_hash']) == 64
    assert 'private user message' not in daily_file.read_text(encoding='utf-8')
    assert 'private prompt' not in daily_file.read_text(encoding='utf-8')
    assert persisted['payload']['prompt']['length'] == len('private prompt')
    assert persisted['payload']['api_key'] == '[REDACTED]'
    assert snapshot['payload']['api_key'] == '[REDACTED]'
    assert snapshot_file.stat().st_mode & 0o777 == 0o600


def test_async_queue_writes_event_to_daily_ledger(monkeypatch, tmp_path):
    root = _set_root(monkeypatch, tmp_path)
    monkeypatch.delenv('SWARM_VORTEX_LEDGER_DISABLED', raising=False)
    monkeypatch.setattr(ledger, '_maintenance_loop', lambda: threading.Event().wait())

    queued = ledger.enqueue_event({
        'id': 'queued-event',
        'ts': datetime(2025, 5, 2, tzinfo=timezone.utc).timestamp(),
        'kind': 'system',
        'source': 'test',
        'message': 'test',
        'payload': {'action_type': 'queued_test', 'execution_status': 'completed'},
    })

    assert queued
    assert ledger.flush(timeout=2)
    records = [
        json.loads(line)
        for line in (root / 'ledger' / '2025-05-02.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert len(records) == 1
    assert records[0]['action_type'] == 'queued_test'


def test_retention_prunes_expired_compressed_snapshots_only(monkeypatch, tmp_path):
    root = _set_root(monkeypatch, tmp_path)
    ledger._ensure_layout()
    now = datetime(2025, 5, 1, tzinfo=timezone.utc)
    old_day = (now.date() - timedelta(days=91)).isoformat()
    boundary_day = (now.date() - timedelta(days=90)).isoformat()

    for folder_name in ('ledger', 'indexes'):
        folder = root / folder_name
        (folder / f'{old_day}.jsonl').write_text('{}\n', encoding='utf-8')
        (folder / f'{boundary_day}.jsonl').write_text('{}\n', encoding='utf-8')
    for day in (old_day, boundary_day):
        snapshot_dir = root / 'snapshots' / day
        snapshot_dir.mkdir()
        (snapshot_dir / 'event.json.gz').write_bytes(gzip.compress(b'{}'))

    counts = ledger.prune_expired(now=now)

    assert counts['ledger_files'] == 1
    assert counts['index_files'] == 1
    assert counts['snapshot_files'] == 1
    assert not (root / 'snapshots' / old_day).exists()
    assert (root / 'snapshots' / boundary_day / 'event.json.gz').exists()


def test_capacity_guard_compresses_unflagged_snapshots_and_preserves_window(monkeypatch, tmp_path):
    root = _set_root(monkeypatch, tmp_path)
    ledger._ensure_layout()
    day = '2025-05-01'
    snapshot_dir = root / 'snapshots' / day
    snapshot_dir.mkdir()
    plain = snapshot_dir / 'plain.json'
    plain.write_text(json.dumps({'event_id': 'plain', 'flagged': False, 'payload': 'x' * 1000}))
    flagged = snapshot_dir / 'flagged.json'
    flagged.write_text(json.dumps({'event_id': 'flagged', 'flagged': True, 'payload': 'keep'}))
    usage_type = type('Usage', (), {})
    low_usage = usage_type()
    low_usage.total, low_usage.free = 1000, 10
    recovered_usage = usage_type()
    recovered_usage.total, recovered_usage.free = 1000, 100
    usage_results = iter((recovered_usage,))
    monkeypatch.setattr(ledger.shutil, 'disk_usage', lambda _path: next(usage_results))

    result = ledger._capacity_guard(root, usage=low_usage)

    compressed = snapshot_dir / 'plain.json.gz'
    assert result['compressed'] == 1
    assert result['free_fraction'] == 0.1
    assert not plain.exists()
    assert json.loads(gzip.decompress(compressed.read_bytes()))['event_id'] == 'plain'
    assert flagged.exists()
    pointer = json.loads((root / 'indexes' / f'{day}.jsonl').read_text(encoding='utf-8'))
    assert pointer['action_type'] == 'snapshot_compressed'
    assert pointer['compressed_snapshot'] == f'snapshots/{day}/plain.json.gz'
