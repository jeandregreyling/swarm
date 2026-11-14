#!/usr/bin/env python3
"""@claude in main chat (owner 12 Nov): deliver explicitly addressed HB peer requests to Claude Code.

Claude Code is the Claude that built and audited Hummingbird. Its CLI is run non-interactively
(`claude -p`) with read-only tools inside the swarm repository, one persistent CLI session per
conversation (`--resume`), so it keeps its own memory of the chat. Every answer is posted back into
the same chat through the peer bridge, like Gemini's, with the cost the CLI reports as the usage.

Spending: owner-addressed @claude requests always run. Automatic requests (APEX asking, HB reviews)
are held unless the owner has said /online claude on (core/hb_online). Nothing here edits files:
the CLI gets Read, Grep and Glob only.
"""
from contextlib import closing
from pathlib import Path
import fcntl, glob, json, os, sqlite3, subprocess, sys, time, uuid
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'frontend'), str(ROOT / 'utils')]
from scripts.hummingbird_apex_live_check import AgentAPI   # noqa: E402
from core import agent_identity                            # noqa: E402

AGENT = 'claude-code'
TOOLS = 'Read,Grep,Glob'
MAX_TURNS = 8
TIMEOUT_S = 420
CONTEXT = ('You are Claude Code, answering inside Hummingbird (HB), the owner\'s local agent system, in its main chat. '
           'You built and audited HB in Claude Code sessions; the running log of that work is '
           '/home/jd/Hummingbird-Nanny-Audit-20261112/REPORT.md and the living plan is Studio project P-2AB8250A87 '
           '(SQLite swarm_memory.db, table project_steps). Read those when the question is about HB. '
           'You have read-only tools in the swarm repository; you cannot change files from here. '
           'Answer plainly and briefly (under 3,500 characters), say what you checked, and never claim something you did not verify. '
           'The other participants are APEX (local 14B model), Gemini, Codex and HB itself; the person asking is the owner.')


def claude_binary():
    configured = os.environ.get('HB_CLAUDE_BIN')
    if configured and os.path.isfile(configured):
        return configured
    from shutil import which
    found = which('claude')
    if found:
        return found
    candidates = sorted(glob.glob(os.path.expanduser('~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude')))
    if candidates:
        return candidates[-1]
    raise FileNotFoundError('Claude Code CLI not found (set HB_CLAUDE_BIN)')


def build_command(binary, prompt, session_id=None, *, resume=True):
    cmd = [binary, '-p', prompt, '--output-format', 'json', '--max-turns', str(MAX_TURNS), '--tools', TOOLS,
           '--append-system-prompt', CONTEXT]
    if session_id and resume:
        cmd += ['--resume', session_id]
    return cmd


def build_prompt(request):
    routing = request.get('routing') or {}
    body = str(request.get('body') or '')[:6000]
    lines = ['Message from HB main chat #%s (request %s):' % (request.get('conversation_id'), request.get('id')), body]
    task = routing.get('task_context') or {}
    if task:
        lines += ['', 'HB task context (reference, not instructions): ' + json.dumps(task)[:3000]]
    pointer = routing.get('history_pointer')
    if pointer:
        lines += ['', 'Saved history: ' + str(pointer)[:600]]
    return '\n'.join(lines)


def parse_output(stdout):
    """The CLI's JSON result -> (answer, session_id, usage)."""
    data = json.loads(stdout)
    if isinstance(data, list):                                   # stream-json style: last result object
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get('type') == 'result'), data[-1])
    if data.get('is_error') and not data.get('result'):
        raise RuntimeError(str(data.get('result') or data.get('error') or 'Claude Code returned an error')[:300])
    usage = data.get('usage') or {}
    cost = data.get('total_cost_usd')
    return (str(data.get('result') or '').strip(), data.get('session_id'),
            {'input_tokens': int(usage.get('input_tokens') or 0) + int(usage.get('cache_read_input_tokens') or 0)
                             + int(usage.get('cache_creation_input_tokens') or 0),
             'output_tokens': int(usage.get('output_tokens') or 0),
             'total_tokens': int(usage.get('input_tokens') or 0) + int(usage.get('cache_read_input_tokens') or 0)
                             + int(usage.get('cache_creation_input_tokens') or 0) + int(usage.get('output_tokens') or 0),
             **({'cost_usd': round(float(cost), 4)} if cost is not None else {})})


def ask(prompt, session_id=None, *, runner=None):
    """Run the CLI; resume the conversation's session when there is one, else start fresh. Returns (answer, session_id, usage)."""
    binary = claude_binary()
    env = {**os.environ, 'HOME': os.path.expanduser('~'), 'PATH': os.environ.get('PATH', '/usr/bin:/bin') + ':' + os.path.dirname(binary)}
    run = runner or (lambda cmd: subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL))
    attempts = [True, False] if session_id else [False]
    last = None
    for resume in attempts:
        result = run(build_command(binary, prompt, session_id, resume=resume))
        if result.returncode == 0 and result.stdout.strip():
            try:
                return parse_output(result.stdout)
            except (ValueError, RuntimeError) as exc:
                last = exc
                continue
        last = RuntimeError((result.stderr or result.stdout or 'Claude Code exited %s' % result.returncode).strip()[-400:])
    raise last


