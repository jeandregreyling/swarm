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
import fnmatch
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/lib/system')
sys.path.insert(0, '/home/seven/swarm/lib/email')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/agents/specialists')

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
    'ticket_create': {
        'description': 'Create an internal ticket/proposal. Format: <title> || <description>',
        'trust_level': 1,
        'usage': 'SKILL ticket_create <title> || <description>',
        'example': 'SKILL ticket_create Validate queue edge-case || Run sandbox test for duplicate queue ids and report findings',
    },
    'alm_create_proposal': {
        'description': 'Create an ALM work proposal/ticket. Accepts quoted title+description or <title> || <description>.',
        'trust_level': 1,
        'usage': 'SKILL alm_create_proposal "<title>" "<description>"',
        'example': 'SKILL alm_create_proposal "Per-window theme propagation" "Ensure windows inherit app theme at creation and support local overrides."',
    },
    'fs_readonly': {
        'description': 'Read-only filesystem helper for workspace discovery (ls/find/read/head/tail/lines).',
        'trust_level': 0,
        'usage': 'SKILL fs_readonly <ls|find|read|head|tail|lines> <path> [args]',
        'example': 'SKILL fs_readonly lines frontend/terminal.py 5310 5360',
    },
    'fs_write': {
        'description': 'Write (overwrite) any file within the swarm repo. Creates parent dirs as needed.',
        'trust_level': 2,
        'usage': 'SKILL fs_write <path> <content>',
        'example': 'SKILL fs_write sandpits/ten/draft.py print("hello")',
    },
    'fs_patch': {
        'description': 'Replace an exact string in a file (first occurrence). Safe targeted edit without full rewrite.',
        'trust_level': 2,
        'usage': 'SKILL fs_patch <path> <<<OLD>>>exact old text<<<NEW>>>replacement text',
        'example': 'SKILL fs_patch utils/config.py <<<OLD>>>TEN_MODEL = \'gpt-4.1\'<<<NEW>>>TEN_MODEL = \'gpt-4.1-mini\'',
    },
    'knowledge_search': {
        'description': 'Search the consultant knowledge library (SAP HCM, ABAP, emails, PDFs, SAP notes).',
        'trust_level': 0,
        'usage': 'SKILL knowledge_search <query>',
        'example': 'SKILL knowledge_search ECP payroll integration schema',
    },
        'ui_css_edit_checklist': {
            'description': 'Show the global checklist for correct UI/CSS edit workflow (selectors, patching, verification).',
            'trust_level': 0,
            'usage': 'SKILL ui_css_edit_checklist',
            'example': 'SKILL ui_css_edit_checklist',
        },
}


# ── Logging ───────────────────────────────────────────────────────────────────

# Skills that should create a work_proposal entry when they succeed
_PROPOSAL_SKILLS = {'file_write', 'shell', 'schedule', 'fs_write', 'fs_patch'}


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

def _skill_ui_css_edit_checklist(args, agent, **_):
    """Return the global UI/CSS edit checklist for all agents."""
    try:
        path = '/memories/ui-css-edit-checklist.md'
        with open(path, encoding='utf-8') as f:
            content = f.read()
        return True, content
    except Exception as e:
        return False, f'Could not read checklist: {e}'

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
        lines = []
        for row in results[:8]:
            r = dict(row)
            lines.append(
                f'[{r.get("agent", "?")} imp:{r.get("importance", "?")}] '
                f'{r.get("subject", "")}: {str(r.get("content", ""))[:120]}'
            )
        return True, '\n'.join(lines)
    except Exception as e:
        return False, f'Memory search error: {e}'


_FS_ROOT = Path('/home/seven/swarm').resolve()


def _fs_safe_path(path_text):
    candidate = (path_text or '.').strip()
    base = _FS_ROOT
    if candidate.startswith('/'):
        resolved = Path(candidate).resolve()
    else:
        resolved = (base / candidate).resolve()
    if not str(resolved).startswith(str(base)):
        return None
    return resolved


