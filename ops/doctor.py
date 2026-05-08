#!/usr/bin/env python3
"""make doctor — single-shot health/readiness CLI.

Runs:
  - bullshit detector
  - per-batch tests (timeout 30s each, only batches 11..15 + slash_commands)
  - /api/health probe (if a server is running on :5050)
  - DB row counts for the four pillars
  - python + pip versions

Exits non-zero on any RED.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ANSI colors (skip on non-TTY)
_TTY = sys.stdout.isatty()
def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _TTY else text
G = lambda t: _c('32', t)
Y = lambda t: _c('33', t)
R = lambda t: _c('31', t)
B = lambda t: _c('1', t)
DIM = lambda t: _c('2', t)


def _stamp_color(stamp: str) -> str:
    return {'GREEN': G, 'AMBER': Y, 'RED': R}.get(stamp, lambda t: t)(stamp)


def section(title: str):
    print()
    print(B('═' * 70))
    print(B(f' {title}'))
    print(B('═' * 70))


def run_detector() -> str:
    section('Bullshit detector')
    try:
        from ops.bullshit_detector import scan
        d = scan()
        print(f"  stamp        : {_stamp_color(d['stamp'])}")
        print(f"  score        : {d['score']}/100")
        print(f"  critical     : {d['by_severity'].get('critical', 0)}")
        print(f"  warnings     : {d['by_severity'].get('warning', 0)}")
        print(f"  info         : {d['by_severity'].get('info', 0)}")
        print(f"  files scanned: {d['files_scanned']}")
        return d['stamp']
    except Exception as exc:
        print(R(f"  detector failed: {exc}"))
        return 'RED'


_BATCHES = [
    'tests/test_session28_batch11.py',
    'tests/test_session28_batch12.py',
    'tests/test_session28_batch13.py',
    'tests/test_session28_batch14.py',
    'tests/test_session28_batch15.py',
    'tests/test_slash_commands.py',
]


def run_tests() -> str:
    section('Per-batch tests')
    py = str(ROOT / '.venv' / 'bin' / 'python')
    if not Path(py).exists():
        py = sys.executable
    overall = 'GREEN'
    for f in _BATCHES:
        path = ROOT / f
        if not path.exists():
            print(f"  {DIM('skip')} {f} (missing)")
            continue
        cp = subprocess.run(
            ['timeout', '30', py, '-m', 'pytest', str(path), '-x', '-q', '--tb=line'],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        if cp.returncode == 0:
            print(f"  {G('PASS')} {f}")
        else:
            print(f"  {R('FAIL')} {f}")
            tail = (cp.stdout + cp.stderr).strip().splitlines()[-3:]
            for line in tail:
                print(f"       {DIM(line)}")
            overall = 'RED'
    return overall


def probe_health() -> str:
    section('Live /api/health probe')
    try:
        import urllib.request
        with urllib.request.urlopen('http://localhost:5050/api/health', timeout=2) as r:
            data = json.loads(r.read().decode('utf-8'))
        print(f"  composite stamp: {_stamp_color(data.get('stamp', 'UNKNOWN'))}")
        build = data.get('build', {})
        print(f"  detector       : {_stamp_color(build.get('detector_stamp', '?'))} ({build.get('detector_score', '?')}/100)")
        pillars = data.get('pillars', {})
        for slug, p in pillars.items():
            ok = G('ok') if p.get('ok', True) else R('FAIL')
            print(f"  pillar {slug:18s} : {ok}")
        return data.get('stamp', 'UNKNOWN')
    except Exception as exc:
        print(DIM(f"  no server on :5050 ({exc})"))
        return 'SKIP'


def db_counts():
    section('DB row counts')
    try:
        import sqlite3
        db = os.environ.get('SWARM_MEMORY_DB') or str(ROOT / 'swarm_memory.db')
        if not Path(db).exists():
            print(DIM(f"  no DB at {db}"))
            return
        conn = sqlite3.connect(db)
        for table in ('cyber_audit_events', 'financial_positions', 'trading_signals', 'business_ledger', 'seven_learnings'):
            try:
                n = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                print(f"  {table:24s}: {n}")
            except sqlite3.OperationalError:
                print(f"  {table:24s}: {DIM('(missing)')}")
        conn.close()
    except Exception as exc:
        print(DIM(f"  db check failed: {exc}"))


def env_info():
    section('Environment')
    print(f"  python   : {sys.version.split()[0]}")
    print(f"  cwd      : {ROOT}")
    print(f"  SWARM_MEMORY_DB: {os.environ.get('SWARM_MEMORY_DB', '(default)')}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    t0 = time.time()
    env_info()
    detector = run_detector()
    tests = run_tests()
    health = probe_health()
    db_counts()
    section('Summary')
    print(f"  detector : {_stamp_color(detector)}")
    print(f"  tests    : {_stamp_color(tests)}")
    print(f"  health   : {_stamp_color(health) if health != 'SKIP' else DIM('skipped')}")
    print(f"  elapsed  : {time.time() - t0:.1f}s")
    print()
    bad = (detector == 'RED') or (tests == 'RED') or (health == 'RED')
    if bad:
        print(R(B('🔴 doctor: not ready')))
        return 1
    if detector == 'AMBER' or tests == 'AMBER' or health == 'AMBER':
        print(Y(B('🟡 doctor: shipable but not pristine')))
        return 0
    print(G(B('🟢 doctor: green across the board')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
