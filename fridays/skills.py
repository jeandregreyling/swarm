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

import os
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

from proposal_status import ACTIVE_PROPOSAL_STATUSES, STATUS_CLOSED

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
    'alm_self_approve': {
        'description': 'Self-approve your own proposal and set it to in_progress. Creates a Vortex checkpoint. No Ghost approval needed.',
        'trust_level': 1,
        'usage': 'SKILL alm_self_approve <proposal_id> [vortex_label]',
        'example': 'SKILL alm_self_approve WP-0042 before-banner-patch',
    },
    'alm_complete': {
        'description': 'Mark your own in_progress proposal as done (awaiting Ghost confirmation to close).',
        'trust_level': 1,
        'usage': 'SKILL alm_complete <proposal_id>',
        'example': 'SKILL alm_complete WP-0042',
    },
    'alm_vortex': {
        'description': 'Create a named Vortex (time machine) checkpoint. Call before making any file changes.',
        'trust_level': 1,
        'usage': 'SKILL alm_vortex <label>',
        'example': 'SKILL alm_vortex before-banner-redesign',
    },
    'fs_readonly': {
        'description': 'Read-only filesystem helper for workspace discovery (ls/find/read/head/tail/lines/grep). Use grep to search file contents by pattern — much faster than reading line by line.',
        'trust_level': 0,
        'usage': 'SKILL fs_readonly <ls|find|read|head|tail|lines|grep> <path> [args]',
        'example': 'SKILL fs_readonly grep frontend/blueprints/chat.py 900',
    },
    'fs_write': {
        'description': 'Write (overwrite) any file within the swarm repo. Creates parent dirs as needed.',
        'trust_level': 2,
        'usage': 'SKILL fs_write <path> <content>',
        'example': 'SKILL fs_write sandpits/ten/draft.py print("hello")',
    },
    'fs_patch': {
        'description': 'Replace an exact string in a file (first occurrence). Use fs_patch_lines instead when you have line numbers.',
        'trust_level': 2,
        'usage': 'SKILL fs_patch <path> <<<OLD>>>exact old text<<<NEW>>>replacement text',
        'example': 'SKILL fs_patch utils/config.py <<<OLD>>>TEN_MODEL = \'gpt-4.1\'<<<NEW>>>TEN_MODEL = \'gpt-4.1-mini\'',
    },
    'fs_patch_lines': {
        'description': 'Replace a line range in a file by line numbers. PREFERRED over fs_patch — no exact-match fragility. Read with fs_readonly lines first to get line numbers, then replace that range.',
        'trust_level': 2,
        'usage': 'SKILL fs_patch_lines <path> <start_line> <end_line>\n<<<NEW>>>\nreplacement content',
        'example': 'SKILL fs_patch_lines frontend/static/js/views/fridays.js 9 41\n<<<NEW>>>\n  function _fetchAndRenderTemp() {\n    // new body\n  }',
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
    'fs_verify': {
        'description': 'Syntax-check a Python or JavaScript file after patching. ALWAYS run this after every fs_patch or fs_patch_lines call.',
        'trust_level': 0,
        'usage': 'SKILL fs_verify <path>',
        'example': 'SKILL fs_verify frontend/blueprints/chat.py',
    },
    'system_index': {
        'description': 'Generate or query the system index (modules, blueprints, tables, agents, skills). No args = regenerate. With args = search the index.',
        'trust_level': 0,
        'usage': 'SKILL system_index [search query]',
        'example': 'SKILL system_index circuit breaker',
    },
}


# ── Logging ───────────────────────────────────────────────────────────────────

# Skills that should create a work_proposal entry when they succeed
_PROPOSAL_SKILLS = {'file_write', 'shell', 'schedule', 'fs_write', 'fs_patch', 'fs_patch_lines'}


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


