"""V7C-A04 — Monitor health-check visibility.

Project: P-E9BAE4159F
Step:    S-42D0BC0EB1

Audit: user must SEE health-state deltas (not just raw numbers).
- CPU temp warning label toggles ('High Temp Warning' vs 'Temp OK')
- Service Health row colour: green / amber / red by state
- Inference insights panel surfaces advisories
- Model Residency count visible
- Timestamp shown after each refresh (last update = trust anchor)
"""
from pathlib import Path

MON = (Path(__file__).resolve().parents[1] / 'frontend' / 'static' / 'js' / 'views' / 'monitor.js').read_text()


def test_a04_r1_temp_warning_label():
    assert "'High Temp Warning'" in MON
    assert "'Temp OK'" in MON
    assert "> 80" in MON


def test_a04_r2_service_row_colour_states():
    # Green active, amber activating, red down — three visible states.
    assert "'#4caf50'" in MON  # active green
    assert "'activating'" in MON
    assert "'#ffb366'" in MON  # amber
    assert "'#ff6b6b'" in MON  # red


def test_a04_r3_insights_panel_visible():
    assert "mn-insights" in MON
    assert "monitor_insights" in MON
    # Empty-state fallback renders, not blank.
    assert "No advisory insights." in MON


def test_a04_r4_model_residency_count():
    assert "mn-models-count" in MON
    assert "active_models_count" in MON


def test_a04_r5_timestamp_trust_anchor():
    assert "mn-timestamp" in MON
    assert "Updated" in MON
    assert "data.last_activity" in MON or "data.timestamp" in MON


def test_a04_r6_alm_governance_visible():
    assert "monitor-alm-status" in MON
    assert "ALM Governance" in MON


def test_a04_r7_activity_scrollable():
    # Health UX: activity has scroll so history is browsable.
    assert "max-height:200px" in MON
    assert "overflow-y:auto" in MON
