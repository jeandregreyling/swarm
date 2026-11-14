"""Owner 13 Nov: HB's own git upkeep, run by APEX as a guarded tool. It only clears git's index lock when the lock is clearly
stale: the file is empty, older than ten minutes and no git process is running. It never touches anything else."""
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STALE_AFTER_S = 600


def git_running():
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            command = Path('/proc', pid, 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if command and os.path.basename(command[0].decode('utf-8', 'replace')) == 'git':
            return True
    return False


def clear_stale_lock(root=ROOT, now=None, running=git_running):
    lock = Path(root) / '.git' / 'index.lock'
    now = time.time() if now is None else now
    if not lock.exists():
        return {'removed': False, 'reason': 'no lock file'}
    info = lock.stat()
    age = now - info.st_mtime
    if info.st_size:
        return {'removed': False, 'reason': 'lock file is not empty'}
    if age < STALE_AFTER_S:
        return {'removed': False, 'reason': 'lock file is younger than 10 minutes'}
    if running():
        return {'removed': False, 'reason': 'a git process is running'}
    lock.unlink()
    return {'removed': True, 'path': str(lock), 'age_minutes': int(age // 60)}
