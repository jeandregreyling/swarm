"""Prepare Practice 192 (plan 20 Nov, items 1, 2, 7): Ghost reserve on the GPU; email from sevenpotato9; restarts wait for a running turn."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
SW = 'core/hb_apex_swap.py'
GG = 'core/hb_gpu_guard.py'
TM = 'core/hb_task_manager.py'
WF = 'core/hb_plan_workflow.py'
PC = 'core/peer_coordination.py'

ghost = '''

# Practice 192 (owner 20 Nov 2026: "I always want at least 2 GB in GPU for Ghost (me). Sometimes the system just hangs and I can't scroll ...
# there should be the housekeeping in place on HB to make sure that I can always talk and use the Linux system"). The desktop draws on the
# same RX 6800 as APEX; with APEX at 13.9 GB and the desktop at 1.2 GB only 0.9 GB was left, and the desktop's buffers were pushed out of
# the GPU (laggy mouse, stalled scrolling). APEX now loads with an 8-bit KV cache and a --fit margin of at least GHOST_MARGIN_MIB
# (core/hb_apex_swap.render), and ghost_tick() watches the free VRAM: three low readings in a row while APEX is idle raise the margin by
# MARGIN_STEP_MIB (up to MARGIN_MAX_MIB) and say so in main chat.
GHOST_GB = 2.0
GHOST_MARGIN_MIB = 3584
GHOST_GAP_S = 1800
GHOST_HINT_GAP_S = 6 * 3600


def vram_free_gb(root='/sys/class/drm'):
    from pathlib import Path
    for card in sorted(Path(root).glob('card*/device')):
        try:
            total = int((card / 'mem_info_vram_total').read_text())
            used = int((card / 'mem_info_vram_used').read_text())
        except (OSError, ValueError):
            continue
        return round((total - used) / 2 ** 30, 2)
    return None


def ghost_tick(conn, now=None, free=None, path=None, idle=_idle, reload=_reload, restart=_restart, answers=_answers, say=None):
    now = now or time.time()
    conn.execute('CREATE TABLE IF NOT EXISTS hb_ghost_reserve(at REAL, free_gb REAL, action TEXT)')
    free = vram_free_gb() if free is None else free
    if free is None:
        return None
    conn.execute('INSERT INTO hb_ghost_reserve VALUES (?,?,NULL)', (now, free))
    conn.execute('DELETE FROM hb_ghost_reserve WHERE at < ? AND action IS NULL', (now - 3600,))
    recent = [r[0] for r in conn.execute('SELECT free_gb FROM hb_ghost_reserve WHERE action IS NULL ORDER BY at DESC LIMIT 3')]
    if len(recent) < 3 or max(recent) >= GHOST_GB:
        return None
    acted = conn.execute("SELECT MAX(at) FROM hb_ghost_reserve WHERE action='raised'").fetchone()[0]
    if acted and now - acted < GHOST_GAP_S:
        return None
    path = path or dropin()
    try:
        text = path.read_text()
    except OSError:
        return None
    old = margin(text)
    if old is not None and old >= MARGIN_MAX_MIB:
        hinted = conn.execute("SELECT MAX(at) FROM hb_ghost_reserve WHERE action='hint'").fetchone()[0]
        if hinted and now - hinted < GHOST_HINT_GAP_S:
            return None
        conn.execute("INSERT INTO hb_ghost_reserve VALUES (?,?,'hint')", (now, free))
        line = (f"⚠ Only {free} GB of the GPU is free for your desktop (HB keeps {GHOST_GB} GB for you) and APEX already leaves the most "
                "room it can. Closing a GPU-heavy program (a browser with many tabs, a game) helps; a smaller APEX model would too.")
    else:
        if not idle():
            return None
        new = min((old or GHOST_MARGIN_MIB) + MARGIN_STEP_MIB, MARGIN_MAX_MIB)
        changed = with_margin(text, new)
        if changed is None:
            return None
        path.with_name(path.name + '.before-hb').write_text(text)
        path.write_text(changed)
        ok = bool(reload() and restart() and answers())
        conn.execute("INSERT INTO hb_ghost_reserve VALUES (?,?,'raised')", (now, free))
        line = (f"↺ HB gave your desktop more of the GPU: only {free} GB was free (HB keeps {GHOST_GB} GB for you), so APEX now leaves "
                f"{new} MiB free (was {old}). " + ('A test answer works.' if ok else 'It does not answer yet; the GPU guard keeps watching.'))
    if say:
        say(line)
    else:
        from core.hb_chat import owner_chat
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (owner_chat(conn), line))
    return line
'''

edits = [
    # 1. APEX's server: 8-bit KV cache for the 27B, and a margin floor for JD's desktop (render keeps spill raises above the floor)
    {'path': SW, 'old': "ARGS_BY_MODEL = {'swift-qwen3.8-27b': {'-b': '512', '-ub': '256'},",
     'new': "ARGS_BY_MODEL = {'swift-qwen3.8-27b': {'-b': '512', '-ub': '256', '-ctk': 'q8_0', '-ctv': 'q8_0'},   # Practice 192: 8-bit KV"},
    {'path': SW, 'old': "            new = new.replace('--no-webui', f'{flag} {value} --no-webui', 1)\n    return new\n",
     'new': "            new = new.replace('--no-webui', f'{flag} {value} --no-webui', 1)\n"
            "    for flag in ('-ctk', '-ctv'):   # Practice 192: KV cache types belong to the model that asked for them; a swap removes them\n"
            "        if flag not in server_args(cand['name']):\n"
            "            new = re.sub(r'\\s' + re.escape(flag) + r'\\s+\\S+', '', new, count=1)\n"
            "    try:   # Practice 192: never less than the Ghost reserve margin (JD's desktop keeps 2 GB+ of the GPU); higher spill margins stay\n"
            "        floor = guard.GHOST_MARGIN_MIB\n"
            "        current = guard.margin(new)\n"
            "        if current is not None and current < floor:\n"
            "            new = guard.with_margin(new, floor)\n"
            "    except Exception:\n"
            "        pass\n"
            "    return new\n"},
    {'path': GG, 'old': "\n\n# Practice 158 (owner 18 Nov 2026): at 13:36:56 the card reset", 'new': ghost + "\n\n# Practice 158 (owner 18 Nov 2026): at 13:36:56 the card reset"},
    {'path': PC, 'old': "                        try:  # Practice 182: a translator HB started for an Asian-language reply stops after 30 quiet minutes",
     'new': "                        try:  # Practice 192: JD's desktop keeps 2 GB+ of the GPU (Ghost reserve)\n"
            "                            from core.hb_gpu_guard import ghost_tick\n"
            "                            ghost_tick(conn)\n"
            "                            conn.commit()\n"
            "                        except Exception:\n"
            "                            LOG.exception('Ghost reserve check failed')\n"
            "                        try:  # Practice 182: a translator HB started for an Asian-language reply stops after 30 quiet minutes"},
    # older render tests pinned the previous margin and flag order - deliberate change (Practice 192), so the tests follow it
    {'path': 'tests/test_practice_152_apex_swap.py', 'old': "'--chat-template-file' not in new and '-fitt 1536' in new and '--jinja' in new",
     'new': "'--chat-template-file' not in new and '-fitt 3584' in new and '--jinja' in new   # Practice 192: Ghost reserve floor"},
    {'path': 'tests/test_practice_159_model_batches.py', 'old': "    assert '-b 512 -ub 256 --no-webui' in new and '-fitt 1536' in new and '-m /m/swift.gguf' in new\n    back = s.render(new, GPT)\n    assert '-b 2048 -ub 1024 --no-webui' in back and '-m /blobs/gptoss' in back",
     'new': "    assert '-b 512 -ub 256 -ctk q8_0 -ctv q8_0 --no-webui' in new and '-fitt 3584' in new and '-m /m/swift.gguf' in new   # Practice 192\n    back = s.render(new, GPT)\n    assert '-b 2048 -ub 1024 --no-webui' in back and '-m /blobs/gptoss' in back and '-ctk' not in back"},
    {'path': 'tests/test_practice_159_model_batches.py', 'old': "    new = s.render(plain, SWIFT)\n    assert '-b 512 -ub 256 --no-webui' in new",
     'new': "    new = s.render(plain, SWIFT)\n    assert '-b 512 -ub 256 -ctk q8_0 -ctv q8_0 --no-webui' in new   # Practice 192: 8-bit KV for the 27B"},
    # 2. Email: ninepotato7's login is refused by Google (app password needed); sevenpotato9 sends, with delivery records and retries
    {'path': TM, 'old': "            (send or __import__('utils.config', fromlist=['nine_email']).nine_email)(subject, body)",
     'new': "            (send or _send_owner_email)(subject, body)"},
    {'path': TM, 'old': "def email_owner(conn, task, text, send=None, now=None):",
     'new': '''def _send_owner_email(subject, body):
    """Practice 192: from HB's sevenpotato9 account (lib.email.email_handler.send_reply: delivery records, retries) to the owner address
    in config. ninepotato7's login is refused by Google until it has an app password."""
    from utils.config import GHOST_EMAIL
    from lib.email.email_handler import send_reply
    return send_reply(GHOST_EMAIL, subject, body, sender_name='Hummingbird')


