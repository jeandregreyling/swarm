"""Practice 268: APEX's prompt names the model that really plays him."""
from core import hb_master_prompt as mp


def test_apex_knows_his_model(monkeypatch):
    monkeypatch.setattr('core.hb_apex_swap.playing', lambda: 'swift-qwen3.8-27b')
    assert 'the model playing you now is Swift (swift-qwen3.8-27b) on the GPU' in mp.for_role('apex')
    assert 'the model playing you now' not in mp.for_role('fred')
