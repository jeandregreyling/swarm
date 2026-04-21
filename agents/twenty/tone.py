"""Tone detection — classify user input into interaction modes.

Heuristic only, no LLM.  Four modes per §4b.5.
"""

import re

# ── Mode constants ────────────────────────────────────────────────────

ANALYTICAL  = 'analytical'
CREATIVE    = 'creative'
URGENT      = 'urgent'
EXPLORATORY = 'exploratory'

# ── Keyword / pattern lists ──────────────────────────────────────────

_URGENT_WORDS = re.compile(
    r'\b(now|broken|error|fix|crash|down|urgent|asap|help|stuck|fail|dead|kill)\b',
    re.IGNORECASE,
)

_CREATIVE_WORDS = re.compile(
    r'\b(what if|imagine|maybe we could|how about|idea|brainstorm|explore|experiment|wild)\b',
    re.IGNORECASE,
)

_EXPLORATORY_WORDS = re.compile(
    r'\b(i think|maybe|perhaps|there was|wonder|not sure|might be|could be|vaguely)\b',
    re.IGNORECASE,
)

_ANALYTICAL_WORDS = re.compile(
    r'\b(how many|count|status|list|show me|which|where is|report|compare|percentage)\b',
    re.IGNORECASE,
)


def classify_tone(text):
    """Classify text into one of four interaction modes.

    Priority order: urgent > analytical > creative > exploratory.
    Falls back to analytical (safest default).

    Returns one of: 'analytical', 'creative', 'urgent', 'exploratory'.
    """
    if not text or not text.strip():
        return ANALYTICAL

    # Exclamation marks boost urgency signal
    exclamation_count = text.count('!')

    # Score each mode
    urgent_score = len(_URGENT_WORDS.findall(text)) + (exclamation_count * 0.5)
    creative_score = len(_CREATIVE_WORDS.findall(text))
    exploratory_score = len(_EXPLORATORY_WORDS.findall(text))
    analytical_score = len(_ANALYTICAL_WORDS.findall(text))

    # Short sentences with question marks lean analytical
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    avg_len = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
    if avg_len < 8 and '?' in text:
        analytical_score += 1

    # Long sentences lean creative/exploratory
    if avg_len > 15:
        creative_score += 0.5
        exploratory_score += 0.5

    scores = {
        URGENT: urgent_score,
        ANALYTICAL: analytical_score,
        CREATIVE: creative_score,
        EXPLORATORY: exploratory_score,
    }

    best = max(scores, key=scores.get)

    # Only return non-analytical if there's a clear signal
    if scores[best] < 1.0:
        return ANALYTICAL

    return best