def email_owner(conn, task, text, send=None, now=None):'''},
    # 7. HB's restart never lands in the middle of an APEX or Fred turn
    {'path': WF, 'old': "    except Exception:\n        pass\n    import os, subprocess, sys\n",
     'new': "    except Exception:\n        pass\n"
            "    if _has(conn, 'hb_peer_work') and conn.execute(\"SELECT 1 FROM hb_peer_work WHERE state='running'\").fetchone():\n"
            "        return None                                # Practice 192: a running APEX/Fred turn finishes first\n"
            "    import os, subprocess, sys\n"},
]

test = '''"""Practice 192: the Ghost reserve keeps 2 GB+ of the GPU for JD's desktop; email goes from sevenpotato9; restarts wait for turns."""
import sqlite3
import time

from core import hb_apex_swap as s
from core import hb_gpu_guard as g
from core import hb_plan_workflow as wf
from core import hb_task_manager as tm

DROPIN = """[Service]
ExecStart=
ExecStart=/x/llama-server -m /m/swift.gguf --device ROCm0 --fit on -fitt 2048 -fitc 16384 --jinja --flash-attn on -b 512 -ub 256 --no-webui
"""


def test_render_floors_the_margin_and_quantizes_the_27b_kv_cache():
    out = s.render(DROPIN, {'name': 'swift-qwen3.8-27b', 'path': '/m/swift.gguf', 'template': None})
    assert '-fitt 3584' in out and '-ctk q8_0' in out and '-ctv q8_0' in out
    higher = s.render(DROPIN.replace('-fitt 2048', '-fitt 4096'), {'name': 'swift-qwen3.8-27b', 'path': '/m/swift.gguf', 'template': None})
    assert '-fitt 4096' in higher
    other = s.render(DROPIN, {'name': 'gpt-oss:20b', 'path': '/m/oss.gguf', 'template': None})
    assert '-ctk' not in other and '-fitt 3584' in other


