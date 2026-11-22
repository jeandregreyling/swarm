"""Tests for Defect 1: Nectar backfill from hb_merits, APEX live wallet prompt awareness, Right Sundial 🍯 wallet & change_set hint."""
import sqlite3
from pathlib import Path
import subprocess

from core import hb_carry_forward as cf, hb_nectar as nectar

ROOT = Path(__file__).resolve().parents[1]


def test_backfill_from_merits_credits_ledger_and_shadow_idempotently():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE hb_merits(id INTEGER PRIMARY KEY, role TEXT, kind TEXT, step_id TEXT, note TEXT)')
    conn.execute("INSERT INTO hb_merits(id, role, kind, step_id, note) VALUES (1, 'APEX', 'success', 'S-AAA1111111', 'Proposal: Liquid Glass')")
    conn.execute("INSERT INTO hb_merits(id, role, kind, step_id, note) VALUES (2, 'APEX', 'success', 'S-BBB2222222', 'Proposal: Telegram buttons')")
    assert nectar.backfill_from_merits(conn, 'APEX') == 2
    assert nectar.backfill_from_merits(conn, 'APEX') == 0
    assert nectar.balance(conn, 'APEX') >= 6
    assert nectar.reconcile_shadow(conn, 'APEX')['clean'] is True


def test_lean_chat_prompt_includes_live_nectar_wallet_and_right_sundial_ui():
    prompt = cf.lean_chat_prompt('mistral-nemo-12b-abliterated', '', nectar_line='🍯 APEX Nectar wallet: 28 Nectar (🌺×4)')
    assert 'LIVE NECTAR WALLET' in prompt and '28 Nectar' in prompt
    html = (ROOT / 'frontend/templates/terminal_base.html').read_text(encoding='utf-8')
    assert 'id="dial-nectar-btn"' in html
    assert '/api/peer/v1/hb/nectar' in (ROOT / 'frontend/blueprints/peer_bridge.py').read_text(encoding='utf-8')
    js_path = ROOT / 'frontend/static/js/hb-live.js'
    assert 'window.hbToggleNectarWallet' in js_path.read_text(encoding='utf-8')
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
    runner_src = (ROOT / 'core/apex_test_runner.py').read_text(encoding='utf-8')
    assert 'change_set' in runner_src and '{"action": "apply"}' in runner_src
