"""Owner 14 Nov: Gemini Flash bounded and onboarded - HB's read-only tools (only those HB grants it), its own memory, nothing that changes HB."""
import sys
import types as pytypes

import pytest

sys.path.insert(0, 'scripts')


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _fake_genai(script, seen):
    genai = pytypes.ModuleType('google.genai')
    t = pytypes.ModuleType('google.genai.types')
    for name in ('Content', 'Tool', 'GenerateContentConfig', 'AutomaticFunctionCallingConfig', 'HttpOptions', 'HttpRetryOptions'):
        setattr(t, name, lambda name=name, **kw: _Obj(kind=name, **kw))
    t.Part = type('Part', (), {'__init__': lambda self, **kw: self.__dict__.update(kw),
                               'from_function_response': staticmethod(lambda name, response: _Obj(fn=name, response=response))})

    class Models:
        def generate_content(self, model, contents, config):
            seen.append({'model': model, 'tools': bool(getattr(config, 'tools', None)), 'turns': len(contents),
                         'instruction': config.system_instruction})
            return script.pop(0)
    genai.Client = lambda **kw: _Obj(models=Models(), close=lambda: None)
    genai.types = t
    google = pytypes.ModuleType('google')
    google.genai = genai
    return {'google': google, 'google.genai': genai, 'google.genai.types': t}


def test_gemini_checks_facts_with_read_only_tools_then_answers(monkeypatch):
    import hummingbird_gemini_peer as g
    seen, ran = [], []
    usage = _Obj(prompt_token_count=10, candidates_token_count=5)
    script = [_Obj(function_calls=[_Obj(name='knowledge_search', args={'query': 'DOES'})], candidates=[_Obj(content='model turn')],
                   usage_metadata=usage, text=''),
              _Obj(function_calls=[], candidates=[], usage_metadata=usage, text='DOES means Do, Operate, Execute, Sustain.')]
    for name, mod in _fake_genai(script, seen).items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setitem(sys.modules, 'config', _Obj(GEMINI_AGENT_MODEL='gemini-2.5-flash', GEMINI_API_KEY='k', GEMINI_SYSTEM_PROMPT='p'))
    monkeypatch.setattr(g, 'selected_provider_model', lambda configured: 'gemini-2.5-flash')
    model, answer, tokens = g._generate('What is DOES?', '', '', run_tool=lambda n, a, m: ran.append((n, a, m)) or {'items': ['KC 1']},
                                        granted={'knowledge_search', 'read_file', 'propose_patch'})
    assert answer == 'DOES means Do, Operate, Execute, Sustain.' and model == 'gemini-2.5-flash' and tokens == 30
    assert ran == [('knowledge_search', {'query': 'DOES'}, 'gemini-2.5-flash')]
    assert seen[0]['tools'] and seen[1]['turns'] == 3                          # the tool result went back to Gemini
    assert 'read-only for research and grounding' in seen[0]['instruction'] and 'studio_proposal' in seen[0]['instruction']
    assert 'You cannot change anything in HB yourself' in seen[0]['instruction']


def test_only_read_only_tools_are_ever_declared():
    import hummingbird_gemini_peer as g
    names = [d['name'] for d in g.tool_declarations({'read_file', 'propose_patch', 'propose_write_file', 'run_tests', 'memory_save', 'does_rename'})]
    assert names == ['read_file', 'memory_save']
    assert 'studio_proposal' in [d['name'] for d in g.tool_declarations({'studio_proposal', 'propose_patch'})]   # proposals yes, patches no
