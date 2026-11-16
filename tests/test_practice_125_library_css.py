"""Practice 125 (owner 17 Nov 2026, audit review): the file audit's one real non-colour finding - #library-header-right was defined twice,
word for word. One copy is enough."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / 'frontend/static/css/library.css').read_text()


def test_practice_125_library_header_rule_once():
    assert len(re.findall(r'(^|\n)\s*#library-header-right\s*\{', CSS)) == 1
    body = re.sub(r'/\*.*?\*/', '', CSS, flags=re.S)
    assert body.count('{') == body.count('}')