def _capture_file_diff(rel_path):
    """Run git diff on a single file. Returns diff string or empty string on failure."""
    import subprocess as _sp
    try:
        result = _sp.run(
            ['git', 'diff', 'HEAD', '--', rel_path],
            capture_output=True, text=True, timeout=10,
            cwd='/home/seven/swarm',
        )
        diff = result.stdout.strip()
        if not diff:
            # File may be untracked — try git diff without HEAD
            result2 = _sp.run(
                ['git', 'diff', '--', rel_path],
                capture_output=True, text=True, timeout=10,
                cwd='/home/seven/swarm',
            )
            diff = result2.stdout.strip()
        return diff[:4000] if diff else ''
    except Exception as e:
        logger.debug(f'[Skills] git diff failed for {rel_path}: {e}')
        return ''


def _extract_changed_path(skill_name, args):
    """Extract the file path from a write-type skill's args string."""
    try:
        raw = (args or '').strip()
        if skill_name in ('fs_patch', 'fs_patch_lines', 'fs_write'):
            # Path is always the first token before any space or <<<
            first = re.split(r'[\s<]', raw)[0].strip()
            return first if first else None
        if skill_name in ('file_write',):
            # path is first token (may include agent/ prefix)
            return raw.split()[0] if raw else None
    except Exception:
        pass
    return None


def _attach_diff_to_active_proposal(agent, rel_path, diff):
    """Find the agent's current in_progress proposal and append the diff to its description."""
    if not diff:
        return
    try:
        from database import get_connection
        conn = get_connection()
        row = conn.execute(
            """SELECT proposal_id, description FROM work_proposals
               WHERE agent=? AND status='in_progress'
               ORDER BY created_at DESC LIMIT 1""",
            (agent,)
        ).fetchone()
        if row:
            pid = row['proposal_id'] if isinstance(row, dict) else row[0]
            existing = row['description'] if isinstance(row, dict) else row[1]
            tracer_block = (
                f'\n\n---\n**Tracer — {rel_path}**\n'
                f'```diff\n{diff}\n```'
            )
            conn.execute(
                "UPDATE work_proposals SET description=? WHERE proposal_id=?",
                ((existing or '') + tracer_block, pid)
            )
            conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f'[Skills] tracer proposal update failed: {e}')


def _log_as_internal_proposal(skill_name, agent, args_preview, result_preview, diff=''):
    """
    Log a successful write-type skill call as an internal work_proposal and queue entry.
    Called automatically after file_write, shell, and schedule succeed.
    This ensures every Fridays-executed change is a first-class citizen in the queue
    and visible to all agents.

    Marked closed immediately so it does not appear as an actionable pending item —
    it is a change-log record only, used by the alm_complete guard.

    If `diff` is provided, it is embedded in the description as a fenced diff block.
    """
    try:
        from queue_manager import intake_internal, update_proposal_status
        title = f'[{skill_name}] {args_preview[:80]}'
        description = (
            f'Agent {agent} executed skill `{skill_name}`.\n'
            f'Args: {args_preview[:300]}\n'
            f'Result: {result_preview[:300]}'
        )
        if diff:
            description += f'\n\n---\n**Tracer diff:**\n```diff\n{diff}\n```'
        _, proposal_id = intake_internal(agent, title, description, priority=5)
        update_proposal_status(proposal_id, STATUS_CLOSED)
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


