"""Practice 62 (owner 15 Nov): /note <number> looks up an SAP Note through the separate sign-in script and keeps it in the KC."""
import subprocess
from pathlib import Path
import core.hb_sap_notes as n
import core.hb_commands as cmds

ROOT = Path(__file__).resolve().parents[1]


class Done:
    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_practice_62_fetch_runs_the_sign_in_script_as_its_own_process():
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return Done('SAP Note 2382421: Optimizing the Network\ncomponent HAN-DB\nSymptom ...')
    ok, text = n.fetch('2382421', run)
    assert ok and text.startswith('SAP Note 2382421')
    assert calls == [['/usr/bin/python3', str(ROOT / 'scripts/hb_sap_note.py'), '2382421']]
    assert n.fetch('rm -rf', run) == (False, 'Give a note number, for example /note 2382421.') and len(calls) == 1


def test_practice_62_failures_are_said_plainly():
    assert n.fetch('1234567', lambda cmd, **kw: Done(stderr='x\nSAP sign-in failed: SAP asks for a second factor', returncode=2)) == \
        (False, 'SAP sign-in failed: SAP asks for a second factor')

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 180)
    assert n.fetch('1234567', slow) == (False, 'SAP did not answer in 3 minutes.')
    assert n.command(None, '1234567', slow).startswith('SAP Note 1234567: SAP did not answer')


def test_practice_62_command_shows_the_note_and_keeps_it():
    kept = []
    out = n.command('conn', '2382421', lambda cmd, **kw: Done('SAP Note 2382421: Title\n' + 'line\n' * 900),
                    keep=lambda conn, number, text: kept.append((conn, number, len(text))) or 77)
    assert out.startswith('SAP Note 2382421: Title') and '[...]' in out and out.endswith('(KC77); every model can read it there.')
    assert kept and kept[0][:2] == ('conn', '2382421')


def test_practice_62_no_secret_handling_here_and_note_is_a_command():
    src = (ROOT / 'core/hb_sap_notes.py').read_text()
    assert 'hb_secure_creds' not in src and 'password_lookup' not in src and 'import requests' not in src
    assert 'note' in cmds.NAMES and cmds.parse('note 2382421') == ('note', ['2382421']) and cmds.parse('note') is None
