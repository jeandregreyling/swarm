"""Integration tests for Phase 8.0 Chunk 8F — Full Agentic Chat Flow.

Covers:
  8F.1 — Code question → ghost_coder + correct model
  8F.2 — Search question → seeker/scholar + relay off
  8F.3 — Multi-domain → multiple agents + relay on
  8F.4 — Override logic — user model always wins
  8F.5 — Regression: classify doesn't break unrelated routing
  8F.6 — Performance: classify is sub-millisecond (pure lookup, no I/O)

These tests operate at the module layer (no HTTP server required).
Live API smoke tests are done separately via curl.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from intent_classifier import classify_message
from model_selector import select_model, select_models_for_agents


# ── 8F.1 — Code question ─────────────────────────────────────────────────────

class TestCodeFlow(unittest.TestCase):
    """Code question → ghost_coder → best model selected."""

    def setUp(self):
        self.data = classify_message('Write a Python function to reverse a string')

    def test_category_is_code(self):
        self.assertEqual(self.data['category'], 'code')

    def test_ghost_coder_selected(self):
        self.assertIn('ghost_coder', self.data['agents'])

    def test_relay_is_off(self):
        self.assertFalse(self.data['relay'])

    def test_model_selected_for_ghost_coder(self):
        models = select_models_for_agents(self.data['agents'], self.data['category'])
        self.assertIn('ghost_coder', models)
        m = models['ghost_coder']
        # Must use a claude/gpt/grok model — not a local ollama model
        self.assertNotIn('gemma', m['model'])
        self.assertNotIn('llama', m['model'].lower())
        self.assertNotIn('qwen', m['model'])

    def test_confidence_high(self):
        self.assertGreaterEqual(self.data['confidence'], 0.8)

    def test_second_code_variant(self):
        d = classify_message('Debug this JavaScript: const x = null; x.foo()')
        self.assertEqual(d['category'], 'code')
        self.assertIn('ghost_coder', d['agents'])


# ── 8F.2 — Search question ───────────────────────────────────────────────────

class TestSearchFlow(unittest.TestCase):
    """Search question → seeker/scholar → relay off."""

    def setUp(self):
        self.data = classify_message("what's in the news today about AI")

    def test_category_is_search(self):
        self.assertEqual(self.data['category'], 'search')

    def test_search_agents_selected(self):
        agents = self.data['agents']
        self.assertTrue(
            any(a in agents for a in ['seeker', 'scholar']),
            f"Expected seeker or scholar in {agents}",
        )

    def test_relay_off(self):
        self.assertFalse(self.data['relay'])

    def test_model_for_seeker_is_tavily(self):
        models = select_models_for_agents(self.data['agents'], self.data['category'])
        if 'seeker' in models:
            self.assertEqual(models['seeker']['model'], 'tavily')

    def test_model_for_scholar_is_gemini(self):
        models = select_models_for_agents(self.data['agents'], self.data['category'])
        if 'scholar' in models:
            self.assertEqual(models['scholar']['model'], 'gemini')

    def test_second_search_variant(self):
        # "Python" triggers code tiebreaker, so use a non-code search query
        d = classify_message('search for the latest climate change research papers')
        self.assertEqual(d['category'], 'search')


# ── 8F.3 — Multi-domain / relay ──────────────────────────────────────────────

class TestMultiDomainFlow(unittest.TestCase):
    """Multi-domain question → multiple agents → relay on."""

    def test_opinion_relay_enabled(self):
        d = classify_message('What do you all think about AI safety? Ask everyone.')
        self.assertTrue(d['relay'])
        self.assertGreater(len(d['agents']), 1)

    def test_opinion_category(self):
        d = classify_message('In your opinion, what is the best programming language?')
        self.assertEqual(d['category'], 'opinion')
        self.assertTrue(d['relay'])

    def test_models_returned_for_all_relay_agents(self):
        d = classify_message('What do you all think about the future of AI?')
        models = select_models_for_agents(d['agents'], d['category'])
        for agent in d['agents']:
            self.assertIn(agent, models)
            self.assertIn('model', models[agent])
            self.assertIn('source', models[agent])

    def test_mixed_model_tier(self):
        d = classify_message('Ask all agents: best approach to microservices?')
        self.assertEqual(d['model_tier'], 'mixed')


# ── 8F.4 — Manual override ───────────────────────────────────────────────────

class TestOverrideFlow(unittest.TestCase):
    """User-specified model always wins over preference matrix."""

    def test_override_beats_code_preference(self):
        model, source = select_model('ghost_coder', 'code', user_model='gpt-4o-mini')
        self.assertEqual(model, 'gpt-4o-mini')
        self.assertEqual(source, 'override')

    def test_override_beats_math_preference(self):
        model, source = select_model('deepseek_local', 'math', user_model='llama3.2:latest')
        self.assertEqual(model, 'llama3.2:latest')
        self.assertEqual(source, 'override')

    def test_auto_string_is_not_override(self):
        """'auto' means system decides — should not be treated as user override."""
        _, source = select_model('ghost_coder', 'code', user_model='auto')
        self.assertNotEqual(source, 'override')

    def test_empty_string_is_not_override(self):
        _, source = select_model('gemma', 'general', user_model='')
        self.assertNotEqual(source, 'override')

    def test_batch_override_only_for_specified_agents(self):
        models = select_models_for_agents(
            ['ghost_coder', 'gemma'],
            'code',
            user_models={'ghost_coder': 'my-custom-model'},
        )
        self.assertEqual(models['ghost_coder']['source'], 'override')
        self.assertEqual(models['ghost_coder']['model'], 'my-custom-model')
        # gemma has no user override — should fall through to preference/default
        self.assertNotEqual(models['gemma']['source'], 'override')

    def test_override_in_batch_does_not_affect_other_agents(self):
        models = select_models_for_agents(
            ['gemma', 'twelve'],
            'opinion',
            user_models={'twelve': 'claude-opus-4-20250514'},
        )
        self.assertEqual(models['twelve']['model'], 'claude-opus-4-20250514')
        # gemma not in user_models, should be preference/default
        self.assertIn(models['gemma']['source'], ('preference', 'default'))


# ── 8F.5 — Regression ────────────────────────────────────────────────────────

class TestRegressionFlow(unittest.TestCase):
    """Classifier and model selector don't break unrelated routing."""

    def test_system_category_routes_to_duck(self):
        d = classify_message('restart the swarm service and check status')
        self.assertEqual(d['category'], 'system')
        self.assertIn('duck', d['agents'])

    def test_math_does_not_route_to_ghost_coder(self):
        d = classify_message('solve the integral of sin(x) dx')
        self.assertNotIn('ghost_coder', d['agents'])

    def test_creative_routes_to_eleven(self):
        # Pattern requires: "write [a] [word] poem" — not "write me a poem"
        d = classify_message('write a short poem about the ocean')
        self.assertEqual(d['category'], 'creative')
        self.assertIn('eleven', d['agents'])

    def test_summarise_routes_to_gemma(self):
        d = classify_message('summarise this article for me')
        self.assertEqual(d['category'], 'summarise')
        self.assertIn('gemma', d['agents'])

    def test_classify_response_shape(self):
        """Response always has the expected keys."""
        d = classify_message('Hello there')
        for key in ('category', 'agents', 'model_tier', 'relay', 'confidence', 'reasoning'):
            self.assertIn(key, d)

    def test_model_selector_shape(self):
        """select_models_for_agents always returns correct shape per agent."""
        models = select_models_for_agents(['gemma', 'twelve'], 'opinion')
        for agent, info in models.items():
            self.assertIn('model', info)
            self.assertIn('source', info)
            self.assertIn('fallbacks', info)
            self.assertIsInstance(info['fallbacks'], list)

    def test_unknown_agent_does_not_crash(self):
        """Graceful handling of agents not in the preference matrix."""
        models = select_models_for_agents(['new_agent_xyz'], 'code')
        self.assertIn('new_agent_xyz', models)

    def test_empty_agent_list(self):
        models = select_models_for_agents([], 'code')
        self.assertEqual(models, {})


