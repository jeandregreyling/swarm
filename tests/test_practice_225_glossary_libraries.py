"""The glossary knows JD's words for the file and model libraries."""
import json
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / 'core' / 'capability_packs' / 'hb.glossary.v1.json'


def test_library_words_point_to_the_libraries():
    terms = json.loads(PACK.read_text())['terms']
    where = {w: t['where'] for t in terms for w in t['words']}
    assert '/srv/archive/HB-Library/INDEX.md' in where['library'] and 'hb://library' in where['files']
    assert '/srv/archive/models/MODELS.md' in where['unbounded'] and 'hb_model_jobs' in where['who does what']
