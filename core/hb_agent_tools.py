"""Guarded execution additions for the assigned APEX task, not a host shell."""
import json
import re
from contextlib import closing

READ_TOOLS = {'local_job_status','gemini_status','task_context', 'task_memory', 'task_evidence','reference_lookup','studio_evidence_get','studio_resume'}
ACCEPT_TOOLS = {'studio_accept','task_plan','runtime_reload','clip_doer','studio_log_change'}
WRITE_TOOLS = {'gemini_reload','local_review','archive_acquire','studio_note', 'studio_status', 'studio_task','task_plan', 'run_tests', 'reference_import', 'git_clear_stale_lock'}
WRITE_TOOLS = WRITE_TOOLS | {'does_rename', 'layout', 'change_set', 'studio_proposal', 'hb_tasks', 'request_access', 'gpu_profile', 'hb_restart', 'hb_service', 'hb_media_download', 'hb_custom_tool'}     # owner 13 Nov: the DOES rename tool (core/hb_rename.py)


def public_error(value):
    text = str(value)[:1000]
    text = re.sub(r'(?i)(?:hbp_|AIza|sk-)[A-Za-z0-9_-]{12,}', '[redacted]', text)
    text = re.sub(r'(?i)(authorization|api[_ -]?key|password|cookie|bearer|secret|token)\s*[:=]\s*[^\s,;}]+', r'\1=[redacted]', text)
    return text


# Practice 162 (owner 18 Nov 2026, question suite): answers opened with "Correcting my previous answer:" or "You're right, I left one out" -
# the model replying to HB's own checks as if JD had spoken. That opening is dropped; the rest of the answer stays.
_CHECK_REPLY = re.compile(r"^\s*(?:you(?:'re| are) right[^.\n]*|correcting my (?:previous|earlier|last) answer|(?:i )?(?:apologi[sz]e|sorry)[^.\n]*|"
                          r"(?:here is|here's) (?:the|my) (?:corrected|revised|updated) answer)[.:!]?\s*", re.I)


def drop_check_reply(answer):
    text = str(answer or '')
    out = _CHECK_REPLY.sub('', text, count=1)
    return out if out.strip() else text


def ground_answer(answer,receipts):
    for receipt in reversed(receipts):
        if receipt.get('tool')!='archive_acquire' or receipt.get('status')!='succeeded':continue
        try:result=json.loads(receipt.get('output','{}'))
        except (ValueError,TypeError):continue
        state=result.get('status');job=result.get('job_id')
        if job and state in {'queued','running','paused','failed'}:
            return 'HF job '+str(job)+' is '+state+': '+str(result.get('stage') or result.get('error') or 'waiting for the worker')+'. Download/index completion is not yet verified; HB will return its result.'
    for receipt in reversed(receipts):
        if receipt.get('tool')!='ask_instructor' or receipt.get('status')!='succeeded':continue
        try:result=json.loads(receipt.get('output','{}'))
        except (ValueError,TypeError):continue
        if result.get('status') in {'waiting','not_queued','local_review_queued'} and re.search(r'(?i)queue|permission|authoriz',answer):
            if result['status'] in {'not_queued','local_review_queued'}:return result['notice']
            return ('The previous request '+str(result['request_ids'][0])+' remains '+str(result.get('recorded_state','waiting'))+
                    ': '+str(result.get('recorded_stage','provider unavailable'))+'. No new online request was queued. '+result['notice'])
    answer = drop_check_reply(answer)   # Practice 162
    try:   # Practice 137 (owner 17 Nov 2026): references point to the KC copy used and its online origin
        from core.hb_note_links import link_notes, sources_footer
        return link_notes(answer) + sources_footer(receipts)
    except Exception:
        return answer


def ui_discover(tool, args):
    """Return a read‑only description of the UI controls for the current agent.

    The function inspects the desktop header template (frontend/templates/terminal_base.html)
    and extracts the controls that belong to the #home-controls div.  It returns a list
    of dictionaries, each containing:

    * ``id`` – the element id
    * ``label`` – the visible text or aria‑label
    * ``source`` – a tuple ``(path, line)`` pointing to the template line where the
      element is defined

    The function is intentionally read‑only; it does not modify any state and is
    safe to call from unauthenticated contexts.  It raises ``ValueError`` if the
    required template cannot be found or parsed.
    """
    from pathlib import Path
    template_path = Path('frontend/templates/terminal_base.html')
    if not template_path.is_file():
        raise ValueError('UI template not found')
    lines = template_path.read_text().splitlines()
    controls = []
    start = None
    end = None
    for i, line in enumerate(lines, 1):
        if '<div id="home-controls"' in line:
            start = i
        if start and '</div>' in line:
            end = i
            break
    if not start or not end:
        raise ValueError('home-controls div not found')
    for i in range(start, end + 1):
        line = lines[i - 1]
        m = re.search(r'id="([^"]+)"\s+[^>]*>([^<]+)</', line)
        if m:
            controls.append({
                'id': m.group(1),
                'label': m.group(2).strip(),
                'source': ('frontend/templates/terminal_base.html', i)
            })
    return controls

# Existing dispatcher

