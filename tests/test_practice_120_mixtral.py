"""Practice 120 (17 Nov 2026): HB's Mixtral 8x7B could never load ("tensor 'blk.0.ffn_down_exps.weight' not found" - the Dec 2023 file stores each
expert separately). The new file (current layout, SHA-256 checked) loads and answers; the registry and the benchmark now point at it."""
from pathlib import Path

from core import hb_model_bench as mb
from core.seven_llm import registry

NEW = '/srv/archive/models/gguf/mixtral-8x7b-instruct-v2/Mixtral-8x7B-Instruct-v0.1-Q4_K_M.gguf'


def test_practice_120_mixtral_points_at_the_new_file():
    assert dict(mb.EXTRA)['mixtral-8x7b-instruct'] == NEW
    entry = registry.get('mixtral-cpu:8x7b')
    assert entry is not None and str(entry.path) == NEW and entry.options['ngl'] == 0
    if Path(NEW).exists():
        assert Path(NEW).stat().st_size == 28448467808
