"""Tests for utils/model_selector.py (Phase 8.0 Chunk 8E)."""
import os
import sys
import unittest

# Ensure utils/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))
from model_selector import select_model, get_fallback_chain, select_models_for_agents


class TestSelectModel(unittest.TestCase):
    """select_model() — priority: override > preference > default."""

    def test_user_override_wins(self):
        model, source = select_model('ghost_coder', 'code', user_model='gpt-4.1')
        self.assertEqual(model, 'gpt-4.1')
        self.assertEqual(source, 'override')

    def test_auto_override_ignored(self):
        """user_model='auto' means let system decide — not an override."""
        model, source = select_model('ghost_coder', 'code', user_model='auto')
        self.assertEqual(source, 'preference')

    def test_empty_override_ignored(self):
        model, source = select_model('gemma', 'summarise', user_model='')
        self.assertEqual(source, 'preference')

    def test_category_preference(self):
        model, source = select_model('ghost_coder', 'code')
        self.assertEqual(model, 'claude-sonnet-4-20250514')
        self.assertEqual(source, 'preference')

    def test_ghost_coder_creative_prefers_opus(self):
        model, _ = select_model('ghost_coder', 'creative')
        self.assertIn('opus', model)

    def test_deepseek_math(self):
        model, source = select_model('deepseek_local', 'math')
        self.assertEqual(model, 'deepseek-r1:7b')
        self.assertEqual(source, 'preference')

    def test_gemma_summarise(self):
        model, _ = select_model('gemma', 'summarise')
        self.assertEqual(model, 'gemma3:latest')

    def test_default_when_no_category(self):
        model, source = select_model('gemma')
        self.assertEqual(model, 'gemma3:latest')
        self.assertEqual(source, 'default')

    def test_default_when_unknown_category(self):
        model, source = select_model('llama', 'unknown_category')
        self.assertEqual(model, 'llama3.2:latest')
        self.assertEqual(source, 'default')

    def test_unknown_agent_defaults(self):
        model, source = select_model('nonexistent_agent', 'code')
        self.assertEqual(model, 'gemma3:latest')  # ultimate fallback
        self.assertEqual(source, 'default')


class TestFallbackChain(unittest.TestCase):
    """get_fallback_chain() — ordered list of fallback models."""

    def test_ghost_coder_code_chain(self):
        chain = get_fallback_chain('ghost_coder', 'code')
        self.assertGreaterEqual(len(chain), 3)
        self.assertEqual(chain[0], 'claude-sonnet-4-20250514')
        self.assertIn('gpt-4.1', chain)
        self.assertIn('grok-3', chain)

    def test_default_appended(self):
        """Agent default should be in the chain even if not in preferences."""
        chain = get_fallback_chain('gemma', 'opinion')
        self.assertIn('gemma3:latest', chain)

    def test_no_duplicates(self):
        chain = get_fallback_chain('gemma', 'summarise')
        self.assertEqual(len(chain), len(set(chain)))

    def test_no_category_gives_default_only(self):
        chain = get_fallback_chain('phi3')
        self.assertEqual(chain, ['phi3:latest'])


class TestSelectModelsForAgents(unittest.TestCase):
    """select_models_for_agents() — batch model selection."""

    def test_basic_output(self):
        result = select_models_for_agents(['ghost_coder', 'gemma'], 'code')
        self.assertIn('ghost_coder', result)
        self.assertIn('gemma', result)
        self.assertEqual(result['ghost_coder']['model'], 'claude-sonnet-4-20250514')
        self.assertEqual(result['ghost_coder']['source'], 'preference')

    def test_user_override_in_batch(self):
        result = select_models_for_agents(
            ['ghost_coder'], 'code',
            user_models={'ghost_coder': 'gpt-4o'},
        )
        self.assertEqual(result['ghost_coder']['model'], 'gpt-4o')
        self.assertEqual(result['ghost_coder']['source'], 'override')

    def test_fallbacks_exclude_selected(self):
        result = select_models_for_agents(['ghost_coder'], 'code')
        fb = result['ghost_coder']['fallbacks']
        self.assertNotIn(result['ghost_coder']['model'], fb)
        self.assertGreater(len(fb), 0)

    def test_multi_agent_different_models(self):
        result = select_models_for_agents(
            ['gemma', 'twelve', 'nine'], 'opinion',
        )
        self.assertEqual(result['gemma']['model'], 'gemma3:latest')
        self.assertEqual(result['twelve']['model'], 'claude-haiku-4-5')
        self.assertEqual(result['nine']['model'], 'llama-3.3-70b-versatile')

    def test_search_agents(self):
        result = select_models_for_agents(['seeker', 'scholar'], 'search')
        self.assertEqual(result['seeker']['model'], 'tavily')
        self.assertEqual(result['scholar']['model'], 'gemini')


class TestClassifyEndpointModels(unittest.TestCase):
    """Integration: classify_message + select_models_for_agents together."""

    def test_code_classify_includes_models(self):
        from intent_classifier import classify_message
        data = classify_message('Write a Python function to sort a list')
        models = select_models_for_agents(data['agents'], data['category'])
        self.assertIn('ghost_coder', models)
        self.assertIn('model', models['ghost_coder'])
        self.assertIn('source', models['ghost_coder'])

    def test_math_classify_includes_models(self):
        from intent_classifier import classify_message
        data = classify_message('What is the derivative of x squared?')
        models = select_models_for_agents(data['agents'], data['category'])
        self.assertIn('deepseek_local', models)
        self.assertEqual(models['deepseek_local']['model'], 'deepseek-r1:7b')


if __name__ == '__main__':
    unittest.main()
