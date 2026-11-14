"""Practice 63 (owner 15 Nov): System cleanup, batch 1 - the ten unused root entries are in the archive; nothing was deleted."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EARLIER = ['APEX_TIERED_SETUP.md', 'CODEX_CLOUD_HANDOFF.md', 'CODEX_HUMMINGBIRD_CONNECTION.md', 'COMPLETE_MISTRAL_VIBE_SETUP.md', 'MISTRAL_VIBE_INTEGRATION.md']
MOVES = [('MISTRAL_VIBE_UI_INTEGRATION.md', 'archive/MISTRAL_VIBE_UI_INTEGRATION.md'), ('QUICK_START_HB_BRIDGE.md', 'archive/QUICK_START_HB_BRIDGE.md'), ('verify_mistral_vibe_setup.sh', 'archive/verify_mistral_vibe_setup.sh')]


def test_practice_63_batch_1_is_in_the_archive():
    for name in EARLIER:
        assert (ROOT / 'archive' / name).is_file() and not (ROOT / name).exists(), name
    for src, dst in MOVES:
        assert (ROOT / dst).is_file() and not (ROOT / src).exists(), src
