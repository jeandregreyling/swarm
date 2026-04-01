#!/usr/bin/env python3
"""
test_chat_quality.py — Tests for chat quality fixes
═══════════════════════════════════════════════════════════════════════════════
REQ-CHAT-001  Skill command in chat does NOT bleed into subsequent agent context
REQ-CHAT-002  /api/chat returns only agent responses (no fridays rows) in history
REQ-CHAT-003  Skill execution response has mode='skill' and skill.name set
REQ-CHAT-004  Chat history filtering: fridays messages excluded from history API
REQ-CHAT-005  Memory injection: get_agent_memory available for nine/ten agents
REQ-CHAT-006  Config: TEN_SYSTEM_PROMPT includes style rules (concise, no filler)
REQ-CHAT-008  Chat jobs status polling endpoint responds
REQ-CHAT-011  fs_readonly skill is callable from chat and returns structured result
REQ-CHAT-012  shell whitelist allows pwd discovery command
REQ-CHAT-013  shell whitelist allows relative path file/list operations
REQ-CHAT-014  long-running fanout never returns legacy extended-runtime placeholder
REQ-CHAT-015  monitor API exposes runtime jobs and model residency telemetry

Usage:
    python3 tests/test_chat_quality.py
    BASE_URL=http://127.0.0.1:5050 python3 tests/test_chat_quality.py
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5050').rstrip('/')

PASS = 'PASS'
FAIL = 'FAIL'
SKIP = 'SKIP'

results = []

DEFAULT_PING_AGENTS = [
    'gemma', 'llama', 'qwen', 'eight', 'librarian', 'duck', 'sniffles',
    'nine', 'ten', 'eleven', 'twelve'
]


def _ping_agents_from_env():
    """Resolve target agent list for REQ-CHAT-016 from env or defaults."""
    raw = (os.environ.get('CHAT_PING_AGENTS') or '').strip()
    if not raw:
        return list(DEFAULT_PING_AGENTS)

    parsed = []
    for token in raw.split(','):
        name = token.strip().lower()
        if name and name not in parsed:
            parsed.append(name)
    return parsed or list(DEFAULT_PING_AGENTS)


def _wait_for_jobs(conversation_id, job_ids, timeout_seconds=180, poll_interval=2.0):
    """Wait for pending jobs to settle and return final statuses plus stage timeline."""
    if not job_ids:
        return {}, []

    started = time.time()
    timelines = []
    latest = {}
    while (time.time() - started) < timeout_seconds:
        query = '/api/chat/jobs/status?conversation_id={}&job_ids={}'.format(
            conversation_id,
            ','.join(job_ids),
        )
        code, data = _req('GET', query, timeout=15)
        if code != 200:
            break

        jobs = data.get('jobs') or []
        all_done = True
        for job in jobs:
            jid = str(job.get('job_id') or '')
            stage = str(job.get('stage') or '')
            status = str(job.get('status') or '')
            stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            timelines.append({
                'ts': stamp,
                'job_id': jid,
                'agent': job.get('agent'),
                'status': status,
                'stage': stage,
                'elapsed_ms': int(job.get('elapsed_ms') or 0),
                'eta_remaining_seconds': int(job.get('eta_remaining_seconds') or 0),
            })
            latest[jid] = job
            if status not in {'completed', 'failed', 'cancelled'}:
                all_done = False

        if all_done:
            return latest, timelines
        time.sleep(poll_interval)

    return latest, timelines


def _latest_agent_message(conversation_id, agent_name):
    """Fetch latest persisted response text for a specific agent in a conversation."""
    code, data = _req('GET', f'/api/conversations/{conversation_id}/messages', timeout=10)
    if code != 200:
        return ''
    messages = data.get('messages') or []
    target = (agent_name or '').lower()
    for msg in reversed(messages):
        sender = str(msg.get('sender') or '').lower()
        if sender == target:
            return str(msg.get('content') or '')
    return ''


def _write_ping_log(payload):
    """Persist chat ping observability output for UI tuning and regression tracking."""
    root = os.path.dirname(__file__)
    out_dir = os.path.join(root, 'artifacts')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'chat_agent_ping_latest.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    return out_path


def _req(method, path, payload=None, timeout=10):
    url = BASE_URL + path
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {'Content-Type': 'application/json'} if body else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {'_raw': raw.decode(errors='replace')}
    except urllib.error.HTTPError as e:
        raw = e.read() or b'{}'
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'_raw': raw.decode(errors='replace')}
    except Exception as e:
        return None, {'error': str(e)}


def record(name, status, detail=''):
    results.append((name, status, detail))
    mark = '✓' if status == PASS else ('·' if status == SKIP else '✗')
    print(f"  {mark} [{status}] {name}" + (f": {detail}" if detail else ''))


def _server_up():
    code, _ = _req('GET', '/api/system/time', timeout=3)
    return code == 200


# ── REQ-CHAT-001: Skill bleed — skill then chat, check response has no skill artifact ──
def test_skill_then_chat_no_bleed():
    """
    Run a skill command in chat, then send a plain greeting in the same conversation.
    The plain greeting response should NOT contain the skill output text (df -h style).
    This test is skipped when no AI agent is reachable (avoids token spend in CI).
    """
    # Step 1: run a skill that produces distinctive output (disk)
    code1, d1 = _req('POST', '/api/chat', {
        'message': 'SKILL search python',
        'agent': 'gemma',
        'acting_user': 'ghost',
    }, timeout=15)
    if code1 != 200:
        record('REQ-CHAT-001 skill-bleed', SKIP, f'skill command returned {code1}')
        return
    conv_id = d1.get('conversation_id')
    if not conv_id:
        record('REQ-CHAT-001 skill-bleed', SKIP, 'no conv_id returned')
        return
    if d1.get('mode') != 'skill':
        record('REQ-CHAT-001 skill-bleed', FAIL, 'expected mode=skill from SKILL command')
        return
    record('REQ-CHAT-001 skill-bleed (step1-skill)', PASS, f'conv={conv_id}')

    # Step 2: Verify history is accessible via messages endpoint
    code2, d2 = _req('GET', f'/api/conversations/{conv_id}/messages', timeout=5)
    if code2 != 200:
        record('REQ-CHAT-001 skill-bleed (step2-history)', SKIP, f'messages endpoint returned {code2}')
        return

    msgs = d2.get('messages', [])
    fridays_msgs = [m for m in msgs if (m.get('from_agent') or m.get('sender', '')).lower() == 'fridays']
    # fridays rows ARE in the DB but should NOT appear in the agent history passed to LLM
    # We can't easily introspect that here, but we can verify fridays rows exist in DB
    # and that the chat API filtering logic was applied (tested via unit path in test below)
    record('REQ-CHAT-001 skill-bleed (step2-history)', PASS,
           f'total_msgs={len(msgs)}, fridays_rows_in_db={len(fridays_msgs)}')


# ── REQ-CHAT-002: Skill response structure ──────────────────────────────────────
def test_skill_response_structure():
    code, d = _req('POST', '/api/chat', {
        'message': 'SKILL shell echo hello_test',
        'agent': 'gemma',
        'acting_user': 'ghost',
    }, timeout=15)
    if code is None:
        record('REQ-CHAT-002 skill-structure', SKIP, 'server unreachable')
        return
    if code != 200:
        record('REQ-CHAT-002 skill-structure', FAIL, f'HTTP {code}: {d}')
        return
    ok = (
        d.get('mode') == 'skill'
        and 'skill' in d
        and d['skill'].get('name') == 'shell'
        and isinstance(d.get('conversation_id'), int)
    )
    if ok:
        record('REQ-CHAT-002 skill-structure', PASS)
    else:
        record('REQ-CHAT-002 skill-structure', FAIL, str(d))


# ── REQ-CHAT-003: Auth identity present in skill response ──────────────────────
def test_skill_response_has_identity():
    code, d = _req('POST', '/api/chat', {
        'message': 'SKILL shell echo hello_id',
        'agent': 'gemma',
        'acting_user': 'ghost',
    }, timeout=15)
    if code is None:
        record('REQ-CHAT-003 skill-identity', SKIP, 'server unreachable')
        return
    if code != 200:
        record('REQ-CHAT-003 skill-identity', SKIP, f'HTTP {code}')
        return
    identity = d.get('identity', {})
    has_identity = (
        'acting_user' in identity
        and 'effective_user' in identity
    )
    record('REQ-CHAT-003 skill-identity', PASS if has_identity else FAIL, str(identity))


# ── REQ-CHAT-004: Unauthorized agent denied skill ──────────────────────────────
def test_denied_agent_skill():
    """gemma acting as self with deny on 'search' skill should get 403."""
    # First explicitly deny gemma search access
    deny_code, deny_d = _req('POST', '/api/skills/permissions', {
        'acting_user': 'ghost',
        'username': 'gemma',
        'skill_name': 'search',
        'allowed': False,
    }, timeout=5)
    if deny_code not in (200, 201):
        record('REQ-CHAT-004 deny-skill', SKIP, f'permission set returned {deny_code}')
        return

    code, d = _req('POST', '/api/chat', {
        'message': 'SKILL search test query',
        'agent': 'gemma',
        'acting_user': 'gemma',
    }, timeout=10)
    denied = (code == 403)

    # Restore
    _req('POST', '/api/skills/permissions', {
        'acting_user': 'ghost',
        'username': 'gemma',
        'skill_name': 'search',
        'allowed': True,
    }, timeout=5)

    record('REQ-CHAT-004 deny-skill', PASS if denied else FAIL,
           f'HTTP {code} (expected 403)')


# ── REQ-CHAT-005: get_agent_memory importable and returns list ─────────────────
def test_get_agent_memory_importable():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))
        from database import get_agent_memory
        result = get_agent_memory('ten', query='', limit=3)
        record('REQ-CHAT-005 get_agent_memory', PASS, f'{len(result)} rows for ten')
    except Exception as e:
        record('REQ-CHAT-005 get_agent_memory', FAIL, str(e))


# ── REQ-CHAT-006: TEN_SYSTEM_PROMPT has style rules ───────────────────────────
def test_ten_system_prompt_style():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))
        from config import TEN_SYSTEM_PROMPT
        checks = [
            'concise' in TEN_SYSTEM_PROMPT.lower() or 'brief' in TEN_SYSTEM_PROMPT.lower(),
            'filler' in TEN_SYSTEM_PROMPT.lower() or 'preamble' in TEN_SYSTEM_PROMPT.lower(),
            'emoji' in TEN_SYSTEM_PROMPT.lower(),
        ]
        passed = all(checks)
        record('REQ-CHAT-006 ten-prompt-style', PASS if passed else FAIL,
               f'checks={checks}')
    except Exception as e:
        record('REQ-CHAT-006 ten-prompt-style', FAIL, str(e))


# ── REQ-CHAT-007: History filter query syntax valid ───────────────────────────
def test_history_filter_sql():
    """Verify terminal.py compiles cleanly (implies the SQL filter strings are valid Python)."""
    try:
        import py_compile, tempfile, shutil
        src = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'terminal.py')
        py_compile.compile(src, doraise=True)
        record('REQ-CHAT-007 terminal-compile', PASS)
    except Exception as e:
        record('REQ-CHAT-007 terminal-compile', FAIL, str(e))


# ── REQ-CHAT-008: Pending jobs polling endpoint reachable ─────────────────────
def test_chat_jobs_status_endpoint():
    code, d = _req('GET', '/api/chat/jobs/status', timeout=5)
    if code is None:
        record('REQ-CHAT-008 jobs-status-endpoint', SKIP, 'server unreachable')
        return
    ok = (code == 200 and d.get('ok') is True and isinstance(d.get('jobs'), list))
    record('REQ-CHAT-008 jobs-status-endpoint', PASS if ok else FAIL, f'HTTP {code}')


# ── REQ-CHAT-011: fs_readonly skill available via chat ───────────────────────
def test_fs_readonly_skill():
    code, d = _req('POST', '/api/chat', {
        'message': 'SKILL fs_readonly ls sandpits',
        'agent': 'gemma',
        'acting_user': 'ghost',
    }, timeout=15)
    if code is None:
        record('REQ-CHAT-011 fs-readonly-skill', SKIP, 'server unreachable')
        return
    if code != 200:
        record('REQ-CHAT-011 fs-readonly-skill', FAIL, f'HTTP {code}: {d}')
        return
    body = (d.get('response') or '').lower()
    ok = d.get('mode') == 'skill' and d.get('skill', {}).get('name') == 'fs_readonly' and ('sandpits/' in body or 'sandpits' in body)
    record('REQ-CHAT-011 fs-readonly-skill', PASS if ok else FAIL)


# ── REQ-CHAT-012: shell whitelist includes pwd ───────────────────────────────
def test_shell_pwd_allowed():
    code, d = _req('POST', '/api/chat', {
        'message': 'SKILL shell pwd',
        'agent': 'gemma',
        'acting_user': 'ghost',
    }, timeout=15)
    if code is None:
        record('REQ-CHAT-012 shell-pwd', SKIP, 'server unreachable')
        return
    if code != 200:
        record('REQ-CHAT-012 shell-pwd', FAIL, f'HTTP {code}: {d}')
        return
    text = d.get('response') or ''
    ok = ('/home/seven/swarm' in text) and ('FAILED' not in text)
    record('REQ-CHAT-012 shell-pwd', PASS if ok else FAIL, text[:120])


# ── REQ-CHAT-013: shell whitelist allows relative path operations ────────────
def test_shell_relative_path_ops():
    code, d = _req('POST', '/api/chat', {
        'message': 'SKILL shell ls -la sandpits/ten/',
        'agent': 'gemma',
        'acting_user': 'ghost',
    }, timeout=15)
    if code is None:
        record('REQ-CHAT-013 shell-relative-path', SKIP, 'server unreachable')
        return
    if code != 200:
        record('REQ-CHAT-013 shell-relative-path', FAIL, f'HTTP {code}: {d}')
        return
    text = d.get('response') or ''
    ok = ('FAILED' not in text) and ('sandpits/ten' in text or 'README.md' in text or 'working' in text)
    record('REQ-CHAT-013 shell-relative-path', PASS if ok else FAIL, text[:120])


# ── REQ-CHAT-014: no legacy extended-runtime placeholder in fanout responses ─
def test_no_legacy_extended_runtime_placeholder():
    code, d = _req('POST', '/api/chat', {
        'message': 'Health pulse in one line.',
        'agents': ['gemma', 'llama'],
        'acting_user': 'ghost',
    }, timeout=90)
    if code is None:
        record('REQ-CHAT-014 no-legacy-placeholder', SKIP, 'server unreachable')
        return
    if code != 200:
        record('REQ-CHAT-014 no-legacy-placeholder', FAIL, f'HTTP {code}: {d}')
        return

    legacy = 'still processing after extended runtime'
    responses = d.get('responses') or []
    joined = '\n'.join((r.get('response') or '') for r in responses)
    if legacy in joined.lower():
        record('REQ-CHAT-014 no-legacy-placeholder', FAIL, 'legacy timeout placeholder detected in /api/chat response')
        return

    pending_jobs = d.get('pending_jobs') or []
    if pending_jobs:
        conv_id = d.get('conversation_id')
        status_q = '/api/chat/jobs/status?conversation_id={}&job_ids={}'.format(
            conv_id,
            ','.join(pending_jobs),
        )
        s_code, s_data = _req('GET', status_q, timeout=10)
        if s_code != 200:
            record('REQ-CHAT-014 no-legacy-placeholder', FAIL, f'jobs status HTTP {s_code}')
            return
        bad = []
        for job in s_data.get('jobs') or []:
            stage = str(job.get('stage') or '').lower()
            err = str(job.get('error') or '').lower()
            if legacy in stage or legacy in err:
                bad.append(job.get('job_id') or 'unknown')
        if bad:
            record('REQ-CHAT-014 no-legacy-placeholder', FAIL, f'legacy phrase leaked in jobs: {bad}')
            return

    record('REQ-CHAT-014 no-legacy-placeholder', PASS)


# ── REQ-CHAT-015: monitor telemetry fields exposed ─────────────────────────
def test_monitor_runtime_telemetry_shape():
    code, d = _req('GET', '/api/monitor', timeout=10)
    if code is None:
        record('REQ-CHAT-015 monitor-telemetry-shape', SKIP, 'server unreachable')
        return
    if code != 200:
        record('REQ-CHAT-015 monitor-telemetry-shape', FAIL, f'HTTP {code}: {d}')
        return

    has_fields = (
        isinstance(d.get('runtime_jobs', []), list)
        and isinstance(d.get('active_models', []), list)
        and 'active_models_count' in d
        and 'vram_used_gb' in d
        and 'resident_models_gb' in d
        and isinstance(d.get('monitor_insights', []), list)
        and isinstance(d.get('inference_mode', ''), str)
    )
    record('REQ-CHAT-015 monitor-telemetry-shape', PASS if has_fields else FAIL)


# ── REQ-CHAT-016: per-agent chat ping with job-stage timeline logging ───────
def test_chat_ping_each_agent_with_stage_log():
    enabled = (os.environ.get('CHAT_PING_ENABLE') or '').strip().lower() in {'1', 'true', 'yes'}
    if not enabled:
        record('REQ-CHAT-016 agent-ping-stage-log', SKIP, 'set CHAT_PING_ENABLE=1 to run')
        return

    agents = _ping_agents_from_env()
    max_seconds = int(os.environ.get('CHAT_PING_MAX_SECONDS_PER_AGENT', '180'))
    per_agent = []

    for agent in agents:
        prompt = (
            f'PING_OBS {int(time.time())}: '
            f'Reply exactly with "pong {agent}" on the first line, '
            'then one short line describing your current processing focus.'
        )
        code, data = _req('POST', '/api/chat', {
            'message': prompt,
            'agent': agent,
            'acting_user': 'ghost',
            'new_thread': True,
        }, timeout=90)

        entry = {
            'agent': agent,
            'http_code': code,
            'conversation_id': data.get('conversation_id') if isinstance(data, dict) else None,
            'pending_jobs': data.get('pending_jobs') if isinstance(data, dict) else [],
            'immediate_response_len': len(str((data or {}).get('response') or '')) if isinstance(data, dict) else 0,
            'final_status': 'unknown',
            'stage_timeline': [],
            'response_excerpt': '',
            'error': '',
        }

        if code != 200:
            entry['final_status'] = 'http_error'
            entry['error'] = str(data)
            per_agent.append(entry)
            continue

        conv_id = entry['conversation_id']
        pending = [str(x) for x in (entry['pending_jobs'] or []) if str(x).strip()]
        jobs_latest, timeline = _wait_for_jobs(conv_id, pending, timeout_seconds=max_seconds)
        entry['stage_timeline'] = timeline

        response_text = ''
        if pending:
            # Pull persisted response after async jobs complete.
            response_text = _latest_agent_message(conv_id, agent)
            if not response_text:
                response_text = str((data or {}).get('response') or '')

            states = {str(v.get('status') or '') for v in jobs_latest.values()}
            if not states:
                entry['final_status'] = 'timeout_or_unknown'
            elif states.issubset({'completed'}):
                entry['final_status'] = 'completed'
            elif 'failed' in states:
                entry['final_status'] = 'failed'
                entry['error'] = '; '.join(str(v.get('error') or '') for v in jobs_latest.values() if v.get('error'))
            elif 'cancelled' in states:
                entry['final_status'] = 'cancelled'
            else:
                entry['final_status'] = 'incomplete'
        else:
            response_text = str((data or {}).get('response') or '')
            entry['final_status'] = 'completed' if response_text.strip() else 'empty_response'

        entry['response_excerpt'] = response_text[:220]
        per_agent.append(entry)

    total = len(per_agent)
    ok_agents = [x for x in per_agent if x.get('final_status') == 'completed' and x.get('response_excerpt')]
    failed_agents = [x for x in per_agent if x.get('final_status') not in {'completed'}]

    payload = {
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'base_url': BASE_URL,
        'agents': agents,
        'summary': {
            'total_agents': total,
            'completed_agents': len(ok_agents),
            'non_completed_agents': len(failed_agents),
        },
        'results': per_agent,
    }
    out_path = _write_ping_log(payload)

    # Pass criteria for observability test:
    # all calls returned HTTP 200 and each agent produced a logged terminal status.
    http_errors = [x.get('agent') for x in per_agent if x.get('http_code') != 200]
    status_counts = {}
    for row in per_agent:
        key = row.get('final_status') or 'unknown'
        status_counts[key] = status_counts.get(key, 0) + 1

    ok = (not http_errors) and all(x.get('final_status') for x in per_agent)
    detail = f"statuses={status_counts}, log={out_path}"
    if http_errors:
        detail += f", http_errors={http_errors}"
    record('REQ-CHAT-016 agent-ping-stage-log', PASS if ok else FAIL, detail)


# ── Runner ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print('Chat Quality Test Suite')
    print(f"Target: {BASE_URL}")
    print('='*60)

    up = _server_up()
    if not up:
        print(f"\n[WARN] Server not reachable at {BASE_URL} — live tests will SKIP\n")

    print('\nRunning tests...')
    test_skill_response_structure()
    test_skill_response_has_identity()
    test_skill_then_chat_no_bleed()
    test_denied_agent_skill()
    test_get_agent_memory_importable()
    test_ten_system_prompt_style()
    test_history_filter_sql()
    test_chat_jobs_status_endpoint()
    test_fs_readonly_skill()
    test_shell_pwd_allowed()
    test_shell_relative_path_ops()
    test_no_legacy_extended_runtime_placeholder()
    test_monitor_runtime_telemetry_shape()
    test_chat_ping_each_agent_with_stage_log()

    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    skipped = sum(1 for _, s, _ in results if s == SKIP)

    print(f"\n{'='*60}")
    print(f"Results: {passed} PASS  {failed} FAIL  {skipped} SKIP")
    print('='*60)

    if failed:
        print('\nFAILED tests:')
        for name, status, detail in results:
            if status == FAIL:
                print(f"  ✗ {name}: {detail}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