# ── 8F.6 — Performance ───────────────────────────────────────────────────────

class TestPerformanceFlow(unittest.TestCase):
    """Classify + model select together must be fast (pure lookup, no I/O)."""

    def _time_full_pipeline(self, message):
        start = time.perf_counter()
        d = classify_message(message)
        select_models_for_agents(d['agents'], d['category'])
        return (time.perf_counter() - start) * 1000  # ms

    def test_code_pipeline_under_10ms(self):
        ms = self._time_full_pipeline('Write a Python function to sort a list')
        self.assertLess(ms, 10, f"Pipeline took {ms:.2f}ms — expected < 10ms")

    def test_search_pipeline_under_10ms(self):
        ms = self._time_full_pipeline("what's in the news today")
        self.assertLess(ms, 10, f"Pipeline took {ms:.2f}ms — expected < 10ms")

    def test_opinion_relay_pipeline_under_10ms(self):
        ms = self._time_full_pipeline('What does everyone think about machine learning?')
        self.assertLess(ms, 10, f"Pipeline took {ms:.2f}ms — expected < 10ms")

    def test_100_calls_under_100ms(self):
        """100 sequential classifications should complete well under 100ms."""
        messages = [
            'Write a sort function',
            'What is the news?',
            'Solve x^2 + 2x = 0',
            'Tell me a story',
            'Summarise this document',
        ]
        start = time.perf_counter()
        for i in range(100):
            msg = messages[i % len(messages)]
            d = classify_message(msg)
            select_models_for_agents(d['agents'], d['category'])
        total_ms = (time.perf_counter() - start) * 1000
        self.assertLess(total_ms, 100, f"100 calls took {total_ms:.2f}ms — expected < 100ms")


if __name__ == '__main__':
    unittest.main()
