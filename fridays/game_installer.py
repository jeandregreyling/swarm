"""
fridays/game_installer.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Windows game installs for Fridays agents, run through Bottles (Flatpak).

Workflow:
  Ghost's chat (preferred): Ghost types "install <file name>" to any writing
  agent. The skills loop matches Ghost's stored chat message (not model output)
  and starts setup. "setup finished" then registers the game in Bottles.

  Agent skills:
  1. SKILL game_installers                      — find the installer and bottle
  2. SKILL alm_create_proposal naming the exact installer file
  3. Ghost approves or starts that proposal (Duck or agent approvals are not accepted)
  4. SKILL game_install <proposal_id> <file in ~/Downloads> [bottle=<name>]
     → ISOs are unpacked to ~/Downloads/.fridays-staging, then setup opens on
       Ghost's desktop. Ghost clicks through the installer.
  5. SKILL game_register <proposal_id> <Program name> [exe=<name hint>]
     → finds the new game executable in the bottle and adds it to Bottles.

Safety rules:
  - Installers come only from ~/Downloads (no path or symlink escapes).
  - Only an existing bottle is used. Bottles' Flatpak sandbox gives Windows
    programs read-only Downloads access, not the rest of the home folder.
  - Each skill run needs a proposal owned by the calling agent, approved or
    started by Ghost in the governance log, whose title or description names
    the installer file.
═══════════════════════════════════════════════════════════════════════════════
"""

import hashlib
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

HOME = Path(os.environ.get('SWARM_GAME_HOME', str(Path.home())))
DOWNLOADS = Path(os.environ.get('SWARM_GAME_DOWNLOADS', str(HOME / 'Downloads')))
STAGING = DOWNLOADS / '.fridays-staging'
BOTTLES_ROOT = Path(os.environ.get(
    'SWARM_BOTTLES_ROOT',
    str(HOME / '.var/app/com.usebottles.bottles/data/bottles/bottles'),
))
DEFAULT_BOTTLE = os.environ.get('SWARM_GAME_BOTTLE', 'Fridays')
STATE_FILE = Path(__file__).resolve().parent.parent / 'runtime' / 'game_installs.json'
BOTTLES_CLI = ['flatpak', 'run', '--command=bottles-cli', 'com.usebottles.bottles']

INSTALLER_SUFFIXES = {'.iso', '.exe', '.msi'}
HUMAN_APPROVERS = {'ghost', 'user'}
_BOTTLE_NAME_RE = re.compile(r'^[\w][\w .-]{0,63}$')
_SETUP_NAMES = ('setup.exe', 'install.exe', 'installer.exe', 'autorun.exe')
_NOT_GAME_RE = re.compile(
    r'^(unins\d*|setup|install(er)?|vc_?redist|vcredist|dxsetup|dxwebsetup|directx|'
    r'dotnet|ndp|physx|oalinst|crash|bugreport|report|update|updater|launcherpatcher)',
    re.IGNORECASE,
)
_state_lock = threading.Lock()


# ── State ─────────────────────────────────────────────────────────────────────

def _load_jobs():
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def _save_job(job):
    with _state_lock:
        jobs = [j for j in _load_jobs() if j.get('job_id') != job['job_id']]
        jobs.append(job)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(jobs[-50:], indent=2), encoding='utf-8')
        tmp.replace(STATE_FILE)


def _latest_job(proposal_id):
    matches = [j for j in _load_jobs() if j.get('proposal_id') == proposal_id]
    return matches[-1] if matches else None


# ── Argument parsing ──────────────────────────────────────────────────────────

def _parse(args, keys):
    """Split '<proposal> <free text...> key=value' into (proposal, text, options)."""
    try:
        tokens = shlex.split(args or '')
    except ValueError as exc:
        raise ValueError(f'Could not parse arguments: {exc}') from exc
    options, rest = {}, []
    for token in tokens:
        key, sep, value = token.partition('=')
        if sep and key.lower() in keys:
            options[key.lower()] = value.strip()
        else:
            rest.append(token)
    if len(rest) < 2:
        raise ValueError('missing arguments')
    return rest[0].strip(), ' '.join(rest[1:]).strip(), options


