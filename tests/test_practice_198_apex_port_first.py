"""Practice 198: in Auto, APEX's turns go to the model served on APEX's port (8080), not a 7B stand-in."""
from types import SimpleNamespace

from core import apex_routing


def _entry(name, endpoint=None, ram=1.0, role='general', ctx=32768):
    return SimpleNamespace(name=name, driver='llamacpp', role=role, options={'api_model': 'gpt-oss:20B'} if endpoint else {},
                           path='/m/' + name, endpoint=endpoint, ctx=ctx, ram_gb=ram)


def test_apex_port_wins_in_auto():
    entries = [_entry('apex-direct:7b', ram=5), _entry('qwen2.5:14b-instruct', ram=9), _entry('gpt-oss:20b', endpoint='http://127.0.0.1:8080', ram=14)]
    route = apex_routing.select_local_model('fix the python test in core/x.py', entries, {'http://127.0.0.1:8080': {'gpt-oss:20B'}},
                                            exists=lambda p: True, switches={'apex-direct:7b': 'auto', 'gpt-oss:20b': 'auto'})
    assert route.model == 'gpt-oss:20b'


def test_switched_off_apex_port_is_skipped():
    entries = [_entry('apex-direct:7b', ram=5), _entry('gpt-oss:20b', endpoint='http://127.0.0.1:8080', ram=14)]
    route = apex_routing.select_local_model('hello there', entries, {'http://127.0.0.1:8080': {'gpt-oss:20B'}},
                                            exists=lambda p: True, switches={'gpt-oss:20b': 'off'})
    assert route.model == 'apex-direct:7b'