def _ui_discover_helper():
    """Placeholder for future UI discovery logic.
    This helper is kept read‑only and is intended to be expanded by the
    real ui_discover implementation.  It does not modify state.
    """
    return []


def gpu_profile_tool(args, run=None):
    """Practice 271 (JD 22 Nov 01:0x: "let HB and apex do it on our behalf"): list / status / apply NAME / reset JD's approved GPU
    profiles via the root helper JD installed (/usr/local/sbin/hb-gpu-profile, one sudo rule). Numbers live in JD's root-owned
    /etc/hb/gpu-profiles.json - APEX picks a profile, he never sets clocks or voltages. Every apply/reset is posted in main chat."""
    import subprocess
    action = str(args.get('action') or 'status').lower()
    if set(args) - {'action', 'profile'} or action not in ('list', 'status', 'apply', 'reset'):
        raise ValueError('gpu_profile takes action list, status, apply (with profile) or reset')
    cmd = ['sudo', '-n', '/usr/local/sbin/hb-gpu-profile', action]
    if action == 'apply':
        name = str(args.get('profile') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name):
            raise ValueError('apply needs the name of one of JD\'s approved profiles - call gpu_profile list first')
        cmd.append(name)
    out = (run or subprocess.run)(cmd, capture_output=True, text=True, timeout=180)
    text = (out.stdout or '').strip() or (out.stderr or '').strip()
    if 'a password is required' in text or 'no tty present' in text:
        raise PermissionError('hb-gpu-profile is not installed for HB yet: JD runs sudo sh runtime/claude_helpers/gpu/install-gpu-profile.sh once')
    try:
        result = json.loads(text.splitlines()[-1])
    except (ValueError, IndexError):
        result = {'ok': False, 'error': text[:400]}
    if action in ('apply', 'reset'):
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn, conn:
            line = (f"🖥 GPU {action}{' ' + cmd[-1] if action == 'apply' else ''}: " +
                    ('done' if result.get('ok') else 'NOT applied') +
                    (f" - peak {result.get('peak_temps_c')}" if result.get('peak_temps_c') else '') +
                    (' - automatically reverted (too hot)' if result.get('reverted') else '') +
                    (f" - refused: {'; '.join(result.get('refused', []))}" if result.get('refused') else ''))
            conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'hummingbird','user',?,'response',0)", (line,))
    return result


def hb_tasks_tool(args):
    """Practice 252: APEX runs his own task list. list | continue | pause | cancel (a reason of 8+ characters is required and recorded).
    JD's own steps (owner jd) and HB's record rows are JD's - APEX can list them but not change them."""
    from utils.db._connection import get_connection
    from core import hb_commands
    if set(args) - {'action', 'task_id', 'reason'}:
        raise ValueError('hb_tasks takes action (list, continue, pause or cancel), task_id and reason')
    action = str(args.get('action') or 'list').strip().lower()
    tid = str(args.get('task_id') or '').strip().upper()
    with closing(get_connection()) as conn:
        if action == 'list':
            from core import hb_tasks
            from core.hb_owner_intent import is_chat_task
            tasks = []
            for item in hb_commands._open_tasks(conn, 2845):
                task = hb_tasks.get(conn, item['task_id'])
                if is_chat_task(task) or str(item.get('title') or '').strip().casefold() == 'chat with jd':
                    continue
                item = dict(item)
                step_id = (task or {}).get('step_id')
                owner_row = conn.execute('SELECT owner FROM project_steps WHERE step_id=?', (step_id,)).fetchone() if step_id else None
                item['owner'] = str(owner_row[0] or 'unassigned') if owner_row else 'unassigned'
                tasks.append(item)
            eligible = [t for t in tasks if t['owner'].lower() in ('apex', 'unassigned')
                        and t['mode'] != 'off' and t['state'] not in ('paused', 'needs_review')
                        and t['status'] not in ('held', 'needs_review')]
            other = [t for t in tasks if t not in eligible]
            def lines(items):
                return '\n'.join(f"- {t['task_id']} [{t['state']}, Continue {t['mode']}, {t['status']}, owner {t['owner']}] {t['title'][:90]}" for t in items)
            listing = ('Eligible APEX work:\n' + lines(eligible)) if eligible else 'No eligible APEX work is currently available.'
            if other:
                listing += '\nOther tasks (held, awaiting review, or assigned elsewhere; not eligible for automatic selection):\n' + lines(other)
            return {'tasks': listing, 'notice': 'Choose only eligible work. Report actual holds or ownership when none is eligible. Listing alone does not start work.'}
        if action not in ('continue', 'pause', 'cancel'):
            raise ValueError('action must be list, continue, pause or cancel')
        if not re.fullmatch(r'T-[0-9A-F]{12}', tid):
            raise ValueError('task_id must be a real HB task id like T-0123456789AB - call hb_tasks with action list first')
        owner = conn.execute("SELECT COALESCE(s.owner,''), t.step_id, t.objective FROM hb_tasks t LEFT JOIN project_steps s ON s.step_id=t.step_id WHERE t.task_id=?",
                             (tid,)).fetchone()
        if owner is None:
            raise ValueError(f'No task {tid} - call hb_tasks with action list for the real ids')
        from core.hb_owner_intent import is_chat_task
        if action == 'continue' and is_chat_task({'step_id': owner[1], 'objective': owner[2]}):
            raise ValueError('That ID is not an actionable work task. Select an eligible ID from the latest work list; respect held tasks and owner review.')
        if owner[0] in ('jd', 'hummingbird'):
            raise PermissionError(f'{tid} is JD\'s own step; APEX does not change it')
        if action == 'cancel':
            reason = str(args.get('reason') or '').strip()
            if len(reason) < 8:
                raise ValueError('cancel needs a reason of at least 8 characters (why this task is not real work or is a duplicate)')
            out = hb_commands.cancel_task(conn, tid, 'APEX: ' + reason[:300])
        else:
            out = hb_commands.handle(conn, 2845, f'/{action} {tid}', 'APEX')
        conn.commit()
        return {'result': out}


