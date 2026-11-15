"""Practice 88 (owner 16 Nov 2026): the SAP notes test run failed 7 of its first 20 notes. HB runs without the desktop session bus, so
the fetch script could not read the SAP login from the keyring once the saved SAP session expired, and the D-Bus error counted as a failed
note. Now the script is pointed at the user's session bus, and a keyring error is a sign-in failure, which stops the job at once."""
import os

from core import hb_sap_notes as n
from core import hb_sap_note_job as j


class Done:
    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_practice_88_the_fetch_script_gets_the_session_bus(monkeypatch):
    monkeypatch.delenv('DBUS_SESSION_BUS_ADDRESS', raising=False)
    seen = {}

    def run(cmd, **kw):
        seen.update(kw)
        return Done('SAP Note 3640475: Title')
    assert n.fetch('3640475', run) == (True, 'SAP Note 3640475: Title')
    bus = f'/run/user/{os.getuid()}/bus'
    if os.path.exists(bus):
        assert seen['env']['DBUS_SESSION_BUS_ADDRESS'] == f'unix:path={bus}'
    assert 'PATH' in seen['env']


def test_practice_88_an_existing_session_bus_is_kept(monkeypatch):
    monkeypatch.setenv('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/somewhere/else')
    assert n._env()['DBUS_SESSION_BUS_ADDRESS'] == 'unix:path=/somewhere/else'


def test_practice_88_a_keyring_error_is_a_sign_in_failure_and_stops_the_job():
    err = 'Traceback ...\ngi.repository.GLib.GError: g-io-error-quark: Cannot autolaunch D-Bus without X11 $DISPLAY (0)'
    ok, text = n.fetch('3640475', lambda cmd, **kw: Done(stderr=err, returncode=1))
    assert not ok and text.startswith('SAP sign-in failed: HB could not open the keyring')
    assert n.fetch('3640475', lambda cmd, **kw: Done(stderr='x\nSAP could not be reached: ConnectTimeout', returncode=3)) == \
        (False, 'SAP could not be reached: ConnectTimeout')
