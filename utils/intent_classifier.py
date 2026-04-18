"""Intent classifier for agentic chat routing (Phase 8.0).

Pure keyword/pattern matching — no external API calls — target <50ms.
Reads a user message and recommends: agent(s), model tier, relay on/off.
"""
import re as _re

_CLASSIFY_PATTERNS = {
    'code': _re.compile(
        r'\b(?:code|function|class|def |import |variable|compile|syntax|refactor|debug|stack\s*trace'
        r'|exception|error\s*message|traceback|regex|algorithm|api\s*endpoint|git\s*(?:commit|merge|rebase|diff)'
        r'|pull\s*request|dockerfile|docker|bash|shell|script|terminal\s*command|deploy'
        r'|test\s*(?:case|suite|unit)|lint|format|type\s*hint|typescript|javascript|python|rust|java\b|html|css'
        r'|sql|query|database\s*(?:schema|migration)|backend|frontend|server|endpoint'
        r'|repository|codebase|source\s*code|implement|bug\s*fix|patch|merge\s*conflict)\b',
        _re.IGNORECASE,
    ),
    'search': _re.compile(
        r'\b(?:search|google|look\s*up|find\s*(?:out|info|information)|current\s+(?:news|events|status)|latest\s+news|news|today(?:\s+in)'
        r'|who\s+(?:is|are|was)|when\s+(?:did|was|is)|where\s+(?:is|are)'
        r'|wikipedia|web|online|browse|url|link|website|source|reference|article|paper)\b',
        _re.IGNORECASE,
    ),
    'creative': _re.compile(
        r'\b(?:write\s+(?:a\s+)?(?:\w+\s+)?(?:story|poem|song|essay|letter|email|blog|post|article|script)'
        r'|creative|fiction|narrative|character|plot|dialogue|metaphor|rhyme|lyric|haiku|sonnet'
        r'|brainstorm|imagine|roleplay|scenario)\b',
        _re.IGNORECASE,
    ),
    'math': _re.compile(
        r'\b(?:math|calcul|equation|formula|integral|derivative|algebra|geometry|trigonometry'
        r'|statistics|probability|matrix|vector|theorem|proof|solve|compute|evaluate\s*(?:the|this)'
        r'|arithmetic|logarithm|exponent|factorial|permutation|combination)\b',
        _re.IGNORECASE,
    ),
    'summarise': _re.compile(
        r'\b(?:summarise|summarize|summary|tldr|tl;dr|condense|shorten|brief|recap|overview'
        r'|key\s*points|main\s*(?:points|ideas|takeaways)|in\s*(?:short|brief)|nutshell)\b',
        _re.IGNORECASE,
    ),
    'system': _re.compile(
        r'\b(?:swarm|fridays|agent\s*(?:status|health|config)|restart|service|systemd|uptime'
        r'|queue|ticket|proposal|audit|memory\s*(?:table|cleanup)'
        r'|enrollment|onboarding|schedule|cron|log\s*(?:file|entry)|monitor|watchdog|ollama|model\s*(?:pull|list))\b',
        _re.IGNORECASE,
    ),
    'opinion': _re.compile(
        r'\b(?:debate|opinion|argue|discuss|compare|pros?\s*(?:and|&|vs)\s*cons?|what\s*do\s*you\s*think'
        r'|perspective|viewpoint|disagree|agree|weigh\s*in|hot\s*take|controversial'
        r'|(?:ask|check\s*with)\s*(?:everyone|all|the\s*(?:team|agents|swarm|group)))\b',
        _re.IGNORECASE,
    ),
}

# Category → {agents, model_tier, relay}
_CLASSIFY_ROUTES = {
    'code':      {'agents': ['ghost_coder'], 'model_tier': 'paid', 'relay': False},
    'search':    {'agents': ['seeker', 'scholar'], 'model_tier': 'paid', 'relay': False},
    'creative':  {'agents': ['eleven'], 'model_tier': 'paid', 'relay': False},
    'math':      {'agents': ['deepseek_local'], 'model_tier': 'local', 'relay': False},
    'summarise': {'agents': ['gemma'], 'model_tier': 'local', 'relay': False},
    'system':    {'agents': ['duck'], 'model_tier': 'service', 'relay': False},
    'opinion':   {'agents': ['gemma', 'twelve', 'nine'], 'model_tier': 'mixed', 'relay': True},
    'general':   {'agents': ['gemma'], 'model_tier': 'local', 'relay': False},
}


def classify_message(text):
    """Classify a user message and return routing recommendation.

    Returns dict: {category, agents, model_tier, relay, confidence, reasoning}
    """
    if not text or not text.strip():
        return {
            'category': 'general',
            'agents': ['gemma'],
            'model_tier': 'local',
            'relay': False,
            'confidence': 0.0,
            'reasoning': 'Empty message — defaulting to Gemma.',
        }

    txt = text.strip()
    hits = {}  # category → match_count

    for category, pattern in _CLASSIFY_PATTERNS.items():
        matches = pattern.findall(txt)
        if matches:
            hits[category] = len(matches)

    if not hits:
        return {
            'category': 'general',
            'agents': ['gemma'],
            'model_tier': 'local',
            'relay': False,
            'confidence': 0.5,
            'reasoning': 'No strong category signals — routing to Gemma as general assistant.',
        }

    # Sort by match count descending, with domain-specificity as tiebreaker
    # More specific categories win ties over generic ones (search, general)
    _PRIORITY = {
        'code': 0, 'math': 0, 'creative': 0, 'system': 0,
        'summarise': 1, 'opinion': 1,
        'search': 2, 'general': 3,
    }
    ranked = sorted(hits.items(), key=lambda kv: (-kv[1], _PRIORITY.get(kv[0], 9)))
    top_category, top_count = ranked[0]
    total_matches = sum(c for _, c in ranked)
    confidence = min(1.0, round(top_count / max(total_matches, 1) * 0.8 + 0.2, 2))

    route = _CLASSIFY_ROUTES[top_category]

    # Multi-category → consider relay
    relay = route['relay']
    agents = list(route['agents'])
    model_tier = route['model_tier']

    if len(ranked) >= 2:
        second_category, second_count = ranked[1]
        # If second category is close in strength, blend agents and enable relay
        if second_count >= top_count * 0.5:
            second_route = _CLASSIFY_ROUTES[second_category]
            for a in second_route['agents']:
                if a not in agents:
                    agents.append(a)
            relay = True
            confidence = min(confidence, 0.7)
            model_tier = 'mixed'

    reasoning_parts = [f'{cat}({cnt})' for cat, cnt in ranked]
    reasoning = f'Detected: {", ".join(reasoning_parts)}. '
    reasoning += f'Primary: {top_category} → {", ".join(agents)}.'
    if relay:
        reasoning += ' Multi-domain detected — relay enabled.'

    return {
        'category': top_category,
        'agents': agents,
        'model_tier': model_tier,
        'relay': relay,
        'confidence': confidence,
        'reasoning': reasoning,
    }