_HB_RESTART_COOLDOWN_S = 90
_LAST_HB_RESTART_AT = 0.0

HB_SERVICES = {
    'swarm-terminal': 'swarm-terminal.service',
    'swarm-terminal.service': 'swarm-terminal.service',
    'hb': 'swarm-terminal.service',
    'terminal': 'swarm-terminal.service',
    'ui': 'swarm-terminal.service',
    'swarm-fridays': 'swarm-fridays.service',
    'swarm-fridays.service': 'swarm-fridays.service',
    'fridays': 'swarm-fridays.service',
    'swarm-discord': 'swarm-discord.service',
    'swarm-discord.service': 'swarm-discord.service',
    'discord': 'swarm-discord.service',
    'swarm-housekeeping': 'swarm-housekeeping.service',
    'swarm-housekeeping.service': 'swarm-housekeeping.service',
    'housekeeping': 'swarm-housekeeping.service',
    'ollama': 'ollama.service',
    'ollama.service': 'ollama.service',
    'swarm-terminal-dev': 'swarm-terminal-dev.service',
    'swarm-terminal-dev.service': 'swarm-terminal-dev.service',
    'dev': 'swarm-terminal-dev.service',
    'swarm-terminal-uat': 'swarm-terminal-uat.service',
    'swarm-terminal-uat.service': 'swarm-terminal-uat.service',
    'uat': 'swarm-terminal-uat.service',
}
HB_SERVICE_UNITS = (
    'swarm-terminal.service',
    'swarm-fridays.service',
    'swarm-discord.service',
    'swarm-housekeeping.service',
    'ollama.service',
    'swarm-terminal-dev.service',
    'swarm-terminal-uat.service',
)


def _restart_already_pending():
    import time
    from pathlib import Path
    if time.monotonic() - _LAST_HB_RESTART_AT < _HB_RESTART_COOLDOWN_S:
        return True
    try:
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmd = (entry / 'cmdline').read_bytes().decode(errors='ignore')
                if 'scripts/hb_restart.py' in cmd:
                    return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def hb_restart_tool(args, run=None, *, check_pending=True):
    """Queue an announced HB restart (scripts/hb_restart.py) via systemd-run --user.

    Waits for the current APEX turn lock before restarting swarm-terminal.service so APEX
    finishes and saves its reply cleanly instead of killing itself mid-turn. Deduplicates
    repeated calls within the cooldown window or while a restart script is already waiting.
    """
    global _LAST_HB_RESTART_AT
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path
    if set(args) - {'scope', 'reason'}:
        raise ValueError('hb_restart takes optional scope (ui or all) and reason')
    scope = str(args.get('scope') or 'ui').strip().lower()
    if scope not in ('ui', 'all'):
        raise ValueError('hb_restart scope must be ui or all')
    reason = str(args.get('reason') or 'Restart requested via APEX').strip()[:300]
    if run is None and check_pending and _restart_already_pending():
        return {
            'ok': True,
            'status': 'already_queued',
            'deduplicated': True,
            'scope': scope,
            'reason': reason,
            'notice': 'HB restart is already queued and waiting for this turn to end. Stop calling hb_restart and report to JD now.',
        }
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'hb_restart.py'
    cmd = ['systemd-run', '--user', '--collect', '--quiet', sys.executable, str(script), scope, reason]
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
    env = {
        **os.environ,
        'XDG_RUNTIME_DIR': runtime_dir,
        'DBUS_SESSION_BUS_ADDRESS': os.environ.get('DBUS_SESSION_BUS_ADDRESS') or f'unix:path={runtime_dir}/bus',
    }
    out = (run or subprocess.run)(cmd, env=env, capture_output=True, text=True, timeout=15)
    if getattr(out, 'returncode', 0):
        err = (getattr(out, 'stderr', '') or getattr(out, 'stdout', '') or 'systemd-run failed').strip()[:300]
        raise RuntimeError(f'Could not queue HB restart: {err}')
    if run is None:
        _LAST_HB_RESTART_AT = time.monotonic()
    try:
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn, conn:
            conn.execute(
                "INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                "VALUES (2845,'hummingbird','user',?,'response',0)",
                (f"🔄 HB restart queued ({scope}): {reason}. Maintenance banner will appear once the current turn finishes.",),
            )
    except Exception:
        pass
    return {
        'ok': True,
        'status': 'queued',
        'scope': scope,
        'reason': reason,
        'notice': 'HB restart is queued via systemd-run --user and will run as soon as this turn finishes. Do not call hb_restart again; report to JD now.',
    }


