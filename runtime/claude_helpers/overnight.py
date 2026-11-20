"""Overnight 19-20 Nov 2026 (owner: "line everything up to run overnight, I'll leave it till 8am").
1. Wait until APEX has applied Practice 173 (commit in git), up to 5 h.
2. HB's own backend test: hb_apex_swap.bench('rocm') - waits for APEX idle, measures Vulkan, switches to ROCm, measures, keeps the faster.
3. The full 12-question suite on whichever backend APEX ends up on; results to runtime/question_suites/2026-11-19_overnight.json.
Every step is posted to main chat. Nothing here uses sudo."""
import json, re, subprocess, sys, time
sys.path.insert(0, '/home/jd/swarm')
from contextlib import closing
from utils.db._connection import get_connection
from core.hb_model_bench import _post

SW = '/home/jd/swarm'
PY = SW + '/.venv/bin/python'
OUT = SW + '/runtime/question_suites/2026-11-19_overnight.json'


def log(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)


def say(msg):
    log('CHAT ' + msg.replace('\n', ' | ')[:300])
    try:
        with closing(get_connection()) as c:
            _post(c, msg)
            c.commit()
    except Exception as e:
        log(f'post failed: {e}')


def applied():
    out = subprocess.run(['git', 'log', '--oneline', '-40'], cwd=SW, capture_output=True, text=True).stdout
    return 'Practice 173' in out


say('🌙 Overnight run (set up by Claude Code): when APEX has applied Practice 173, HB tests ROCm against Vulkan on the 27B and keeps the '
    'faster one, then runs the 12-question suite. Results here by morning.')
t0 = time.time()
while not applied() and time.time() - t0 < 5 * 3600:
    time.sleep(120)
if applied():
    time.sleep(60)
    code = ("import sys; sys.path.insert(0,'/home/jd/swarm')\n"
            "from contextlib import closing\nfrom utils.db._connection import get_connection\nfrom core.hb_model_bench import _post\n"
            "from core import hb_apex_swap as s\n"
            "def say(m):\n    print('CHAT', m, flush=True)\n    c = get_connection()\n    _post(c, m); c.commit(); c.close()\n"
            "ok, rep = s.bench('rocm', say)\nsay('Backend test: ' + rep)\n")
    r = subprocess.run([PY, '-c', code], cwd=SW, capture_output=True, text=True, timeout=3 * 3600)
    log('bench rc=%s %s %s' % (r.returncode, r.stdout[-500:], r.stderr[-1500:]))
    if r.returncode:
        say('Backend test did not run (error in the test itself) - APEX stays as it was. Claude Code looks at it in the morning.')
else:
    say('APEX had not applied Practice 173 after 5 hours, so there was no ROCm test tonight; the suite runs on Vulkan.')

sys.path.insert(0, SW + '/runtime/question_suites')
QUESTIONS = json.loads(subprocess.run([PY, '-c', "import sys,json,runpy; sys.argv=['x']; src=open('/home/jd/swarm/runtime/question_suites/suite.py').read(); "
                                       "ns={}; exec(src.split('def answers')[0], ns); print(json.dumps(ns['QUESTIONS']))"],
                                      capture_output=True, text=True).stdout)


def answers():
    import urllib.request
    try:
        req = urllib.request.Request('http://127.0.0.1:8080/completion', json.dumps({'prompt': 'Say OK.', 'n_predict': 4}).encode(),
                                     {'Content-Type': 'application/json'})
        return bool(json.loads(urllib.request.urlopen(req, timeout=60).read()).get('content'))
    except Exception:
        return False


backend = subprocess.run([PY, '-c', "import sys; sys.path.insert(0,'/home/jd/swarm'); from core import hb_apex_swap as s; print(s.backend())"],
                         cwd=SW, capture_output=True, text=True).stdout.strip()
say(f'Suite: 12 questions (SAP, HB, code, chat) on APEX with the {backend} backend - about 1-2 hours.')
results = []
for i, (cat, q) in enumerate(QUESTIONS, 1):
    rec = {'n': i, 'category': cat, 'question': q, 'backend': backend}
    for attempt in (1, 2):
        start = time.time()
        try:
            p = subprocess.run([PY, SW + '/runtime/question_suites/ask.py', q], cwd=SW, capture_output=True, text=True, timeout=960)
            text = p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            text = 'TIMEOUT'
        head = text.split('=====ANSWER=====', 1)[0]
        rec.update(seconds=round(time.time() - start), attempt=attempt)
        if text == 'TIMEOUT' or 'ErrorDeviceLost' in head or 'local runtime error' in head:
            rec['error'] = 'timeout' if text == 'TIMEOUT' else 'card reset / runtime error'
            w = time.time()
            while time.time() - w < 420 and not answers():
                time.sleep(20)
            continue
        rec.pop('error', None)
        break
    rec['tools'] = re.findall(r'^TOOL (\w+) (.*?) (succeeded|failed|denied)$', text, re.M)
    rec['checks'] = re.findall(r'BACKEND ([A-Z]+ (?:CHECK|LIMIT))', text)
    rec['answer'] = text.split('=====ANSWER=====', 1)[1].strip() if '=====ANSWER=====' in text else text[-1500:]
    results.append(rec)
    json.dump(results, open(OUT, 'w'), indent=1)
    log(f"[{i}/12] {cat} {rec['seconds']}s tools={len(rec['tools'])} checks={rec['checks']} {rec.get('error', 'ok')}")
lines = [f"| {r['n']} | {r['category']} | {r['seconds']} s | {len(r['tools'])} | {r.get('error', 'answered')} |" for r in results]
say(f'Suite done on {backend}: ' + f"{sum(1 for r in results if not r.get('error'))}/12 answered without errors.\n"
    '| # | kind | time | tools | result |\n|---|---|---|---|---|\n' + '\n'.join(lines)
    + '\nAnswers saved in runtime/question_suites/2026-11-19_overnight.json - Claude Code checks them for correctness in the morning.')
log('OVERNIGHT DONE')
