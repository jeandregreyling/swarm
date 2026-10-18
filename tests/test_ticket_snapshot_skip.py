import importlib.util
import pathlib
import re
import sys


def _load():
    src = pathlib.Path('frontend/blueprints/chat.py').read_text()
    start = src.index('def _should_attach_ticket_snapshot')
    end = src.index('def _build_ticket_snapshot_block')
    ns = {'re': re}
    exec(src[start:end], ns)
    return ns['_should_attach_ticket_snapshot']


def test_explicit_skill_line_skips_snapshot():
    f = _load()
    assert not f('Use the shell skill: SKILL shell python3 x "select status from t"', [])
    assert f('what is the ticket status?', [])


def test_data_questions_skip_snapshot():
    f = _load()
    assert not f('how many project steps are done, what status?', [])
    assert f('give me a status update on tickets', [])
