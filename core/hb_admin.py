"""Admin steps through Linux's own sudo prompt (Practice 170, owner 19 Nov 2026: "if it's bound by the linux HB can use it and it's not
built into HB so it can't really change it, go ahead").

HB never runs anything as root by itself and never sees a password. It PROPOSES an admin step - one command from a fixed allowlist - as a
card in main chat. When JD types /admin approve A-xxxx in his own authenticated main chat, HB opens a terminal window on JD's desktop that
runs `sudo <command>`: Linux asks for the password there. HB reads only the output (a log file) and reports how it ended.

Allowlist (anything else is refused):
  apt-get update
  apt-get install -y <package names, or a .deb HB downloaded into runtime/admin_downloads>
  amdgpu-install --usecase=<rocm|hiplibsdk|opencl|graphics, comma-separated> --no-dkms -y
Downloads (no admin needed) only from repo.radeon.com.
/admin                     list admin steps
/admin approve A-xxxx      JD only: open the sudo window for that step
/admin decline A-xxxx
/admin rocm                download AMD's installer and propose the two ROCm steps
/admin check rocm          rocminfo (no admin): does ROCm see the card?
"""
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_DIR = ROOT / 'runtime' / 'admin_downloads'
LOG_DIR = ROOT / 'runtime' / 'admin_logs'
_PKG = re.compile(r'^[a-z0-9][a-z0-9+.-]{0,80}$')
USECASES = {'rocm', 'hiplibsdk', 'opencl', 'graphics'}
AGENTS = {'claude code', 'apex', 'hummingbird', 'fred', 'codex', 'gemini', 'hb', 'hb gpu guard'}
RADEON = 'https://repo.radeon.com/amdgpu-install/latest/ubuntu/noble/'


def validate(argv):
    """A plain-English description of an allowed admin command; ValueError for anything else."""
    a = [str(x) for x in argv or []]
    if a == ['apt-get', 'update']:
        return 'refresh the package lists'
    if a[:3] == ['apt-get', 'install', '-y'] and len(a) > 3:
        for item in a[3:]:
            if item.endswith('.deb'):
                p = Path(item)
                if not p.is_absolute() or p.resolve().parent != ADMIN_DIR.resolve() or not p.exists():
                    raise ValueError(f'{item}: a .deb must be one HB downloaded into {ADMIN_DIR}')
            elif not _PKG.match(item):
                raise ValueError(f'{item}: not a package name')
        return 'install ' + ', '.join(Path(i).name for i in a[3:])
    if a and a[0] == 'amdgpu-install' and set(a[1:]) - {x for x in a[1:] if x.startswith('--usecase=')} == {'--no-dkms', '-y'}:
        uses = [x for x in a[1:] if x.startswith('--usecase=')]
        if len(uses) == 1 and set(uses[0].split('=', 1)[1].split(',')) <= USECASES:
            return f"install AMD's {uses[0].split('=', 1)[1]} stack without AMD's kernel module (your kernel's driver is used)"
    raise ValueError('not an allowed admin command: ' + ' '.join(a))


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_admin_requests(id TEXT PRIMARY KEY, argv TEXT NOT NULL, why TEXT, state TEXT, needs TEXT, '
                 'created_at REAL, updated_at REAL, exit_code INTEGER, log TEXT)')


def _say(conn, text):
    from core.hb_model_bench import _post
    _post(conn, text)


def propose(conn, argv, why='', needs=None):
    ensure_schema(conn)
    what = validate(argv)
    rid = 'A-' + uuid.uuid4().hex[:6].upper()
    now = time.time()
    conn.execute('INSERT INTO hb_admin_requests VALUES (?,?,?,?,?,?,?,?,?)', (rid, json.dumps(list(argv)), why or what, 'proposed', needs, now, now, None, None))
    _say(conn, f"🔐 Admin step {rid}: `sudo {' '.join(argv)}`\nWhat it does: {why or what}."
               + (f' Runs after {needs} has finished.' if needs else '')
               + f"\nType /admin approve {rid} and a terminal window opens on your desktop; Linux asks for your password there (HB never sees it)."
               f" /admin decline {rid} to skip it.")
    return rid