def _skill_fs_readonly(args, agent, **_):
    raw = (args or '').strip()
    if not raw:
        return False, 'Usage: SKILL fs_readonly <ls|find|read|head|tail> <path> [args]'

    parts = raw.split()
    action = parts[0].lower()

    if action == 'ls':
        rel = parts[1] if len(parts) > 1 else '.'
        target = _fs_safe_path(rel)
        if not target or not target.exists() or not target.is_dir():
            return False, f'Invalid directory: {rel}'
        entries = sorted(target.iterdir(), key=lambda p: p.name.lower())[:120]
        lines = []
        for p in entries:
            suffix = '/' if p.is_dir() else ''
            try:
                rel_path = str(p.relative_to(_FS_ROOT))
            except Exception:
                rel_path = p.name
            lines.append(rel_path + suffix)
        return True, '\n'.join(lines) if lines else '(empty directory)'

    if action == 'find':
        rel = parts[1] if len(parts) > 1 else '.'
        pattern = parts[2] if len(parts) > 2 else '*'
        try:
            limit = max(1, min(int(parts[3]) if len(parts) > 3 else 50, 200))
        except Exception:
            limit = 50
        target = _fs_safe_path(rel)
        if not target or not target.exists() or not target.is_dir():
            return False, f'Invalid directory: {rel}'
        matches = []
        for p in target.rglob('*'):
            if len(matches) >= limit:
                break
            name = p.name + ('/' if p.is_dir() else '')
            if not fnmatch.fnmatch(name.rstrip('/'), pattern):
                continue
            try:
                rel_path = str(p.relative_to(_FS_ROOT))
            except Exception:
                rel_path = str(p)
            matches.append(rel_path + ('/' if p.is_dir() else ''))
        return True, '\n'.join(matches) if matches else '(no matches)'

    if action in {'read', 'head', 'tail', 'lines'}:
        if len(parts) < 2:
            return False, f'Usage: SKILL fs_readonly {action} <path> [n]'
        rel = parts[1]
        target = _fs_safe_path(rel)
        if not target or not target.exists() or not target.is_file():
            return False, f'Invalid file: {rel}'
        try:
            text = target.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            return False, f'File read failed: {e}'

        if action == 'read':
            max_chars = 8000
            if len(parts) > 2:
                try:
                    max_chars = max(200, min(int(parts[2]), 40000))
                except Exception:
                    max_chars = 8000
            if len(text) > max_chars:
                text = text[:max_chars] + '\n\n[... truncated ...]'
            return True, text

        if action == 'lines':
            # SKILL fs_readonly lines <path> <start> [end]
            # Returns lines start..end (1-indexed, inclusive). Default window: 80 lines.
            file_lines = text.splitlines()
            total = len(file_lines)
            try:
                start = max(1, int(parts[2]) if len(parts) > 2 else 1)
            except Exception:
                start = 1
            try:
                end = min(total, int(parts[3]) if len(parts) > 3 else start + 79)
            except Exception:
                end = min(total, start + 79)
            end = min(end, start + 299)  # hard cap: max 300 lines per call
            picked = file_lines[start - 1:end]
            header = f'[{rel} lines {start}–{end} of {total}]\n'
            return True, header + '\n'.join(f'{start + i:5d}  {l}' for i, l in enumerate(picked))

        file_lines = text.splitlines()
        n = 40
        if len(parts) > 2:
            try:
                n = max(1, min(int(parts[2]), 300))
            except Exception:
                n = 40
        picked = file_lines[:n] if action == 'head' else file_lines[-n:]
        return True, '\n'.join(picked)

    return False, 'Unknown fs_readonly action. Use: ls, find, read, head, tail, lines'


def _skill_ticket_create(args, agent, **_):
    payload = (args or '').strip()
    if not payload:
        return False, 'Usage: SKILL ticket_create <title> || <description>'

    if '||' in payload:
        title, description = [x.strip() for x in payload.split('||', 1)]
    else:
        # Fallback: first sentence as title, full payload as description
        title = payload.split('.', 1)[0].strip()[:120] or 'Internal ticket from skill'
        description = payload

    if not title:
        return False, 'ticket_create requires a non-empty title.'

    try:
        from queue_manager import intake_internal
        queue_id, proposal_id = intake_internal(agent, title, description, priority=5)
        return True, f'Internal ticket created: queue_id={queue_id}, proposal_id={proposal_id}'
    except Exception as e:
        return False, f'ticket_create failed: {e}'


