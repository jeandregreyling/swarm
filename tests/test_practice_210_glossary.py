"""Practice 210: JD's everyday words reach APEX's card as HB parts and file paths."""
import json
from pathlib import Path

from core.hb_learning import glossary_for

ROOT = Path(__file__).resolve().parents[1]


def test_ribbon_and_clipboard_map_to_files():
    g = glossary_for('I hate that the ribbon needs a drag, and the clipboard is empty')
    assert 'frontend/static/js/hb-live.js' in g and 'core/hb_clipboard.py' in g and g.startswith("JD's words")


def test_no_match_no_noise():
    assert glossary_for('what is wage type /XQE?') == ''
    assert glossary_for('the pipeline') == ''          # "pipe" words do not match "pane"/"plan" by accident


def test_every_path_in_the_glossary_exists():
    pack = json.loads((ROOT / 'core/capability_packs/hb.glossary.v1.json').read_text())
    import re
    for term in pack['terms']:
        for path in re.findall(r'(?:core|frontend|scripts)/[\w/.-]+\.(?:py|json|js)\b', term['where']):
            assert (ROOT / path).is_file(), path


def test_cards_carry_it():
    assert 'glossary_for' in (ROOT / 'core/hb_dream_method.py').read_text()
    assert 'glossary_for(said)' in (ROOT / 'core/hb_owner_intent.py').read_text()
