"""Practice 204: the gold approval pop-up has real buttons."""
from pathlib import Path


def test_gold_popup_can_approve():
    js = (Path(__file__).resolve().parents[1] / 'frontend/static/js/views/hb-approval-popup.js').read_text()
    assert 'data-q="accept"' in js and ">Approve</button>" in js and "fetch('/api/peer/v1/hb/queue'" in js
    assert "getElementById('hb-live-pane')" in js
