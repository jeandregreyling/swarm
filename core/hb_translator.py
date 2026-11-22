"""Practice 182 (owner 20 Nov 2026: "the translator bot doesn't always have to run, I have the button next to the chat box that I can turn on
if I need the translator ... it should be associated with auto on for talking to models that prefer Asian languages, the English ones
are fine without it"). hb-translate.service (a 3B llama-server on the CPU, port 8081) was enabled at login with Restart=always, so it ran
all the time; the chat button only changed what the page did.

Now:
  the button   JD's switch: on starts the service ('manual'), off stops it and keeps it from starting at login
  auto         a model reply that is mostly Chinese, Japanese or Korean starts it ('auto'), remembers that model's language
               (hb_model_language) and says so in main chat; idle_tick() stops an auto start 30 minutes after the last such reply
Only user-level systemctl is used (no sudo)."""
import os
import re
import subprocess
import time

SERVICE = 'hb-translate'
AUTO_IDLE_S = 1800
SKIP = {'user', 'hummingbird', 'system', 'ghost', 'jd'}
NAMES = {'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean'}
_CJK = re.compile('[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]')


def _ctl(verb, run=subprocess.run):
    uid = os.getuid()
    env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{uid}', 'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{uid}/bus'}
    return run(['systemctl', '--user', verb, SERVICE], env=env, capture_output=True, text=True, timeout=60)


def running(run=subprocess.run):
    return _ctl('is-active', run).stdout.strip() == 'active'


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_model_language(model TEXT PRIMARY KEY, lang TEXT, at REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_translator(id INTEGER PRIMARY KEY CHECK (id=1), mode TEXT, at REAL)')


def mode(conn):
    ensure(conn)
    row = conn.execute('SELECT mode, at FROM hb_translator WHERE id=1').fetchone()
    return (row[0], row[1]) if row else ('off', None)


def _set(conn, value, now):
    ensure(conn)
    conn.execute('INSERT OR REPLACE INTO hb_translator VALUES (1,?,?)', (value, now))


def switch(conn, on, run=subprocess.run, now=None):
    """JD's button. Returns (ok, running)."""
    now = now or time.time()
    if on:
        ok = _ctl('start', run).returncode == 0
        _set(conn, 'manual', now)
    else:
        ok = _ctl('stop', run).returncode == 0
        _ctl('disable', run)                       # not back at the next login; the button or an Asian-language reply starts it
        _set(conn, 'off', now)
    return ok, running(run)


def start_auto(conn, run=subprocess.run, now=None):
    """Start the translator on demand without turning an automatic start into manual mode."""
    now = time.time() if now is None else now
    current, _ = mode(conn)
    if running(run):
        if current != 'manual':
            _set(conn, 'auto', now)
        return True
    ok = _ctl('start', run).returncode == 0
    if ok:
        _set(conn, 'auto', now)
    return ok


def cjk_share(text):
    letters = [c for c in str(text or '') if c.isalpha()]
    return sum(1 for c in letters if _CJK.match(c)) / len(letters) if len(letters) >= 2 else 0.0


def language_of(text):
    text = str(text or '')
    if re.search('[\u3040-\u30ff]', text):
        return 'ja'
    if re.search('[\uac00-\ud7af]', text):
        return 'ko'
    return 'zh'


def on_reply(conn, agent, text, run=subprocess.run, say=None, now=None):
    """A reply that is mostly CJK: remember the model's language; start the translator when it is off. Returns what happened."""
    if str(agent or '').lower() in SKIP or cjk_share(text) < 0.3:
        return None
    now = now or time.time()
    ensure(conn)
    lang = language_of(text)
    conn.execute('INSERT OR REPLACE INTO hb_model_language VALUES (?,?,?)', (str(agent), lang, now))
    current, _ = mode(conn)
    if running(run):
        if current != 'manual':
            _set(conn, 'auto', now)                # keeps an auto start alive while the replies keep coming
        return 'running'
    ok = _ctl('start', run).returncode == 0
    _set(conn, 'auto', now)
    if say:
        say(f"HB: {agent} answered in {NAMES.get(lang, lang)}, so the translator is on (started by HB). It stops by itself 30 minutes "
            "after the last such reply; the translate button next to the chat box turns it off sooner.")
    return 'started' if ok else 'failed'


def idle_tick(conn, now=None, run=subprocess.run):
    """An auto start stops 30 minutes after the last Asian-language reply. JD's own 'manual' start is left alone."""
    now = now or time.time()
    current, at = mode(conn)
    if current == 'auto' and at and now - at > AUTO_IDLE_S:
        _ctl('stop', run)
        _set(conn, 'off', now)
        return True
    return False


def languages(conn):
    ensure(conn)
    return [{'model': m, 'lang': l} for m, l in conn.execute('SELECT model, lang FROM hb_model_language ORDER BY at DESC LIMIT 20')]
