"""Telegram native inline Approve / Hold buttons bound to exact Studio step IDs via callback_query."""
import json
import sqlite3

from core import hb_channels as ch


def test_telegram_buttons_builds_inline_keyboard_for_exact_step_id():
    markup = ch.telegram_buttons('QA passed. /accept S-AABBCC1122 approves it; /pause T-112233445566 holds it.')
    assert markup is not None
    row = markup['inline_keyboard'][0]
    assert row[0]['callback_data'] == '/accept S-AABBCC1122'
    assert '🌺 Approve S-AABBCC1122' in row[0]['text']
    assert row[1]['callback_data'] == '/pause T-112233445566'
    assert ch.telegram_buttons('Plain chat message without commands') is None


def test_telegram_send_attaches_reply_markup_and_poll_handles_callback_query():
    sent = []
    def fake_call(method, payload=None, timeout=20):
        sent.append((method, payload))
        if method == 'getUpdates':
            return {'ok': True, 'result': [{
                'update_id': 500,
                'callback_query': {
                    'id': 'cb-99',
                    'from': {'username': 'jd'},
                    'message': {'chat': {'id': 12345}},
                    'data': '/accept S-AABBCC1122',
                },
            }]}
        return {'ok': True}

    assert ch.telegram_send(12345, 'Ready: /accept S-AABBCC1122', call=fake_call) is True
    assert 'reply_markup' in sent[0][1]
    kb = json.loads(sent[0][1]['reply_markup'])
    assert kb['inline_keyboard'][0][0]['callback_data'] == '/accept S-AABBCC1122'

    conn = sqlite3.connect(':memory:')
    ch.ensure(conn)
    handled = []
    def fake_handle(c, channel, key, name, text):
        handled.append((channel, key, name, text))
        return 'Accepted S-AABBCC1122 (Liquid-Glass Drawers)!'

    count = ch.telegram_poll_once(conn, call=fake_call, handle=fake_handle)
    assert count == 1
    assert handled == [('telegram', 'telegram:12345', 'jd', '/accept S-AABBCC1122')]
    assert any(m == 'answerCallbackQuery' and p.get('callback_query_id') == 'cb-99' for m, p in sent)
    assert any(m == 'sendMessage' and 'Accepted S-AABBCC1122' in p.get('text', '') for m, p in sent)