def _calls():
    seen = []
    return seen, (lambda: seen.append('reload') or True), (lambda: seen.append('restart') or True), (lambda: True)


def test_three_low_readings_raise_the_margin_when_apex_is_idle(tmp_path):
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN.replace('2048', '3584'))
    c, said = sqlite3.connect(':memory:'), []
    seen, reload, restart, answers = _calls()
    for i, free in enumerate((1.2, 1.1, 1.0)):
        out = g.ghost_tick(c, now=1000 + i * 60, free=free, path=p, idle=lambda: True, reload=reload, restart=restart, answers=answers, say=said.append)
    assert '-fitt 4096' in p.read_text() and seen == ['reload', 'restart'] and 'more of the GPU' in said[0]
    assert g.ghost_tick(c, now=1300, free=0.9, path=p, idle=lambda: True, reload=reload, restart=restart, answers=answers, say=said.append) is None


def test_no_change_while_apex_works_or_when_there_is_room(tmp_path):
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN)
    c = sqlite3.connect(':memory:')
    for i in range(3):
        assert g.ghost_tick(c, now=1000 + i * 60, free=1.0, path=p, idle=lambda: False, say=lambda m: None) is None
    assert '-fitt 2048' in p.read_text()
    c2 = sqlite3.connect(':memory:')
    for i, free in enumerate((1.0, 2.5, 1.0)):
        assert g.ghost_tick(c2, now=1000 + i * 60, free=free, path=p, idle=lambda: True, say=lambda m: None) is None