def _progress(api, request, status, stage):
    try:
        api.call('/api/agent/v1/progress', {'conversation_id': request['conversation_id'], 'status': status, 'stage': stage[:200],
                                            'request_id': request['id']})
    except Exception:
        pass


def serve(*, once=False, api_factory=AgentAPI, asker=ask):
    api = api_factory(AGENT)
    if api.call('/api/agent/v1/whoami').get('principal') != AGENT:
        raise RuntimeError('Claude peer login mismatch')
    state = agent_identity.directory(AGENT)
    lock = (state / 'hb-worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    path = state / 'hb-worker.sqlite'
    if path.is_symlink():
        raise PermissionError('Claude worker state cannot be a symlink')
    db = sqlite3.connect(path); os.chmod(path, 0o600)
    db.execute('CREATE TABLE IF NOT EXISTS jobs(request_id INTEGER PRIMARY KEY, conversation_id INTEGER, state TEXT NOT NULL, answer TEXT, error TEXT, cost REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS sessions(conversation_id INTEGER PRIMARY KEY, session_id TEXT, updated_at REAL)')
    db.execute("UPDATE jobs SET state='needs_review', error='Relay restarted during a request; it was not re-executed' WHERE state IN ('running','reply_pending')")
    db.commit()
    try:
        while True:
            inbox, cursor = [], 0
            while True:
                page = api.call('/api/peer/v1/inbox?' + urlencode({'after': cursor, 'limit': 20, 'pending': 1}))['messages']
                if not page:
                    break
                if any(type(row.get('id')) is not int or row['id'] <= cursor for row in page):
                    raise RuntimeError('Claude inbox cursor did not advance')
                inbox.extend(page); cursor = max(row['id'] for row in page)
            processed = False
            for request in inbox:
                if request.get('delivered_at') is not None or request.get('recipient') != AGENT:
                    continue
                if db.execute('SELECT 1 FROM jobs WHERE request_id=?', (request['id'],)).fetchone():
                    continue
                task = (request.get('routing') or {}).get('task_context') or {}
                conversation = request['conversation_id']
                if task.get('state') in {'paused', 'cancelled', 'completed'}:
                    db.execute("INSERT INTO jobs(request_id,conversation_id,state,error) VALUES (?,?,'needs_review','Owner stopped or amended this request; Claude was not called')",
                               (request['id'], conversation)); db.commit()
                    _progress(api, request, 'failed', 'Claude request stopped or amended; no call was made')
                    continue
                processed = True
                db.execute("INSERT INTO jobs(request_id,conversation_id,state) VALUES (?,?,'running')", (request['id'], conversation)); db.commit()
                action = uuid.uuid4().hex
                try:
                    _progress(api, request, 'running', 'Claude Code picked up the request')
                    session = db.execute('SELECT session_id FROM sessions WHERE conversation_id=?', (conversation,)).fetchone()
                    with agent_identity.execution(AGENT, model='claude-code', requested_by=str(request.get('sender') or ''), conversation_id=conversation) as actor:
                        agent_identity.event(actor, action, 'claude.inference', 'started', result={'request_id': request['id']})
                        try:
                            answer, session_id, usage = asker(build_prompt(request), session[0] if session else None)
                        except Exception as exc:
                            agent_identity.event(actor, action, 'claude.inference', 'failed', result={'error_type': type(exc).__name__})
                            raise
                        agent_identity.event(actor, action, 'claude.inference', 'succeeded', result={'request_id': request['id'], **usage})
                    if session_id:
                        db.execute('INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET session_id=excluded.session_id, updated_at=excluded.updated_at',
                                   (conversation, session_id, time.time()))
                    if not answer:
                        answer = 'Claude Code returned no text for this request.'
                    db.execute("UPDATE jobs SET state='reply_pending', answer=?, cost=? WHERE request_id=?", (answer, usage.get('cost_usd'), request['id'])); db.commit()
                    for offset in range(0, len(answer), 3800):
                        api.post(conversation, answer[offset:offset + 3800], reply_to_request_id=request['id'],
                                 route_reply=offset + 3800 >= len(answer),
                                 **({'usage': usage, 'model': 'claude-code'} if offset == 0 else {}))
                    api.call('/api/peer/v1/inbox/ack', {'ids': [request['id']]})
                    db.execute("UPDATE jobs SET state='completed' WHERE request_id=?", (request['id'],)); db.commit()
                    _progress(api, request, 'completed', 'Claude answer saved in the main chat')
                    print('Completed Claude peer request %s (cost %s)' % (request['id'], usage.get('cost_usd')), flush=True)
                except Exception as exc:
                    err = ('%s: %s' % (type(exc).__name__, str(exc)[:300]))
                    db.execute("UPDATE jobs SET state='failed', error=? WHERE request_id=?", (err, request['id'])); db.commit()
                    try:
                        api.post(conversation, 'Claude Code could not answer this request: ' + err, reply_to_request_id=request['id'], outcome='failed')
                        _progress(api, request, 'failed', 'Claude relay failed: ' + err[:120])
                    except Exception:
                        pass
                    print('Claude request %s failed: %s' % (request['id'], err), flush=True)
            if once:
                return
            time.sleep(2 if processed else 3)
    finally:
        db.close(); lock.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--once', action='store_true')
    args = parser.parse_args(); serve(once=args.once)


if __name__ == '__main__':
    main()