def hb_service_tool(args, run=None):
    """Manage all HB systemd services (status/list/start/stop/restart) without shell or file deletion."""
    import subprocess
    if set(args) - {'action', 'service', 'reason'}:
        raise ValueError('hb_service takes action (list, status, start, stop, restart), optional service and reason')
    action = str(args.get('action') or 'list').strip().lower()
    if action not in ('list', 'status', 'start', 'stop', 'restart'):
        raise ValueError('hb_service action must be list, status, start, stop or restart')
    runner = run or subprocess.run
    if action == 'list':
        states = {}
        for unit in HB_SERVICE_UNITS:
            out = runner(['systemctl', 'is-active', unit], capture_output=True, text=True, timeout=10)
            states[unit] = (getattr(out, 'stdout', '') or getattr(out, 'stderr', '') or 'unknown').strip()
        return {'ok': True, 'services': states}
    raw_service = str(args.get('service') or '').strip().lower()
    unit = HB_SERVICES.get(raw_service)
    if not unit:
        raise ValueError('Unknown HB service. Allowed: ' + ', '.join(HB_SERVICE_UNITS))
    if action == 'status':
        out = runner(['systemctl', 'show', '-p', 'ActiveState,SubState,MainPID,ActiveEnterTimestamp', unit],
                     capture_output=True, text=True, timeout=10)
        info = {}
        for line in (getattr(out, 'stdout', '') or '').splitlines():
            if '=' in line:
                k, _, v = line.partition('=')
                info[k] = v
        return {'ok': True, 'service': unit, 'status': info}
    reason = str(args.get('reason') or f'APEX hb_service {action} {unit}').strip()[:240]
    if unit == 'swarm-terminal.service' and action == 'restart':
        return hb_restart_tool({'scope': 'ui', 'reason': reason}, run=run)
    out = runner(['sudo', '-n', '/usr/bin/systemctl', action, unit], capture_output=True, text=True, timeout=30)
    if getattr(out, 'returncode', 0):
        err = (getattr(out, 'stderr', '') or getattr(out, 'stdout', '') or 'systemctl failed').strip()[:300]
        raise RuntimeError(f'hb_service {action} {unit} failed: {err}')
    try:
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn, conn:
            conn.execute(
                "INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                "VALUES (2845,'hummingbird','user',?,'response',0)",
                (f"⚙️ HB service {action}: {unit} ({reason})",),
            )
    except Exception:
        pass
    return {'ok': True, 'service': unit, 'action': action, 'reason': reason}


def hb_media_download_tool(args, run=None):
    """Download a public video or audio clip (e.g. YouTube episode) into Media Center downloads via yt-dlp."""
    import hashlib
    import shutil
    import subprocess
    from pathlib import Path
    if set(args) - {'query', 'format'} or not str(args.get('query') or '').strip():
        raise ValueError('hb_media_download requires query (URL or search phrase) and optional format (video or audio)')
    raw = str(args['query']).strip()[:200]
    fmt = str(args.get('format') or 'video').strip().lower()
    if fmt not in ('video', 'audio'):
        raise ValueError('hb_media_download format must be video or audio')
    if any(ch in raw for ch in ('\n', '\r', '\0')):
        raise ValueError('Invalid characters in media query')
    ytdlp = shutil.which('yt-dlp') or '/usr/bin/yt-dlp'
    if run is None and not Path(ytdlp).is_file():
        raise RuntimeError('yt-dlp is not installed on this host')
    dest = Path(__file__).resolve().parents[1] / 'artifacts' / 'media_center' / 'downloads'
    dest.mkdir(parents=True, exist_ok=True)
    target = raw if raw.startswith(('https://', 'http://')) else f'ytsearch1:{raw}'
    cmd = [ytdlp, '--no-playlist', '--restrict-filenames', '--print', 'after_move:filepath',
           '-o', str(dest / '%(title).80s-[%(id)s].%(ext)s')]
    if fmt == 'audio':
        cmd += ['-x', '--audio-format', 'mp3']
    else:
        cmd += ['-f', 'bv*[height<=1080]+ba/b[height<=1080]/best', '--merge-output-format', 'mp4']
    cmd.append(target)
    out = (run or subprocess.run)(cmd, capture_output=True, text=True, timeout=180)
    if getattr(out, 'returncode', 0):
        err = (getattr(out, 'stderr', '') or getattr(out, 'stdout', '') or 'yt-dlp failed').strip()[:300]
        raise RuntimeError(f'Media download failed: {err}')
    lines = [ln.strip() for ln in (getattr(out, 'stdout', '') or '').splitlines() if ln.strip()]
    saved = lines[-1] if lines else str(dest)
    try:
        from core.apex_knowledge import mirror_to_kc
        digest = hashlib.sha256(f'{fmt}:{raw.lower()}'.encode()).hexdigest()[:16]
        mirror_to_kc(
            f'Media download ({fmt}): {Path(saved).name[:160]}',
            f'Query: {raw}\nFormat: {fmt}\nSaved to: {saved}',
            source_ref=f'media-download://{digest}',
            source_type='media',
            domain_tags='media,download,youtube,executive-assistant',
            subcategory='media',
            added_by='apex',
        )
    except Exception:
        pass
    try:
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn, conn:
            conn.execute(
                "INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                "VALUES (2845,'hummingbird','user',?,'response',0)",
                (f"🎬 Media downloaded ({fmt}): {Path(saved).name} → {saved}",),
            )
    except Exception:
        pass
    return {'ok': True, 'format': fmt, 'query': raw, 'saved_path': saved, 'filename': Path(saved).name}


