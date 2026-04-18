"""Tests for the intent classifier (Phase 8.0 Chunk 8B)."""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))


# ---------------------------------------------------------------------------
# Import the classifier function directly — no Flask context needed
# ---------------------------------------------------------------------------
from intent_classifier import classify_message as _classify


class TestClassifyCode:
    def test_python_function(self):
        r = _classify("Write a Python function to sort a list")
        assert r['category'] == 'code'
        assert 'ghost_coder' in r['agents']

    def test_debug_traceback(self):
        r = _classify("I'm getting a traceback error in my code")
        assert r['category'] == 'code'
        assert r['model_tier'] == 'paid'

    def test_git_merge(self):
        r = _classify("How do I fix a git merge conflict?")
        assert r['category'] == 'code'

    def test_sql_query(self):
        r = _classify("Write a SQL query to find duplicate rows")
        assert r['category'] == 'code'

    def test_dockerfile(self):
        r = _classify("Create a Dockerfile for a Flask app")
        assert r['category'] == 'code'


class TestClassifySearch:
    def test_current_news(self):
        r = _classify("What is the latest news about AI?")
        assert r['category'] == 'search'
        assert any(a in r['agents'] for a in ('seeker', 'scholar'))

    def test_lookup(self):
        r = _classify("Look up the population of Japan")
        assert r['category'] == 'search'

    def test_who_is(self):
        r = _classify("Who is the president of France?")
        assert r['category'] == 'search'


class TestClassifyCreative:
    def test_write_poem(self):
        r = _classify("Write a poem about the ocean")
        assert r['category'] == 'creative'
        assert 'eleven' in r['agents']

    def test_story(self):
        r = _classify("Write a short story about a robot")
        assert r['category'] == 'creative'

    def test_brainstorm(self):
        r = _classify("Brainstorm ideas for a birthday party")
        assert r['category'] == 'creative'


class TestClassifyMath:
    def test_equation(self):
        r = _classify("Solve the equation 2x + 5 = 15")
        assert r['category'] == 'math'
        assert 'deepseek_local' in r['agents']

    def test_calculus(self):
        r = _classify("What is the derivative of x squared?")
        assert r['category'] == 'math'


class TestClassifySummarise:
    def test_summarise(self):
        r = _classify("Summarise this article for me")
        assert r['category'] == 'summarise'
        assert 'gemma' in r['agents']

    def test_tldr(self):
        r = _classify("Give me a TLDR of this document")
        assert r['category'] == 'summarise'


class TestClassifySystem:
    def test_swarm_status(self):
        r = _classify("Check the swarm agent status")
        assert r['category'] == 'system'
        assert 'duck' in r['agents']

    def test_ollama(self):
        r = _classify("Is Ollama running? Pull the latest model")
        assert r['category'] == 'system'


class TestClassifyOpinion:
    def test_debate(self):
        r = _classify("Let's debate whether AI will replace programmers")
        assert r['category'] == 'opinion'
        assert r['relay'] is True
        assert len(r['agents']) >= 2

    def test_ask_everyone(self):
        r = _classify("Ask everyone what they think about this idea")
        assert r['category'] == 'opinion'
        assert r['relay'] is True


class TestClassifyGeneral:
    def test_hello(self):
        r = _classify("Hello, how are you?")
        assert r['category'] == 'general'
        assert 'gemma' in r['agents']
        assert r['relay'] is False

    def test_empty(self):
        r = _classify("")
        assert r['category'] == 'general'
        assert r['confidence'] == 0.0


class TestClassifyMultiDomain:
    def test_code_and_search(self):
        r = _classify("Search online for a Python JSON parser and write a function for it")
        # Should detect both code and search — relay should be on
        assert r['relay'] is True
        assert len(r['agents']) >= 2


class TestClassifyResponse:
    def test_has_required_keys(self):
        r = _classify("Test message")
        for key in ('category', 'agents', 'model_tier', 'relay', 'confidence', 'reasoning'):
            assert key in r, f'Missing key: {key}'

    def test_confidence_range(self):
        r = _classify("Write a function")
        assert 0.0 <= r['confidence'] <= 1.0

    def test_agents_is_list(self):
        r = _classify("anything")
        assert isinstance(r['agents'], list)
        assert len(r['agents']) >= 1
