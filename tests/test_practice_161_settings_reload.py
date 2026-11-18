"""Practice 161 (owner 18 Nov 2026: "I don't want to manually swap models, this should be done via HB automatically"): HB reloads APEX
by itself when the playing model's prescribed settings changed, only while APEX is idle and at most once per half hour."""
import sqlite3

from core import hb_apex_swap as s

ROWS = [{'name': 'swift-qwen3.8-27b', 'path': '/m/s', 'template': None, 'size_gb': 12.1, 'fits': True}]
OLD = 'Description=APEX swift-qwen3.8-27b Vulkan llama-server\\nExecStart=/x -m /m/s --jinja -b 2048 -ub 1024 --no-webui\\n'


def test_practice_161_reload_when_settings_differ():
    c, said, calls = sqlite3.connect(':memory:'), [], []
    out = s.settings_tick(c, now=10_000, idle=lambda: True, swapper=lambda n, say: (calls.append(n) or (True, 'APEX is now ' + n)),
                          say=said.append, rows=ROWS, text=OLD)
    assert calls == ['swift-qwen3.8-27b'] and '-b 512' in said[0] and said[-1].startswith('Done:')
    assert s.settings_tick(c, now=10_100, idle=lambda: True, swapper=lambda n, say: (calls.append(n) or (True, '')),
                           say=said.append, rows=ROWS, text=OLD) is None and calls == ['swift-qwen3.8-27b']


def test_practice_161_nothing_when_settings_match_or_busy():
    c, calls = sqlite3.connect(':memory:'), []
    same = s.render(OLD, ROWS[0])
    assert s.settings_tick(c, now=10_000, idle=lambda: True, swapper=lambda n, say: calls.append(n), say=print, rows=ROWS, text=same) is None
    assert s.settings_tick(c, now=10_000, idle=lambda: False, swapper=lambda n, say: calls.append(n), say=print, rows=ROWS, text=OLD) is None
    assert calls == []
