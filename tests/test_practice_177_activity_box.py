"""Practice 177: the live activity box grows with its text and stays readable."""
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live-activity.js').read_text()


def test_box_does_not_shrink_and_grows_with_text():
    assert 'flex:0 0 auto' in JS and 'max-height:40vh' in JS and 'max-height:160px' not in JS
    assert 'color:var(--text-dim' not in JS.split('box.style.cssText', 1)[1].split(';\n', 1)[0]


def test_box_sits_under_the_main_chat_bubble_and_follows_the_bottom():
    assert ".hc-bubble[data-pending-job-id]" in JS
    assert 'atBottom' in JS and 'host.scrollTop = host.scrollHeight' in JS