def test_at_the_maximum_margin_hb_only_hints_once(tmp_path):
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN.replace('2048', str(g.MARGIN_MAX_MIB)))
    c, said = sqlite3.connect(':memory:'), []
    for i in range(5):
        g.ghost_tick(c, now=1000 + i * 60, free=1.0, path=p, idle=lambda: True, say=said.append)
    assert len(said) == 1 and 'Closing a GPU-heavy program' in said[0]


def test_owner_email_goes_through_sevenpotato9(monkeypatch):
    sent = []
    import lib.email.email_handler as eh
    monkeypatch.setattr(eh, 'send_reply', lambda to, subject, body, **kw: sent.append((subject, kw.get('sender_name'))) or True)
    tm._send_owner_email('HB needs you: x', 'body')
    assert sent == [('HB needs you: x', 'Hummingbird')]


def test_restart_waits_for_a_running_turn():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_restart_queue(task_id TEXT PRIMARY KEY, scope TEXT, reason TEXT, at REAL)')
    c.execute("INSERT INTO hb_restart_queue VALUES ('T-1','ui','x',0)")
    c.execute('CREATE TABLE hb_peer_work(request_id INTEGER, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    c.execute("INSERT INTO hb_peer_work VALUES (1,'apex','running','turn',0)")
    launched = []
    assert wf.restart_tick(c, now=time.time(), run=launched.append) is None and launched == []
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1500)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("Plan 20 Nov items 1, 2, 7 (owner: \"I always want at least 2 GB in GPU for Ghost (me)\"; \"send me an email\"). "
                            "APEX 13.9 GB + desktop 1.2 GB left 0.9 GB of the RX 6800: the desktop's buffers were evicted (laggy mouse). "
                            "hb_apex_swap.render: 8-bit KV cache for the 27B and a --fit margin floor of 3.5 GB (spill raises above it stay); "
                            "HB applies it with its own settings reload while APEX is idle. hb_gpu_guard.ghost_tick: three readings below 2 GB "
                            "free raise the margin by 512 MiB (max 4 GB) while APEX is idle, or hint once per 6 h at the max. Email to JD "
                            "goes from sevenpotato9 (ninepotato7's login is refused by Google until it has an app password). restart_tick "
                            "waits while an APEX/Fred turn runs (restarts mid-turn left 'Worker restarted during a turn' items)."),
                 edits=edits, new_files={'tests/test_practice_192_ghost_reserve.py': test},
                 test={'tests': ['tests/test_practice_192_ghost_reserve.py', 'tests/test_practice_191_email_and_fred.py', 'tests/test_practice_152_apex_swap.py',
                                 'tests/test_practice_159_model_batches.py', 'tests/test_practice_161_settings_reload.py', 'tests/test_practice_173_apex_backend.py',
                                 'tests/test_practice_133_gpu_spill.py', 'tests/test_hb_plan_workflow.py'], 'keyword': ''}, run=run)
print(out['verified'])
