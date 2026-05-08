"""V7C-R10 + A12 — Seven role-model sanity + Coding Bible inclusion.

Project: P-E9BAE4159F
Steps:   S-FEA99A4CFA (R10), S-8E819739D2 (A12)

Contract:
  - Seven's system prompt exists with identity as Ghost One's companion
  - Seven IS in _CODING_BIBLE_AGENTS (A12 fix — previously excluded)
  - Role defaults match slot-role matrix for canonical slots
  - Librarian remains excluded (tags-only output)
  - Coding Bible injection is best-effort (never blocks config import)
"""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_SRC = (ROOT / 'utils' / 'config.py').read_text()


def test_r10_r1_seven_in_coding_bible():
    # A12 core fix: Seven is a 7B merge, not phi3:mini — it belongs.
    assert "'SEVEN_SYSTEM_PROMPT'" in CONFIG_SRC
    tuple_start = CONFIG_SRC.index('_CODING_BIBLE_AGENTS = (')
    tuple_end = CONFIG_SRC.index(')', tuple_start)
    tup = CONFIG_SRC[tuple_start:tuple_end]
    assert 'SEVEN_SYSTEM_PROMPT' in tup


def test_r10_r2_librarian_still_excluded():
    # Librarian emits comma-separated tags only — must stay out of the list.
    tuple_start = CONFIG_SRC.index('_CODING_BIBLE_AGENTS = (')
    tuple_end = CONFIG_SRC.index(')', tuple_start)
    tup = CONFIG_SRC[tuple_start:tuple_end]
    assert 'LIBRARIAN' not in tup


def test_r10_r3_seven_identity_correct():
    from utils import config  # type: ignore
    assert 'Seven' in config.SEVEN_SYSTEM_PROMPT
    assert 'Ghost One' in config.SEVEN_SYSTEM_PROMPT


def test_r10_r4_gemma_orchestrator_role():
    from utils import config  # type: ignore
    assert 'orchestrator of Seven' in config.GEMMA_SYSTEM_PROMPT


def test_r10_r5_llama_researcher_role():
    from utils import config  # type: ignore
    assert 'researcher' in config.LLAMA_SYSTEM_PROMPT.lower()
    assert 'internet' in config.LLAMA_SYSTEM_PROMPT.lower()


def test_r10_r6_mistral_quick_coder_role():
    from utils import config  # type: ignore
    assert 'QUICK CODER' in config.MISTRAL_SYSTEM_PROMPT


def test_r10_r7_bible_injection_best_effort():
    # Must be wrapped in try/except so a missing bible doesn't break config import.
    tail = CONFIG_SRC[CONFIG_SRC.index('_CODING_BIBLE_AGENTS'):]
    assert 'try:' in tail
    assert '# Bible is best-effort; never block config import.' in tail