# SWARM_ROOT env var lets DEV/UAT servers redirect file operations to their
# own worktree directory instead of the PROD filesystem.
# Default: /home/seven/swarm (the canonical PROD location).
_FS_ROOT = Path(os.environ.get('SWARM_ROOT', '/home/seven/swarm')).resolve()


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

    # Implicit 'read' — if first token looks like a file path rather than an action keyword,
    # prepend 'read' so that `SKILL fs_readonly path/to/file` works correctly.
    _KNOWN_ACTIONS = {'ls', 'find', 'read', 'head', 'tail', 'lines', 'grep'}
    if action not in _KNOWN_ACTIONS and ('/' in parts[0] or '.' in parts[0]):
        raw = 'read ' + raw
        parts = raw.split()
        action = 'read'

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

    if action == 'grep':
        # SKILL fs_readonly grep <path> <pattern> [context_lines]
        # Searches file content for pattern, returns matching lines with line numbers.
        # context_lines (default 2) shows surrounding lines for context.
        if len(parts) < 3:
            return False, 'Usage: SKILL fs_readonly grep <path> <pattern> [context_lines]'
        rel = parts[1]
        pattern = parts[2]
        try:
            ctx = max(0, min(int(parts[3]) if len(parts) > 3 else 2, 10))
        except Exception:
            ctx = 2
        target = _fs_safe_path(rel)
        if not target or not target.exists() or not target.is_file():
            return False, f'Invalid file: {rel}'
        try:
            file_lines = target.read_text(encoding='utf-8', errors='replace').splitlines()
        except Exception as e:
            return False, f'Could not read {rel}: {e}'
        import re as _re
        try:
            pat = _re.compile(pattern, _re.IGNORECASE)
        except _re.error:
            pat = _re.compile(_re.escape(pattern), _re.IGNORECASE)
        hits = [i for i, l in enumerate(file_lines) if pat.search(l)]
        if not hits:
            return True, f'No matches for "{pattern}" in {rel}'
        shown = set()
        result_lines = []
        for i in hits:
            for j in range(max(0, i - ctx), min(len(file_lines), i + ctx + 1)):
                if j not in shown:
                    shown.add(j)
                    marker = '>>>' if j == i else '   '
                    result_lines.append(f'{j + 1:5d} {marker} {file_lines[j]}')
        return True, f'grep "{pattern}" in {rel} — {len(hits)} match(es):\n' + '\n'.join(result_lines[:200])

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


def _skill_alm_create_proposal(args, agent, source_conv_id=None, **_):
    """Create an ALM work proposal, record the originating chat thread, and trigger Duck review."""
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

    # Conversation-level dedup: if any active proposal already exists for this
    # conversation, return it rather than creating another.
    # This prevents Grok-style retry storms where a new proposal is created each
    # time the user nudges or the topic shifts slightly mid-task.
    if source_conv_id:
        try:
            import sys as _sys2
            _sys2.path.insert(0, '/home/seven/swarm/utils')
            from database import get_connection as _gc2
            _c2 = _gc2()
            _active_placeholders = ','.join('?' for _ in ACTIVE_PROPOSAL_STATUSES)
            existing = _c2.execute(
                f"""SELECT proposal_id, title FROM work_proposals
                    WHERE source_conv_id=?
                      AND status IN ({_active_placeholders})
                    ORDER BY created_at ASC
                    LIMIT 1""",
                (int(source_conv_id), *ACTIVE_PROPOSAL_STATUSES)
            ).fetchone()
            _c2.close()
            if existing:
                return True, (
                    f'Active proposal already exists for this conversation: {existing["proposal_id"]} — "{existing["title"]}".\n'
                    'Do NOT create another proposal. Use SKILL alm_self_approve to start it, '
                    'or SKILL alm_complete to finish it if changes are already done.\n'
                    'Only create a new proposal if the previous one is fully completed or rejected.'
                )
        except Exception:
            pass

    try:
        from queue_manager import intake_internal
        queue_id, proposal_id = intake_internal(agent, title, description, priority=5)

        # Record the originating conversation so Duck can reply back to the thread
        if source_conv_id:
            try:
                import sys as _sys
                _sys.path.insert(0, '/home/seven/swarm/utils')
                from database import get_connection as _gc
                _c = _gc()
                _c.execute(
                    'UPDATE work_proposals SET source_conv_id=? WHERE proposal_id=?',
                    (int(source_conv_id), proposal_id)
                )
                _c.commit()
                _c.close()
            except Exception:
                pass

        # Fire Duck review in background — Duck will post approval/rejection back to thread
        import threading as _threading
        def _duck_review():
            try:
                import sys as _s
                _s.path.insert(0, '/home/seven/swarm')
                from proposal_review import duck_review_proposal
                duck_review_proposal(proposal_id, title, description, agent, source_conv_id)
            except Exception:
                pass
        _threading.Thread(target=_duck_review, daemon=True).start()

        return True, f'ALM proposal created: queue_id={queue_id}, proposal_id={proposal_id}'
    except Exception as e:
        return False, f'alm_create_proposal failed: {e}'


