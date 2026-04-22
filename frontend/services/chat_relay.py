"""chat_relay.py — Pure chat relay / intent parsing helpers

Extracted from frontend/blueprints/chat.py during Session 25 Step 4.
All functions here are pure: no DB, no network, no I/O. They operate on
strings only.

LINKED TO:
  frontend/blueprints/chat.py — consumes these through `from services import *`.
  services/__init__.py        — re-exports every name below.
"""
import re

from .chat_jobs import _normalize_chat_participant


# Patterns that indicate an agent is trying to route to another agent.
_RELAY_ROUTE_PATTERNS = re.compile(
    r'(?:'
    r'(?:route|send|forward|hand(?:\s*off)?|pass|relay|escalate|ask|check\s+with|consult)\s+(?:this\s+)?(?:to\s+)?(?:agent\s+)?(?:ten|nine|eight|eleven|twelve|thirteen|gemma|llama|mistral|qwen|duck|sniffles|librarian|grok|claude|scholar|seeker|phi3|lmstudio|deepseek.local)\b'
    r'|(?:ten|nine|eight|eleven|twelve|thirteen|gemma|llama|mistral|qwen|duck|sniffles|librarian|grok|claude|scholar|seeker|phi3|lmstudio|deepseek.local):\s+can\s+you'
    r'|→\s*(?:ten|nine|eight|eleven|twelve|thirteen|gemma|llama|mistral|qwen|duck|sniffles|librarian|grok|claude|scholar|seeker|phi3|lmstudio|deepseek.local)\b'
    r'|(?:\d+\s*[·•]\s*)?(?:ten|nine|eight|eleven|twelve|thirteen|grok|claude)\s+to\s+(?:\d+\s*[·•]\s*)?(?:ten|nine|eight|eleven|twelve|thirteen|grok|claude)'
    r')',
    re.IGNORECASE,
)


# Lines that are purely routing/handoff instructions with no content value.
_RELAY_LINE_PATTERNS = re.compile(
    r'^\s*(?:'
    r'(?:ten|nine|eight|eleven|twelve|thirteen|gemma|llama|mistral|qwen|duck|sniffles|librarian|grok|claude|scholar|seeker|phi3|lmstudio|deepseek.local):\s+can\s+you\b.*'
    r'|(?:\d+\s*[·•]\s*)?(?:ten|nine|eight|eleven|twelve|thirteen|grok|claude)\s+to\s+\S.*'
    r'|route\s+to\s+\S.*'
    r'|→\s*(?:ten|nine|eight|eleven|twelve|thirteen|gemma|llama|mistral|qwen|duck|sniffles|librarian|grok|claude|scholar|seeker|phi3|lmstudio|deepseek.local)\b.*'
    r'|\d+\s*[·•]\s*(?:ten|nine|eight|eleven|twelve|thirteen|grok|claude|github|groq).*?:\s+.*'
    r')\s*$',
    re.IGNORECASE,
)


def _infer_reply_target_from_text(response_text):
    text = str(response_text or '').strip()
    if not text:
        return ''
    _relay_re = re.compile(r'^(?:@)?([A-Za-z][A-Za-z0-9_ /-]{0,30})\s*[:,]\s+', re.MULTILINE)
    # Check first line (legacy format: relay at start)
    first_line = text.splitlines()[0].strip()
    match = _relay_re.match(first_line)
    if match:
        target = _normalize_chat_participant(match.group(1))
        if target:
            return target
    # Check last 5 lines (instructed format: relay at end of response)
    tail_lines = text.splitlines()[-5:]
    for line in reversed(tail_lines):
        line = line.strip()
        if not line:
            continue
        match = _relay_re.match(line)
        if match:
            target = _normalize_chat_participant(match.group(1))
            if target:
                return target
    return ''


def _resolve_chat_reply_target(selected_agent, response_text, reply_context):
    explicit = _infer_reply_target_from_text(response_text)
    selected = _normalize_chat_participant(selected_agent)
    if explicit and explicit != selected and explicit != 'fridays':
        return explicit

    fallback = _normalize_chat_participant(reply_context.get('default_reply_target')) or 'user'
    if fallback == selected:
        fallback = _normalize_chat_participant(reply_context.get('previous_participant')) or 'user'
    if fallback == 'ghost':
        return 'user'
    return fallback or 'user'


