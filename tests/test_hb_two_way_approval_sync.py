"""Tests for Two-Way Unilateral Approval Sync (Telegram <-> HB Web) and Shakira BA plan_problems fix."""
import sqlite3
from pathlib import Path
import subprocess

from core import hb_channels as ch, hb_homework as hw

ROOT = Path(__file__).resolve().parents[1]


def test_sync_decision_clears_telegram_buttons_and_notifies_when_approved_in_web():
    conn = sqlite3.connect(':memory:')
    ch.ensure(conn)
    ch._ensure_approval_sync_table(conn)
    conn.execute("INSERT INTO hb_channel_identities(key,role,name,added_by,at) VALUES ('telegram:8735763890','owner','JD','test',1.0)")
    conn.execute("INSERT INTO hb_telegram_approval_msgs(step_id,chat_id,message_id,settled,at) VALUES ('S-AABBCCDDEE','8735763890',777,0,1.0)")
    calls = []
    def fake_call(method, payload=None, timeout=10):
        calls.append((method, payload))
        return {'ok': True, 'result': {'message_id': 778}}
    cleared = ch.sync_decision(conn, 'S-AABBCCDDEE', 'approved', actor='JD via HB web', call=fake_call)
    assert cleared == 1
    assert any(m == 'editMessageReplyMarkup' and p.get('message_id') == 777 for m, p in calls)
    assert any(m == 'sendMessage' and 'Approved S-AABBCCDDEE in HB' in p.get('text', '') for m, p in calls)
    # Settled row is not cleared twice
    assert ch.sync_decision(conn, 'S-AABBCCDDEE', 'approved', actor='JD via Telegram', call=fake_call) == 0


def test_hb_live_js_dismisses_golden_popup_and_updates_dial_on_external_approval():
    js_path = ROOT / 'frontend/static/js/hb-live.js'
    js = js_path.read_text(encoding='utf-8')
    assert "document.getElementById('hb-approval-popup')" in js
    assert "if (box && S.popup && !needs.some((n) => n.key === S.popup))" in js
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr


def test_shakira_plan_problems_accepts_concrete_test_runs_and_escaped_dots():
    known = {'frontend/static/js/core/theme.js', 'tests/test_hb_unified_theme_engine.py'}
    plan = [r'run tests/test_hb_unified_theme_engine\.py to ensure the new logic works as expected']
    assert hw.plan_problems(plan, known, {}) == []
