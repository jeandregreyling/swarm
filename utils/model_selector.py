"""Model selector for agentic chat routing (Phase 8.0 — Chunk 8E).

Picks the best model for an agent given a task category.

Priority order:
  1. User override — explicitly set in Agents config (DB `agents.model`)
  2. Category-specific preference — from _PREFERENCES matrix
  3. Agent default — from _DEFAULTS dict

Includes fallback chains for when preferred model is unavailable.
No external API calls — pure lookup.
"""

import logging as _logging

_log = _logging.getLogger(__name__)

# ── Preference matrix ────────────────────────────────────────────────────────
# (agent_name, category) → ordered list of preferred models (best first)

_PREFERENCES = {
    # Ghost Coder — strongest model per task type
    ('ghost_coder', 'code'):      ['claude-sonnet-4-20250514', 'gpt-4.1', 'grok-3'],
    ('ghost_coder', 'creative'):  ['claude-opus-4-20250514', 'gpt-4.1', 'grok-3'],
    ('ghost_coder', 'math'):      ['claude-sonnet-4-20250514', 'gpt-4.1'],
    ('ghost_coder', 'summarise'): ['claude-sonnet-4-20250514', 'gpt-4o'],
    ('ghost_coder', 'general'):   ['claude-sonnet-4-20250514', 'gpt-4o', 'grok-3'],

    # DeepSeek — math/code specialist
    ('deepseek_local', 'math'):   ['deepseek-r1:7b'],
    ('deepseek_local', 'code'):   ['deepseek-r1:7b'],

    # Gemma — general / summarise
    ('gemma', 'summarise'):       ['gemma3:latest'],
    ('gemma', 'general'):         ['gemma3:latest'],
    ('gemma', 'opinion'):         ['gemma3:latest'],

    # Eight — larger model for complex tasks
    ('eight', 'code'):            ['gemma4:26b'],
    ('eight', 'creative'):        ['gemma4:26b'],
    ('eight', 'math'):            ['gemma4:26b'],

    # Eleven (Grok) — creative specialist
    ('eleven', 'creative'):       ['grok-3', 'grok-api'],
    ('eleven', 'opinion'):        ['grok-3', 'grok-api'],

    # Twelve (Claude) — reasoning / opinion
    ('twelve', 'opinion'):        ['claude-haiku-4-5'],
    ('twelve', 'code'):           ['claude-haiku-4-5'],

    # Nine (Groq) — fast inference
    ('nine', 'opinion'):          ['llama-3.3-70b-versatile'],
    ('nine', 'general'):          ['llama-3.3-70b-versatile'],

    # Scholar (Gemini) — search / research
    ('scholar', 'search'):        ['gemini'],

    # Seeker (Tavily) — web search
    ('seeker', 'search'):         ['tavily'],

    # Mistral — creative / general
    ('mistral', 'creative'):      ['mistral:latest'],
    ('mistral', 'opinion'):       ['mistral:latest'],

    # LLaMA — general purpose
    ('llama', 'general'):         ['llama3.2:latest'],
    ('llama', 'opinion'):         ['llama3.2:latest'],

    # Qwen — general purpose
    ('qwen', 'general'):          ['qwen2.5:latest'],
    ('qwen', 'creative'):        ['qwen2.5:latest'],

    # Duck / Librarian — system agents
    ('duck', 'system'):           ['qwen:latest'],
    ('librarian', 'system'):      ['qwen:latest'],
}

# ── Agent default models (fallback if no category match) ─────────────────────
_DEFAULTS = {
    'ghost_coder':   'claude-sonnet-4-20250514',
    'gemma':         'gemma3:latest',
    'llama':         'llama3.2:latest',
    'mistral':       'mistral:latest',
    'qwen':          'qwen2.5:latest',
    'eight':         'gemma4:26b',
    'deepseek_local': 'deepseek-r1:7b',
    'phi3':          'phi3:latest',
    'nine':          'llama-3.3-70b-versatile',
    'ten':           'gpt-4o',
    'eleven':        'grok-api',
    'twelve':        'claude-haiku-4-5',
    'thirteen':      'meta-llama/Llama-3.3-70B-Instruct',
    'scholar':       'gemini',
    'seeker':        'tavily',
    'duck':          'qwen:latest',
    'librarian':     'qwen:latest',
    'sniffles':      'deepseek-r1:7b',
    'seven':         'qwen2.5:0.5b',
    'ghost':         'external',
}


def select_model(agent_name, category=None, user_model=None):
    """Select the best model for an agent given a task category.

    Parameters
    ----------
    agent_name : str
        Agent code name (e.g. 'ghost_coder', 'gemma').
    category : str | None
        Task category from classifier (e.g. 'code', 'math', 'creative').
    user_model : str | None
        User-configured model from DB (Agents tile override).
        If set and not 'auto', always wins.

    Returns
    -------
    tuple[str, str]
        (model_string, source) where source is 'override' | 'preference' | 'default'.
    """
    # 1. User override always wins (unless 'auto' which means let system decide)
    if user_model and user_model not in ('auto', ''):
        return user_model, 'override'

    # 2. Category-specific preference
    if category:
        prefs = _PREFERENCES.get((agent_name, category))
        if prefs:
            return prefs[0], 'preference'

    # 3. Agent default
    default = _DEFAULTS.get(agent_name, 'gemma3:latest')
    return default, 'default'


def get_fallback_chain(agent_name, category=None):
    """Get ordered list of fallback models for an agent+category.

    Returns a list of model strings, best first.
    """
    chain = []

    # Category preferences first
    if category:
        prefs = _PREFERENCES.get((agent_name, category))
        if prefs:
            chain.extend(prefs)

    # Agent default as final fallback
    default = _DEFAULTS.get(agent_name)
    if default and default not in chain:
        chain.append(default)

    return chain


def select_models_for_agents(agents, category=None, user_models=None):
    """Select models for a list of agents given a category.

    Parameters
    ----------
    agents : list[str]
        Agent names.
    category : str | None
        Task category from classifier.
    user_models : dict | None
        {agent_name: model_string} from DB / registry.

    Returns
    -------
    dict
        {agent_name: {'model': str, 'source': str, 'fallbacks': list[str]}}
    """
    user_models = user_models or {}
    result = {}
    for agent in agents:
        model, source = select_model(
            agent, category, user_model=user_models.get(agent),
        )
        fallbacks = get_fallback_chain(agent, category)
        # Remove the selected model from fallbacks list
        fallbacks = [f for f in fallbacks if f != model]
        result[agent] = {
            'model': model,
            'source': source,
            'fallbacks': fallbacks,
        }
    return result
