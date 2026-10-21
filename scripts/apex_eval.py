"""Scored edit eval for the worker seat, judged only from the files on disk.

The agent's reply is never evidence. Each task edits a practice copy of the wrapper's
first 200 lines through the same chat route the browser uses, and the result is the
diff between that copy and the lines the task should have produced.

    .venv/bin/python3 scripts/apex_eval.py            # all tasks
    .venv/bin/python3 scripts/apex_eval.py 1 4        # chosen tasks
"""
import json
import os
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SOURCE = os.path.join(ROOT, 'frontend', 'templates', 'terminal_base.html')
SANDPIT = os.path.join(ROOT, 'sandpits', 'apex')
BASE_URL = os.environ.get('SWARM_EVAL_URL', 'http://localhost:5050')
OLLAMA_URL = os.environ.get('SWARM_OLLAMA_URL', 'http://localhost:11434')
COPY_LINES = 200
JOB_TIMEOUT_SECONDS = 300


def _insert_after(lines, anchor, new):
    out = []
    for line in lines:
        out.append(line)
        if line.strip() == anchor:
            out.append(new)
    return out


def _insert_before(lines, anchor, new):
    out = []
    for line in lines:
        if line.strip() == anchor:
            out.append(new)
        out.append(line)
    return out


TASKS = [
    {
        'id': 1,
        'name': 'insert before </head>',
        'prompt': 'add the one line <!-- eval one --> immediately BEFORE the </head> line',
        'expected': lambda lines: _insert_before(lines, '</head>', '<!-- eval one -->'),
    },
    {
        'id': 2,
        'name': 'insert after <body>',
        'prompt': 'add the one line <!-- eval two --> immediately AFTER the <body> line',
        'expected': lambda lines: _insert_after(lines, '<body>', '<!-- eval two -->'),
    },
    {
        'id': 3,
        'name': 'extend the <html> tag',
        'prompt': 'change the line <html lang="en"> so it reads <html lang="en" data-eval="3">',
        'expected': lambda lines: [
            '<html lang="en" data-eval="3">' if line.strip() == '<html lang="en">' else line for line in lines
        ],
    },
    {
        'id': 4,
        'name': 'change text inside a line',
        'prompt': 'in the viewport meta line change initial-scale=1.0 to initial-scale=1',
        'expected': lambda lines: [line.replace('initial-scale=1.0', 'initial-scale=1') for line in lines],
    },
    {
        'id': 5,
        'name': 'append at the end',
        'prompt': 'add the one line <!-- eval five --> at the very end of the file',
        'expected': lambda lines: lines + ['<!-- eval five -->'],
    },
    {
        'id': 6,
        'name': 'missing anchor must change nothing',
        'prompt': 'add the one line <!-- eval six --> immediately after the line <nav id="no-such-nav">. '
                  'If that line does not exist, change nothing and say so',
        'expected': lambda lines: list(lines),
    },
]


def check_edit(original, expected, actual):
    """Return (passed, detail) comparing whole files, ignoring only blank lines at the very end."""
    def trimmed(lines):
        lines = list(lines)
        while lines and not lines[-1].strip():
            lines.pop()
        return lines

    want, got = trimmed(expected), trimmed(actual)
    if want == got:
        return True, 'file matches the expected result exactly'
    for index, (w, g) in enumerate(zip(want, got), start=1):
        if w != g:
            return False, f'first difference at line {index}: wanted {w[:70]!r}, found {g[:70]!r}'
    return False, f'length differs: wanted {len(want)} lines, found {len(got)} (original had {len(original)})'


