import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'utils'), str(ROOT / 'lib' / 'search')]

from lib.search import internet


@pytest.mark.parametrize('text,expected', [
    ('Any recent SAP Australian payroll notes come out lately?', True),
    ('@gemma what is the latest Python version?', True),
    ('can you tell me the latest SAP SuccessFactors release news?', True),
    ('When is the ATO STP Phase 2 deadline?', True),
    ('search for Lutris vs Bottles reviews', True),
    ('hello', False),
    ('fix the downloads panel', False),
    ('what is gemma doing?', False),
    ('how many open tickets are there?', False),
    ('open qbittorrent and tell me what is downloading?', False),
    ('search my memory for the vortex notes', False),
    ('write a poem about cats', False),
    ('what do you think of my plan?', False),
])
def test_needs_web_lookup(text, expected):
    assert internet.needs_web_lookup(text) is expected


def _fake(module_name, func_name, func, monkeypatch):
    import types
    module = types.ModuleType(module_name)
    setattr(module, 'search', func)
    monkeypatch.setitem(sys.modules, module_name, module)


def test_search_best_prefers_serper_then_falls_back(monkeypatch):
    _fake('internet_serper', 'search', lambda q, num_results: f'[Serper search unavailable for: {q}]', monkeypatch)
    _fake('internet_tavily', 'search', lambda q, max_results: 'Tavily AI results: https://example.com', monkeypatch)
    monkeypatch.setattr(internet, 'search_web', lambda *a, **k: pytest.fail('DuckDuckGo should not run'))
    assert internet.search_best('sap payroll') == ('Tavily', 'Tavily AI results: https://example.com')

    _fake('internet_serper', 'search', lambda q, num_results: 'Google results https://sap.com', monkeypatch)
    assert internet.search_best('sap payroll')[0] == 'Serper (Google)'


def test_search_best_reports_total_failure(monkeypatch):
    _fake('internet_serper', 'search', lambda q, num_results: '[Serper search unavailable]', monkeypatch)
    _fake('internet_tavily', 'search', lambda q, max_results: '[Tavily search unavailable]', monkeypatch)
    monkeypatch.setattr(internet, 'search_web', lambda *a, **k: '[Search failed: offline]')
    assert internet.search_best('x') == (None, '')
    assert internet.web_context_block('x') == ''


def test_web_context_block_is_labelled_and_capped(monkeypatch):
    monkeypatch.setattr(internet, 'search_best', lambda q, max_results: ('Serper (Google)', 'a' * 9000))
    block = internet.web_context_block('@qwen latest SAP news', max_chars=1000)
    assert block.startswith('LIVE WEB RESULTS (Serper (Google), fetched ')
    assert 'for: latest SAP news' in block and 'instead of guessing' in block
    assert block.count('a' * 1000) == 1 and 'a' * 1001 not in block


def test_chat_injects_web_only_for_factual_questions(monkeypatch):
    sys.path.insert(0, str(ROOT / 'frontend'))
    from frontend.blueprints import chat
    monkeypatch.setattr(internet, 'web_context_block', lambda q: 'LIVE WEB RESULTS x')
    stages = []
    out = chat._with_live_web_context('PROMPT', 'What is the latest SAP ECP release?', lambda *a: stages.append(a))
    assert out == 'LIVE WEB RESULTS x\n\nPROMPT' and stages
    assert chat._with_live_web_context('PROMPT', 'fix the downloads panel') == 'PROMPT'
    assert {'gemma', 'qwen', 'llama'} <= chat.WEB_LOOKUP_AGENTS


def test_skill_search_uses_best_engine(monkeypatch):
    from fridays import skills
    monkeypatch.setattr(internet, 'search_best', lambda q, max_results: ('Tavily', 'result https://x'))
    monkeypatch.setitem(sys.modules, 'internet', internet)
    assert skills._skill_search('sap', 'gemma') == (True, '[Tavily]\nresult https://x')


@pytest.mark.parametrize('text', ['what are some of their names', 'What year did it come out?'])
def test_short_followups_are_not_searched_out_of_context(text):
    assert internet.needs_web_lookup(text) is False