def _alm_api_post(path, payload, timeout=10):
    """
    Call the local swarm API, trying all running server ports.
    Returns (data_dict, error_str).  error_str is None on success.
    """
    import requests as _req
    _PORTS = [5050, 5053, 5052, 5051]
    last_err = 'no server responded'
    for port in _PORTS:
        try:
            url = f'http://127.0.0.1:{port}{path}'
            resp = _req.post(url, json=payload, timeout=timeout)
            data = resp.json()
            if data.get('ok'):
                return data, None
            # Got a response but not ok — keep trying other ports if "not found"
            if 'not found' in str(data.get('error', '')).lower():
                last_err = f'port {port}: {data.get("error")}'
                continue
            return data, data.get('error', resp.text[:200])
        except Exception as e:
            last_err = f'port {port}: {e}'
    return {}, last_err


def _skill_alm_self_approve(args, agent, **_):
    """Advance own proposal: pending/approved → in_progress with Vortex checkpoint."""
    raw = (args or '').strip()
    # Split args into proposal_id and optional vortex_label cleanly
    parts = raw.split(None, 1)
    proposal_id  = parts[0].strip() if parts else ''
    vortex_label = parts[1].strip() if len(parts) > 1 else ''
    if not proposal_id:
        return False, 'Usage: SKILL alm_self_approve <proposal_id> [vortex_label]'

    data, err = _alm_api_post(
        f'/api/work-proposals/{proposal_id}/agent-advance',
        {'agent': agent, 'action': 'start', 'vortex_label': vortex_label},
    )
    if err:
        return False, f'agent-advance failed: {err}'

    try:
        from frontend.services import _safe_workflow_checkpoint
        _safe_workflow_checkpoint(
            label=f'{proposal_id}-start',
            agent=agent,
            description=f'Self-approve + start {proposal_id}'
        )
    except Exception:
        pass

    vchk = data.get('vortex_checkpoint', '')
    return True, (
        f'Proposal {proposal_id} is now IN PROGRESS.\n'
        f'Vortex checkpoint: {vchk or "created"}\n'
        'Proceed with SKILL fs_patch/fs_write changes. '
        'When done, run SKILL alm_complete to mark it done for Ghost review.'
    )


