"""Asynchronous, privacy-conscious JSONL ledger for Vortex execution events."""
from __future__ import annotations

import hashlib
import gzip
import json
import logging
import os
import queue
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger('core.vortex_ledger')

LEDGER_ROOT = Path(os.environ.get('SWARM_VORTEX_LEDGER_ROOT', '/mnt/archive/vortex'))
RETENTION_DAYS = 90
CAPACITY_FREE_FRACTION = 0.05
MAINTENANCE_INTERVAL_SECONDS = 3600
MAX_PENDING_EVENTS = 10000

_QUEUE: queue.Queue[dict | None] = queue.Queue(maxsize=MAX_PENDING_EVENTS)
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False
_MAINTENANCE_STARTED = False
_COUNTER_LOCK = threading.Lock()
_COUNTERS = {'written': 0, 'failed': 0, 'snapshots_compressed': 0}
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_SECRET_KEY_RE = re.compile(r'(?:secret|token|password|credential|authorization|api[_-]?key|cookie)', re.I)
_CONTENT_KEY_RE = re.compile(r'(?:content|prompt|response|query|text|output|notes|detail|chunk|context|body)', re.I)
_SECRET_TEXT_RE = re.compile(
    r'(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)'
    r'(\s*[:=]\s*)(["\']?)[^\s,"\'}]+'
)
_BEARER_RE = re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+')


def hash_context(*parts: Any) -> str:
    """Return a stable SHA-256 fingerprint without persisting source content."""
    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            raw = part
        elif isinstance(part, str):
            raw = part.encode('utf-8', errors='replace')
        else:
            raw = json.dumps(part, sort_keys=True, ensure_ascii=True, default=str).encode('utf-8')
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
    return digest.hexdigest()


def _content_descriptor(value: str) -> dict[str, Any]:
    raw = value.encode('utf-8', errors='replace')
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'length': len(raw)}


