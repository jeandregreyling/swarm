import sqlite3
import sys
import types

import pytest

from agents.gemini import gemini_agent as g


def test_is_transient():
    assert g._is_transient(Exception('503 UNAVAILABLE'))
    assert g._is_transient(Exception('429 quota'))
    assert not g._is_transient(Exception('403 PERMISSION_DENIED'))


def test_memory_block_handles_sqlite_rows(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 'subj' AS subject, 'body' AS content").fetchone()
    fake_db = types.SimpleNamespace(get_agent_memory=lambda *a, **k: [row])
    monkeypatch.setitem(sys.modules, 'database', fake_db)
    assert '[subj] body' in g._memory_block()


def test_fallback_after_transient_errors(monkeypatch):
    pytest.importorskip('google.genai')
    from google.genai import models as M

    calls = []

    def fake_generate(self, model, contents, config):
        calls.append(model)
        if len(calls) <= 3:
            raise Exception('503 UNAVAILABLE high demand')
        return types.SimpleNamespace(text='OK', usage_metadata=None)

    monkeypatch.setattr(M.Models, 'generate_content', fake_generate)
    monkeypatch.setattr(g.time, 'sleep', lambda s: None)
    monkeypatch.setattr(g, '_memory_block', lambda: '')
    monkeypatch.setitem(
        sys.modules, 'config',
        types.SimpleNamespace(
            GEMINI_AGENT_MODEL='gemini-3.8-flash', GEMINI_API_KEY='k',
            GEMINI_SYSTEM_PROMPT='sys',
        ),
    )
    answer, _ = g.chat('Reply OK. Do not use tools or memory.')
    assert 'OK' in answer
    assert len(set(calls)) >= 2


def test_gemini_429_skips_to_next_model_without_sleeping(monkeypatch):
    pytest.importorskip('google.genai')
    from google.genai import models as M

    calls = []

    def fake_generate(self, model, contents, config):
        calls.append(model)
        if len(calls) == 1:
            raise Exception('429 RESOURCE_EXHAUSTED free_tier_requests')
        return types.SimpleNamespace(text='OK', usage_metadata=None)

    def no_sleep(s):
        raise AssertionError('429 must not sleep')

    monkeypatch.setattr(M.Models, 'generate_content', fake_generate)
    monkeypatch.setattr(g.time, 'sleep', no_sleep)
    monkeypatch.setattr(g, '_memory_block', lambda: '')
    monkeypatch.setitem(
        sys.modules, 'config',
        types.SimpleNamespace(
            GEMINI_AGENT_MODEL='gemini-3.8-flash', GEMINI_API_KEY='k',
            GEMINI_SYSTEM_PROMPT='sys',
        ),
    )
    answer, _ = g.chat('Reply OK. Do not use tools or memory.')
    assert 'OK' in answer
    assert calls[0] != calls[1]


def test_ten_uses_gemini_backend_and_falls_back_on_429(monkeypatch):
    openai = pytest.importorskip('openai')
    from agents.ten import copilot_agent as t

    used = {}
    calls = []

    class FakeClient:
        def __init__(self, api_key, base_url):
            used['key'], used['url'] = api_key, base_url
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create)
            )

        def _create(self, model, messages, max_tokens):
            calls.append(model)
            if len(calls) == 1:
                raise Exception('Error code: 429 - quota')
            msg = types.SimpleNamespace(content='OK')
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=msg)],
                usage=types.SimpleNamespace(total_tokens=7),
            )

    monkeypatch.setattr(openai, 'OpenAI', FakeClient)
    monkeypatch.setattr(t.time, 'sleep', lambda s: None)
    monkeypatch.setattr(t, '_build_context', lambda m: '')
    monkeypatch.setitem(
        sys.modules, 'config',
        types.SimpleNamespace(
            GEMINI_API_KEY='gk', TEN_SYSTEM_PROMPT='sys',
            TEN_MODEL='gemini-3.6-flash',
            TEN_BASE_URL='https://example.test/openai/',
        ),
    )
    answer, tokens = t.chat('Reply OK. Do not use tools.')
    assert 'OK' in answer
    assert used == {'key': 'gk', 'url': 'https://example.test/openai/'}
    assert calls[0] == 'gemini-3.6-flash' and calls[1] != calls[0]