def _skill_alm_complete(args, agent, **_):
    """Mark own in_progress proposal as done — awaiting Ghost confirmation."""
    raw = (args or '').strip()
    parts = raw.split(None, 1)
    proposal_id = parts[0].strip() if parts else ''
    if not proposal_id:
        return False, 'Usage: SKILL alm_complete <proposal_id>'

    # Guard: require at least one file change (fs_patch or fs_write) since
    # alm_self_approve was called. Proposals created by _log_as_internal_proposal
    # have titles like '[fs_patch] ...' or '[fs_write] ...'.
    # Completing without file changes means the work was not actually done.
    try:
        from database import get_connection as _gc
        _conn = _gc()
        _prop = _conn.execute(
            'SELECT updated_at FROM work_proposals WHERE proposal_id = ?',
            [proposal_id]
        ).fetchone()
        if _prop:
            _since = _prop['updated_at']
            _n = _conn.execute(
                "SELECT COUNT(*) FROM work_proposals "
                "WHERE (title LIKE '[fs_patch]%' OR title LIKE '[fs_write]%' OR title LIKE '[fs_patch_lines]%') "
                "AND agent = ? AND created_at >= ?",
                [agent, _since]
            ).fetchone()[0]
            if _n == 0:
                _conn.close()
                return False, (
                    f'BLOCKED: No file changes detected for {proposal_id}. '
                    'You must make actual changes with SKILL fs_patch_lines, SKILL fs_patch, or SKILL fs_write '
                    'before calling alm_complete. '
                    'Use SKILL fs_readonly to read the current file state, apply your '
                    'changes, then call alm_complete again.'
                )
        _conn.close()
    except Exception:
        pass  # Do not block on guard failure — proceed to completion

    try:
        from core.time_machine import time_wizard
        time_wizard.create_workflow_checkpoint(
            label=f'{proposal_id}-complete',
            agent=agent,
            description=f'ALM complete: {proposal_id}'
        )
    except Exception:
        pass

    # Health check — run quick smoke test before marking done
    health_summary = ''
    try:
        import subprocess as _sp
        hc = _sp.run(
            ['python3', 'scripts/health_check.py'],
            capture_output=True, text=True, timeout=30,
            cwd='/home/seven/swarm',
        )
        hc_out = (hc.stdout + hc.stderr).strip()
        passed = hc.returncode == 0
        health_summary = f'\n\nHealth check: {"PASS" if passed else "FAIL"}\n{hc_out[-1200:]}'
        if not passed:
            # Append failures to proposal description
            try:
                from database import get_connection as _gc2
                _c3 = _gc2()
                _row = _c3.execute(
                    'SELECT description FROM work_proposals WHERE proposal_id=?',
                    [proposal_id]
                ).fetchone()
                if _row:
                    existing_desc = _row['description'] if isinstance(_row, dict) else _row[0]
                    _c3.execute(
                        'UPDATE work_proposals SET description=? WHERE proposal_id=?',
                        [(existing_desc or '') + health_summary, proposal_id]
                    )
                    _c3.commit()
                _c3.close()
            except Exception:
                pass
    except Exception as _hce:
        health_summary = f'\n\n[Health check skipped: {_hce}]'

    data, err = _alm_api_post(
        f'/api/work-proposals/{proposal_id}/agent-advance',
        {'agent': agent, 'action': 'complete'},
    )
    if err:
        return False, f'alm_complete failed: {err}'

    return True, (
        f'Proposal {proposal_id} marked DONE.\n'
        'Ghost will review and confirm close. Your work is complete.'
        + health_summary
    )


def _skill_alm_vortex(args, agent, **_):
    """Create a named Vortex checkpoint (time machine save point)."""
    label = (args or '').strip()
    if not label:
        return False, 'Usage: SKILL alm_vortex <label>'
    try:
        import sys
        sys.path.insert(0, '/home/seven/swarm')
        from core.time_machine import time_wizard
        result = time_wizard.create_workflow_checkpoint(label=label, agent=agent,
                                                         description=f'Agent checkpoint: {label}')
        return True, f'Vortex checkpoint created: {label} (result={result})'
    except Exception as e:
        return False, f'alm_vortex error: {e}'