def _row(conn, rid):
    ensure_schema(conn)
    return conn.execute('SELECT id, argv, why, state, needs FROM hb_admin_requests WHERE id=?', (str(rid).upper(),)).fetchone()


def _launch(rid, argv, log, status):
    # Practice 171 (owner 19 Nov 2026): the first ROCm step stopped at dpkg's "amdgpu.list / rocm.list (Y/I/N/O/D/Z)?" questions, and when
    # the window was closed the install hung on a terminal nobody could reach. Admin steps now never ask (noninteractive, new config files).
    script = ('echo "HB admin step $HB_ADMIN_ID: sudo $*"; echo; sudo -- env DEBIAN_FRONTEND=noninteractive "$@" 2>&1 | tee "$HB_ADMIN_LOG"; s=${PIPESTATUS[0]}; '
              'echo "$s" > "$HB_ADMIN_STATUS"; echo; echo "Finished with exit code $s - you can close this window."; '
              'read -r -p "Press Enter to close" _')
    env = dict(os.environ, DISPLAY=os.environ.get('DISPLAY') or ':0', XAUTHORITY=os.environ.get('XAUTHORITY') or str(Path.home() / '.Xauthority'),
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus', HB_ADMIN_ID=rid, HB_ADMIN_LOG=str(log),
               HB_ADMIN_STATUS=str(status))
    return subprocess.Popen(['gnome-terminal', '--title', f'HB admin {rid}', '--', 'bash', '-c', script, 'hb-admin', *argv], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def approve(conn, rid, actor, owner=False, launcher=None, watch=True):
    row = _row(conn, rid)
    if not row:
        return f'No admin step {rid}.'
    if not owner or str(actor or '').strip().lower() in AGENTS:
        return 'Only JD can approve an admin step, by typing /admin approve in his own main chat.'
    rid, argv, why, state, needs = row
    if state != 'proposed':
        return f'{rid} is {state}, not waiting for approval.'
    if needs:
        dep = _row(conn, needs)
        if dep and dep[3] != 'done':
            return f'{rid} runs after {needs}, which is {dep[3]}.'
    argv = json.loads(argv)
    validate(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log, status = LOG_DIR / f'{rid}.log', LOG_DIR / f'{rid}.status'
    for p in (log, status):
        if p.exists():
            p.unlink()
    (launcher or _launch)(rid, unattended(argv), log, status)
    conn.execute("UPDATE hb_admin_requests SET state='running', updated_at=? WHERE id=?", (time.time(), rid))
    if watch:
        threading.Thread(target=_watch, args=(rid, log, status), name='hb-admin-' + rid, daemon=True).start()
    return f'🔐 {rid}: a terminal window titled "HB admin {rid}" is open on your desktop - type your password there. HB reports here when it ends.'


def unattended(argv):
    """Practice 171: apt-get takes the package's new config files instead of asking (the 19 Nov amdgpu.list / rocm.list prompts)."""
    a = list(argv)
    if a[:1] == ['apt-get']:
        return ['apt-get', '-o', 'Dpkg::Options::=--force-confnew', '-o', 'Dpkg::Options::=--force-confdef'] + a[1:]
    return a


def _running(rid):
    """Is the admin step's sudo still running (its window may have been closed)?"""
    try:
        out = subprocess.run(['pgrep', '-f', 'sudo -- env DEBIAN_FRONTEND=noninteractive'], capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip())
    except Exception:
        return True


def _watch(rid, log, status, limit=4 * 3600, sleep=time.sleep, running=None):
    from contextlib import closing
    from utils.db._connection import get_connection
    running = running or _running
    start = time.time()
    gone = 0
    while not status.exists() and time.time() - start < limit:
        sleep(5)
        # Practice 171: the window was closed before the step finished - say so instead of waiting for hours
        gone = gone + 1 if time.time() - start > 60 and not running(rid) else 0
        if gone >= 3:
            break
    if not status.exists() and gone >= 3:
        return finish(rid, -1, log.read_text(errors='replace') if log.exists() else '', get_connection)
    code = int(status.read_text().strip() or 1) if status.exists() else None
    finish(rid, code, log.read_text(errors='replace') if log.exists() else '', get_connection)


def finish(rid, code, log_text, connect):
    from contextlib import closing
    state = 'done' if code == 0 else ('timed out' if code is None else 'window closed before it finished' if code == -1 else 'failed')
    tail = '\n'.join(log_text.strip().splitlines()[-25:])
    with closing(connect()) as conn:
        conn.execute('UPDATE hb_admin_requests SET state=?, exit_code=?, log=?, updated_at=? WHERE id=?', (state, code, log_text[-20000:], time.time(), rid))
        _say(conn, f"🔐 Admin step {rid} {state}" + (f' (exit code {code})' if code not in (0, None) else '') + '.'
                   + (f"\n```text\n{tail.replace('```', '` ` `')}\n```" if tail else ''))
        conn.commit()
    return state


def fetch_installer(get=None):
    """Download AMD's amdgpu-install .deb for Ubuntu 24.04 (noble) into ADMIN_DIR; returns its path."""
    get = get or (lambda url: urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read())
    page = get(RADEON).decode('utf-8', 'replace')
    names = sorted(set(re.findall(r'amdgpu-install_[\w.~+-]+_all\.deb', page)))
    if not names:
        raise RuntimeError('no amdgpu-install .deb on ' + RADEON)
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)
    path = ADMIN_DIR / names[-1]
    path.write_bytes(get(RADEON + names[-1]))
    return path


def check_rocm(run=subprocess.run):
    try:
        out = run(['/opt/rocm/bin/rocminfo'], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return 'ROCm is not installed yet (/opt/rocm/bin/rocminfo is missing).'
    gfx = sorted(set(re.findall(r'gfx\d{3,4}\w*', out.stdout or '')))
    if 'gfx1030' in gfx:
        return 'ROCm sees the RX 6800 (gfx1030). Next: build llama.cpp with ROCm and benchmark it against Vulkan.'
    return 'rocminfo ran but does not list gfx1030' + (f' (found: {", ".join(gfx)})' if gfx else '') + ':\n' + (out.stderr or out.stdout or '')[-800:]


def command(conn, args, actor, owner=False):
    ensure_schema(conn)
    if not args:
        rows = conn.execute('SELECT id, argv, state FROM hb_admin_requests ORDER BY created_at DESC LIMIT 10').fetchall()
        return ('Admin steps:\n' + '\n'.join(f"- {r[0]}: sudo {' '.join(json.loads(r[1]))} - {r[2]}" for r in rows)) if rows else \
            'No admin steps yet. /admin rocm prepares the ROCm install.'
    verb = args[0].lower()
    if verb == 'approve' and len(args) == 2:
        return approve(conn, args[1], actor, owner)
    if verb == 'decline' and len(args) == 2:
        row = _row(conn, args[1])
        if not row:
            return f'No admin step {args[1]}.'
        conn.execute("UPDATE hb_admin_requests SET state='declined', updated_at=? WHERE id=?", (time.time(), row[0]))
        return f'{row[0]} declined; nothing ran.'
    if verb == 'check' and args[1:] == ['rocm']:
        return check_rocm()
    if verb == 'rocm':
        deb = fetch_installer()
        a = propose(conn, ['apt-get', 'install', '-y', str(deb)], f"install AMD's installer tool ({deb.name}, downloaded from repo.radeon.com)")
        b = propose(conn, ['amdgpu-install', '--usecase=rocm,hiplibsdk', '--no-dkms', '-y'], needs=a)
        return f'Downloaded {deb.name}. Two admin steps are waiting for you: {a}, then {b}. Afterwards: /admin check rocm.'
    return 'Use /admin, /admin rocm, /admin approve A-xxxx, /admin decline A-xxxx or /admin check rocm.'