# ── Validation ────────────────────────────────────────────────────────────────

def resolve_source(rel_path):
    """Return the real installer path, confined to the Downloads folder."""
    raw = (rel_path or '').strip()
    if not raw:
        raise ValueError('An installer file is required.')
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = DOWNLOADS / candidate
    real = candidate.resolve()
    root = DOWNLOADS.resolve()
    if real != root and root not in real.parents:
        raise ValueError(f'Installers must be inside {root}.')
    if STAGING.resolve() in real.parents:
        raise ValueError('Name the original download, not a staged copy.')
    if not real.is_file():
        raise ValueError(f'Installer not found: {real}')
    if real.suffix.lower() not in INSTALLER_SUFFIXES:
        raise ValueError('Only .iso, .exe and .msi installers are supported.')
    return real


def check_bottle(name):
    name = (name or DEFAULT_BOTTLE).strip()
    if not _BOTTLE_NAME_RE.match(name) or name in {'.', '..'}:
        raise ValueError(f'Invalid bottle name: {name!r}')
    path = BOTTLES_ROOT / name
    if not (path / 'bottle.yml').is_file():
        raise ValueError(f'Bottle {name!r} does not exist. Ask Ghost to create it in Bottles first.')
    return name, path


def require_ghost_approval(proposal_id, agent, source_name, conn=None):
    """Return an error string, or '' when Ghost approved this agent's proposal for this file."""
    from database import get_connection

    own = conn is None
    conn = conn or get_connection()
    try:
        return _approval_error(conn, proposal_id, agent, source_name)
    except sqlite3.Error as exc:
        return f'Approval could not be verified: {exc}'
    finally:
        if own:
            conn.close()


def _approval_error(conn, proposal_id, agent, source_name):
    proposal = conn.execute(
        'SELECT proposal_id, agent, status, title, description FROM work_proposals WHERE proposal_id=?',
        (proposal_id,),
    ).fetchone()
    if not proposal:
        return f'Proposal {proposal_id} was not found.'
    caller = (agent or '').strip().lower()
    owner = (proposal['agent'] or '').strip().lower()
    if owner != caller:
        return f'Proposal {proposal_id} belongs to {owner or "nobody"}, not {caller}.'
    if proposal['status'] not in {'approved', 'in_progress'}:
        return f'Proposal {proposal_id} is {proposal["status"]}; Ghost must approve it first.'
    approval = conn.execute(
        "SELECT actor FROM governance_log WHERE proposal_id=? "
        "AND new_status IN ('approved', 'in_progress') AND lower(actor) IN ('ghost', 'user') "
        'ORDER BY id DESC LIMIT 1',
        (proposal_id,),
    ).fetchone()
    if not approval:
        return f'Proposal {proposal_id} has no Ghost approval in the governance log.'
    text = f"{proposal['title'] or ''}\n{proposal['description'] or ''}".lower()
    if source_name.lower() not in text:
        return f'Proposal {proposal_id} must name the installer file "{source_name}".'
    return ''


# ── ISO staging and setup discovery ───────────────────────────────────────────

def _stage_dir(source):
    stem = re.sub(r'[^\w.-]+', '_', source.stem).strip('._') or 'installer'
    digest = hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:10]
    return STAGING / f'{stem}-{digest}'


