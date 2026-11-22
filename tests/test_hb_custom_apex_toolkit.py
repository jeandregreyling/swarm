"""Tests for APEX's Grand Gift Toolkit (0 Nectar tax) + Flying Hummingbirds & Flowers celebration overlay."""
from pathlib import Path
import subprocess

from core import hb_custom_tools

ROOT = Path(__file__).resolve().parents[1]


def test_custom_apex_toolkit_gift_all_five_actions(tmp_path, monkeypatch):
    names = [t['name'] for t in hb_custom_tools.list_tools()]
    assert 'custom_apex_toolkit' in names
    lint = hb_custom_tools.invoke('custom_apex_toolkit', {'action': 'lint_check', 'path': 'core/hb_nectar.py'})
    assert lint['ok'] is True and lint['lines'] > 50
    search = hb_custom_tools.invoke('custom_apex_toolkit', {'action': 'smart_search', 'query': 'reconcile_shadow'})
    assert search['ok'] is True and search['definitions'] >= 1
    trophy = hb_custom_tools.invoke('custom_apex_toolkit', {'action': 'trophy'})
    assert trophy['ok'] is True and '0 Nectar Tax' in trophy['award']
    prio = hb_custom_tools.invoke('custom_apex_toolkit', {'action': 'prioritize_tasks', 'limit': 5})
    assert prio['ok'] is True and '0 Nectar tax' in prio['gift']
    bad_test = tmp_path / 'bad_test.py'
    bad_test.write_text('def test_x():\n    s = ImaginaryStudio()\n    assert s\n', encoding='utf-8')
    from core.hb_custom_tools import custom_apex_toolkit as tk
    monkeypatch.setattr(tk, 'ROOT', tmp_path)
    pred = tk.run({'action': 'predict_mistakes', 'path': 'bad_test.py'})
    assert pred['ok'] is False and any('ImaginaryStudio' in w for w in pred['warnings'])


def test_flying_hummingbirds_and_flowers_celebration_in_hb_live_js():
    js_path = ROOT / 'frontend/static/js/hb-live.js'
    js = js_path.read_text(encoding='utf-8')
    assert 'window.hbLaunchCelebration' in js
    assert 'hb-flyer' in js and 'hb-petal' in js
    assert 'prefers-reduced-motion' in js
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
