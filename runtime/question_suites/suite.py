"""Run a broad question suite through APEX/HB (same turn as main chat, via ask.py) and record HB's review, tools, checks, answer, time."""
import json, re, subprocess, sys, time, urllib.request
sys.path.insert(0, '/home/jd/swarm')
A = '/tmp/claude-1000/-home-jd/12a48d48-c161-4f13-ab48-18ba6f3e4cde/scratchpad/ask'
PY = '/home/jd/swarm/.venv/bin/python'

QUESTIONS = [
    ('sap-kc', 'What do our SAP notes say about the changes to STP Phase 2 reporting for Payday Super?'),
    ('sap-kc', 'What is wage type /XQE and when does payroll create it?'),
    ('sap-kc', 'What are the tax thresholds and limits for the 2025-2026 tax year in Australian payroll according to our notes?'),
    ('sap-web', 'What is a personnel calculation rule (PCR) in SAP payroll and how is it used in a schema?'),
    ('sap-web', 'How does retroactive accounting work in SAP payroll, and what sets the earliest retro date?'),
    ('sap-web', 'tell be how the wage types /001 and /002 work? How to they get their values? What are they for?'),
    ('hb', 'How does HB decide which model plays APEX for a question?'),
    ('hb', 'What does the HB GPU guard do when the graphics card resets?'),
    ('code', 'In this repo, where is the SAP note meaning (vector) index built and how often is it refreshed?'),
    ('code', 'Write a Python function that merges overlapping intervals given as [start, end] pairs.'),
    ('code', 'What is the difference between a list and a tuple in Python, and when should I use each?'),
    ('chat', 'Good afternoon APEX, what should we work on next?'),
]


def answers():
    try:
        req = urllib.request.Request('http://127.0.0.1:8080/completion', json.dumps({'prompt': 'Say OK.', 'n_predict': 4}).encode(),
                                     {'Content-Type': 'application/json'})
        return bool(json.loads(urllib.request.urlopen(req, timeout=60).read()).get('content'))
    except Exception:
        return False


def review(q):
    code = ("import sys,json; sys.path.insert(0,'/home/jd/swarm'); from core import hb_apex_swap as s; "
            f"r=s.review({q!r}); p=s.manual_pick({q!r}); print(json.dumps({{'review': r, 'manual': p, 'playing': s.playing()}}))")
    out = subprocess.run([PY, '-c', code], capture_output=True, text=True, timeout=120)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        return {'error': out.stderr[-300:]}


ONLY = {3, 6, 7, 8}
results = []
for i, (cat, q) in enumerate(QUESTIONS, 1):
    if i not in ONLY:
        continue
    rec = {'n': i, 'category': cat, 'question': q, 'review': review(q)}
    for attempt in (1, 2):
        start = time.time()
        p = subprocess.run([PY, f'{A}/ask.py', q], capture_output=True, text=True, timeout=960)
        text = p.stdout + p.stderr
        rec.update(seconds=round(time.time() - start), attempt=attempt)
        if 'ErrorDeviceLost' in text or 'local runtime error' in text:
            rec['error'] = 'card reset / runtime error'
            t0 = time.time()
            while time.time() - t0 < 420 and not answers():
                time.sleep(20)
            continue
        rec.pop('error', None)
        break
    rec['tools'] = re.findall(r'^TOOL (\w+) (.*?) (succeeded|failed|denied)$', text, re.M)
    rec['checks'] = re.findall(r'BACKEND ([A-Z]+ (?:CHECK|LIMIT))', text)
    rec['answer'] = text.split('=====ANSWER=====', 1)[1].strip() if '=====ANSWER=====' in text else text[-1500:]
    results.append(rec)
    json.dump(results, open(f'{A}/suite_results_part3.json', 'w'), indent=1)
    print(f"[{i}/{len(QUESTIONS)}] {cat} {rec['seconds']}s tools={len(rec['tools'])} checks={rec['checks']} {'ERROR' if rec.get('error') else 'ok'}", flush=True)
print('SUITE DONE')
