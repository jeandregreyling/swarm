"""Practice 73 (owner 15 Nov): "why can't I queue messages yet" - a message typed while HB is answering waits in a visible outbox
(first / edit / remove) and is sent by itself afterwards; it is no longer dropped."""
import subprocess
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / 'frontend/static/js/views/home-chat.js'


def test_practice_73_a_second_message_waits_instead_of_being_dropped():
    src = JS.read_text()
    assert 'if (_hcSending) { _hcOutboxAdd(); return; }' in src and 'if (_hcSending) return;' not in src
    assert 'sendBtn && (sendBtn.disabled = true);' not in src            # the button stays usable while HB answers
    assert 'setTimeout(_hcOutboxNext, 150);' in src


def test_practice_73_outbox_is_visible_and_editable():
    src = JS.read_text()
    for piece in ("id = 'home-chat-outbox'", 'data-outbox="first"', 'data-outbox="edit"', 'data-outbox="remove"', 'Waiting to send (', 'const draft = input.value;'):
        assert piece in src, piece
    assert '${_hcEsc(text)}' in src                                       # typed text is escaped before it is shown


def test_practice_73_script_still_parses():
    done = subprocess.run(['node', '--check', str(JS)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-400:]
