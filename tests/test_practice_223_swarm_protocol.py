"""Practice 223 (calm swarm 5/5): every HB agent reads that HB is a swarm and that HB orchestrates instead of waiting or asking."""
from pathlib import Path

from core import hb_master_prompt as mp

ROOT = Path(__file__).resolve().parents[1]


def test_every_agent_reads_both_rules():
    for agent in ('apex', 'fred', 'nanny', 'default', 'codex-instructor', 'gemini-advisor'):
        text = mp.for_role(agent)
        assert 'HB is a swarm' in text and 'HB orchestrates; it does not wait or ask' in text, agent


def test_small_models_get_the_compact_form():
    small = mp.for_role('nanny', compact=True)
    assert 'restarts and short waits are routine' in small and 'never wait or ask' in small and len(small) < 900


def test_homework_and_fred_prompts_are_built_from_the_pack():
    assert "for_role('default')" in (ROOT / 'core' / 'hb_homework.py').read_text()
    assert "for_role('fred')" in (ROOT / 'core' / 'hb_counsel.py').read_text()
    assert "for_role('apex')" in (ROOT / 'scripts' / 'hummingbird_peer_worker.py').read_text()