def _get_json(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'),
                                 headers={'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def preconditions(worker_agent, worker_model):
    """List what is not true yet. An empty list means the eval may run."""
    problems = []
    try:
        with urllib.request.urlopen(f'{BASE_URL}/_health', timeout=10) as resp:
            if resp.status != 200:
                problems.append(f'{BASE_URL}/_health returned {resp.status}')
    except Exception as exc:
        problems.append(f'PROD is not answering at {BASE_URL}: {exc}')
    try:
        loaded = [m['name'] for m in _get_json(f'{OLLAMA_URL}/api/ps').get('models', [])]
        if worker_model not in loaded:
            problems.append(f'{worker_model} is not loaded in Ollama (loaded: {loaded or "nothing"})')
    except Exception as exc:
        problems.append(f'Ollama is not answering at {OLLAMA_URL}: {exc}')
    try:
        import sqlite3
        db = sqlite3.connect(f'file:{os.path.join(ROOT, "swarm_memory.db")}?mode=ro', uri=True, timeout=10)
        try:
            busy = db.execute(
                "select count(*) from chat_jobs where status not in "
                "('completed','done','failed','cancelled','error')").fetchone()[0]
        finally:
            db.close()
        if busy:
            problems.append(f'{busy} chat job(s) are still running')
    except Exception as exc:
        problems.append(f'could not read chat jobs: {exc}')
    if not os.path.isfile(SOURCE):
        problems.append(f'wrapper source missing: {SOURCE}')
    if not worker_agent:
        problems.append('no worker agent is configured')
    return problems


def run_chat(agent, message):
    sent = _post_json(f'{BASE_URL}/api/chat', {'agent': agent, 'message': message, 'new_thread': True,
                                           'auto_relay': False, 'history_mode': 'none'})
    conversation_id = sent.get('conversation_id')
    if not sent.get('ok', True):
        return {'status': 'failed', 'error': sent.get('response') or sent.get('error'), 'conversation_id': conversation_id}
    immediate = (sent.get('responses') or [sent])[0]
    if not sent.get('pending_jobs') and not immediate.get('pending') and immediate.get('response'):
        return {**immediate, 'status': 'completed', 'conversation_id': conversation_id}
    deadline = time.time() + JOB_TIMEOUT_SECONDS
    job = {}
    while time.time() < deadline:
        time.sleep(3)
        jobs = _get_json(f'{BASE_URL}/api/chat/jobs/status?conversation_id={conversation_id}').get('jobs') or []
        if jobs:
            job = jobs[-1]
            if job.get('status') != 'running':
                return job
    job['status'] = job.get('status') or 'timeout'
    return job


def run_local_team(agent_names=None):
    """Live inference and model-selected writes; never synthesize the proof files."""
    import uuid
    from pathlib import Path
    from core import model_runtime_gateway as gateway
    from core.seven_llm import llama_server
    from ops.seed_agent_permissions import LOCAL_NOTE_AGENTS

    run_id = uuid.uuid4().hex[:10]
    roster = _get_json(f'{BASE_URL}/api/agents/config')
    if isinstance(roster, dict):
        roster = roster.get('agents', [])
    agents = [row for row in roster if row.get('enabled') and row.get('tier') == 'local'
              and (not agent_names or row['name'] in agent_names)]
    results = []
    report_path = Path(ROOT) / 'runtime' / 'local_model_acceptance.json'
    try:
        for row in agents:
            name, model = row['name'], row['model']
            marker = f'CONNECTED_{name}_{run_id}'
            result = {'agent': name, 'configured_model': model, 'connection_pass': False,
                      'write_pass': False, 'observer': name == 'seven'}
            started = time.time()
            try:
                response = gateway.chat(model, [{'role': 'system', 'content': 'Follow the user\'s harmless text-copy instruction exactly.'},
                                                {'role': 'user', 'content': f'Copy this text exactly, without quotes: {marker}'}],
                                        options={'num_predict': 64, 'num_ctx': 4096},
                                        absolute_timeout_s=150, idle_timeout_s=150)
                result.update(connection_pass=bool(response.ok and marker in response.content and response.tokens > 0),
                              connection_reply=response.content[:250], connection_error=response.error,
                              connection_tokens=response.tokens)
                filename = f'model_write_{run_id}.txt'
                rel = f'sandpits/{name}/{filename}'
                target = Path(ROOT) / rel
                assert not target.exists(), 'The model proof must start with an absent file'
                content = f'{name} model write proof {run_id}'
                if name != 'seven':
                    message = (f'Write this audit note in your own sandpit using the file_write skill. '
                               f'Use this exact command on its own line: SKILL file_write {name}/{filename} {content}\n'
                               f'After it returns, use SKILL file_read {name}/{filename} and report the result.')
                elif name == 'seven':
                    message = f'State your role. Are you allowed to create {rel}? Do not use tools or mutate files.'
                else:
                    message = (f'Run the fs_write skill now to create {rel}. Emit its SKILL line followed by one fenced block. '
                               f'The block must contain exactly the text {content} without quotation marks, extra delimiters or extra lines.\n'
                               f'After the backend returns, run fs_readonly lines {rel} 1 1. '
                               'Use no other tools. Do not claim success without the actual backend result.')
                job = run_chat(name, message)
                actual = target.read_text() if target.exists() else None
                result.update(path=rel, expected_content=content, actual_content=actual,
                              job_status=job.get('status'), reply=str(job.get('response') or '')[:2500],
                              error=str(job.get('error') or ''))
                result['write_pass'] = (not target.exists() if name == 'seven' else
                                        actual is not None and actual.rstrip('\n') == content)
            except Exception as exc:
                result['error'] = str(exc)
            result['seconds'] = round(time.time() - started, 1)
            result['passed'] = result['connection_pass'] and result['write_pass']
            results.append(result)
            report_path.write_text(json.dumps({'run_id': run_id, 'results': results,
                                               'passed': all(item['passed'] for item in results)}, indent=2))
            print(f"{name}: connection={'PASS' if result['connection_pass'] else 'FAIL'} "
                  f"{'observer' if name == 'seven' else 'model-write'}={'PASS' if result['write_pass'] else 'FAIL'} "
                  f"({result['seconds']}s) {result.get('error', '')[:180]}", flush=True)
    finally:
        for server in llama_server.snapshot():
            llama_server.stop(server['model'])
    print(f'Results: {report_path}', flush=True)
    return 0 if results and all(item['passed'] for item in results) else 1


def run_task(task, agent, original):
    rel = f'sandpits/apex/eval_{task["id"]}.html'
    path = os.path.join(ROOT, rel)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(original) + '\n')
    message = f'Task (practice copy only): in {rel} {task["prompt"]}. Change nothing else. Prove it with a read-back.'
    started = time.time()
    try:
        job = run_chat(agent, message)
    except Exception as exc:
        job = {'status': f'chat error: {exc}', 'response': ''}
    seconds = round(time.time() - started)
    with open(path, encoding='utf-8') as handle:
        actual = handle.read().splitlines()
    passed, detail = check_edit(original, task['expected'](original), actual)
    return {
        'id': task['id'], 'name': task['name'], 'passed': passed, 'detail': detail,
        'job_status': job.get('status'), 'seconds': seconds,
        'reply_head': str(job.get('response') or '').strip().replace('\n', ' ')[:110],
        'path': path,
    }


def main(argv):
    from utils.worker import WORKER_AGENT, WORKER_MODEL

    if '--local-team' in argv:
        return run_local_team([arg for arg in argv if not arg.startswith('--')])

    problems = preconditions(WORKER_AGENT, WORKER_MODEL)
    if problems:
        print('Conditions are not met, so nothing was run:')
        for problem in problems:
            print(f'  - {problem}')
        return 2

    wanted = {int(a) for a in argv if a.isdigit()}
    tasks = [t for t in TASKS if not wanted or t['id'] in wanted]
    with open(SOURCE, encoding='utf-8') as handle:
        original = handle.read().splitlines()[:COPY_LINES]
    os.makedirs(SANDPIT, exist_ok=True)

    print(f'{WORKER_AGENT} on {WORKER_MODEL}: {len(tasks)} task(s), judged from the files only\n')
    results = []
    for task in tasks:
        result = run_task(task, WORKER_AGENT, original)
        results.append(result)
        mark = 'PASS' if result['passed'] else 'FAIL'
        print(f'[{mark}] {result["id"]}. {result["name"]} ({result["seconds"]}s, job {result["job_status"]})')
        print(f'       file:  {result["detail"]}')
        print(f'       reply: {result["reply_head"]}')
        try:
            os.remove(result['path'])
        except OSError:
            pass

    passed = sum(1 for r in results if r['passed'])
    print(f'\n{passed}/{len(results)} passed')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
