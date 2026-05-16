"""Standalone scheduler loop for Fridays.

The email listener can still call ``check_due()`` for backward compatibility,
but production scheduling should run through this small process so inbox IO,
agent recovery work, and scheduled task ownership do not share one long-lived
SQLite writer.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)


_STOP = False


def _handle_stop(signum, frame):  # pragma: no cover - signal glue
    global _STOP
    _STOP = True


def _clear_scheduler_leases(log: logging.Logger, owner_prefix: str = 'sched-') -> None:
    try:
        db_path = os.environ.get('SWARM_DB_PATH') or os.path.join(_SWARM_ROOT, 'swarm_memory.db')
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute(
                "UPDATE scheduled_tasks SET lease_owner='', lease_expires_at='' "
                "WHERE lease_owner LIKE ?",
                (f'{owner_prefix}%',),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.warning('could not clear scheduler leases: %s', exc)


def _run_check_due_once(log: logging.Logger, timeout_seconds: int) -> bool:
    env = os.environ.copy()
    env['PYTHONPATH'] = _SWARM_ROOT + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    cmd = [
        sys.executable,
        '-c',
        'from fridays.scheduler import check_due; check_due()',
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=_SWARM_ROOT,
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        output, _ = proc.communicate(timeout=max(30, int(timeout_seconds or 600)))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        output, _ = proc.communicate(timeout=10)
        log.warning('check_due timed out after %ss; killed scheduler work process', timeout_seconds)
        if output:
            log.warning('check_due partial output: %s', output[-1000:])
        _clear_scheduler_leases(log)
        return False
    if output:
        log.info('check_due output: %s', output[-1000:].strip())
    if proc.returncode:
        log.warning('check_due exited rc=%s', proc.returncode)
        return False
    return True


def run_loop(interval_seconds: int = 60, task_timeout_seconds: int = 600) -> None:
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')
    log = logging.getLogger('seven.scheduler_daemon')
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    interval = max(5, min(int(interval_seconds or 60), 300))
    task_timeout = max(60, min(int(task_timeout_seconds or 600), 3600))
    log.info('scheduler daemon started interval=%ss task_timeout=%ss', interval, task_timeout)
    while not _STOP:
        started = time.time()
        _run_check_due_once(log, task_timeout)
        elapsed = time.time() - started
        sleep_for = max(1.0, interval - elapsed)
        deadline = time.time() + sleep_for
        while not _STOP and time.time() < deadline:
            time.sleep(min(1.0, deadline - time.time()))
    log.info('scheduler daemon stopped')


def main() -> None:
    parser = argparse.ArgumentParser(description='Run Fridays scheduled tasks outside the email listener.')
    parser.add_argument('--interval-seconds', type=int, default=60)
    parser.add_argument('--task-timeout-seconds', type=int, default=600)
    args = parser.parse_args()
    run_loop(args.interval_seconds, args.task_timeout_seconds)


if __name__ == '__main__':
    main()
