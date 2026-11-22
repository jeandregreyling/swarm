"""Tests for Per-Model Individual Nectar Wallets (separate wallets per model, never one shared APEX pit)."""
import sqlite3
from pathlib import Path
import subprocess

import pytest
from core import hb_commands as hc, hb_nectar as nectar

ROOT = Path(__file__).resolve().parents[1]


def test_models_have_separate_individual_nectar_wallets_and_cannot_spend_each_others():
    conn = sqlite3.connect(':memory:')
    nectar.earn_flower(conn, 'mistral-nemo-12b-abliterated', 'S-1111111111', files_count=3, title='Telegram buttons')
    nectar.earn_flower(conn, 'llama-direct:3.2', 'S-2222222222', files_count=1, title='Small fix')
    assert nectar.balance(conn, 'mistral-nemo-12b-abliterated') == 5
    assert nectar.balance(conn, 'llama-direct:3.2') == 1
    wallets = nectar.all_wallets(conn)
    names = [w['agent'] for w in wallets]
    assert 'mistral-nemo-12b-abliterated' in names and 'llama-direct:3.2' in names
    # llama-direct:3.2 has only 1 Nectar and CANNOT spend mistral-nemo's 5 Nectar!
    with pytest.raises(ValueError, match='earn more flowers first'):
        nectar.spend(conn, 'llama-direct:3.2', 'qa_review')
    out = hc.run(conn, 2845, 'nectar', [], 'JD')
    assert 'mistral-nemo-12b-abliterated: 5 Nectar' in out
    assert 'llama-direct:3.2: 1 Nectar' in out


def test_merits_credits_model_wallet_and_hb_live_renders_wallets():
    assert 'wallet_owner = _real_model(people[0][1])' in (ROOT / 'core/hb_merits.py').read_text(encoding='utf-8')
    js_path = ROOT / 'frontend/static/js/hb-live.js'
    assert 'Array.isArray(d.wallets)' in js_path.read_text(encoding='utf-8')
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