def _skill_alm_create_proposal(args, agent, **_):
    payload = (args or '').strip()
    if not payload:
        return False, 'Usage: SKILL alm_create_proposal "<title>" "<description>"'

    title = ''
    description = ''

    # Preferred format: two quoted strings
    m = re.match(r'^"([^"]+)"\s+"([\s\S]+)"$', payload)
    if m:
        title, description = m.group(1).strip(), m.group(2).strip()
    elif '||' in payload:
        # Compatibility format
        title, description = [x.strip() for x in payload.split('||', 1)]
    else:
        # Fallback: first sentence as title, full body as description
        title = payload.split('.', 1)[0].strip()[:120] or 'ALM proposal from skill'
        description = payload

    if not title:
        return False, 'alm_create_proposal requires a non-empty title.'

    try:
        from queue_manager import intake_internal
        queue_id, proposal_id = intake_internal(agent, title, description, priority=5)
        return True, f'ALM proposal created: queue_id={queue_id}, proposal_id={proposal_id}'
    except Exception as e:
        return False, f'alm_create_proposal failed: {e}'


def _skill_fs_write(args, agent, **_):
    """Write (overwrite) any file within the swarm repo."""
    raw = (args or '').strip()
    if not raw:
        return False, 'Usage: SKILL fs_write <path> <content>'
    parts = raw.split(None, 1)
    if len(parts) < 2:
        return False, 'Usage: SKILL fs_write <path> <content>'
    rel, content = parts[0], parts[1]
    target = _fs_safe_path(rel)
    if not target:
        return False, f'Path outside swarm root or invalid: {rel}'
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return True, f'Written {len(content)} chars to {rel}'
    except Exception as e:
        return False, f'fs_write failed: {e}'


def _skill_fs_patch(args, agent, **_):
    """Replace first occurrence of an exact string in a file."""
    raw = (args or '').strip()
    if '<<<OLD>>>' not in raw or '<<<NEW>>>' not in raw:
        return False, 'Usage: SKILL fs_patch <path> <<<OLD>>>old text<<<NEW>>>new text'
    path_and_rest, new_text = raw.split('<<<NEW>>>', 1)
    if '<<<OLD>>>' not in path_and_rest:
        return False, 'Missing <<<OLD>>> marker'
    path_part, old_text = path_and_rest.split('<<<OLD>>>', 1)
    rel = path_part.strip()
    target = _fs_safe_path(rel)
    if not target:
        return False, f'Path outside swarm root or invalid: {rel}'
    if not target.exists() or not target.is_file():
        return False, f'File not found: {rel}'
    try:
        original = target.read_text(encoding='utf-8', errors='replace')
        if old_text not in original:
            return False, f'Old text not found in {rel}. No changes made.'
        patched = original.replace(old_text, new_text, 1)
        target.write_text(patched, encoding='utf-8')
        return True, f'Patched {rel}: replaced {len(old_text)} chars with {len(new_text)} chars'
    except Exception as e:
        return False, f'fs_patch failed: {e}'


def _skill_knowledge_search(args, agent, **_):
    query = (args or '').strip()
    if not query:
        return False, 'Usage: SKILL knowledge_search <query>'
    try:
        import sys
        from pathlib import Path as _Path
        _swarm = str(_Path(__file__).resolve().parents[1])
        if _swarm not in sys.path:
            sys.path.insert(0, _swarm)
        from lib.knowledge.retrieval import search
        results = search(query, top_k=5)
        if not results:
            return True, 'No matching knowledge found.'
        lines = []
        for r in results:
            excerpt = r['chunk_text'][:400].replace('\n', ' ')
            lines.append(f"[{r['title']} | score:{r['score']:.2f}]\n{excerpt}")
        return True, '\n\n---\n'.join(lines)
    except Exception as e:
        return False, f'knowledge_search error: {e}'


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
    'ticket_create':  _skill_ticket_create,
    'alm_create_proposal': _skill_alm_create_proposal,
    'fs_readonly':    _skill_fs_readonly,
    'fs_write':       _skill_fs_write,
    'fs_patch':        _skill_fs_patch,
    'knowledge_search': _skill_knowledge_search,
    'ui_css_edit_checklist': _skill_ui_css_edit_checklist,
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
