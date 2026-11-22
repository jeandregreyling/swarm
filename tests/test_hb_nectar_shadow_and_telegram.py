"""Tests for Nectar HMAC shadow ledger (Banana Tax -100) and reliable Telegram approval alerts."""
import sqlite3
from core import hb_channels as ch, hb_nectar as nectar


def test_shadow_ledger_catches_cheating_and_slaps_minus_100_banana_tax():
    conn = sqlite3.connect(':memory:')
    nectar.earn_flower(conn, 'APEX', 'S-1111222233', files_count=3, title='Telegram feature')
    assert nectar.reconcile_shadow(conn, 'APEX')['clean'] is True
    assert nectar.balance(conn, 'APEX') == 5

    # Sneaky AI inserts fake +999 Nectar directly into hb_nectar_ledger!
    conn.execute(
        "INSERT INTO hb_nectar_ledger(at, agent, delta, flower, kind, counterparty, ref, note) "
        "VALUES (1.0, 'APEX', 999, 'sunburst', 'earn', 'SELF', 'S-FAKE999999', 'totally legit')"
    )
    res = nectar.reconcile_shadow(conn, 'APEX')
    assert res['clean'] is False and res['cheated'] is True
    assert res['balance'] == -100
    assert '🍌 BANANA ALERT!' in res['alert']
    assert nectar.balance(conn, 'APEX') == -100
    # After the Banana Tax penalty, both ledgers are reconciled at -100 so APEX must work back to 0
    assert nectar.reconcile_shadow(conn, 'APEX')['clean'] is True


def test_telegram_needs_message_includes_title_and_uses_any_not_all():
    src = open('core/hb_channels.py', encoding='utf-8').read()
    assert 'any([telegram_send(o, text) for o in owners])' in src
    assert 'title and why and title.lower() not in why.lower()' in src
