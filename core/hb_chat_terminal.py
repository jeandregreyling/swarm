"""Terminal in main chat (owner 16 Nov 2026, step S-9B9907AF1F; restores the 12 Nov ask "Usable terminal in main chat").

JD types "$ df -h" (or "/sh df -h") in main chat. HB:
  - checks it: one plain command from HB's terminal whitelist (fridays.shell_agent.WHITELIST), read-only and status commands only
    (level <= MAX_LEVEL), no ; | & $ ` < > or backslashes - it never runs through a shell, so nothing can be chained onto it;
  - saves JD's line and one HB result message in the chat, and runs the command in its own process group;
  - updates that message about once a second with the live output, then with how it ended (completed / failed / stopped / timed out);
  - stops it on request (the whole process group), and after a restart marks a command that was cut off "interrupted by an HB restart"
    and kills anything it left behind.
A refused command is saved too, with the reason, and nothing runs.
"""
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from contextlib import closing

MAX_LEVEL = 2                 # whitelist levels 0-2: system info, file reads in the repo, service status; never sudo, curl or python
MAX_OUTPUT = 20000
TIMEOUT_S = 120
UPDATE_S = 1.0
ROOT = os.environ.get('SWARM_ROOT', str(__import__('pathlib').Path(__file__).resolve().parent.parent))
BOOT = uuid.uuid4().hex       # this HB process; a "running" row from another boot was cut off by a restart
_META = re.compile(r'[\x00-\x1f;|&`$<>\\]')
_PROCS = {}
_STOPPED = set()
_LOCK = threading.Lock()