def _gate_relay_target(target, allowed_agents):
    """Restrict relay targets to agents that were explicitly selected for this conversation.

    Agents are only allowed to relay to agents in allowed_agents (the initial
    normalized_agents selection). Any out-of-scope target is redirected to 'user'
    so the response surfaces to Ghost rather than spawning an unexpected chain.
    """
    if not target or target in ('user', 'ghost', 'fridays'):
        return target or 'user'
    if target in allowed_agents:
        return target
    return 'user'


def _parse_chat_skill_command(text):
    raw = (text or '').strip()
    upper = raw.upper()
    if not raw:
        return None

    if upper in {'/SKILLS', 'SKILLS', '/SKILL', 'SKILL'}:
        return 'list', ''

    if upper.startswith('/SKILL '):
        payload = raw[7:].strip()
    elif upper.startswith('SKILL '):
        payload = raw[6:].strip()
    else:
        return None

    if not payload:
        return 'list', ''

    parts = payload.split(None, 1)
    skill_name = parts[0].strip().lower()
    skill_args = parts[1].strip() if len(parts) > 1 else ''
    return skill_name, skill_args


def _strip_relay_routing(text: str) -> str:
    """Remove agent-routing language from a response when auto_relay is OFF.

    Removes:
    - Lines that are just routing directives ("Ten: can you...", "→ Eight", "Route to X")
    - Agent-to-agent question lines injected at the end of responses
    """
    if not text:
        return text
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        if _RELAY_LINE_PATTERNS.match(line):
            continue  # drop pure routing lines
        cleaned.append(line)
    result = '\n'.join(cleaned).strip()
    return result or text  # never return empty if we had content


def _is_execution_confirmation(text):
    raw = str(text or '').strip().lower()
    if not raw:
        return False
    confirmations = {
        'go ahead', 'yes', 'y', 'yep', 'yeah', 'continue', 'proceed', 'do it',
        'go for it', 'execute', 'run it', 'ship it',
    }
    if raw in confirmations:
        return True
    return bool(re.search(r'\b(go\s+ahead|continue|proceed|do\s+it|execute|run\s+it|ship\s+it|yes)\b', raw))


def _derive_proposal_from_text(selected_agent, text, user_prompt):
    body = str(text or '').strip()
    if not body:
        return None

    # Require at least one structured field label in colon form.
    # Bare mentions of words like "title" or "description" in a conversational
    # response must not auto-trigger proposal creation.
    if not re.search(r'(?:title|description|scope|goal|objective)\s*:', body, re.IGNORECASE):
        return None

    title = ''
    desc = ''

    m_title = re.search(r'(?:\*\*\s*)?title(?:\s*\*\*)?\s*:\s*(.+)', body, re.IGNORECASE)
    if m_title:
        title = m_title.group(1).strip().strip('*').strip()

    m_desc = re.search(r'(?:\*\*\s*)?description(?:\s*\*\*)?\s*:\s*([\s\S]{20,1200})', body, re.IGNORECASE)
    if m_desc:
        desc = m_desc.group(1).strip()
        desc = re.split(r'\n\s*(?:---|##+\s+|\*\*\w)', desc, maxsplit=1)[0].strip()

    if not title:
        title = f'{selected_agent} proposal from chat confirmation'
    if not desc:
        desc = str(user_prompt or '').strip()[:600] or body[:600]

    if not title or not desc:
        return None

    return title[:180], desc[:1500]


def _extract_skill_lines_from_text(text):
    from fridays.skills import parse_skill_command

    cmds = []
    for raw_line in str(text or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = None
        if line.upper().startswith('SKILL '):
            parsed = parse_skill_command(line)
        elif line.upper().startswith('/SKILL '):
            parsed = parse_skill_command('SKILL ' + line[7:].strip())
        if not parsed:
            continue
        skill_name, skill_args = parsed
        if skill_name == 'list':
            continue
        cmds.append((skill_name, skill_args))
    return cmds[:4]


__all__ = [
    '_RELAY_LINE_PATTERNS',
    '_RELAY_ROUTE_PATTERNS',
    '_derive_proposal_from_text',
    '_extract_skill_lines_from_text',
    '_gate_relay_target',
    '_infer_reply_target_from_text',
    '_is_execution_confirmation',
    '_parse_chat_skill_command',
    '_resolve_chat_reply_target',
    '_strip_relay_routing',
]
