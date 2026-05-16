"""Bounded subprocess wrapper for Fridays Tasker Python tasks."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)


def _db_path() -> str:
    return os.environ.get('SWARM_DB_PATH') or os.path.join(_SWARM_ROOT, 'swarm_memory.db')


def _record_timeout(task_name: str, task_args: str, timeout_seconds: int, output: str) -> None:
    try:
        conn = sqlite3.connect(_db_path(), timeout=5)
        try:
            conn.execute(
                """INSERT INTO task_run_log
                   (task_name, status, output, run_at, duration_ms, details_json)
                   VALUES (?, 'timeout', ?, ?, ?, ?)""",
                (
                    task_name,
                    output[-2000:],
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    int(timeout_seconds * 1000),
                    json.dumps({'args': task_args, 'timeout_seconds': int(timeout_seconds)}),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def run_bounded(task_name: str, task_args: str, timeout_seconds: int) -> int:
    timeout = max(30, min(int(timeout_seconds or 900), 3600))
    env = os.environ.copy()
    env['PYTHONPATH'] = _SWARM_ROOT + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    code = (
        'import sys; '
        'from fridays.task_runner import run_task; '
        'ok,out=run_task(sys.argv[1], args=sys.argv[2]); '
        'print(("OK" if ok else "FAIL") + " " + str(out)[:2000]); '
        'sys.exit(0 if ok else 1)'
    )
    proc = subprocess.Popen(
        [sys.executable, '-c', code, task_name, task_args],
        cwd=_SWARM_ROOT,
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    started = time.time()
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        output, _ = proc.communicate(timeout=10)
        elapsed = int(time.time() - started)
        message = f'TIMEOUT {task_name} exceeded {timeout}s after {elapsed}s\n{output or ""}'
        print(message[-2500:])
        _record_timeout(task_name, task_args, timeout, message)
        return 124
    if output:
        print(output[-2500:].rstrip())
    return int(proc.returncode or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description='Run one Fridays Python task with a hard timeout.')
    parser.add_argument('--timeout-seconds', type=int, default=int(os.environ.get('FRIDAYS_TASK_WORKER_TIMEOUT', '900')))
    parser.add_argument('task_name')
    parser.add_argument('task_args', nargs='?', default='')
    args = parser.parse_args()
    raise SystemExit(run_bounded(args.task_name, args.task_args, args.timeout_seconds))


if __name__ == '__main__':
    main()
