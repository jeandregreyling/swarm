"""Tests for complexity-tiered flowers & spendable Nectar micro-economy."""
import sqlite3
import pytest

from core import hb_commands as hc, hb_nectar as nectar


def test_complexity_tiered_flowers_earn_and_deduplicate():
    conn = sqlite3.connect(':memory:')
    r1 = nectar.earn_flower(conn, 'APEX', 'S-1111111111', files_count=1, title='Fix typo')
    assert r1['awarded'] is True and r1['flower'] == 'daisy' and r1['nectar'] == 1 and r1['balance'] == 1
    r1_dup = nectar.earn_flower(conn, 'APEX', 'S-1111111111', files_count=1, title='Fix typo')
    assert r1_dup['awarded'] is False and r1_dup['balance'] == 1
    r2 = nectar.earn_flower(conn, 'APEX', 'S-2222222222', files_count=3, title='Telegram inline buttons')
    assert r2['flower'] == 'hibiscus' and r2['nectar'] == 5 and r2['balance'] == 6
    r3 = nectar.earn_flower(conn, 'APEX', 'S-3333333333', files_count=5, title='Unified architecture milestone')
    assert r3['flower'] == 'sunburst' and r3['nectar'] == 10 and r3['balance'] == 16


def test_spend_nectar_enforces_balance_and_pays_counterparty():
    conn = sqlite3.connect(':memory:')
    nectar.earn_flower(conn, 'APEX', 'S-AAAAAAAA01', files_count=3, title='Telegram feature')
    with pytest.raises(ValueError, match='earn more flowers first'):
        nectar.spend(conn, 'APEX', 'commission_tool', to_agent='copilot-instructor')
    tx = nectar.spend(conn, 'APEX', 'qa_review', to_agent='copilot-instructor', note='QA custom_lint_check')
    assert tx['ok'] is True and tx['spent'] == 2 and tx['balance'] == 3
    assert nectar.balance(conn, 'copilot-instructor') == 2
    assert '3 Nectar' in nectar.summary_text(conn, 'APEX')
    assert hc.parse('nectar') == ('nectar', [])
    assert '3 Nectar' in hc.run(conn, 2845, 'nectar', [], 'JD')
