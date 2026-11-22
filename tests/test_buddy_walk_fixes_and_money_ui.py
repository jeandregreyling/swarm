"""Tests for Buddy-Walk Bug-Hunt Fixes: needs_owner never falsely parked, change_set show preview banner, Money Hub Payroll & Paper Lab UI."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_task_manager_never_falsely_parks_qa_confirmed_needs_owner():
    src = (ROOT / 'core/hb_task_manager.py').read_text(encoding='utf-8')
    assert "if row['state']=='needs_owner' and hb_tasks.requires_owner_review(conn,task) and not hb_tasks.owner_review_blocker(conn,task['step_id']):" in src


def test_change_set_show_explicitly_marks_preview_only():
    src = (ROOT / 'core/hb_change_sets.py').read_text(encoding='utf-8')
    assert 'PREVIEW ONLY — no files written yet' in src


def test_money_hub_js_syntax_and_payroll_paper_mounts():
    js_path = ROOT / 'frontend/static/js/views/money-hub.js'
    src = js_path.read_text(encoding='utf-8')
    assert '/api/business/payroll/calculate' in src
    assert '/api/business/payroll/commit' in src
    assert '/api/trading/paper/scorecard' in src
    assert '/api/trading/paper/open' in src
    assert 'PAPER-ONLY' in src
    node = shutil.which('node')
    if node:
        res = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
