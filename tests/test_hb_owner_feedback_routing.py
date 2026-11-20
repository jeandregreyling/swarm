"""Owner conduct guidance must not launch SAP research or hide an actual work request."""
import pytest
from core import hb_owner_intent as intent, hb_apex_swap
from core.hb_learning import skills_for_text
from core.apex_tools import research_question

OWNER_MESSAGE = ('@apex you need to be super nice to the larger models that are teaching you please, this is me asking you to behave, '
                 'we can be more chaotic later, for now, I want yo7u to please listen to the learning models and they will guide you, is that ok?')


@pytest.mark.parametrize('text', [OWNER_MESSAGE, 'Please listen to Codex and learn from the examples.',
                                 '@apex please be nice to the models teaching you.',
                                 'Can you please listen to the larger models?'])
def test_conduct_guidance_is_chat_without_research(text):
    assert intent.classify(text) == 'remark'
    assert not research_question(text)
    assert 'research' not in skills_for_text(text)
    def no_search(_):
        pytest.fail('operating feedback searched the Knowledge Centre')
    assert hb_apex_swap.review(text, search=no_search)['kind'] == 'default'


@pytest.mark.parametrize('text', ['How do local models learn to listen to instructions?',
                                 'Explain how to train a local model with a dataset.',
                                 'What does status 03 mean in SAP payroll?',
                                 'How do I clear the backlog in SAP workflow?',
                                 'Do not clear your task list; explain SAP payroll schemas.',
                                 'If you need to clear your task list, explain why first.'])
def test_genuine_questions_negation_and_conditionals_keep_research(text):
    assert not intent.operating_feedback(text)
    assert research_question(text)
    assert intent.classify(text) != 'drive'


@pytest.mark.parametrize('text', ['Please be nice and fix the login page.',
                                 'Listen to Codex, then implement the queue repair.',
                                 'Please listen to the models and update core/hb_channels.py.',
                                 'Please be nice. Research SAP wage types and write a summary.'])
def test_guidance_does_not_hide_concrete_work(text):
    assert not intent.operating_feedback(text)
    assert intent.classify(text) is None


@pytest.mark.parametrize('text', ['Do not listen to the models.', 'If you need to be nice, ask me first.',
                                 'Why should you be nice to the larger models?'])
def test_embedded_mention_is_not_a_direct_conduct_instruction(text):
    assert not intent.operating_feedback(text)
