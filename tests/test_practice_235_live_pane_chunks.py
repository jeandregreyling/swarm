"""Practice 235: the Live pane shows chunk n of N for every worker and every row.

Stage 1 (Practice 234) put every task's chunks in the live snapshot:
  item.chunks = {total, done, doing, next, list}

This test verifies:
  1. Active worker cards show 'chunk n/N: <text>' with CSS progress dots
     (span.hb-chunk-dot.done / .doing / .todo - no glyph characters).
  2. Clipboard rows show 'n/N' next to the title and the current chunk as subtitle.
  3. Rows and workers without chunks render exactly as before (no chunk markup).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'

# Snapshot with chunks on some items, none on others.
SNAP = {
    'at': 2000,
    'lanes': [
        {'id': 'gpu', 'label': 'GPU \u00b7 APEX', 'state': 'busy', 'items': [
            {'actor': 'apex', 'model': 'swift-qwen3.8-27b', 'device': 'ROCm',
             'title': 'APEX: chunk task', 'since': 1900, 'purpose': 'main-chat turn',
             'last_step': 'working on chunk 2',
             'chunks': {'total': 5, 'done': 1, 'doing': 2, 'next': 'write the test file',
                        'list': ['write the test file', 'patch hb-live.js', 'patch CSS', 'run test', 'verify']},
             'trail': []},
        ]},
        {'id': 'fred', 'label': 'CPU \u00b7 Fred', 'state': 'idle', 'items': [
            {'actor': 'fred', 'model': 'mistral-24b', 'device': 'CPU',
             'title': 'Fred: no chunks', 'since': 1800, 'purpose': 'review',
             'last_step': 'reading', 'trail': []},
        ]},
    ],
    'needs_you': [],
    'master': {'on': True, 'auto': False, 'items': [
        {'step_id': 'S-100', 'task_id': 'T-100', 'title': 'Chunk task', 'state': 'now', 'doer': 'apex',
         'live': {'lane': 'gpu', 'last_step': 'working on chunk 2'},
         'chunks': {'total': 5, 'done': 1, 'doing': 2, 'next': 'write the test file',
                    'list': ['write the test file', 'patch hb-live.js', 'patch CSS', 'run test', 'verify']}},
        {'step_id': 'S-200', 'task_id': 'T-200', 'title': 'No chunk task', 'state': 'waiting', 'doer': 'fred',
         'live': {'lane': 'fred', 'last_step': 'reading'}},
    ]},
    'history': [],
    'unexplained': [],
    'telemetry': {'gpu': {'busy_pct': 40, 'temp_c': 50, 'vram_used_gb': 10, 'vram_total_gb': 16},
                  'cpu': {'load1': 1.0, 'cores': 16}, 'ram': {'used_gb': 20, 'total_gb': 64}},
}


def _node(expr, snap=None):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    s = snap if snap is not None else SNAP
    code = f"const R=require({json.dumps(str(JS))}); const snap={json.dumps(s)}; process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_worker_card_shows_chunk_label_and_dots():
    """Active worker with chunks shows 'chunk 2/5: write the test file' and dot spans."""
    html = _node('R.renderActive(snap, 2000)')
    # The chunk label text
    assert 'chunk 2/5' in html
    assert 'write the test file' in html
    # CSS progress dots (no glyph characters)
    assert 'hb-chunk-dot' in html
    assert 'hb-chunk-dot done' in html
    assert 'hb-chunk-dot doing' in html
    assert 'hb-chunk-dot todo' in html
    # No glyph characters in the dot markup
    dot_section = html[html.index('hb-chunk-dot'):]
    # The dots themselves should not contain unicode glyphs like \u25cf or \u25cb
    assert '\u25cf' not in dot_section[:200]
    assert '\u25cb' not in dot_section[:200]


def test_worker_without_chunks_has_no_chunk_markup():
    """Fred's card (no chunks) renders without any chunk dot or label."""
    html = _node('R.renderActive(snap, 2000)')
    # Find Fred's card section (card body, not the top summary chip)
    fred_idx = html.index('<div class="hbl-item-title">Fred: no chunks')
    fred_section = html[fred_idx:fred_idx + 500]
    assert 'hb-chunk-dot' not in fred_section
    assert 'chunk ' not in fred_section


def test_clipboard_row_shows_n_of_n_and_chunk_subtitle():
    """Clipboard row with chunks shows '1/5' next to title and chunk text as subtitle."""
    html = _node('R.renderList(snap)')
    # The n/N indicator
    assert '1/5' in html
    # The current chunk text as subtitle
    assert 'write the test file' in html


def test_clipboard_row_without_chunks_unchanged():
    """Row without chunks has no n/N indicator and no chunk subtitle."""
    html = _node('R.renderList(snap)')
    # Find the 'No chunk task' row
    idx = html.index('No chunk task')
    row_section = html[idx:idx + 300]
    assert '1/5' not in row_section
    assert 'hb-chunk-dot' not in row_section


def test_chunk_dots_count_matches_total():
    """The number of dot spans equals the total chunk count."""
    html = _node('R.renderActive(snap, 2000)')
    # Count all hb-chunk-dot spans in the APEX card area
    apex_idx = html.index('APEX: chunk task')
    apex_section = html[apex_idx:apex_idx + 1000]
    dot_count = apex_section.count('hb-chunk-dot')
    # total=5, so 5 dots
    assert dot_count == 5


def test_no_glyph_characters_in_chunk_dots():
    """Brand rule: chunk dots use CSS classes only, no unicode glyph characters."""
    html = _node('R.renderActive(snap, 2000)')
    # Extract all dot span elements
    import re
    dots = re.findall(r'<span class="hb-chunk-dot[^"]*">(.*?)</span>', html)
    for d in dots:
        # Each dot span should be empty or contain only whitespace
        assert d.strip() == '', f'Dot contains glyph: {repr(d)}'
