"""
agents/skill_intent.py - lightweight routing for local-agent tool nudges.

Local models can answer ordinary creative/chat prompts directly. The skill
loop nudge is useful for file, project, and diagnostic work, but it can
contaminate plain answers by pressuring the model to invent SKILL commands.
"""

import re


_CREATIVE_TERMS = re.compile(
    r"\b("
    r"song|lyrics?|verse|chorus|poem|story|joke|caption|prompt|image|picture|"
    r"video|audio|music|melody|beat|art|paint|draw|creative|write me|compose"
    r")\b",
    re.IGNORECASE,
)

_STRONG_TOOL_TERMS = re.compile(
    r"\b("
    r"fix|patch|edit|change|update|implement|refactor|debug|test|run|inspect|"
    r"read|search|find|open|create|delete|move|rename|migrate|seed|record|"
    r"add|route|restart|verify|investigate|consolidate|archive"
    r")\b",
    re.IGNORECASE,
)

_OPERATIONAL_CONTEXT_TERMS = re.compile(
    r"\b("
    r"project|proposal|studio|tasker|knowledge center|kc|database|db|sqlite|"
    r"file|folder|directory|repo|repository|code|api|endpoint|ui|frontend|"
    r"backend|timeout|handoff|agent|memory|calendar|newsletter|sap|vortex"
    r")\b",
    re.IGNORECASE,
)


def message_likely_needs_skills(message):
    """Return True when a user request probably needs local skills/tools.

    This intentionally favors direct answers for creative-only prompts. If a
    creative request also mentions operational actions, Studio, files, or
    debugging, it still routes through the skill nudge.
    """
    text = str(message or "").strip()
    if not text:
        return False

    if _STRONG_TOOL_TERMS.search(text):
        return True

    has_creative_intent = bool(_CREATIVE_TERMS.search(text))
    if has_creative_intent:
        return False

    if _OPERATIONAL_CONTEXT_TERMS.search(text):
        return True

    return False
