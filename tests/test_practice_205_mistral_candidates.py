"""Practice 205: the Mistral models are APEX candidates."""
from core import hb_apex_swap as s


def test_mistral_models_are_candidates():
    names = {r['name']: r for r in s.candidates()}
    assert 'mistral-nemo-12b' in names and names['mistral-nemo-12b']['fits']
    assert not any(r['fits'] for r in names.values() if 'Mixtral' in r['path'])   # 28 GB: never on the GPU
