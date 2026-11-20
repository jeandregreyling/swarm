"""Prepare Practice 182: the translator runs only when wanted - the 文A button starts/stops it, an Asian-language reply starts it."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
DB = 'utils/db/chat.py'
PC = 'core/peer_coordination.py'
PB = 'frontend/blueprints/peer_bridge.py'
J = 'frontend/static/js/hb-translate-bubble.js'

module = '''"""Practice 182 (owner 20 Nov 2026: "the translator bot doesn't always have to run, I have the button next to the chat box that I can turn on
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
_CJK = re.compile('[\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uac00-\\ud7af]')


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


def cjk_share(text):
    letters = [c for c in str(text or '') if c.isalpha()]
    return sum(1 for c in letters if _CJK.match(c)) / len(letters) if len(letters) >= 20 else 0.0


def language_of(text):
    text = str(text or '')
    if re.search('[\\u3040-\\u30ff]', text):
        return 'ja'
    if re.search('[\\uac00-\\ud7af]', text):
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
'''

edits = [
    {'path': DB, 'old': '''    conn.commit()
    conn.close()
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('thread', conv_id, actor='log_message')
    except Exception:
        pass
''', 'new': '''    conn.commit()
    conn.close()
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('thread', conv_id, actor='log_message')
    except Exception:
        pass
    _translator_watch(from_agent, content)


def _translator_watch(from_agent, content):
    """Practice 182: a model reply mostly in Chinese/Japanese/Korean switches the translator on (in the background)."""
    try:
        from core import hb_translator
        if str(from_agent or '').lower() in hb_translator.SKIP or hb_translator.cjk_share(content) < 0.3:
            return
    except Exception:
        return

    def work():
        try:
            from core.hb_model_bench import _post
            c = get_connection()
            try:
                hb_translator.on_reply(c, from_agent, content, say=lambda text: _post(c, text))
                c.commit()
            finally:
                c.close()
        except Exception:
            pass
    __import__('threading').Thread(target=work, name='hb-translator-auto', daemon=True).start()
'''},
    {'path': PC, 'old': '''                        try:  # Practice 158: a card reset seen in the kernel log - prove APEX answers, restart it when it does not''',
     'new': '''                        try:  # Practice 182: a translator HB started for an Asian-language reply stops after 30 quiet minutes
                            from core.hb_translator import idle_tick as translator_idle
                            translator_idle(conn)
                            conn.commit()
                        except Exception:
                            LOG.exception('translator idle check failed')
                        try:  # Practice 158: a card reset seen in the kernel log - prove APEX answers, restart it when it does not'''},
    {'path': PB, 'old': "@peer_bridge_bp.route('/api/peer/v1/hb/queue',methods=['GET','POST'])\n", 'new': '''@peer_bridge_bp.route('/api/peer/v1/hb/translator',methods=['GET','POST'])
@require_owner
def hb_translator_view(current_user=None):
    """Practice 182: the translate button starts/stops the translator service; GET says whether it runs and who started it."""
    from contextlib import closing
    from urllib.parse import urlsplit
    from core import hb_translator
    with closing(get_connection()) as conn:
        if request.method=='POST':
            origin=request.headers.get('Origin')
            if request.headers.get('Sec-Fetch-Site')=='cross-site' or origin and urlsplit(origin).netloc!=request.host:
                return jsonify(ok=False,error='Use the authenticated main chat'),403
            body=request.get_json(silent=True) or {}
            if type(body.get('on')) is not bool:return jsonify(ok=False,error='JSON {on: true|false} required'),400
            hb_translator.switch(conn,body['on'])
            conn.commit()
        current,_=hb_translator.mode(conn)
        return jsonify(ok=True,running=hb_translator.running(),mode=current,languages=hb_translator.languages(conn))


@peer_bridge_bp.route('/api/peer/v1/hb/queue',methods=['GET','POST'])
'''},
    {'path': J, 'old': '''    try { return localStorage.getItem(KEY_ON) !== '0'; } catch (e) { return true; }''',
     'new': '''    try { return localStorage.getItem(KEY_ON) === '1'; } catch (e) { return false; }   // Practice 182: off unless switched on'''},
    {'path': J, 'old': '''    try { return localStorage.getItem(KEY_IN) !== '0'; } catch (e) { return true; }''',
     'new': '''    try { return localStorage.getItem(KEY_IN) === '1'; } catch (e) { return false; }   // Practice 182: off unless switched on'''},
    {'path': J, 'old': '''  function refreshToggle() {
    if (!toggleBtn) return;
    const any = isEnabled() || repliesEnabled();''', 'new': '''  // Practice 182 (owner 20 Nov 2026): the button also starts and stops the translator itself, and HB switches it on for a model that
  // answers in Chinese, Japanese or Korean - the page then translates its replies.
  let serverOn = null;
  function syncServer(any) {
    if (serverOn === any) return;
    serverOn = any;
    fetch('/api/peer/v1/hb/translator', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on: any }) }).catch(() => {});
  }
  function watchServer() {
    if (document.hidden) return;
    fetch('/api/peer/v1/hb/translator', { credentials: 'same-origin' }).then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d || !d.ok) return;
      if (d.running && d.mode === 'auto' && !repliesEnabled()) { serverOn = true; setRepliesEnabled(true); }
      if (!d.running && d.mode === 'off' && serverOn === null) serverOn = false;
    }).catch(() => {});
  }
  setInterval(watchServer, 30000);
  setTimeout(watchServer, 1500);

  function refreshToggle() {
    if (!toggleBtn) return;
    const any = isEnabled() || repliesEnabled();
    if (serverOn !== null || any) syncServer(any);'''},
]

