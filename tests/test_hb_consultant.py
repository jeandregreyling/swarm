"""Practice 43 (owner 12 Nov): consultant protocol - acknowledge at once, four labelled options checked by plain Python, choice recorded."""
import json
import sqlite3
import core.hb_consultant as k
import core.hb_commands as cmds

GOOD = {'options': [{'label': l, 'title': 't', 'reasons': 'r', 'risk': 'low', 'effort': 'S', 'evidence': 'e'} for l in k.LABELS]}


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    return c


def test_practice_43_shape_check_is_deterministic():
    assert k.validate(GOOD) == [] and k.validate(json.dumps(GOOD)) == []
    assert k.validate('not json') == ['the answer is not JSON']
    three = {'options': GOOD['options'][:3]}
    assert any('four labels' in p for p in k.validate(three))
    bad = json.loads(json.dumps(GOOD)); bad['options'][3]['evidence'] = ' '
    assert k.validate(bad) == ['option 4 is missing: evidence']


def test_practice_43_wrong_shape_goes_back_to_the_same_model_with_the_format():
    seen = []

    def model(messages):
        seen.append(messages)
        return 'I think you should...' if len(seen) == 1 else json.dumps(GOOD)
    options, attempts = k.ask(model, 'How should we price the payroll audit?')
    assert attempts == 2 and len(options) == 4
    assert k.FORMAT in seen[1][-1]['content'] and 'rejected' in seen[1][-1]['content']


def test_practice_43_gives_up_after_the_retries():
    calls = []
    try:
        k.ask(lambda m: calls.append(1) or '{}', 'How should we price the payroll audit?')
        assert False
    except ValueError:
        assert len(calls) == k.RETRIES + 1


def test_practice_43_acknowledge_investigate_choose():
    c = db()
    ack = k.open_consultation(c, 7, 'How should we price the payroll audit?', 'jd')
    assert ack.startswith('👋 I am looking at it.') and 'four options' in ack
    cid = c.execute('SELECT consult_id FROM hb_consultations').fetchone()[0]
    assert k.investigate(c, cid, model=lambda m: json.dumps(GOOD)) == 'options'
    posted = c.execute('SELECT content FROM messages WHERE conversation_id=7').fetchone()[0]
    assert f'/choose {cid} N' in posted and '1. Recommended:' in posted and '4. Dream:' in posted
    assert 'option 2 (possible 1' in k.choose(c, cid, 2, 'jd')
    assert c.execute('SELECT state, choice FROM hb_consultations').fetchone() == ('chosen', 2)
    assert k.choose(c, 'C-NOPE', 1, 'jd') == 'No consultation C-NOPE.'


def test_practice_43_commands_are_known():
    assert {'consult', 'choose'} <= set(cmds.NAMES)
    assert cmds.parse('consult How should we price the payroll audit?') == ('consult', ['How should we price the payroll audit?'])
    assert cmds.parse('choose c-1a2b3c4d 3') == ('choose', ['C-1A2B3C4D', '3'])