def _connect():
    from utils.db._connection import get_connection
    return get_connection()


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_chat_terminal(command_id TEXT PRIMARY KEY, conversation_id INTEGER, message_id INTEGER,
        command TEXT, state TEXT, pid INTEGER, boot TEXT, output TEXT, returncode INTEGER, started_at REAL, ended_at REAL, actor TEXT)''')


def allowed():
    """Plain list of what main chat may run."""
    from fridays import shell_agent
    return sorted({desc for _pattern, level, desc in shell_agent.WHITELIST if level <= MAX_LEVEL})


# Practice 107 (owner 16 Nov 2026): "it should ask to add commands to whitelist if they aren't in it". JD can add one EXACT command
# (never a pattern). It still runs without a shell, with Stop and the timeout. Never: privilege (sudo, su, doas, pkexec) or commands that
# destroy or switch off the system - those belong in a real terminal.
NEVER = {'sudo', 'su', 'doas', 'pkexec', 'rm', 'dd', 'shred', 'shutdown', 'reboot', 'poweroff', 'halt', 'init', 'telinit'}


def _allow_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_chat_terminal_allowed(command TEXT PRIMARY KEY, added_by TEXT, added_at REAL)')


def allowed_extra(connect=None):
    try:
        with closing((connect or _connect)()) as conn:
            _allow_schema(conn)
            return {r[0] for r in conn.execute('SELECT command FROM hb_chat_terminal_allowed')}
    except Exception:
        return set()


def can_allow(command):
    """(True, None) when JD may add this exact command to main chat's list, else (False, why)."""
    cmd = str(command or '').strip()
    if not cmd or len(cmd) > 500:
        return False, 'it is empty or too long'
    if _META.search(cmd):
        return False, 'it chains or redirects (; | & $ ` < > or backslashes)'
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return False, 'it has unbalanced quotes'
    program = os.path.basename(argv[0])
    if program in NEVER or program.startswith('mkfs'):
        return False, f'{program} needs root or changes the system; run it in a real terminal'
    if shutil.which(argv[0]) is None:
        return False, f'there is no program called {argv[0]} on this machine'
    return True, None


def allow(command, actor='owner', connect=None):
    """JD adds one exact command to main chat's terminal list."""
    ok, why = can_allow(command)
    if not ok:
        return {'ok': False, 'error': f'Not added: {why}.'}
    cmd = str(command).strip()
    with closing((connect or _connect)()) as conn:
        _allow_schema(conn)
        conn.execute('INSERT OR IGNORE INTO hb_chat_terminal_allowed(command, added_by, added_at) VALUES (?,?,?)', (cmd, actor, time.time()))
        conn.commit()
    return {'ok': True, 'command': cmd}


def check(command, connect=None):
    """(argv, None) for a command main chat may run, else (None, why)."""
    from fridays import shell_agent
    cmd = str(command or '').strip()
    if not cmd:
        return None, 'Type a command after "$ ", for example "$ df -h".'
    if len(cmd) > 500:
        return None, 'That command is too long (500 characters at most).'
    if _META.search(cmd):
        return None, 'One plain command only: no ; | & $ ` < > or backslashes. Nothing runs through a shell, so nothing can be chained on.'
    match = shell_agent._match_whitelist(cmd)
    if match is None and cmd in allowed_extra(connect):     # JD added this exact command (Practice 107)
        match = (0, 'added by JD')
    if match is None:
        return None, "That command is not on HB's terminal list, so nothing ran. Main chat can run: " + ', '.join(allowed()) + '.'
    if match[0] > MAX_LEVEL:
        return None, (f'"{cmd}" needs elevated rights ({match[1]}, level {match[0]}). Main chat runs read-only and status commands only; '
                      'nothing ran.')
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return None, 'The command could not be read (unbalanced quotes); nothing ran.'
    return argv, None


def render(command, output, state, returncode=None, seconds=None, why=None):
    """The chat message for one command: the command, its output, and how it ended."""
    ending = {'running': 'running… (Stop ends it)',
              'completed': f'completed, exit {returncode}',
              'failed': f'failed, exit {returncode}',
              'stopped': 'stopped by JD',
              'timeout': f'timed out after {TIMEOUT_S} s and was stopped',
              'interrupted': 'interrupted by an HB restart; the output above is what came before it',
              'refused': f'refused: {why}'}.get(state, state)
    if seconds is not None and state in ('completed', 'failed', 'stopped'):
        ending += f' ({seconds:.1f} s)'
    body = (output or '').rstrip('\n')
    shown = f"```text\n{body.replace('```', '` ` `')}\n```\n" if body else ('' if state == 'refused' else '(no output)\n')
    return f'💻 $ {command}\n{shown}— {ending}'


def _say(conn, conversation_id, who, text):
    return conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,?,?,?,'terminal',0)",
                        (conversation_id, who, 'hummingbird' if who == 'user' else 'user', text)).lastrowid


def _write(connect, command_id, **values):
    with closing(connect()) as conn:
        row = conn.execute('SELECT message_id, command, output, state, returncode, started_at, ended_at FROM hb_chat_terminal WHERE command_id=?',
                           (command_id,)).fetchone()
        if not row:
            return
        cur = dict(zip(('message_id', 'command', 'output', 'state', 'returncode', 'started_at', 'ended_at'), row), **values)
        conn.execute('UPDATE hb_chat_terminal SET ' + ', '.join(f'{k}=?' for k in values) + ' WHERE command_id=?', (*values.values(), command_id))
        seconds = (cur['ended_at'] - cur['started_at']) if cur['ended_at'] and cur['started_at'] else None
        conn.execute('UPDATE messages SET content=? WHERE id=?',
                     (render(cur['command'], cur['output'], cur['state'], cur['returncode'], seconds), cur['message_id']))
        conn.commit()


def start(conversation_id, command, actor='owner', connect=None, root=None):
    """Run one command for main chat. Returns {'ok', 'command_id', 'message_id', 'state', 'error'}."""
    connect = connect or _connect
    argv, why = check(command, connect)
    cmd = str(command or '').strip()
    command_id = uuid.uuid4().hex
    now = time.time()
    with closing(connect()) as conn:
        ensure_schema(conn)
        _say(conn, conversation_id, 'user', f'$ {cmd}')
        offer = bool(why) and why.startswith("That command is not on HB's terminal list") and can_allow(cmd)[0]
        if offer:
            why = (f'"{cmd}" is not on the HB terminal list, so nothing ran. Add it? Press "Allow and run" under this message, or type '
                   f'/sh allow {cmd} - only this exact command is added, and it still runs without a shell.')
        state = 'refused' if why else 'running'
        mid = _say(conn, conversation_id, 'hummingbird', render(cmd, '', state, why=why))
        conn.execute('INSERT INTO hb_chat_terminal(command_id,conversation_id,message_id,command,state,boot,output,started_at,ended_at,actor) '
                     'VALUES (?,?,?,?,?,?,?,?,?,?)', (command_id, conversation_id, mid, cmd, state, BOOT, '', now, now if why else None, actor))
        conn.commit()
    if why:
        return {'ok': False, 'command_id': command_id, 'message_id': mid, 'state': 'refused', 'error': why, 'can_allow': offer}
    try:
        proc = subprocess.Popen(argv, cwd=root or ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, bufsize=1, start_new_session=True)
    except OSError as exc:
        _write(connect, command_id, state='failed', returncode=127, output=f'{argv[0]}: {exc.strerror or exc}', ended_at=time.time())
        return {'ok': False, 'command_id': command_id, 'message_id': mid, 'state': 'failed', 'error': str(exc)}
    with _LOCK:
        _PROCS[command_id] = proc
    _write(connect, command_id, pid=proc.pid)
    threading.Thread(target=_follow, args=(command_id, proc, connect), name='hb-chat-terminal', daemon=True).start()
    return {'ok': True, 'command_id': command_id, 'message_id': mid, 'state': 'running'}


def _follow(command_id, proc, connect):
    out, last, started = [], 0.0, time.time()
    size, timed_out = 0, False
    killer = threading.Timer(TIMEOUT_S, lambda: _kill(proc))
    killer.daemon = True
    killer.start()
    try:
        for line in proc.stdout:
            if size < MAX_OUTPUT:
                piece = line[:MAX_OUTPUT - size]
                out.append(piece)
                size += len(piece)
                if size >= MAX_OUTPUT:
                    out.append('\n[... output cut at 20,000 characters ...]\n')
            if time.time() - last >= UPDATE_S:
                last = time.time()
                _write(connect, command_id, output=''.join(out))
        returncode = proc.wait()
        timed_out = time.time() - started >= TIMEOUT_S - 0.5 and returncode < 0
    finally:
        killer.cancel()
        with _LOCK:
            _PROCS.pop(command_id, None)
            stopped = command_id in _STOPPED
            _STOPPED.discard(command_id)
    state = 'stopped' if stopped else 'timeout' if timed_out else 'completed' if proc.returncode == 0 else 'failed'
    _write(connect, command_id, output=''.join(out), state=state, returncode=proc.returncode, ended_at=time.time())


def _kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def stop(command_id):
    """Stop a running command (its whole process group). True when it was running here."""
    with _LOCK:
        proc = _PROCS.get(command_id)
        if proc is None or proc.poll() is not None:
            return False
        _STOPPED.add(command_id)
    _kill(proc)
    return True


def status(command_id, connect=None):
    connect = connect or _connect
    with closing(connect()) as conn:
        ensure_schema(conn)
        row = conn.execute('SELECT command_id, message_id, command, state, output, returncode, started_at, ended_at FROM hb_chat_terminal '
                           'WHERE command_id=?', (command_id,)).fetchone()
        if not row:
            return None
        d = dict(zip(('command_id', 'message_id', 'command', 'state', 'output', 'returncode', 'started_at', 'ended_at'), row))
        content = conn.execute('SELECT content FROM messages WHERE id=?', (d['message_id'],)).fetchone()
        d['content'] = content[0] if content else ''
        return d


def recover(conn, connect=None):
    """After a restart: a command still marked running from another HB process was cut off. Kill what it left behind, say so."""
    ensure_schema(conn)
    rows = conn.execute("SELECT command_id, pid FROM hb_chat_terminal WHERE state='running' AND boot<>?", (BOOT,)).fetchall()
    for command_id, pid in rows:
        if pid:
            try:
                if os.getpgid(pid) == pid:          # the session leader HB started (start_new_session), not a reused pid
                    os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        conn.execute("UPDATE hb_chat_terminal SET state='interrupted', ended_at=? WHERE command_id=?", (time.time(), command_id))
        row = conn.execute('SELECT message_id, command, output FROM hb_chat_terminal WHERE command_id=?', (command_id,)).fetchone()
        conn.execute('UPDATE messages SET content=? WHERE id=?', (render(row[1], row[2], 'interrupted'), row[0]))
    return len(rows)
