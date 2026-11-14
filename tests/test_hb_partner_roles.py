"""Owner 13 Nov (I18): the local models get a role, not just rules. APEX is JD's payroll-consultant partner and ends a
work turn with an action or a named blocker; Fred gives specific, checkable advice instead of generic advice."""
from pathlib import Path

from core.apex_tools import PARTNER_ROLE
from core.chat_continuity import apex_system_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_apex_chat_prompt_carries_the_partner_role_in_both_modes():
    for recovery in (False, True):
        prompt = apex_system_prompt({'name': 'apex', 'label': 'APEX'}, recovery=recovery)
        assert PARTNER_ROLE.strip() in prompt
        assert prompt.index('Who you are') < prompt.index('Hummingbird operating contract')


def test_role_states_the_consultant_protocol_and_the_turn_rule():
    for words in ('payroll consultant', 'one recommended, two possible, one dream', 'reasons, risk, effort and evidence',
                  "'blocked because ...'", "'I will proceed'"):
        assert words in PARTNER_ROLE


def test_worker_and_fred_prompts_use_their_roles():
    worker = (ROOT / 'scripts/hummingbird_peer_worker.py').read_text()
    assert "'You are APEX, JD\\'s local assistant in Hummingbird. ')+PARTNER_ROLE+" in worker
    fred = (ROOT / 'core/hb_local_review.py').read_text()
    assert 'You are Fred, the senior LOCAL reviewer' in fred and 'Generic advice such as' in fred


def test_coding_lessons_reach_every_write_turn():
    """Owner 13 Nov: coaching lessons are kept in a lessons pack and given to APEX on every turn that can change files."""
    from pathlib import Path
    from core.hb_learning import coding_lessons
    text = coding_lessons()
    assert 'leading space' in text and 'run the test next' in text and 'leave case_id out' in text
    worker = (Path(__file__).resolve().parents[1] / 'scripts' / 'hummingbird_peer_worker.py').read_text()
    assert "AUTONOMOUS_WRITE_GUIDANCE+' '+_coding_lessons()" in worker