def hb_custom_tool_handler(args):
    """List or invoke approved drop-in APEX plugins in core/hb_custom_tools/."""
    from core import hb_custom_tools
    if set(args) - {'action', 'name', 'payload'}:
        raise ValueError('hb_custom_tool takes action (list or run), and for run: name and optional payload JSON string')
    action = str(args.get('action') or 'list').strip().lower()
    if action == 'list':
        tools = hb_custom_tools.list_tools()
        return {'ok': True, 'tools': tools,
                'notice': 'To create a new tool you need, submit a studio_proposal adding core/hb_custom_tools/custom_<name>.py + tests/test_custom_<name>.py for JD to approve.'}
    if action != 'run':
        raise ValueError('hb_custom_tool action must be list or run')
    name = str(args.get('name') or '').strip()
    raw_payload = args.get('payload')
    if isinstance(raw_payload, str) and raw_payload.strip():
        parsed = json.loads(raw_payload)
    elif isinstance(raw_payload, dict):
        parsed = raw_payload
    else:
        parsed = {}
    return hb_custom_tools.invoke(name, parsed)


def studio_evidence_get_tool(args):
    """Read bounded Studio evidence or fall back to task_evidence when a task event ID is passed."""
    from core import agent_identity, hb_tasks
    from core.apex_evidence import read_evidence
    if set(args) != {'evidence_id'}:
        raise ValueError('studio_evidence_get accepts only evidence_id')
    eid = args['evidence_id']
    if type(eid) is not int or eid <= 0:
        raise ValueError('evidence_id must be a positive integer')
    actor = agent_identity.CURRENT.get() or {}
    conv_id = actor.get('conversation_id') or 2845
    owner = actor.get('requested_by') or 'user'
    result = read_evidence(int(conv_id), str(owner), eid)
    if result.get('status') == 'not_found' and actor.get('peer_request_id'):
        try:
            task_ev = hb_tasks.call('task_evidence', {'evidence_id': eid})
            if task_ev:
                return {'status': 'found', 'source': 'hb_task_events', 'evidence_id': eid, **task_ev}
        except Exception:
            pass
    return result


def studio_resume_tool(args):
    """Read bounded Studio handoff context for the active conversation."""
    from core import agent_identity
    from core.apex_studio import read_handoff
    if set(args) - {'offset'}:
        raise ValueError('studio_resume accepts only optional offset')
    offset = args.get('offset', 0)
    if type(offset) is not int or offset < 0:
        raise ValueError('offset must be a nonnegative integer')
    actor = agent_identity.CURRENT.get() or {}
    conv_id = actor.get('conversation_id') or 2845
    owner = actor.get('requested_by') or 'user'
    try:
        return read_handoff(int(conv_id), str(owner), offset=offset, raw=False)
    except (ValueError, RuntimeError) as exc:
        return {'status': 'not_found', 'detail': str(exc)[:300],
                'notice': 'Use task_context to read the current task instructions and plan.'}


def clip_doer_tool(args, conn=None):
    """Instructor-only audited step reassignment via /api/agent/v1/tools (keeps /api/knowledge/* 403 intact)."""
    from core import agent_identity, hb_clipboard
    actor = agent_identity.CURRENT.get() or {}
    principal = actor.get('principal')
    if principal not in agent_identity.INSTRUCTORS:
        raise PermissionError('Step reassignment via clip_doer requires an authenticated instructor')
    if set(args) - {'step_id', 'doer', 'reason'} or not {'step_id', 'doer'} <= set(args):
        raise ValueError('clip_doer requires step_id, doer, and optional reason')
    step_id = str(args['step_id']).strip().upper()
    doer = str(args['doer']).strip().lower()
    reason = str(args.get('reason') or '').strip()[:240]
    if not re.fullmatch(r'S-[0-9A-F]{10}', step_id):
        raise ValueError('step_id must look like S- followed by 10 uppercase hex characters')
    if doer not in hb_clipboard.DOERS:
        raise ValueError('doer must be one of: ' + ', '.join(hb_clipboard.DOERS))
    label = f'{principal} via clip_doer' + (f' ({reason})' if reason else '')

    def _run(db):
        said = hb_clipboard.edit(db, ['doer', step_id, doer], label)
        if said.endswith('is not a Studio step.'):
            raise ValueError(said)
        cols = {r[1] for r in db.execute('PRAGMA table_info(project_steps)')}
        sel = [c for c in ('owner', 'owner_route') if c in cols]
        row = db.execute(f"SELECT {', '.join(sel)} FROM project_steps WHERE step_id=?", (step_id,)).fetchone() if sel else None
        meta = dict(zip(sel, row)) if row else {}
        return {'ok': True, 'step_id': step_id, 'doer': doer, 'actor': principal, 'result': said, **meta}

    if conn is not None:
        return _run(conn)
    from utils.db._connection import get_connection
    with closing(get_connection()) as db, db:
        return _run(db)


