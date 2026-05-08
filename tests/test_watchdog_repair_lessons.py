from __future__ import annotations

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_watchdog_records_repair_lesson(monkeypatch, tmp_path):
    from utils.db import watchdog_lessons

    db_path = tmp_path / 'watchdog-lessons.db'

    def _conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(watchdog_lessons, 'get_connection', _conn)

    lesson = watchdog_lessons.record_repair_lesson(
        'vortex_github_logging',
        'Vortex is not updating GitHub evidence reliably.',
        'Route Vortex/GitHub failures into Watchdog repair lessons with proof before promotion.',
        proof_required='A DEV/UAT replay shows Vortex checkpoint, GitHub update, and trace row.',
        evidence={'thread_id': 2579, 'component': 'vortex'},
        source_thread_id='2579',
        lesson_id='WDL-VORTEX-GITHUB-PYTEST',
    )

    assert lesson['lesson_id'] == 'WDL-VORTEX-GITHUB-PYTEST'
    assert lesson['status'] == 'open'
    assert lesson['evidence']['component'] == 'vortex'

    open_lessons = watchdog_lessons.list_open_repair_lessons()
    assert [row['lesson_id'] for row in open_lessons] == ['WDL-VORTEX-GITHUB-PYTEST']

