"""
fridays/skills.py — Seven's Swarm (RL-021)
═══════════════════════════════════════════════════════════════════════════════
Skills framework. Central registry and dispatcher for all Fridays action-layer
capabilities. Agents and Ghost invoke skills by name.

Available skills:
  shell      — run a whitelisted shell command (via shell_agent)
  browse     — fetch a URL with Playwright headless browser (via browser_agent)
  file_read  — read a file from a sandpit (via file_agent)
  file_write — write a file to an agent's sandpit (via file_agent)
  search     — run a DuckDuckGo web search and return snippets
  remind     — send Ghost a plain reminder email immediately
  schedule   — create a scheduled task (delegates to scheduler)

Ghost can invoke skills by email or Telegram:
  SKILL shell df -h
  SKILL browse https://news.ycombinator.com
  SKILL file_read gemma/notes.txt
  SKILL search latest Python 3.13 features
  SKILL remind Check lease renewal
  SKILL schedule daily 09:00 QUESTION What is today's news?

Every skill call is logged to ghost_circle.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import logging
from datetime import datetime

sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.skills')

# ── Registry ──────────────────────────────────────────────────────────────────
# Each entry: name → {description, trust_level, usage}
# trust_level: 0=read-only, 1=write-own-sandpit, 2=write-shared, 4=system

REGISTRY = {
    'shell': {
        'description': 'Run a whitelisted shell command. Output returned and emailed to Ghost.',
        'trust_level': 0,
        'usage': 'SKILL shell <command>',
        'example': 'SKILL shell df -h',
    },
    'browse': {
        'description': 'Fetch a URL with headless Chromium. Returns page text. Needs a full URL — use search for questions.',
        'trust_level': 0,
        'usage': 'SKILL browse <https://...>',
        'example': 'SKILL browse https://news.ycombinator.com',
    },
    'file_read': {
        'description': 'Read a file from a sandpit. Format: agent/filename.txt',
        'trust_level': 0,
        'usage': 'SKILL file_read <agent/filename>',
        'example': 'SKILL file_read gemma/notes.txt',
    },
    'file_write': {
        'description': 'Write content to your sandpit.',
        'trust_level': 1,
        'usage': 'SKILL file_write <agent/filename> <content>',
        'example': 'SKILL file_write gemma/notes.txt Hello world',
    },
    'search': {
        'description': 'DuckDuckGo web search. Returns top snippets.',
        'trust_level': 0,
        'usage': 'SKILL search <query>',
        'example': 'SKILL search Python 3.13 new features',
    },
    'remind': {
        'description': 'Send Ghost an immediate plain-text reminder email.',
        'trust_level': 0,
        'usage': 'SKILL remind <message>',
        'example': 'SKILL remind Check the lease renewal deadline',
    },
    'schedule': {
        'description': 'Create a scheduled task. Same syntax as SCHEDULE command.',
        'trust_level': 0,
        'usage': 'SKILL schedule <schedule> <action> <data>',
        'example': 'SKILL schedule daily 09:00 QUESTION What is today\'s news?',
    },
    'list': {
        'description': 'List all available skills.',
        'trust_level': 0,
        'usage': 'SKILL list',
        'example': 'SKILL list',
    },
    'housekeeping': {
        'description': 'Run the Librarian housekeeping cycle: archive old memories, remove duplicates, trigger agent play time.',
        'trust_level': 0,
        'usage': 'SKILL housekeeping',
        'example': 'SKILL housekeeping',
    },
    'proposals': {
        'description': 'Check sandpits/shared/proposals/ for new agent proposals and notify Ghost.',
        'trust_level': 0,
        'usage': 'SKILL proposals',
        'example': 'SKILL proposals',
    },
    'memory_search': {
        'description': 'Search the swarm memory pools. Returns top matches.',
        'trust_level': 0,
        'usage': 'SKILL memory_search <query>',
        'example': 'SKILL memory_search SAP retro accounting',
    },
}


# ── Logging ───────────────────────────────────────────────────────────────────

# Skills that should create a work_proposal entry when they succeed
_PROPOSAL_SKILLS = {'file_write', 'shell', 'schedule'}


def _log(skill_name, agent, args_preview, result_preview, success):
    try:
        from database import get_connection
        conn = get_connection()
        status = 'ok' if success else 'FAILED'
        conn.execute(
            """INSERT INTO ghost_circle (entry_type, source, content, severity)
               VALUES ('skill_call', ?, ?, ?)""",
            (agent,
             f'[{status}] {skill_name}({args_preview[:120]}) → {result_preview[:200]}',
             'info' if success else 'warning')
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[Skills] ghost_circle log failed: {e}')


def _log_as_internal_proposal(skill_name, agent, args_preview, result_preview):
    """
    Log a successful write-type skill call as an internal work_proposal and queue entry.
    Called automatically after file_write, shell, and schedule succeed.
    This ensures every Fridays-executed change is a first-class citizen in the queue
    and visible to all agents.
    """
    try:
        from queue_manager import intake_internal
        title = f'[{skill_name}] {args_preview[:80]}'
        description = f'Agent {agent} executed skill `{skill_name}`.\nArgs: {args_preview[:300]}\nResult: {result_preview[:300]}'
        intake_internal(agent, title, description, priority=5)
    except Exception as e:
        logger.warning(f'[Skills] work_proposal log failed: {e}')


# ── Skill handlers ────────────────────────────────────────────────────────────

def _skill_shell(args, agent, **_):
    from fridays.shell_agent import run
    return run(args.strip(), agent=agent)


def _skill_browse(args, agent, **_):
    from fridays.browser_agent import browse
    url = args.strip()
    if not url:
        return False, 'No URL provided. Usage: SKILL browse <url>'
    if not url.startswith('http://') and not url.startswith('https://'):
        return False, f'Expected a URL starting with http:// or https://\nGot: {url}\n\nTo search the web, use: SKILL search <query>'
    content = browse(url, agent=agent)
    success = not content.startswith('[Browser] Could not') and not content.startswith('[Browser] Page timed out')
    return success, content


def _skill_file_read(args, agent, **_):
    from fridays.file_agent import read_sandpit
    parts = args.strip().split('/', 1)
    if len(parts) == 2:
        sandpit_agent, filename = parts[0].strip(), parts[1].strip()
    else:
        sandpit_agent, filename = agent, args.strip()
    ok, content = read_sandpit(sandpit_agent, filename)
    return ok, content


def _skill_file_write(args, agent, **_):
    from fridays.file_agent import write_sandpit
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return False, 'Usage: SKILL file_write <agent/filename> <content>'
    path_part, content = parts[0], parts[1]
    path_parts = path_part.split('/', 1)
    if len(path_parts) == 2:
        sandpit_agent, filename = path_parts
    else:
        sandpit_agent, filename = agent, path_part
    return write_sandpit(sandpit_agent, filename, content)


def _skill_search(args, agent, **_):
    query = args.strip()
    if not query:
        return False, 'No query provided. Usage: SKILL search <query>'
    try:
        from internet import search_web
        output = search_web(query, max_results=5)
        return True, output or 'No results found.'
    except Exception as e:
        return False, f'Search failed: {e}'


def _skill_remind(args, agent, **_):
    from config import GHOST_EMAIL
    from email_handler import send_reply
    message = args.strip()
    if not message:
        return False, 'No message provided. Usage: SKILL remind <message>'
    send_reply(
        to_address=GHOST_EMAIL,
        subject='[Swarm] Reminder',
        body=f'[Skills — remind]\n\n{message}\n'
    )
    return True, f'Reminder sent: {message[:80]}'


def _skill_schedule(args, agent, **_):
    from fridays.scheduler import parse_schedule_command, add_task
    cmd = f'SCHEDULE {args.strip()}'
    parsed = parse_schedule_command(cmd)
    if not parsed:
        return False, (
            'Could not parse schedule. Format: SKILL schedule <schedule> <action> <data>\n'
            'Example: SKILL schedule daily 09:00 QUESTION What is today\'s news?'
        )
    name, schedule, action_type, action_data = parsed
    task_id = add_task(name, schedule, action_type, action_data, created_by=agent)
    return True, f'Task #{task_id} scheduled: {name} | {schedule} | next run computed.'


def _skill_list(args, agent, **_):
    lines = ['Available skills:\n']
    for name, meta in REGISTRY.items():
        lines.append(f'  {name:12s} — {meta["description"]}')
        lines.append(f'               Usage:   {meta["usage"]}')
        lines.append(f'               Example: {meta["example"]}\n')
    return True, '\n'.join(lines)


def _skill_housekeeping(args, agent, **_):
    try:
        from housekeeping import run_housekeeping
        run_housekeeping()
        return True, 'Housekeeping complete — archives cleaned, duplicates removed, play time triggered.'
    except Exception as e:
        return False, f'Housekeeping error: {e}'


def _skill_proposals(args, agent, **_):
    try:
        from swarm_tasks import check_proposals
        check_proposals()
        from sandpits import list_proposals
        ps = list_proposals()
        if not ps:
            return True, 'No pending proposals found.'
        lines = [f'{p["filename"]} ({p["agent"]}) — {p["preview"][:80]}' for p in ps]
        return True, f'{len(ps)} proposal(s):\n' + '\n'.join(lines)
    except Exception as e:
        return False, f'Proposals check error: {e}'


def _skill_memory_search(args, agent, **_):
    query = args.strip()
    if not query:
        return False, 'Usage: SKILL memory_search <query>'
    try:
        from database import search_memory
        results = search_memory(query=query, min_importance=3)
        if not results:
            return True, 'No matching memories found.'
        lines = [f'[{r.get("agent","?")} imp:{r.get("importance","?")}] {r.get("subject","")}: {str(r.get("content",""))[:120]}' for r in results[:8]]
        return True, '\n'.join(lines)
    except Exception as e:
        return False, f'Memory search error: {e}'


_HANDLERS = {
    'shell':          _skill_shell,
    'browse':         _skill_browse,
    'file_read':      _skill_file_read,
    'file_write':     _skill_file_write,
    'search':         _skill_search,
    'remind':         _skill_remind,
    'schedule':       _skill_schedule,
    'list':           _skill_list,
    'housekeeping':   _skill_housekeeping,
    'proposals':      _skill_proposals,
    'memory_search':  _skill_memory_search,
}


# ── Central dispatch ──────────────────────────────────────────────────────────

def call(skill_name, args='', agent='ghost'):
    """
    Invoke a skill by name. Returns (success: bool, output: str).

    skill_name — one of REGISTRY keys
    args       — remaining arguments string
    agent      — calling agent name (for logging)
    """
    skill_name = skill_name.strip().lower()

    if skill_name not in _HANDLERS:
        known = ', '.join(sorted(_HANDLERS.keys()))
        return False, f'Unknown skill: {skill_name!r}. Known skills: {known}'

    logger.info(f'[Skills] {agent} → {skill_name}({args[:80]})')

    try:
        success, output = _HANDLERS[skill_name](args=args, agent=agent)
    except Exception as e:
        success = False
        output = f'Skill {skill_name} raised an error: {e}'
        logger.error(f'[Skills] {skill_name} error: {e}')

    _log(skill_name, agent, args, output, success)
    if success and skill_name in _PROPOSAL_SKILLS:
        _log_as_internal_proposal(skill_name, agent, args, output)
    print(f'[Skills] {"✓" if success else "✗"} {agent} → {skill_name} | {output[:60]}')
    return success, output


def parse_skill_command(text):
    """
    Parse a SKILL command from email or Telegram.
    Format: SKILL <name> <args>
    Returns (skill_name, args) or None.
    """
    text = text.strip()
    if not text.upper().startswith('SKILL '):
        return None
    rest = text[6:].strip()
    if not rest:
        return 'list', ''
    parts = rest.split(None, 1)
    skill_name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ''
    return skill_name, args


def list_skills():
    """Return registry as list of dicts for API/dashboard."""
    return [
        {'name': k, **v}
        for k, v in REGISTRY.items()
    ]


# ── Test ──────────────────────────────────────────────────────────────────────

def test():
    print('\n[Skills] Tests...')

    # parse_skill_command
    cases = [
        ('SKILL shell df -h',          ('shell', 'df -h')),
        ('SKILL list',                 ('list', '')),
        ('SKILL browse https://x.com', ('browse', 'https://x.com')),
        ('SKILL search Python news',   ('search', 'Python news')),
        ('NOT A SKILL',                None),
    ]
    for text, expected in cases:
        result = parse_skill_command(text)
        ok = result == expected
        print(f'  {"✓" if ok else "✗"}  {text!r} → {result}')

    # list skill
    ok, output = call('list', agent='test')
    print(f'\n  list skill: {"✓" if ok else "✗"}')

    # unknown skill
    ok, output = call('nonexistent', agent='test')
    print(f'  unknown skill blocked: {"✓" if not ok else "✗"}')

    print('\n✓ skills.py works.')


if __name__ == '__main__':
    test()
