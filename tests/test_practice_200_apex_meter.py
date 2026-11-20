"""Practice 200: the APEX meter shows live token counts; the page reloads after an HB restart."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core import hb_live

JS = Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live.js'


def test_apex_live_reads_the_slot():
    slot = [{'is_processing': True, 'n_prompt_tokens': 15449, 'n_prompt_tokens_processed': 9000, 'n_prompt_tokens_cache': 0, 'n_ctx': 37632,
             'id_task': 7, 'next_token': [{'n_decoded': 0}]}]
    a = hb_live.apex_live(fetch=lambda: slot)
    assert a['up'] and a['busy'] and a['prompt_tokens'] == 15449 and a['prompt_done'] == 9000 and a['ctx'] == 37632
    assert hb_live.apex_live(fetch=lambda: (_ for _ in ()).throw(OSError('down'))) == {'up': False}


def test_meter_renders_reading_writing_and_idle():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    reading = {'up': True, 'busy': True, 'prompt_tokens': 15449, 'prompt_done': 9000, 'prompt_cached': 0, 'generated': 0, 'ctx': 37632,
               'model': 'swift-qwen3.8-27b', 'device': 'ROCm'}
    writing = dict(reading, prompt_done=15449, generated=342)
    idle = dict(reading, busy=False)
    code = (f"const R=require({json.dumps(str(JS))}); process.stdout.write(JSON.stringify([R.renderMeter({json.dumps(reading)}, 300),"
            f" R.renderMeter({json.dumps(writing)}, 24.6), R.renderMeter({json.dumps(idle)}), R.renderMeter({{up:false}})]))")
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-500:]
    r, w, i, d = json.loads(out.stdout)
    assert 'reading' in r and '9,000 / 15,449 tokens' in r and '300 tok/s' in r and 'swift-qwen3.8-27b' in r
    assert 'writing</b> 342 tokens' in w and '24.6 tok/s' in w and 'context 15,791 / 37,632' in w
    assert 'idle' in i and 'not answering' in d
    assert 'location.reload()' in JS.read_text()