def _skill_fs_verify(args, agent, **_):
    """Syntax-check a Python or JavaScript file. Returns OK or the exact error."""
    import subprocess as _sp
    rel = (args or '').strip().split()[0] if args else ''
    if not rel:
        return False, 'Usage: SKILL fs_verify <path>'
    target = _fs_safe_path(rel)
    if not target:
        return False, f'Path not allowed or outside workspace: {rel}'
    if not target.exists():
        return False, f'File not found: {rel}'
    suffix = target.suffix.lower()
    if suffix == '.py':
        try:
            import ast
            with open(target, encoding='utf-8') as f:
                source = f.read()
            ast.parse(source)
            return True, f'OK — {rel} has no Python syntax errors.'
        except SyntaxError as e:
            return False, f'SyntaxError in {rel} at line {e.lineno}: {e.msg}\n  {e.text}'
        except IndentationError as e:
            return False, f'IndentationError in {rel} at line {e.lineno}: {e.msg}\n  {e.text}'
    elif suffix == '.js':
        try:
            result = _sp.run(
                ['node', '--check', str(target)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, f'OK — {rel} has no JavaScript syntax errors.'
            return False, f'Syntax error in {rel}:\n{(result.stderr or result.stdout)[:600]}'
        except FileNotFoundError:
            return False, 'node not found — cannot check JS syntax. Verify the patch manually.'
        except Exception as e:
            return False, f'JS check failed: {e}'
    else:
        return False, f'No syntax checker for {suffix} files (supported: .py, .js)'


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


_FS_PATCH_LINENO_RE = re.compile(r'^[ ]{0,4}\d{1,5}  ')


def _strip_fs_readonly_line_numbers(text):
    """Strip line-number prefixes produced by 'SKILL fs_readonly lines'.

    fs_readonly lines formats output as '{lineno:5d}  {content}'.
    Agents sometimes copy that output directly into <<<OLD>>>/<<<<NEW>>> blocks.
    Strip the prefix only when ALL non-empty lines match the pattern so we
    don't corrupt content that legitimately starts with a number.
    """
    lines = text.split('\n')
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return text
    if all(_FS_PATCH_LINENO_RE.match(l) for l in non_empty):
        return '\n'.join(_FS_PATCH_LINENO_RE.sub('', l) for l in lines)
    return text


def _skill_fs_patch(args, agent, **_):
    """Replace first occurrence of an exact string in a file."""
    raw = (args or '').strip()
    if not raw or '<<<NEW>>>' not in raw:
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
        # Strip line-number prefixes if agent copied fs_readonly lines output verbatim
        old_text = _strip_fs_readonly_line_numbers(old_text)
        new_text = _strip_fs_readonly_line_numbers(new_text)
        effective_new = new_text
        if old_text.endswith('\n') and not new_text.endswith('\n'):
            effective_new = new_text + '\n'
        if old_text not in original:
            return False, f'Old text not found in {rel}. No changes made.'
        patched = original.replace(old_text, effective_new, 1)
        target.write_text(patched, encoding='utf-8')
        return True, f'Patched {rel}: replaced {len(old_text)} chars with {len(effective_new)} chars'
    except Exception as e:
        return False, f'fs_patch failed: {e}'


def _skill_fs_patch_lines(args, agent, **_):
    """Replace a line range in a file by line numbers.

    More reliable than fs_patch because it never needs exact content matching.
    Workflow: read a section with fs_readonly lines to get line numbers, then
    call fs_patch_lines with those same line numbers and the replacement content.

    Usage:
        SKILL fs_patch_lines <path> <start_line> <end_line>
        <<<NEW>>>
        replacement content here
    """
    raw = (args or '').strip()
    # Split on <<<NEW>>> (case-insensitive)
    split = re.split(r'<<<NEW>>>', raw, maxsplit=1, flags=re.IGNORECASE)
    if len(split) != 2:
        return False, (
            'Usage: SKILL fs_patch_lines <path> <start_line> <end_line>\n'
            '<<<NEW>>>\nreplacement content'
        )
    head, new_text = split
    parts = head.strip().split()
    if len(parts) < 3:
        return False, 'Expected: SKILL fs_patch_lines <path> <start_line> <end_line>'
    rel = parts[0]
    try:
        start = int(parts[1])
        end = int(parts[2])
    except ValueError:
        return False, f'start_line and end_line must be integers, got: {parts[1]!r} {parts[2]!r}'
    if start < 1 or end < start:
        return False, f'Invalid range: start={start} end={end} (must be start >= 1 and end >= start)'

    target = _fs_safe_path(rel)
    if not target:
        return False, f'Path outside swarm root or invalid: {rel}'
    if not target.exists() or not target.is_file():
        return False, f'File not found: {rel}'
    try:
        original = target.read_text(encoding='utf-8', errors='replace')
        file_lines = original.splitlines(keepends=True)
        total = len(file_lines)
        if start > total:
            return False, f'start_line {start} beyond end of file ({total} lines)'
        end = min(end, total)

        # Strip line-number prefixes if agent copied fs_readonly lines output into <<<NEW>>>
        new_text = _strip_fs_readonly_line_numbers(new_text)

        # Strip the leading newline that follows <<<NEW>>> on the same or next line
        new_text = new_text.lstrip('\n')

        # Ensure replacement ends with newline (preserves file structure)
        if new_text and not new_text.endswith('\n'):
            new_text += '\n'

        before = ''.join(file_lines[:start - 1])
        after  = ''.join(file_lines[end:])
        patched = before + new_text + after

        target.write_text(patched, encoding='utf-8')
        old_count = end - start + 1
        new_count = len(new_text.splitlines())
        return True, (
            f'Patched {rel}: replaced lines {start}–{end} '
            f'({old_count} lines → {new_count} lines)'
        )
    except Exception as e:
        return False, f'fs_patch_lines failed: {e}'


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


def _skill_system_index(args, agent, **_):
    """Generate or search the system index."""
    try:
        from scripts.generate_system_index import generate, OUT_PATH
        # Always regenerate first
        generate()
        query = (args or '').strip()
        if not query:
            return True, f'System index regenerated → {OUT_PATH}'
        # Search the index for matching lines
        with open(OUT_PATH, 'r') as f:
            all_lines = f.readlines()
        matches = [l.rstrip() for l in all_lines if query.lower() in l.lower()]
        if not matches:
            return True, f'System index regenerated. No matches for {query!r}.'
        return True, f'Matches for {query!r} ({len(matches)}):\n' + '\n'.join(matches[:40])
    except Exception as e:
        return False, f'system_index error: {e}'


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
    'alm_self_approve':    _skill_alm_self_approve,
    'alm_complete':        _skill_alm_complete,
    'alm_vortex':          _skill_alm_vortex,
    'fs_readonly':         _skill_fs_readonly,
    'fs_write':            _skill_fs_write,
    'fs_patch':            _skill_fs_patch,
    'fs_patch_lines':      _skill_fs_patch_lines,
    'fs_verify':           _skill_fs_verify,
    'knowledge_search': _skill_knowledge_search,
    'ui_css_edit_checklist': _skill_ui_css_edit_checklist,
    'system_index':    _skill_system_index,
}


# ── Central dispatch ──────────────────────────────────────────────────────────

def call(skill_name, args='', agent='ghost', source_conv_id=None):
    """
    Invoke a skill by name. Returns (success: bool, output: str).

    skill_name     — one of REGISTRY keys
    args           — remaining arguments string
    agent          — calling agent name (for logging)
    source_conv_id — originating chat conversation id (forwarded to proposal skills)
    """
    skill_name = skill_name.strip().lower()

    if skill_name not in _HANDLERS:
        known = ', '.join(sorted(_HANDLERS.keys()))
        return False, f'Unknown skill: {skill_name!r}. Known skills: {known}'

    logger.info(f'[Skills] {agent} → {skill_name}({args[:80]})')

    try:
        success, output = _HANDLERS[skill_name](args=args, agent=agent, source_conv_id=source_conv_id)
    except Exception as e:
        success = False
        output = f'Skill {skill_name} raised an error: {e}'
        logger.error(f'[Skills] {skill_name} error: {e}')

    _log(skill_name, agent, args, output, success)

    if success and skill_name in _PROPOSAL_SKILLS:
        # Tracer: capture git diff for file-changing skills
        diff = ''
        _PATCH_SKILLS = {'fs_patch', 'fs_patch_lines', 'fs_write', 'file_write'}
        if skill_name in _PATCH_SKILLS:
            rel = _extract_changed_path(skill_name, args)
            if rel:
                diff = _capture_file_diff(rel)
                if diff:
                    # Also attach diff to the agent's active in_progress proposal
                    _attach_diff_to_active_proposal(agent, rel, diff)
        _log_as_internal_proposal(skill_name, agent, args, output, diff=diff)

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