def _sanitize(value: Any, *, key: str = '', depth: int = 0) -> Any:
    if _SECRET_KEY_RE.search(key):
        return '[REDACTED]'
    if isinstance(value, dict):
        if depth >= 8:
            return '[MAX_DEPTH]'
        return {
            str(k)[:100]: _sanitize(v, key=str(k), depth=depth + 1)
            for k, v in list(value.items())[:200]
        }
    if isinstance(value, (list, tuple)):
        if depth >= 8:
            return '[MAX_DEPTH]'
        return [_sanitize(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, str):
        if key.lower().endswith(('_hash', '_id')):
            return value[:200]
        if _CONTENT_KEY_RE.search(key):
            return _content_descriptor(value)
        safe = _BEARER_RE.sub('Bearer [REDACTED]', value)
        safe = _SECRET_TEXT_RE.sub(r'\1\2[REDACTED]', safe)
        return safe[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return {'type': type(value).__name__}


def _safe_root() -> Path:
    configured_root = Path(LEDGER_ROOT).expanduser()
    root = configured_root.resolve()
    protected = (
        Path('/'),
        Path.home().resolve(),
        Path(__file__).resolve().parents[1],
        Path('/mnt/archive'),
    )
    if any(root == path or path.is_relative_to(root) for path in protected):
        raise ValueError(f'unsafe Vortex ledger root: {root}')
    if configured_root.is_symlink():
        raise ValueError(f'Vortex ledger root must not be a symlink: {configured_root}')
    if root == Path('/mnt/archive/vortex') and not Path('/mnt/archive').is_mount():
        raise OSError('/mnt/archive is not mounted; refusing to write Vortex data on the system disk')
    return root


def _ensure_layout() -> Path:
    root = _safe_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    for name in ('ledger', 'snapshots', 'indexes'):
        path = root / name
        if path.is_symlink():
            raise ValueError(f'Vortex data directory must not be a symlink: {path}')
        path.mkdir(mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
    return root


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n'
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(line.encode('utf-8'))
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(f'incomplete append to {path}')
            view = view[written:]
    finally:
        os.close(fd)


def _date_for_event(event: dict[str, Any]) -> tuple[datetime, str]:
    timestamp = float(event.get('ts') or time.time())
    moment = datetime.fromtimestamp(timestamp, timezone.utc)
    return moment, moment.strftime('%Y-%m-%d')


def _as_string(payload: dict[str, Any], *keys: str, default: str = '') -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and not isinstance(value, (dict, list, tuple)):
            text = str(value).strip()
            if text:
                return text[:160]
    return default


def _event_status(event: dict[str, Any], payload: dict[str, Any]) -> str:
    explicit = _as_string(payload, 'execution_status', 'status')
    if explicit:
        return explicit.lower()
    if isinstance(payload.get('ok'), bool):
        return 'completed' if payload['ok'] else 'failed'
    severity = str(event.get('severity') or '').lower()
    return 'failed' if severity in {'error', 'critical'} else 'warning' if severity == 'warn' else 'recorded'


def _snapshot_needed(event: dict[str, Any]) -> bool:
    kind = str(event.get('kind') or '').lower()
    source = str(event.get('source') or '').lower()
    return (
        kind in {'chat', 'relay_step', 'checkpoint'}
        or any(marker in source for marker in ('tool', 'memory', 'handoff', 'retriev', 'chunk'))
    ) and bool(event.get('payload'))


def _keywords(event: dict[str, Any], source_agent: str, target_agent: str, action_type: str) -> list[str]:
    terms = {str(event.get('kind') or ''), str(event.get('source') or ''), source_agent, target_agent, action_type}
    payload = event.get('payload')
    if isinstance(payload, dict):
        terms.update(str(key) for key in payload)
        for key in ('method', 'task_name', 'tool_name', 'category', 'chunk_count'):
            value = payload.get(key)
            if isinstance(value, (str, int, float)):
                terms.add(str(value))
        details = payload.get('details')
        if isinstance(details, dict):
            for key in ('method', 'task_name', 'tool_name', 'category', 'chunk_count'):
                value = details.get(key)
                if isinstance(value, (str, int, float)):
                    terms.add(str(value))
    normalized = set()
    for term in terms:
        for word in re.findall(r'[a-zA-Z0-9_-]{2,40}', term.lower()):
            normalized.add(word)
    return sorted(normalized)[:100]


def _write_snapshot(root: Path, day: str, event: dict[str, Any], payload: dict[str, Any]) -> tuple[str, bool]:
    event_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(event.get('id') or ''))[:64]
    if not event_id:
        event_id = hash_context(event)[:24]
    flagged = bool(payload.get('retain_snapshot') or payload.get('snapshot_flagged'))
    relpath = Path('snapshots') / day / f'{event_id}.json'
    path = root / relpath
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    snapshot = {
        'event_id': event_id,
        'timestamp': event.get('ts'),
        'kind': str(event.get('kind') or ''),
        'source': str(event.get('source') or ''),
        'agent': str(event.get('agent') or ''),
        'thread_id': str(event.get('thread_id') or ''),
        'flagged': flagged,
        'payload': _sanitize(payload),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return relpath.as_posix(), flagged
    try:
        data = json.dumps(snapshot, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return relpath.as_posix(), flagged


def write_event(event: dict[str, Any]) -> dict[str, Any]:
    """Persist one spine event to the daily ledger, pointer index, and snapshots."""
    if not isinstance(event, dict):
        raise TypeError('Vortex events must be dictionaries')
    root = _ensure_layout()
    moment, day = _date_for_event(event)
    raw_payload = event.get('payload')
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    safe_payload = _sanitize(payload)
    context_hash = hash_context(safe_payload, _content_descriptor(str(event.get('message') or '')))
    source_agent = _as_string(payload, 'source_agent', 'from_agent', 'from', 'sender', default=str(event.get('agent') or ''))
    target_agent = _as_string(payload, 'target_agent', 'to_agent', 'to', 'target', default='')
    action_type = _as_string(payload, 'action_type', 'action', 'stage', default=str(event.get('kind') or 'action'))
    status = _event_status(event, payload)
    snapshot_path = ''
    snapshot_flagged = bool(payload.get('retain_snapshot') or payload.get('snapshot_flagged'))
    if _snapshot_needed(event):
        usage = shutil.disk_usage(root)
        if usage.total and usage.free / usage.total < CAPACITY_FREE_FRACTION:
            _capacity_guard(root, usage=usage)
            usage = shutil.disk_usage(root)
        if usage.total and usage.free / usage.total >= CAPACITY_FREE_FRACTION:
            snapshot_path, snapshot_flagged = _write_snapshot(root, day, event, payload)

    record = {
        'event_id': str(event.get('id') or ''),
        'timestamp': moment.isoformat(),
        'source_agent': source_agent,
        'target_agent': target_agent,
        'action_type': action_type,
        'payload_context_hash': context_hash,
        'execution_status': status,
        'kind': str(event.get('kind') or ''),
        'severity': str(event.get('severity') or 'info'),
        'source': str(event.get('source') or ''),
        'thread_id': _sanitize(str(event.get('thread_id') or '')),
        'change_id': _sanitize(str(event.get('change_id') or '')),
        'snapshot': snapshot_path,
        'snapshot_flagged': snapshot_flagged,
        'payload': safe_payload,
    }
    _append_jsonl(root / 'ledger' / f'{day}.jsonl', record)
    index_record = {
        'event_id': record['event_id'],
        'timestamp': record['timestamp'],
        'kind': record['kind'],
        'source': record['source'],
        'source_agent': source_agent,
        'target_agent': target_agent,
        'action_type': action_type,
        'execution_status': status,
        'payload_context_hash': context_hash,
        'snapshot': snapshot_path,
        'snapshot_flagged': snapshot_flagged,
        'terms': _keywords(event, source_agent, target_agent, action_type),
    }
    _append_jsonl(root / 'indexes' / f'{day}.jsonl', index_record)
    with _COUNTER_LOCK:
        _COUNTERS['written'] += 1
    return record


def _date_from_path(path: Path) -> datetime.date | None:
    if not _DATE_RE.fullmatch(path.name):
        return None
    try:
        return datetime.strptime(path.name, '%Y-%m-%d').date()
    except ValueError:
        return None


def prune_expired(*, now: datetime | None = None) -> dict[str, int]:
    """Remove only date-partitioned files older than the 90-day retention window."""
    root = _ensure_layout()
    today = (now or datetime.now(timezone.utc)).date()
    cutoff = today - timedelta(days=RETENTION_DAYS)
    counts = {'ledger_files': 0, 'index_files': 0, 'snapshot_files': 0, 'snapshot_dirs': 0}
    for folder_name, counter, suffix in (
        ('ledger', 'ledger_files', '.jsonl'),
        ('indexes', 'index_files', '.jsonl'),
    ):
        folder = root / folder_name
        for path in folder.iterdir():
            day = _date_from_path(Path(path.stem))
            if path.is_file() and path.suffix == suffix and day and day < cutoff:
                path.unlink()
                counts[counter] += 1
    snapshots = root / 'snapshots'
    for folder in snapshots.iterdir():
        day = _date_from_path(folder)
        if not folder.is_dir() or not day or day >= cutoff:
            continue
        for path in folder.iterdir():
            if path.is_file() and path.name.endswith(('.json', '.json.gz')):
                path.unlink()
                counts['snapshot_files'] += 1
        try:
            folder.rmdir()
            counts['snapshot_dirs'] += 1
        except OSError:
            logger.warning('Vortex expired snapshot directory was not empty: %s', folder)
    return counts


def _capacity_guard(root: Path, *, usage=None) -> dict[str, int | float]:
    usage = usage or shutil.disk_usage(root)
    free_fraction = usage.free / usage.total if usage.total else 1.0
    result: dict[str, int | float] = {
        'free_bytes': usage.free,
        'free_fraction': free_fraction,
        'compressed': 0,
    }
    if free_fraction >= CAPACITY_FREE_FRACTION:
        return result

    result['compressed'] = _compress_old_snapshots(root)
    usage = shutil.disk_usage(root)
    free_fraction = usage.free / usage.total if usage.total else 1.0
    result.update(free_bytes=usage.free, free_fraction=free_fraction)
    if free_fraction >= CAPACITY_FREE_FRACTION:
        logger.warning(
            'Vortex capacity guard compressed %d snapshots; %.2f%% free remains',
            result['compressed'],
            free_fraction * 100,
        )
        return result

    logger.error(
        'Vortex storage remains below %.0f%% free after snapshot compression; '
        'the 90-day ledger and snapshots were preserved, operator action is required',
        CAPACITY_FREE_FRACTION * 100,
    )
    return result


def _compress_old_snapshots(root: Path) -> int:
    """Gzip unflagged retained snapshots without evicting any part of the 90-day window."""
    snapshots = root / 'snapshots'
    candidates: list[tuple[datetime, Path]] = []
    for folder in snapshots.iterdir():
        day = _date_from_path(folder)
        if not folder.is_dir() or not day:
            continue
        for path in folder.iterdir():
            if path.is_file() and path.suffix == '.json':
                candidates.append((datetime.combine(day, datetime.min.time(), timezone.utc), path))
    compressed_count = 0
    for _day, path in sorted(candidates, key=lambda item: (item[0], item[1].stat().st_mtime)):
        try:
            snapshot = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning('Vortex compression could not inspect snapshot %s: %s', path, exc)
            continue
        if snapshot.get('flagged'):
            continue
        compressed_path = path.with_suffix(path.suffix + '.gz')
        if compressed_path.exists():
            continue
        temporary_path = compressed_path.with_name(f'{compressed_path.name}.{uuid.uuid4().hex}.tmp')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        compressed_bytes = gzip.compress(path.read_bytes(), mtime=0)
        fd = os.open(temporary_path, flags, 0o600)
        try:
            view = memoryview(compressed_bytes)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError(f'incomplete compressed snapshot write: {temporary_path}')
                view = view[written:]
        finally:
            os.close(fd)
        pointer = {
            'event_id': str(snapshot.get('event_id') or path.stem),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action_type': 'snapshot_compressed',
            'snapshot': path.relative_to(root).as_posix(),
            'compressed_snapshot': compressed_path.relative_to(root).as_posix(),
            'reason': 'capacity_guard',
        }
        try:
            os.replace(temporary_path, compressed_path)
            _append_jsonl(root / 'indexes' / f'{path.parent.name}.jsonl', pointer)
            path.unlink()
        except Exception:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            raise
        compressed_count += 1
        with _COUNTER_LOCK:
            _COUNTERS['snapshots_compressed'] += 1
    return compressed_count


def run_maintenance(*, now: datetime | None = None) -> dict[str, Any]:
    """Enforce 90-day retention and the low-space snapshot safeguard."""
    root = _ensure_layout()
    expired = prune_expired(now=now)
    capacity = _capacity_guard(root)
    return {'expired': expired, 'capacity': capacity, 'root': str(root)}


def _writer_loop() -> None:
    while True:
        event = _QUEUE.get()
        try:
            if event is None:
                return
            write_event(event)
        except Exception:
            with _COUNTER_LOCK:
                _COUNTERS['failed'] += 1
            logger.exception('Vortex ledger event write failed')
        finally:
            _QUEUE.task_done()


def _maintenance_loop() -> None:
    while True:
        try:
            run_maintenance()
        except Exception:
            logger.exception('Vortex retention/capacity maintenance failed')
        time.sleep(MAINTENANCE_INTERVAL_SECONDS)


def start() -> None:
    """Start the ledger writer and the periodic cleanup daemon once per process."""
    global _WORKER_STARTED, _MAINTENANCE_STARTED
    if os.environ.get('SWARM_VORTEX_LEDGER_DISABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}:
        return
    with _WORKER_LOCK:
        if not _WORKER_STARTED:
            threading.Thread(target=_writer_loop, name='vortex-ledger-writer', daemon=True).start()
            _WORKER_STARTED = True
        if not _MAINTENANCE_STARTED:
            threading.Thread(target=_maintenance_loop, name='vortex-ledger-retention', daemon=True).start()
            _MAINTENANCE_STARTED = True


def enqueue_event(event: Any) -> bool:
    """Queue a spine event for asynchronous persistence without blocking the caller."""
    if os.environ.get('SWARM_VORTEX_LEDGER_DISABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}:
        return False
    if not isinstance(event, dict):
        raise TypeError('Vortex events must be dictionaries')
    copy = dict(event)
    if isinstance(copy.get('payload'), dict):
        copy['payload'] = dict(copy['payload'])
    start()
    try:
        _QUEUE.put_nowait(copy)
    except queue.Full:
        with _COUNTER_LOCK:
            _COUNTERS['failed'] += 1
        logger.error('Vortex ledger queue is full; event %s was not queued', str(event.get('id') or 'unknown'))
        return False
    return True


def record_action(
    action_type: str,
    *,
    source_agent: str = '',
    target_agent: str = '',
    status: str = 'recorded',
    context_parts: tuple[Any, ...] = (),
    thread_id: str | None = None,
    details: dict[str, Any] | None = None,
    source: str = 'fridays.execution',
) -> bool:
    """Emit a structured action event through the existing spine middleware."""
    if os.environ.get('SWARM_VORTEX_LEDGER_DISABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}:
        return False
    payload = {
        'source_agent': str(source_agent or '')[:160],
        'target_agent': str(target_agent or '')[:160],
        'action_type': str(action_type or 'action')[:160],
        'execution_status': str(status or 'recorded')[:80],
        'payload_context_hash': hash_context(*context_parts),
        'details': details or {},
    }
    try:
        from core import spine

        severity = (
            spine.Severity.ERROR if str(status).lower() in {'failed', 'error', 'timed_out'}
            else spine.Severity.WARN if str(status).lower() in {'warning', 'rejected'}
            else spine.Severity.INFO
        )
        event = spine.log(
            spine.EventKind.CHAT,
            f"{payload['action_type']} {payload['source_agent']} -> {payload['target_agent']} ({payload['execution_status']})",
            severity=severity,
            source=source,
            agent=source_agent or None,
            thread_id=thread_id,
            payload=payload,
        )
        return bool(event)
    except Exception:
        logger.exception('Vortex execution action could not be emitted to the spine')
        return False


def flush(timeout: float = 5.0) -> bool:
    """Wait briefly for queued ledger events; intended for orderly shutdown and tests."""
    deadline = time.monotonic() + max(0.0, timeout)
    while _QUEUE.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.01)
    return _QUEUE.unfinished_tasks == 0


def status() -> dict[str, Any]:
    """Return safe operational metadata for the asynchronous ledger."""
    with _COUNTER_LOCK:
        counters = dict(_COUNTERS)
    return {
        'root': str(LEDGER_ROOT),
        'retention_days': RETENTION_DAYS,
        'capacity_free_fraction': CAPACITY_FREE_FRACTION,
        'pending': _QUEUE.qsize(),
        **counters,
    }
