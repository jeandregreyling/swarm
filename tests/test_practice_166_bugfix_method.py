"""Practice 166 (owner 18 Nov 2026: "teach apex how to spot the bugs and fix them"): 'Bug:' tasks carry HB's bug-fix method."""
from core import hb_learning


def test_practice_166_bugfix_method():
    m = hb_learning.bugfix_method()
    assert m.startswith('Bug-fix method (follow it): (1) Reproduce first')
    for must in ('run_tests', 'read_file', 'propose_patch', 'never weaken a test', 'do not guess a fix'):
        assert must in m


def test_practice_166_card_attaches_it():
    src = open('core/hb_dream_method.py').read()
    assert "startswith('bug:')" in src and 'bugfix_method()' in src
