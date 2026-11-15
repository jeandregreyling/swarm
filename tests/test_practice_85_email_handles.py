"""Practice 85 (owner 15 Nov 2026): JD pasted an email and HB replied "HB does not know @deloitte.com.au yet ... HB does not know
@gmail.com yet". An email address is not an @handle; real handles still work."""
import sqlite3

from core import hb_agents
from core.hb_owner_intent import classify

EMAIL = ("Jeandre Greyling  Senior Consultant\njgreyling@example.com.au | www.example.com.au\n"
         "From: Greyling, Jeandre To: Jeandre <someone@gmail.com>; Node <node9@gmail.com>\n"
         "Subject: FW: SAP notes F9 to G4 - onboarding pack, public no breach of privacy")


def test_practice_85_email_addresses_are_not_handles():
    assert hb_agents.HANDLE_RE.findall(EMAIL) == []
    assert hb_agents.HANDLE_RE.findall('onboard @github please, and @git.') == ['github', 'git']
    assert hb_agents.HANDLE_RE.findall('(@codex) and @mistral-vibe') == ['codex', 'mistral-vibe']


def test_practice_85_a_pasted_email_is_not_an_onboarding_request():
    assert classify(EMAIL) != 'agents'
    assert classify('@apex can you onboard the @github identity') == 'agents'


def test_practice_85_hb_says_nothing_about_unknown_handles_for_an_email():
    conn = sqlite3.connect(':memory:')
    assert hb_agents.onboard_request(conn, 1, EMAIL, 'jd via chat') is None