def studio_log_change_tool(args, conn=None):
    """Instructor-only audited Studio change/plan logger (blackboard + FILE LOG S-69FA40CEB7)."""
    import time
    from core import agent_identity
    from core.knowledge import projects
    actor = agent_identity.CURRENT.get() or {}
    principal = actor.get('principal')
    if principal not in agent_identity.INSTRUCTORS:
        raise PermissionError('Logging changes via studio_log_change requires an authenticated instructor')
    allowed_keys = {'project_id', 'kind', 'summary', 'files', 'receipts', 'how', 'file_log_step_id'}
    if set(args) - allowed_keys or not str(args.get('summary') or '').strip():
        raise ValueError('studio_log_change requires summary and optional project_id, kind, files, receipts, how, file_log_step_id')
    project_id = str(args.get('project_id') or 'P-2AB8250A87').strip()
    kind = str(args.get('kind') or 'handoff').strip().lower()
    if kind not in projects.BLACKBOARD_KINDS:
        raise ValueError(f'kind must be one of {projects.BLACKBOARD_KINDS}')
    summary = str(args['summary']).strip()[:2000]
    files = [str(f).strip()[:200] for f in (args.get('files') or []) if str(f).strip()][:30]
    receipts = [str(r).strip()[:300] for r in (args.get('receipts') or []) if str(r).strip()][:20]
    how = str(args.get('how') or '').strip()[:1000]
    file_log_step = str(args.get('file_log_step_id') or 'S-69FA40CEB7').strip().upper()

    parts = [summary]
    if how:
        parts.append('How: ' + how)
    if files:
        parts.append('Files: ' + ', '.join(files))
    if receipts:
        parts.append('Receipts: ' + '; '.join(receipts))
    body = '\n'.join(parts)[:4000]
    note_id = projects.add_blackboard_note(project_id, body, author=principal, kind=kind)
    if not note_id:
        raise RuntimeError(f'Could not save Studio blackboard note for {project_id}')
    kc_id = None
    try:
        from core.apex_knowledge import mirror_to_kc
        kc_id = mirror_to_kc(
            f'Studio {kind} ({note_id}): {summary[:160]}',
            body,
            source_ref=f'studio://note/{note_id}',
            source_type='note',
            domain_tags=f'studio,{kind},{principal},{project_id}',
            subcategory=kind,
            added_by=principal,
        )
    except Exception:
        pass

    file_log_updated = False
    if files and re.fullmatch(r'S-[0-9A-F]{10}', file_log_step):
        stamp = time.strftime('%d %b %H:%M')
        line = f"\n- {stamp} {principal} ({note_id}): {summary[:220]} | Files: {', '.join(files)}" + (
            f" | Receipts: {'; '.join(receipts)[:260]}" if receipts else ''
        )
        def _append(db):
            row = db.execute('SELECT description FROM project_steps WHERE step_id=?', (file_log_step,)).fetchone()
            if not row:
                return False
            db.execute(
                "UPDATE project_steps SET description=COALESCE(description,'') || ?, updated_at=? WHERE step_id=?",
                (line, time.time(), file_log_step),
            )
            return True
        if conn is not None:
            file_log_updated = _append(conn)
        else:
            from utils.db._connection import get_connection
            with closing(get_connection()) as db, db:
                file_log_updated = _append(db)
    return {
        'ok': True,
        'project_id': project_id,
        'note_id': note_id,
        'kc_source_id': kc_id,
        'kind': kind,
        'actor': principal,
        'files': files,
        'receipts': receipts,
        'file_log_step_id': file_log_step if file_log_updated else None,
        'file_log_updated': file_log_updated,
    }


