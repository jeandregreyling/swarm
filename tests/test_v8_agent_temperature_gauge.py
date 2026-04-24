"""V8 S-FAFF08FF9A: per-agent temperature gauge moved into Agents detail view."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'access.js'


def test_agents_detail_has_temperature_gauge():
    src = ACCESS_JS.read_text()
    assert 'id="agent-temp-block"' in src
    assert 'id="agent-temperature"' in src
    assert 'id="agent-temperature-readout"' in src
    assert 'id="agent-temperature-apply"' in src
    # Calls the per-agent temperature endpoint.
    assert "/temperature" in src
    assert "'Content-Type':'application/json'" in src
