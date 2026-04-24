"""V8 Phase-5 MED code-change guards.

Covers real code changes landed this pass:

* S-0566553752 — Theme timeline 00-06 fill. Hours 03-05 now resolve to
   'morning' instead of 'night', and the mapping is exported as
   `FRIDAYS_HOUR_PHASE_MAP` for downstream surfaces.
* S-7622B4B16D — Vortex view gains an inline `?` help button and a
   collapsible history side panel.
* S-F1055E7A86 — Studio Git files/diff split is resizable via a
   `#git-files-resizer` drag handle.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'theme.js'
VORTEX_HTML = ROOT / 'frontend' / 'templates' / 'views' / 'time-wizard.html'
TERMINAL_BASE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'


def test_theme_timeline_covers_0_to_6_with_morning_predawn():
    src = THEME_JS.read_text()
    assert 'FRIDAYS_HOUR_PHASE_MAP' in src
    # Extract the frozen array and inspect entries for hours 0..23.
    match = re.search(r'FRIDAYS_HOUR_PHASE_MAP\s*=\s*Object\.freeze\(\[(.*?)\]\)', src, re.S)
    assert match, 'FRIDAYS_HOUR_PHASE_MAP must be an Object.freeze array literal'
    entries = re.findall(r"'(night|morning|afternoon|evening)'", match.group(1))
    assert len(entries) == 24, f'mapping must cover 24 hours, got {len(entries)}'
    # Pre-dawn band 03-05 must be pulled into morning.
    for h in (3, 4, 5):
        assert entries[h] == 'morning', f'hour {h} should be morning, got {entries[h]}'
    # Deep night 00-02 stays night.
    for h in (0, 1, 2, 22, 23):
        assert entries[h] == 'night', f'hour {h} should be night, got {entries[h]}'
    # Afternoon + evening bands unchanged.
    for h in (12, 13, 17):
        assert entries[h] == 'afternoon'
    for h in (18, 19, 21):
        assert entries[h] == 'evening'


def test_theme_get_time_of_day_uses_hour_phase_map():
    src = THEME_JS.read_text()
    assert 'function fridaysHourToPhase(hour)' in src
    assert 'return fridaysHourToPhase(new Date().getHours());' in src


def test_vortex_view_has_help_button_and_history_toggle():
    src = VORTEX_HTML.read_text()
    # Inline `?` help button for Vortex.
    assert 'id="tw-help-btn"' in src
    assert "openWindowHelp('time-wizard')" in src
    # History panel collapse toggle.
    assert 'id="tw-toggle-history"' in src
    assert "getElementById('tw-history-panel')" in src


def test_studio_git_files_list_has_resizer_handle():
    src = TERMINAL_BASE.read_text()
    assert 'id="git-files-resizer"' in src
    assert 'cursor:col-resize' in src