def call(tool, args):
    from core import agent_identity, hb_tasks
    actor = agent_identity.CURRENT.get() or {}
    if actor.get('principal') and ((tool == 'does_rename' and args.get('action') in {'move', 'remove_alias'}) or (tool == 'layout' and args.get('action') in {'move', 'undo'}) or tool == 'git_clear_stale_lock'):
        raise PermissionError('JD requires approval before agents delete or move live project files; this tool has no deletion approval flow yet')
    if tool=='studio_evidence_get':
        return studio_evidence_get_tool(args)
    if tool=='studio_resume':
        return studio_resume_tool(args)
    if tool=='clip_doer':
        return clip_doer_tool(args)
    if tool=='studio_log_change':
        return studio_log_change_tool(args)
    if tool=='hb_restart':
        return hb_restart_tool(args)
    if tool=='hb_service':
        return hb_service_tool(args)
    if tool=='hb_media_download':
        return hb_media_download_tool(args)
    if tool=='hb_custom_tool':
        return hb_custom_tool_handler(args)
    if tool=='gpu_profile':   # Practice 271
        return gpu_profile_tool(args)
    if tool=='request_access':   # Practice 270: APEX asks the owners for a tool on his task
        from utils.db._connection import get_connection
        actor=agent_identity.CURRENT.get() or {}
        with closing(get_connection()) as conn,conn:
            task=(hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else None)
            from core.hb_access import request as ask
            return ask(conn,'apex',args.get('tool'),task['task_id'] if task else None,args.get('why'))
    if tool=='hb_tasks':   # Practice 252
        return hb_tasks_tool(args)
    if tool in {'local_review','local_job_status','archive_acquire'}:
        from core.hb_local_jobs import call as local_call
        return local_call(tool,args)
    if tool=='gemini_reload':
        from core.hb_peer_control import gemini_reload
        return gemini_reload(args)
    if tool=='gemini_status':
        if args:raise ValueError('gemini_status takes no arguments')
        import config
        from core.peer_coordination import worker_alive
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn:
            rows=[dict(zip(('request_id','state','stage','delivered_at'),row)) for row in conn.execute('''SELECT p.id,w.state,w.stage,p.delivered_at FROM peer_messages p
                LEFT JOIN hb_peer_work w ON w.request_id=p.id WHERE p.recipient='gemini-advisor'
                AND p.body NOT LIKE '[TEAM COPY, observe:%' ORDER BY p.id DESC LIMIT 4''')]
            success=conn.execute("SELECT p.id,p.conversation_id,p.delivered_at FROM peer_messages p JOIN hb_peer_work w ON w.request_id=p.id WHERE p.recipient='gemini-advisor' AND w.state='completed' AND p.delivered_at IS NOT NULL ORDER BY p.id DESC LIMIT 1").fetchone()
        from scripts.hummingbird_gemini_peer import selected_provider_model
        return {'provider':'Google','model':selected_provider_model(config.GEMINI_AGENT_MODEL),'configured_model':config.GEMINI_AGENT_MODEL,'credential_configured':bool(config.GEMINI_API_KEY),
                'worker_running':worker_alive('gemini-advisor'),'recent_requests':rows,
                'last_verified_delivery':dict(zip(('request_id','conversation_id','delivered_at'),success)) if success else None,
                'notice':'Canonical recorded metadata only; no credential values and no new online call. A successful delivery does not guarantee future provider availability.'}
    if tool == 'reference_lookup':
        from core.hb_references import lookup
        if set(args)-{'query','allow_online'} or 'query' not in args:raise ValueError('reference_lookup requires query and optional allow_online')
        return lookup(**args)
    if tool == 'reference_import':
        from core.hb_references import ingest
        if set(args)!={'kind','repo','revision','path'}:raise ValueError('reference_import requires kind, repo, revision and path')
        return ingest(**args)
    if tool=='runtime_reload':
        if args:raise ValueError('runtime_reload takes no arguments; the accepted task fixes its scope')
        from core.hb_runtime_reload import request_reload
        return request_reload()
    if tool in {'task_context','task_memory','task_evidence','studio_note','studio_status','studio_task','task_plan','studio_accept'}:
        return hb_tasks.call(tool,args)
    actor=agent_identity.CURRENT.get()
    if tool=='studio_proposal':
        if not actor or not actor.get('principal') or not actor.get('credential_id'):
            raise PermissionError('Studio proposals require an authenticated agent')
        from utils.db._connection import get_connection
        from core.hb_proposals import create as propose
        with closing(get_connection()) as conn,conn:
            task=(hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else
                  hb_tasks.get(conn,actor['task_id']) if actor.get('task_id') else None)

    from core import agent_identity, hb_tasks
    if tool in {'local_review','local_job_status','archive_acquire'}:
        from core.hb_local_jobs import call as local_call
        return local_call(tool,args)
    if tool=='gemini_reload':
        from core.hb_peer_control import gemini_reload
        return gemini_reload(args)
    if tool=='gemini_status':
        if args:raise ValueError('gemini_status takes no arguments')
        import config
        from core.peer_coordination import worker_alive
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn:
            rows=[dict(zip(('request_id','state','stage','delivered_at'),row)) for row in conn.execute('''SELECT p.id,w.state,w.stage,p.delivered_at FROM peer_messages p
                LEFT JOIN hb_peer_work w ON w.request_id=p.id WHERE p.recipient='gemini-advisor'
                AND p.body NOT LIKE '[TEAM COPY, observe:%' ORDER BY p.id DESC LIMIT 4''')]
            success=conn.execute("SELECT p.id,p.conversation_id,p.delivered_at FROM peer_messages p JOIN hb_peer_work w ON w.request_id=p.id WHERE p.recipient='gemini-advisor' AND w.state='completed' AND p.delivered_at IS NOT NULL ORDER BY p.id DESC LIMIT 1").fetchone()
        from scripts.hummingbird_gemini_peer import selected_provider_model
        return {'provider':'Google','model':selected_provider_model(config.GEMINI_AGENT_MODEL),'configured_model':config.GEMINI_AGENT_MODEL,'credential_configured':bool(config.GEMINI_API_KEY),
                'worker_running':worker_alive('gemini-advisor'),'recent_requests':rows,
                'last_verified_delivery':dict(zip(('request_id','conversation_id','delivered_at'),success)) if success else None,
                'notice':'Canonical recorded metadata only; no credential values and no new online call. A successful delivery does not guarantee future provider availability.'}
    if tool == 'reference_lookup':
        from core.hb_references import lookup
        if set(args)-{'query','allow_online'} or 'query' not in args:raise ValueError('reference_lookup requires query and optional allow_online')
        return lookup(**args)
    if tool == 'reference_import':
        from core.hb_references import ingest
        if set(args)!={'kind','repo','revision','path'}:raise ValueError('reference_import requires kind, repo, revision and path')
        return ingest(**args)
    if tool=='runtime_reload':
        if args:raise ValueError('runtime_reload takes no arguments; the accepted task fixes its scope')
        from core.hb_runtime_reload import request_reload
        return request_reload()
    if tool in {'task_context','task_memory','task_evidence','studio_note','studio_status','studio_task','task_plan','studio_accept'}:
        return hb_tasks.call(tool,args)
    actor=agent_identity.CURRENT.get()
    if tool=='studio_proposal':
        if not actor or not actor.get('principal') or not actor.get('credential_id'):
            raise PermissionError('Studio proposals require an authenticated agent')
        from utils.db._connection import get_connection
        from core.hb_proposals import create as propose
        with closing(get_connection()) as conn,conn:
            task=(hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else
                  hb_tasks.get(conn,actor['task_id']) if actor.get('task_id') else None)
            return propose(conn,actor['principal'],args,task)
    if not actor or actor['principal']!='apex' or not (actor.get('peer_request_id') or actor.get('task_id')):
        raise PermissionError('Guarded tests require the assigned authenticated APEX turn')
    if tool=='layout':     # owner 13 Nov: system review and cleanup (core/hb_layout.py); moves are logged and undoable
        from utils.db._connection import get_connection
        from core.hb_layout import call as layout_call
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task:raise PermissionError('layout requires a linked Studio task')
        result=layout_call(args)
        if args.get('action') in ('move','undo'):
            with closing(get_connection()) as conn,conn:
                hb_tasks.event(conn,task,actor['principal'],'mutation',{'status':'succeeded','tool':'layout','output':'layout '+str(args.get('action'))+': '+json.dumps(result)[:400]},request_id=actor.get('peer_request_id'))
        return result
    if tool=='change_set':     # owner 14 Nov: Claude Code's prepared, tested change for this step (core/hb_change_sets.py)
        from utils.db._connection import get_connection
        from core.hb_change_sets import call as change_set_call
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task:raise PermissionError('change_set requires a linked Studio task')
        result=change_set_call(args,task.get('step_id'))
        if args.get('action')=='apply' and result.get('state')=='applied':
            with closing(get_connection()) as conn,conn:
                hb_tasks.event(conn,task,actor['principal'],'mutation',{'status':'succeeded','tool':'change_set',
                    'output':'change set applied: '+json.dumps(result)[:400]},request_id=actor.get('peer_request_id'))
        return result
    if tool=='does_rename':
        from utils.db._connection import get_connection
        from core.hb_rename import call as rename_call
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task:raise PermissionError('does_rename requires a linked Studio task')
        result=rename_call(args)
        if args.get('action')!='status' and 'note' not in result:
            with closing(get_connection()) as conn,conn:
                hb_tasks.event(conn,task,actor['principal'],'mutation',{'status':'succeeded','tool':'does_rename',
                    'output':'DOES rename '+str(args.get('action'))+': '+json.dumps(result)[:400]},request_id=actor.get('peer_request_id'))
        return result
    if tool=='git_clear_stale_lock':
        if args:raise ValueError('git_clear_stale_lock takes no arguments')
        from core.hb_git_maintenance import clear_stale_lock
        return clear_stale_lock()
    if tool=='run_tests':
        from utils.db._connection import get_connection
        from core.apex_test_runner import run_tests
        from core.apex_alm import run_recorded_tests
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task or not task.get('step_id'):
            # Practice 201: in main chat ("Chat with JD" has no Studio step) run_tests used to crash APEX's whole turn. It now runs the
            # tests and says plainly that the run is not recorded against a step.
            out=dict(run_tests(dict(args)))
            out['note']=((out.get('note')+' ') if out.get('note') else '')+'Not recorded against a Studio step (this task has none).'
            return out
        values=dict(args)
        if values.get('case_id') in (None,'',task['step_id']):   # APEX often passes its step id; the step's own case is meant
            values.pop('case_id',None)
        if 'case_id' not in values:
            from core.knowledge import projects
            cases=projects.list_test_cases(task['project_id'],step_id=task['step_id'])
            if not cases:
                # Practice 168: the auto case names the command it runs, so it is a runnable criterion
                title='Guarded task regression checks: python -m pytest '+' '.join(str(t) for t in (args.get('tests') or [])[:4])
                case=projects.add_test_case(task['project_id'],title.strip()[:200],step_id=task['step_id'],owner='apex')
                if not case:raise RuntimeError('Could not register the task test case')
            else:
                case=cases[0]['case_id']
            values['case_id']=case
        else:
            from core.knowledge import projects
            case=projects.get_test_case(values['case_id'])
            if not case or case.get('step_id')!=task['step_id']:
                raise PermissionError('Test case must belong to this assigned task step (leave case_id out to use the step\'s own case)')
        result=run_recorded_tests(values,run_tests)
        with closing(get_connection()) as conn,conn:
            hb_tasks.event(conn,task,actor['principal'],'test_result',result,request_id=actor.get('peer_request_id'))
        return result
    raise ValueError('Unknown guarded tool')
