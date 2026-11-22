"""Practice 284 (JD 22 Nov: "homework should have the actor title such as ... a business analyst ... so the homework BA knows how to spec and
interrogate these tasks properly, design and scope before delivering ... chunking knowledge to HB's task board for APEX"): homework is HB's
BA. It interrogates each task in a fixed order - goal, scope in/out, design, risks, check, chunks - HB refuses a spec without scope or with a
design that names no real file, and APEX's card shows the whole spec."""
import json

from core import hb_background, hb_homework as hw

FACTS = {'files': [{'path': 'frontend/static/js/views/hb-needs-you.js', 'lines': []}], 'done_when': ['tests/test_x.py passes']}
CARD = {'goal': 'Make waiting approvals visible in the header', 'check': 'tests/test_x.py passes',
        'scope_in': ['the header dial in hb-needs-you.js'], 'scope_out': ['the Telegram bot'],
        'design': ['dial() in frontend/static/js/views/hb-needs-you.js adds a glow class when approvals wait'],
        'risks': ['the dial redraws every 2 s'], 'plan': ['run tests/test_x.py and read the first failure', 'in frontend/static/js/views/hb-needs-you.js change dial()'],
        'files': ['frontend/static/js/views/hb-needs-you.js'], 'questions': [], 'doer': 'apex', 'importance': 4, 'why': 'x'}


def test_homework_is_hbs_ba_everywhere_jd_reads_it():
    assert 'BA' in hb_background.ROLE['homework'] and 'Shakira' in hb_background.ROLE['homework']
    system = hw.prompt({'title': 't', 'objective': 'o'}, FACTS)[0]['content']
    assert "HB's business analyst (BA)" in system
    for step in ('1. GOAL', '2. SCOPE', '3. DESIGN', '4. RISKS', '5. CHECK', '6. CHUNKS'):
        assert step in system, step
    for field in ('scope_in', 'scope_out', 'design', 'risks'):
        assert field in hw.SCHEMA['required']


def test_hb_refuses_a_spec_without_scope_or_with_a_design_on_no_real_file():
    assert hw.judge(dict(CARD), FACTS)[0]
    assert any('no scope' in w for w in hw.judge({**CARD, 'scope_in': []}, FACTS)[1])
    assert any('design names no real file' in w for w in hw.judge({**CARD, 'design': ['make it glow somehow']}, FACTS)[1])


def test_apexs_card_shows_the_whole_ba_spec():
    text = hw.summary({**CARD, 'model': 'homework-cpu:7b', 'ready': True, 'facts': FACTS})
    assert text.startswith('BA spec (by homework-cpu:7b on the CPU; READY):')
    for word in ('- in scope: the header dial', '- out of scope: the Telegram bot', '- design: dial() in', '- risks: the dial redraws'):
        assert word in text, word
