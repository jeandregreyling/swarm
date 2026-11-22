"""Practice 263: every agent prompt starts with the hard-coded DOES/DREAM law."""
from core import hb_master_prompt as mp


def test_law_leads_every_prompt():
    for agent in ('apex', 'fred', 'codex-instructor'):
        for compact in (False, True):
            text = mp.for_role(agent, compact=compact)
            assert text.startswith(mp.DOES_DREAM_SHORT if compact else mp.DOES_DREAM_LAW), (agent, compact)
    assert 'A system that DOES' in mp.DOES_DREAM_LAW and "'Done: <what changed> (receipt <id>). Is it working?'" in mp.DOES_DREAM_LAW


def test_the_law_survives_a_pack_without_it(monkeypatch):
    monkeypatch.setattr(mp, 'pack', lambda: {'version': 'x', 'shared': [], 'compact': '', 'roles': {'default': 'r', 'apex': 'r'}})
    assert mp.for_role('apex').startswith(mp.DOES_DREAM_LAW)
