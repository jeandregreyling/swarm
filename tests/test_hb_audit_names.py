"""Practice 79 (audit): the names HB's tools advertise match what they accept."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _accepted():
    return re.search(r'gemini_reload accepts only provider_model ([\w.-]+)', (ROOT / 'core' / 'hb_peer_control.py').read_text()).group(1)


def test_apex_schema_offers_the_model_gemini_reload_accepts():
    tools = (ROOT / 'core' / 'apex_tools.py').read_text()
    assert f'"enum":["{_accepted()}"]' in tools


def test_apex_tool_description_names_the_same_model():
    assert f'verified endpoint {_accepted()}' in (ROOT / 'core' / 'apex_tools.py').read_text()


def test_no_tool_advertises_a_model_the_reload_rejects():
    tools = (ROOT / 'core' / 'apex_tools.py').read_text()
    assert 'gemini-2.5-flash"]' not in tools and 'endpoint gemini-2.5-flash' not in tools
