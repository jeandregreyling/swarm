"""Lock the home-tile click contract: clicking a tile must focus an
existing window rather than spawn a duplicate (S-88A6C8C18A acceptance).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_APP_JS = Path(__file__).resolve().parents[1] / 'frontend/static/js/core/app.js'


@pytest.fixture(scope='module')
def src() -> str:
    return _APP_JS.read_text(encoding='utf-8')


def test_openwindow_focus_existing(src: str):
    """openWindow must focus an existing same-id window before creating a new one."""
    # Existing branch: if(existing) winManager.focus(windowKey);
    assert re.search(r'if\s*\(\s*existing\s*\)\s*\{\s*[^}]*winManager\.focus', src, re.DOTALL), \
        'openWindow should call winManager.focus when a non-multi window already exists.'


def test_openwindow_restore_minimised(src: str):
    """If the existing window is minimised, openWindow must restore it (toggle minimize)."""
    assert re.search(r'existing\.minimized[^}]*winManager\.minimize', src, re.DOTALL), \
        'openWindow should toggle minimize() on an already-minimised existing window.'


def test_openwindow_skips_duplicate_create(src: str):
    """The early return must guard against falling through to winManager.create()."""
    # Find the openWindow body and make sure both existing branches return.
    m = re.search(r'function openWindow\([^)]*\)\s*\{(?P<body>.+?)\nfunction\s', src, re.DOTALL)
    assert m, 'Could not locate openWindow function body.'
    body = m.group('body')
    # Both existing branches must include `return;`
    minimized_branch = re.search(r'existing\s*&&\s*existing\.minimized\s*\)\s*\{[^}]*return;', body, re.DOTALL)
    focus_branch    = re.search(r'if\s*\(\s*existing\s*\)\s*\{[^}]*return;', body, re.DOTALL)
    assert minimized_branch, 'Minimised-existing branch must early-return to skip create.'
    assert focus_branch,     'Existing-window focus branch must early-return to skip create.'


def test_openwindow_exposed_globally(src: str):
    assert 'window.openWindow = openWindow' in src
