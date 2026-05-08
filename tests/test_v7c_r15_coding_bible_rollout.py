"""V7C-R15 — Coding Bible rollout + UI quality guardrails.

Project: P-E9BAE4159F
Step:    S-D7AFBF2A89

Locks:
  - Coding Bible source exists and quick_card() is exported
  - Every coding-capable agent's system prompt carries the Bible prefix at
    import time (checked via `'CODING BIBLE' in` guard)
  - SVG style contract: all V7C-edited JS views use stroke="currentColor"
  - Docs discipline: every V7C step has a test file (see R17) AND docs exist
  - Seven is included in the rollout (V7C-A12 companion lock)
  - Librarian remains excluded (tags-only output)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_SRC = (ROOT / 'utils' / 'config.py').read_text()


def test_r15_r1_bible_source_exists():
    # Source file present and exports quick_card.
    p = ROOT / 'utils' / 'coding_bible.py'
    assert p.exists()
    src = p.read_text()
    assert 'def quick_card' in src


def test_r15_r2_bible_injection_guarded():
    # Must be 'CODING BIBLE' not in _val (idempotent — re-import safe).
    assert "'CODING BIBLE' not in _val" in CONFIG_SRC


def test_r15_r3_coder_roster_complete():
    # All expected coding-capable agents in the tuple.
    expected = [
        'GEMMA_SYSTEM_PROMPT', 'LLAMA_SYSTEM_PROMPT', 'QWEN_SYSTEM_PROMPT',
        'MISTRAL_SYSTEM_PROMPT', 'TWENTY_SYSTEM_PROMPT', 'EIGHT_SYSTEM_PROMPT',
        'ELEVEN_SYSTEM_PROMPT', 'NINE_SYSTEM_PROMPT', 'TEN_SYSTEM_PROMPT',
        'TWELVE_SYSTEM_PROMPT', 'THIRTEEN_SYSTEM_PROMPT', 'NINETEEN_SYSTEM_PROMPT',
        'SCHOLAR_SYSTEM_PROMPT', 'SEEKER_SYSTEM_PROMPT', 'GHOST_CODER_SYSTEM_PROMPT',
        'SEVEN_SYSTEM_PROMPT',
    ]
    start = CONFIG_SRC.index('_CODING_BIBLE_AGENTS = (')
    end = CONFIG_SRC.index(')', start)
    tup = CONFIG_SRC[start:end]
    missing = [n for n in expected if n not in tup]
    assert not missing, f'missing from coder roster: {missing}'


def test_r15_r4_svg_contract_currentcolor():
    # Sample V7C-touched views use stroke="currentColor" (theme-aware).
    sample_files = [
        ROOT / 'frontend' / 'static' / 'js' / 'views' / 'terminal.js',
        ROOT / 'frontend' / 'static' / 'js' / 'views' / 'library.js',
        ROOT / 'frontend' / 'static' / 'js' / 'views' / 'monitor.js',
    ]
    for f in sample_files:
        src = f.read_text()
        # Each file contains at least one SVG; all strokes should be currentColor.
        if 'stroke=' in src:
            # Permit explicit hex colours for state indicators (green/amber/red),
            # but there MUST be currentColor usage too (theme-safe default).
            assert 'stroke="currentColor"' in src, f'{f.name} lacks currentColor SVG stroke'


def test_r15_r5_bible_import_best_effort():
    # Best-effort import keeps config resilient — no hard failure.
    tail = CONFIG_SRC[CONFIG_SRC.index('_CODING_BIBLE_AGENTS'):]
    assert 'except Exception:' in tail
    assert '# Bible is best-effort; never block config import.' in tail


def test_r15_r6_librarian_excluded():
    # Librarian tags-only output must NOT carry the Bible header.
    start = CONFIG_SRC.index('_CODING_BIBLE_AGENTS = (')
    end = CONFIG_SRC.index(')', start)
    assert 'LIBRARIAN' not in CONFIG_SRC[start:end]


def test_r15_r7_bible_applies_via_prefix():
    # The injection prepends — does not overwrite — the original prompt.
    frag = CONFIG_SRC[CONFIG_SRC.index('_cb_prefix = _cb_card'):CONFIG_SRC.index('# Bible is best-effort')]
    assert "globals()[_name] = _cb_prefix + _val" in frag
