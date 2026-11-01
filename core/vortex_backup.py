"""Durable, online-consistent Vortex memory backups and non-destructive recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path


def backup_root() -> Path:
    configured = os.environ.get('SWARM_VORTEX_BACKUP_ROOT')
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        archive = Path('/mnt/archive')
        if not archive.is_mount():
            raise OSError('/mnt/archive is not mounted; refusing to put memory backups on the system disk')
        root = archive / 'vortex' / 'memory-backups'
    if root in {Path('/'), Path.home(), Path(__file__).resolve().parents[1]}:
        raise ValueError(f'unsafe Vortex backup root: {root}')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _sync(path: Path) -> None:
    with path.open('rb') as stream:
        os.fsync(stream.fileno())


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _integrity(conn: sqlite3.Connection) -> None:
    results = [row[0] for row in conn.execute('PRAGMA integrity_check')]
    if results != ['ok']:
        raise ValueError(f'Vortex database integrity check failed: {results[:10]}')


def create_backup(source: Path, label: str) -> dict:
    """Publish a backup only after SQLite verification and a durable manifest."""
    source = Path(source).resolve(strict=True)
    root = backup_root()
    if shutil.disk_usage(root).free < source.stat().st_size + 256 * 1024 ** 2:
        raise OSError('not enough free space for a Vortex memory backup plus 256 MiB reserve')
    now = datetime.now(UTC)
    slug = re.sub(r'[^a-zA-Z0-9_-]', '-', label)[:64] or 'memory'
    name = f"{now.strftime('%Y%m%dT%H%M%S')}-{slug}-{uuid.uuid4().hex[:8]}"
    staging = Path(tempfile.mkdtemp(prefix='.pending-', dir=root))
    staging.chmod(0o700)
    try:
        database = staging / 'memory.sqlite'
        database.touch(mode=0o600)
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(database)) as dst:
                src.backup(dst, pages=1024, sleep=0.05)
                _integrity(dst)
                tables = [
                    row[0] for row in dst.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                ]
        manifest = {
            'version': 1,
            'backup_id': name,
            'created_at': now.isoformat(),
            'source': str(source),
            'database': 'memory.sqlite',
            'size_bytes': database.stat().st_size,
            'sha256': _sha256(database),
            'tables': tables,
            'integrity_check': 'ok',
        }
        manifest_path = staging / 'manifest.json'
        with manifest_path.open('x', encoding='utf-8') as stream:
            os.chmod(manifest_path, 0o600)
            json.dump(manifest, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _sync(database)
        _sync_directory(staging)
        destination = root / name
        staging.rename(destination)
        _sync_directory(root)
        return {**manifest, 'manifest_path': str(destination / 'manifest.json')}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_backup(manifest_path: Path) -> tuple[dict, Path]:
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or manifest.get('database') != 'memory.sqlite':
        raise ValueError('unsupported Vortex backup manifest')
    database = manifest_path.parent / 'memory.sqlite'
    if database.is_symlink() or not database.is_file():
        raise ValueError('backup database is missing or is a symlink')
    if database.stat().st_size != manifest['size_bytes'] or _sha256(database) != manifest['sha256']:
        raise ValueError('Vortex backup checksum mismatch')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as conn:
        _integrity(conn)
    return manifest, database


def restore_backup(manifest_path: Path, output: Path, *, live_database: Path) -> dict:
    """Recover all tables into a new DB; never replace a live or existing file."""
    output = Path(output).absolute()
    if output.resolve() == Path(live_database).resolve():
        raise ValueError('stop Swarm first; recovery must target a separate database, not the live database')
    manifest, database = verify_backup(manifest_path)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(output)) as dst:
                src.backup(dst)
                _integrity(dst)
        _sync(output)
        _sync_directory(output.parent)
    except BaseException:
        output.unlink()
        raise
    return {'ok': True, 'backup_id': manifest['backup_id'], 'output': str(output),
            'tables': manifest['tables'], 'integrity_check': 'ok'}


def prune_backups(*, days: int = 30, now: datetime | None = None) -> int:
    """Remove only expired, recognized backups, keeping the newest good copy."""
    if days < 1:
        raise ValueError('backup retention must be at least one day')
    root = backup_root()
    backups = []
    for folder in root.iterdir():
        if not folder.is_dir() or folder.is_symlink() or folder.name.startswith('.'):
            continue
        path = folder / 'manifest.json'
        if not path.is_file() or path.is_symlink():
            continue
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if manifest.get('version') == 1 and manifest.get('backup_id') == folder.name:
            backups.append((datetime.fromisoformat(manifest['created_at']), path))
    backups.sort(reverse=True)
    if not backups:
        return 0
    verify_backup(backups[0][1])
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    removed = 0
    for created, path in backups[1:]:
        if created < cutoff:
            # Do not follow directories or remove unexpected contents.
            folder = path.parent
            if {p.name for p in folder.iterdir()} != {'memory.sqlite', 'manifest.json'}:
                raise ValueError(f'unexpected contents in expired Vortex backup: {folder}')
            (folder / 'memory.sqlite').unlink()
            path.unlink()
            folder.rmdir()
            removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create')
    create.add_argument('--label', default='manual-memory')
    verify = sub.add_parser('verify')
    verify.add_argument('manifest', type=Path)
    restore = sub.add_parser('restore')
    restore.add_argument('manifest', type=Path)
    restore.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'verify':
        manifest, _ = verify_backup(args.manifest)
        print(json.dumps({'ok': True, **manifest}, indent=2))
    elif args.command == 'restore':
        from core.time_machine import DB_PATH
        print(json.dumps(restore_backup(args.manifest, args.output, live_database=DB_PATH), indent=2))
    else:
        from core.time_machine import time_wizard
        result = time_wizard.create_workflow_checkpoint(
            args.label, agent='vortex', description='Full memory restore point', backup_memory=True,
        )
        result['expired_backups_removed'] = prune_backups()
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