test = '''"""Practice 182: the translator runs only when wanted."""
import sqlite3
import subprocess
from pathlib import Path

from core import hb_translator as t

ROOT = Path(__file__).resolve().parents[1]


class Ctl:
    def __init__(self, active=False):
        self.active, self.calls = active, []

    def __call__(self, cmd, **kw):
        verb = cmd[2]
        self.calls.append(verb)
        if verb == 'start':
            self.active = True
        if verb == 'stop':
            self.active = False
        return subprocess.CompletedProcess(cmd, 0, stdout='active' if self.active else 'inactive', stderr='')


def test_button_starts_and_stops():
    c, ctl = sqlite3.connect(':memory:'), Ctl()
    assert t.switch(c, True, run=ctl) == (True, True) and t.mode(c)[0] == 'manual'
    assert t.switch(c, False, run=ctl) == (True, False) and 'disable' in ctl.calls and t.mode(c)[0] == 'off'


def test_asian_language_reply_starts_it_and_it_stops_when_quiet():
    c, ctl, said = sqlite3.connect(':memory:'), Ctl(), []
    assert t.on_reply(c, 'apex', 'The cap is annual.' * 3, run=ctl) is None
    zh = '最高缴款基数是年度上限，超出部分记入工资类型 XQE，不计入养老金缴款基数。'
    assert t.on_reply(c, 'qwen-cn', zh, run=ctl, say=said.append, now=1000) == 'started'
    assert ctl.active and 'Chinese' in said[0] and t.languages(c) == [{'model': 'qwen-cn', 'lang': 'zh'}]
    assert not t.idle_tick(c, now=1000 + 60, run=ctl)
    assert t.idle_tick(c, now=1000 + t.AUTO_IDLE_S + 1, run=ctl) and not ctl.active


def test_manual_start_is_not_stopped_by_idle():
    c, ctl = sqlite3.connect(':memory:'), Ctl()
    t.switch(c, True, run=ctl, now=1)
    assert not t.idle_tick(c, now=10 ** 6, run=ctl) and ctl.active


def test_language_detection():
    assert t.language_of('こんにちは、元気ですか') == 'ja' and t.language_of('안녕하세요 반갑습니다') == 'ko' and t.language_of('你好') == 'zh'


def test_page_defaults_off_and_syncs_the_service():
    js = (ROOT / 'frontend/static/js/hb-translate-bubble.js').read_text()
    assert "localStorage.getItem(KEY_ON) === '1'" in js and "localStorage.getItem(KEY_IN) === '1'" in js
    assert "/api/peer/v1/hb/translator" in js and 'syncServer(any)' in js
    assert '_translator_watch(from_agent, content)' in (ROOT / 'utils/db/chat.py').read_text()
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 20 Nov: \"the translator bot doesn't always have to run ... it should be associated with auto on for talking to "
                            "models that prefer Asian languages, the English ones are fine without it\". hb-translate.service ran from login with "
                            "Restart=always. New core/hb_translator: the chat's translate button starts/stops the service (user systemctl; off "
                            "also disables it at login); a model reply that is mostly Chinese/Japanese/Korean starts it ('auto'), remembers "
                            "the model's language and says so in main chat; an auto start stops 30 min after the last such reply. Route "
                            "/api/peer/v1/hb/translator; hb-translate-bubble.js defaults off and keeps the service in step."),
                 edits=edits, new_files={'core/hb_translator.py': module, 'tests/test_practice_182_translator_on_demand.py': test},
                 test={'tests': ['tests/test_practice_182_translator_on_demand.py', 'tests/test_practice_179_arrow_and_idle.py'], 'keyword': ''}, run=run)
print(out['verified'])