def stage_iso(source, runner=subprocess.run):
    """Unpack an ISO beside Downloads so Bottles can read it. Reuses a complete copy."""
    target = _stage_dir(source)
    stat = source.stat()
    marker = target / '.fridays-complete'
    fingerprint = f'{source}:{stat.st_size}:{stat.st_mtime_ns}'
    if marker.is_file() and marker.read_text(encoding='utf-8').strip() == fingerprint:
        return target
    if shutil.which('7z') is None:
        raise RuntimeError('7z is required to unpack ISO files.')
    STAGING.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(STAGING).free
    if free < stat.st_size * 1.1:
        raise RuntimeError(f'Not enough space to unpack {source.name}.')
    if target.exists():
        shutil.rmtree(target)
    result = runner(
        ['7z', 'x', '-y', f'-o{target}', str(source)],
        capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(f'7z failed: {(result.stderr or result.stdout)[-400:]}')
    marker.write_text(fingerprint, encoding='utf-8')
    return target


def find_setup(folder):
    """Pick the setup program named by autorun.inf, else a standard setup name."""
    folder = folder.resolve()
    entries = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    autorun = entries.get('autorun.inf')
    if autorun:
        for line in autorun.read_text(encoding='latin-1', errors='replace').splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip().lower() == 'open':
                exe = value.strip().strip('"').split()[0] if value.strip() else ''
                target = (folder / exe.replace('\\', '/')).resolve()
                if exe and folder in target.parents and target.is_file():
                    return target
    for name in _SETUP_NAMES:
        if name in entries:
            return entries[name]
    raise RuntimeError(f'No setup program was found in {folder}.')


# ── Launching ─────────────────────────────────────────────────────────────────

def _user_session_env():
    env = dict(os.environ)
    runtime = f'/run/user/{os.getuid()}'
    env.setdefault('XDG_RUNTIME_DIR', runtime)
    env.setdefault('DBUS_SESSION_BUS_ADDRESS', f'unix:path={runtime}/bus')
    return env


def launch_in_bottle(bottle, setup, unit, runner=subprocess.run):
    """Start setup via the user session so its window appears on Ghost's desktop."""
    cmd = [
        'systemd-run', '--user', '--collect', '--quiet', f'--unit={unit}',
        f'--working-directory={setup.parent}', '--',
        *BOTTLES_CLI, 'run', '-b', bottle, '-e', str(setup),
    ]
    result = runner(cmd, capture_output=True, text=True, timeout=30, env=_user_session_env())
    if result.returncode != 0:
        raise RuntimeError(f'Could not start the installer: {(result.stderr or result.stdout)[-400:]}')


def unit_state(unit, runner=subprocess.run):
    try:
        result = runner(
            ['systemctl', '--user', 'is-active', unit],
            capture_output=True, text=True, timeout=10, env=_user_session_env(),
        )
        return (result.stdout or '').strip() or 'unknown'
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


# ── Registration ──────────────────────────────────────────────────────────────

def find_game_executables(bottle_path, since, hint=''):
    """New .exe files in the bottle since the install started, largest first."""
    drive = bottle_path / 'drive_c'
    skip = {drive / 'windows', drive / 'users'}
    found = []
    for root, dirs, files in os.walk(drive):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if root_path / d not in skip]
        for name in files:
            if not name.lower().endswith('.exe') or _NOT_GAME_RE.match(name):
                continue
            path = root_path / name
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime + 5 < since and stat.st_ctime + 5 < since:
                continue
            if hint and hint.lower() not in str(path.relative_to(drive)).lower():
                continue
            found.append((stat.st_size, path))
    return [p for _size, p in sorted(found, key=lambda item: -item[0])]


