"""V7C-R14 + A06 — Vortex / governance affordances.

Project: P-E9BAE4159F
Steps:   S-905D8574E9 (R14), S-249B6C4E05 (A06)

Locks:
  - Vortex has an inline help (?) button wired to openWindowHelp/openDocs
  - History side panel is collapsible via tw-toggle-history
  - Checkpoint capture / dry run / apply step-back all wired
  - Timeline supports text search + state filter
  - Slider-based inspect + labelled readout
  - Auto-refresh opt-in (not forced)
  - Timeline loader bound to loadTimeWizardData
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TPL = (ROOT / 'frontend' / 'templates' / 'views' / 'time-wizard.html').read_text()


def test_r14_r1_help_button():
    assert 'id="tw-help-btn"' in TPL
    assert "openWindowHelp==='function'" in TPL
    assert "'time-wizard'" in TPL


def test_r14_r2_history_collapsible():
    assert 'id="tw-toggle-history"' in TPL
    assert 'id="tw-history-panel"' in TPL
    assert "dataset.collapsed" in TPL


def test_r14_r3_checkpoint_capture():
    assert 'createTwCheckpoint()' in TPL
    assert 'Capture Checkpoint' in TPL


def test_r14_r4_dry_run_and_apply():
    assert 'previewTwCheckpoint(true)' in TPL
    assert 'applyTwRestore()' in TPL
    # Destructive action visually distinguished (amber).
    assert '#f59e0b' in TPL


def test_r14_a06_search_and_filter():
    assert 'id="tw-search"' in TPL
    assert 'id="tw-filter"' in TPL
    assert 'EXECUTED' in TPL and 'PROPOSED' in TPL


def test_r14_r6_slider_with_label():
    assert 'id="tw-slider"' in TPL
    assert 'id="tw-slider-label"' in TPL


def test_r14_r7_auto_refresh_optin():
    # Auto refresh must be a checkbox (off by default), not forced.
    assert 'id="tw-auto-refresh"' in TPL
    assert 'setTwAutoRefresh(this.checked)' in TPL
    assert 'loadTimeWizardData()' in TPL