def list_programs(bottle, runner=subprocess.run):
    result = runner(
        [*BOTTLES_CLI, '-j', 'programs', '-b', bottle],
        capture_output=True, text=True, timeout=60, env=_user_session_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(f'Could not list Bottles programs: {(result.stderr or "")[-300:]}')
    start = result.stdout.find('[')
    return json.loads(result.stdout[start:]) if start >= 0 else []


def add_program(bottle, name, exe, runner=subprocess.run):
    result = runner(
        [*BOTTLES_CLI, 'add', '-b', bottle, '-n', name, '-p', str(exe)],
        capture_output=True, text=True, timeout=60, env=_user_session_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(f'Bottles could not add the program: {(result.stderr or result.stdout)[-300:]}')


# ── Skill entry points ────────────────────────────────────────────────────────

def skill_game_installers(args, agent, **_):
    files = []
    if DOWNLOADS.is_dir():
        for path in sorted(DOWNLOADS.rglob('*')):
            rel = path.relative_to(DOWNLOADS)
            if rel.parts[0] == STAGING.name or len(rel.parts) > 3:
                continue
            if path.is_file() and path.suffix.lower() in INSTALLER_SUFFIXES:
                files.append(f'  {rel}  ({path.stat().st_size / 1_048_576:,.0f} MB)')
    bottles = sorted(p.name for p in BOTTLES_ROOT.glob('*') if (p / 'bottle.yml').is_file()) \
        if BOTTLES_ROOT.is_dir() else []
    lines = ['Installers in ~/Downloads:', *(files or ['  (none)'])]
    lines += ['', f'Bottles: {", ".join(bottles) or "(none)"} (default: {DEFAULT_BOTTLE})']
    jobs = _load_jobs()[-5:]
    if jobs:
        lines += ['', 'Recent installs:']
        for job in jobs:
            state = unit_state(job['unit']) if job.get('status') == 'launched' else job.get('status')
            lines.append(f"  {job.get('proposal_id') or 'chat'}: {job['source_name']} → {job['bottle']} [{state}]")
    lines += ['', 'Next: Ghost types "install <file name>" in chat, or use a Ghost-approved proposal '
              'with SKILL game_install.']
    return True, '\n'.join(lines)


def _start_install(source, bottle, agent, **record):
    """Stage, launch and record an install. Returns (ok, message, job)."""
    try:
        folder = stage_iso(source) if source.suffix.lower() == '.iso' else source.parent
        setup = find_setup(folder) if source.suffix.lower() == '.iso' else source
        job_id = uuid.uuid4().hex[:10]
        unit = f'fridays-game-install-{job_id}'
        started = time.time()
        launch_in_bottle(bottle, setup, unit)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return False, f'Install did not start: {exc}', None
    job = {
        'job_id': job_id, 'proposal_id': record.pop('proposal_id', None), 'agent': agent,
        'bottle': bottle, 'source_name': source.name, 'source': str(source), 'setup': str(setup),
        'unit': unit, 'started_at': started, 'status': 'launched', **record,
    }
    _save_job(job)
    return True, (
        f'Installer started in bottle {bottle}: {setup.name} (unit {unit}).\n'
        'The setup window is open on Ghost\'s desktop; Ghost must click through it. '
        'Install to the default C: drive location. This is not a finished install.'
    ), job


def _register_job(job, name, hint=''):
    """Add the job's installed game to Bottles and verify it. Returns (ok, message)."""
    if unit_state(job['unit']) == 'active':
        return False, 'The installer is still running. Finish or close the setup window first.'
    try:
        bottle, bottle_path = check_bottle(job['bottle'])
        candidates = find_game_executables(bottle_path, job['started_at'], hint)
        if not candidates:
            return False, ('No new game executable was found in the bottle. '
                           'The installer may have been cancelled or failed.')
        if len(candidates) > 1:
            best = _best_match(candidates, job['source_name'])
            if best is None:
                listed = '\n'.join(f'  {p.relative_to(bottle_path / "drive_c")}' for p in candidates[:10])
                return False, f'Several executables were found; name the one to use:\n{listed}'
            candidates = [best]
        exe = candidates[0]
        programs = list_programs(bottle)
        if not any(Path(p.get('folder', '')) / p.get('executable', '') == exe for p in programs):
            add_program(bottle, name, exe)
            programs = list_programs(bottle)
        entry = next((p for p in programs
                      if Path(p.get('folder', '')) / p.get('executable', '') == exe), None)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, f'Registration failed: {exc}'
    if not entry:
        return False, f'Bottles did not list {exe.name} after adding it.'
    job.update({'status': 'registered', 'program': entry.get('name'), 'executable': str(exe)})
    _save_job(job)
    return True, (
        f'Verified in Bottles: "{entry.get("name")}" → {exe} (bottle {bottle}). '
        'Launch it from Bottles. The game has not been launch-tested.'
    )


def skill_game_install(args, agent, **_):
    usage = 'Usage: SKILL game_install <proposal_id> <file in ~/Downloads> [bottle=<name>]'
    try:
        proposal_id, rel_path, options = _parse(args, {'bottle'})
        source = resolve_source(rel_path)
        bottle, _path = check_bottle(options.get('bottle'))
    except ValueError as exc:
        return False, f'{exc}\n{usage}'
    error = require_ghost_approval(proposal_id, agent, source.name)
    if error:
        return False, error
    previous = _latest_job(proposal_id)
    if previous and previous.get('status') == 'launched' and unit_state(previous['unit']) == 'active':
        return False, f'The installer for {proposal_id} is still running. Wait for Ghost to finish it.'
    ok, message, _job = _start_install(source, bottle, agent, proposal_id=proposal_id)
    if ok:
        message += f'\nAfter setup closes, run: SKILL game_register {proposal_id} <Program name>'
    return ok, message


def skill_game_register(args, agent, **_):
    usage = 'Usage: SKILL game_register <proposal_id> <Program name> [exe=<file or folder hint>]'
    try:
        proposal_id, name, options = _parse(args, {'exe'})
    except ValueError as exc:
        return False, f'{exc}\n{usage}'
    job = _latest_job(proposal_id)
    if not job:
        return False, f'No game_install run is recorded for {proposal_id}.'
    error = require_ghost_approval(proposal_id, agent, job['source_name'])
    if error:
        return False, error
    return _register_job(job, name, options.get('exe', ''))


# ── Ghost's direct chat requests ──────────────────────────────────────────────
# "install <file>" typed by Ghost is itself the human approval. The harness acts on
# Ghost's stored chat message, never on model output or agent-relayed text.

_INSTALL_RE = re.compile(r'\b(?:re)?install\b|\bset\s*up\b', re.IGNORECASE)
_REGISTER_RE = re.compile(
    r'\bregister\b|\b(?:finished|done|completed?)\b.*\b(?:install(?:ing|er|ation)?|setup)\b'
    r'|\b(?:install(?:ing|er|ation)?|setup)\b.*\b(?:finished|done|completed?)\b',
    re.IGNORECASE,
)
_FILE_HINT_RE = re.compile(r'\.(?:iso|exe|msi)\b', re.IGNORECASE)
_REQUEST_STOPWORDS = {
    'install', 'reinstall', 'set', 'up', 'setup', 'please', 'the', 'game', 'iso', 'exe', 'msi',
    'from', 'downloads', 'download', 'my', 'it', 'for', 'me', 'can', 'you', 'a', 'an', 'of',
    'in', 'into', 'to', 'and', 'now', 'bottles', 'bottle', 'fridays', 'with', 'using', 'file',
}


def _tokens(text):
    return re.findall(r'[a-z0-9]+', (text or '').lower())


def _installer_files():
    found = []
    if DOWNLOADS.is_dir():
        for path in sorted(DOWNLOADS.rglob('*')):
            rel = path.relative_to(DOWNLOADS)
            if rel.parts[0] == STAGING.name or len(rel.parts) > 3:
                continue
            if path.is_file() and path.suffix.lower() in INSTALLER_SUFFIXES:
                found.append(path)
    return found


def _installer_label(path):
    """Name a download by its folder when the file is a generic setup.exe."""
    rel = path.relative_to(DOWNLOADS)
    if path.name.lower() in _SETUP_NAMES and len(rel.parts) > 1:
        return rel.parts[-2]
    return path.stem


def game_name(source_name):
    name = re.sub(r'\[[^\]]*\]|\([^)]*\)', ' ', Path(source_name).stem)
    name = re.sub(r'\bv?\d+(?:\.\d+)+\b', ' ', name)
    name = re.sub(r"[_'\"]+", ' ', name)
    return re.sub(r'\s+', ' ', name).strip(' -.') or Path(source_name).stem


def match_installers(text):
    """Installers in Downloads that Ghost's message names, by filename or its words."""
    lowered = (text or '').lower()
    files = _installer_files()
    exact = [p for p in files if p.name.lower() in lowered
             or str(p.relative_to(DOWNLOADS)).lower() in lowered]
    if exact:
        return exact
    wanted = [t for t in _tokens(text) if t not in _REQUEST_STOPWORDS]
    if not wanted or not any(len(t) >= 3 for t in wanted):
        return []
    return [p for p in files if set(wanted) <= set(_tokens(_installer_label(p)))]


def _best_match(candidates, source_name):
    words = {t for t in _tokens(game_name(source_name)) if len(t) >= 3}
    scored = sorted(((len(words & set(_tokens(p.stem))), p.stat().st_size, p) for p in candidates),
                    key=lambda item: (item[0], item[1]), reverse=True)
    if not scored or scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][2]


def _latest_operator_message(conv_id):
    """Ghost's newest chat message in this conversation, if it is recent."""
    from database import get_connection

    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, content FROM messages WHERE conversation_id=? AND from_agent='user' "
            "AND created_at >= datetime('now', '-15 minutes') ORDER BY id DESC LIMIT 1",
            (conv_id,),
        ).fetchone()
    finally:
        conn.close()


def _same_request(prompt_text, stored):
    squash = lambda value: ' '.join(str(value or '').split()).lower()  # noqa: E731
    stored_text = squash(stored)
    return bool(stored_text) and stored_text in squash(prompt_text)


def handle_operator_request(agent, operator_text, conv_id):
    """Run an install/register that Ghost typed in chat. Returns a reply, or None if not one.

    Intent and file names are read from Ghost's stored chat message, never from the
    model prompt, which may contain relayed or injected text.
    """
    if not (_INSTALL_RE.search(operator_text or '') or _REGISTER_RE.search(operator_text or '')):
        return None
    if conv_id is None:
        return None
    try:
        message = _latest_operator_message(conv_id)
    except sqlite3.Error as exc:
        logger.warning('game_installer: could not read Ghost message: %s', exc)
        return None
    if not message or not _same_request(operator_text, message['content']):
        return None
    text = message['content']
    wants_register = bool(_REGISTER_RE.search(text))
    wants_install = not wants_register and bool(_INSTALL_RE.search(text))
    if not (wants_install or wants_register):
        return None
    matches = match_installers(text)
    if wants_install and not matches:
        if _FILE_HINT_RE.search(text):
            names = ', '.join(p.name for p in _installer_files()) or 'none'
            return f'No matching installer was found in ~/Downloads. Installers there: {names}.'
        return None
    if wants_register and not matches and not _latest_launch(agent, conv_id):
        return None
    if len(matches) > 1:
        listed = '\n'.join(f'  {p.relative_to(DOWNLOADS)}' for p in matches)
        return f'Several installers match. Say which one, using its file name:\n{listed}'

    if wants_register:
        job = _latest_launch(agent, conv_id, matches[0].name if matches else None)
        if not job:
            return 'No Fridays install is waiting to be registered for that game.'
        ignore = _REQUEST_STOPWORDS | {'register', 'finished', 'done', 'complete', 'completed',
                                       'installed', 'installer', 'installing', 'installation'}
        exe_hint = next((t for t in _tokens(text) if len(t) >= 4 and t not in ignore
                         and t not in _tokens(job['source_name'])), '')
        _ok, reply = _register_job(job, game_name(job['source_name']), exe_hint)
        return reply

    source = matches[0]
    previous = next((j for j in reversed(_load_jobs())
                     if j.get('source') == str(source) and j.get('status') == 'launched'), None)
    if previous and previous.get('message_id') == message['id']:
        return f'This request already started the installer (unit {previous["unit"]}).'
    if previous and unit_state(previous['unit']) == 'active':
        return f'The installer for {source.name} is already running. Finish the setup window first.'
    try:
        bottle, _path = check_bottle(None)
    except ValueError as exc:
        return str(exc)
    ok, reply, _job = _start_install(
        source, bottle, agent,
        authorized_by='ghost-chat', conversation_id=conv_id, message_id=message['id'],
    )
    if ok:
        reply += ('\nWhen setup has finished, tell me "setup finished" and I will add the game '
                  'to Bottles.')
    return reply


def _latest_launch(agent, conv_id, source_name=None):
    for job in reversed(_load_jobs()):
        if job.get('status') != 'launched' or job.get('agent') != agent:
            continue
        if source_name and job.get('source_name') != source_name:
            continue
        if not source_name and job.get('conversation_id') != conv_id:
            continue
        return job
    return None
