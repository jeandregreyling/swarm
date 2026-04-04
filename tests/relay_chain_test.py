#!/usr/bin/env python3
"""
relay_chain_test.py — End-to-end relay chain tests.

Tests run sequentially. Each thread uses a real conversation on the live server.
Local agents can take 60-300s depending on load.

Chains:
  T1: Gemma → LLaMA → Qwen → LLaMA
  T2: LLaMA  (start) → Gemma → LLaMA (end)
  T3: Mistral (start) → LLaMA → Mistral (end)   [analyst relay]
  T4: Eight  → Gemma (Eight must appear somewhere in the thread)
  T5: Gemma  → Mistral → LLaMA → Mistral        [full analyst round-trip]
"""

import time
import sys
import json
import requests

BASE = 'http://localhost:5050'
POLL_INTERVAL = 10      # seconds between job polls
JOB_TIMEOUT   = 540     # max seconds to wait for one agent hop (local CPU models can be slow)
HEADERS       = {'Content-Type': 'application/json'}

# --- ANSI colours ---------------------------------------------------------

def _g(s): return f'\033[32m{s}\033[0m'   # green
def _r(s): return f'\033[31m{s}\033[0m'   # red
def _y(s): return f'\033[33m{s}\033[0m'   # yellow
def _b(s): return f'\033[1m{s}\033[0m'    # bold

# --- helpers ---------------------------------------------------------------

def _send(message: str, agents: list, conv_id=None, new_thread=False, relay_from=None) -> dict:
    """POST /api/chat and return the parsed response dict."""
    payload = {
        'message': message,
        'agents': agents,
        'history_mode': 'recent',
        'history_limit': 6,
    }
    if new_thread or conv_id is None:
        payload['new_thread'] = True
    else:
        payload['conversation_id'] = conv_id
    if relay_from:
        payload['relay_from'] = str(relay_from).lower()
    resp = requests.post(f'{BASE}/api/chat', json=payload, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _wait_for_jobs(job_ids: list, conv_id: int, label: str) -> dict:
    """Poll until all job_ids are done. Returns {job_id: final_job}.
    Terminal statuses from server: 'completed', 'failed', 'cancelled'.
    If a job_id vanishes from the list entirely, it was cleaned up after completion — treat as done.
    """
    if not job_ids:
        return {}
    remaining = set(job_ids)
    results = {}
    deadline = time.time() + JOB_TIMEOUT
    print(f'      ⏳  Polling {len(remaining)} pending job(s) for [{label}]…', flush=True)
    while remaining and time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        r = requests.get(
            f'{BASE}/api/chat/jobs/status',
            params={'conversation_id': conv_id, 'job_ids': ','.join(remaining)},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        seen_ids = {job.get('job_id') for job in data.get('jobs', [])}
        for job in data.get('jobs', []):
            jid = job.get('job_id')
            if jid not in remaining:
                continue
            status = job.get('status', '')
            if status in ('completed', 'failed', 'cancelled'):
                remaining.discard(jid)
                results[jid] = job
                elapsed = int(job.get('elapsed_ms') or 0) // 1000
                colour = _g if status == 'completed' else _r
                print(f'      {colour(status.upper())}  {job.get("agent","?")} — {elapsed}s', flush=True)
        # Jobs that vanished from the response were cleaned up (completed + TTL expired) — treat as done
        vanished = remaining - seen_ids
        for jid in vanished:
            remaining.discard(jid)
            results[jid] = {'job_id': jid, 'status': 'completed', 'response': '', 'agent': '?'}
            print(f'      {_g("COMPLETED (cleaned up)")}  job {jid}', flush=True)
        if remaining:
            elapsed_total = int(JOB_TIMEOUT - (deadline - time.time()))
            stages = []
            for job in data.get('jobs', []):
                if job.get('job_id') in remaining:
                    s = job.get('stage') or 'running'
                    stages.append(f'{job.get("agent","?")}:{s}')
            print(f'      ⌛  {elapsed_total}s elapsed — {", ".join(stages) if stages else "waiting"}', flush=True)
    for jid in remaining:
        results[jid] = {'job_id': jid, 'status': 'timeout', 'response': '[timeout]', 'agent': '?'}
        print(_r(f'      TIMEOUT  job {jid}'))
    return results


def _get_messages(conv_id: int) -> list:
    """Fetch all messages for a conversation, return list sorted by id."""
    r = requests.get(f'{BASE}/api/conversations/{conv_id}/messages', timeout=15)
    r.raise_for_status()
    data = r.json()
    return sorted(data.get('messages', []), key=lambda m: m.get('id', 0))


def _hop(label: str, message: str, agents: list, conv_id=None, new_thread=False, relay_from=None):
    """
    Send one hop of the relay chain. Returns (conv_id, responses_map).
    responses_map is {agent_key: response_text}.
    """
    agent_str = ', '.join(a.upper() for a in agents)
    print(f'\n  {_b("→")} [{label}] sending to {_y(agent_str)}', flush=True)
    print(f'     msg: "{message[:120]}{"…" if len(message)>120 else ""}"', flush=True)

    data = _send(message, agents, conv_id=conv_id, new_thread=new_thread, relay_from=relay_from)
    conv_id = int(data.get('conversation_id') or 0)
    print(f'     conv_id={conv_id}', flush=True)

    responses_map = {}
    pending_jobs = []

    for entry in data.get('responses', []):
        agent_key = str(entry.get('agent') or '').lower()
        if entry.get('pending'):
            jid = entry.get('job_id')
            if jid:
                pending_jobs.append(jid)
            print(f'      ⏳  {agent_key} pending (job={jid})', flush=True)
        else:
            text = str(entry.get('response') or '')
            responses_map[agent_key] = text
            preview = text[:160].replace('\n', ' ')
            print(f'      ✓   {agent_key}: {preview}', flush=True)

    if pending_jobs:
        job_results = _wait_for_jobs(pending_jobs, conv_id, label)
        # After jobs complete, fetch latest messages to get response text
        msgs = _get_messages(conv_id)
        # Take the most recent N response messages for each pending agent
        agent_job_map = {}
        for entry in data.get('responses', []):
            if entry.get('pending') and entry.get('job_id'):
                agent_job_map[entry['job_id']] = str(entry.get('agent') or '').lower()
        pending_agents = set(agent_job_map.values())
        # Find last message per pending agent
        for msg in reversed(msgs):
            sender = str(msg.get('sender') or msg.get('agent') or '').lower()
            if sender in pending_agents and sender not in responses_map:
                text = str(msg.get('message') or msg.get('response') or msg.get('content') or '')
                if text and not text.startswith('[') or len(text) > 50:
                    responses_map[sender] = text
                    preview = text[:160].replace('\n', ' ')
                    print(f'      ✓   {sender} (from job): {preview}', flush=True)

    return conv_id, responses_map


def _check(responses_map: dict, expected_agents: list) -> bool:
    """Return True if all expected_agents have a valid (non-error) response."""
    ok = True
    for agent in expected_agents:
        text = responses_map.get(agent, '')
        if not text or len(text) < 10 or text.strip().startswith('[') and 'error' in text.lower():
            print(_r(f'      FAIL  {agent}: {"(no response)" if not text else text[:120]}'))
            ok = False
        else:
            relay_hint = ''
            # Check for relay directive in response
            for line in text.splitlines():
                stripped = line.strip()
                if ':' in stripped and not stripped.startswith('http'):
                    parts = stripped.split(':', 1)
                    name = parts[0].strip().lower()
                    if name in {'gemma','llama','qwen','mistral','eight','sniffles','duck','nine','ten','eleven','twelve','scholar','seeker','librarian'}:
                        relay_hint = f' → relay detected: [{stripped[:80]}]'
                        break
            print(_g(f'      PASS  {agent} ({len(text)} chars{relay_hint})'))
    return ok


# ── THREAD 1: Gemma → LLaMA → Qwen → LLaMA ──────────────────────────────

def thread1():
    print(_b('\n══ THREAD 1: Gemma → LLaMA → Qwen → LLaMA ══'))
    passed = True
    conv_id = None

    conv_id, r = _hop('T1-Gemma', 'What are the main trade-offs between CPU and GPU inference for local LLMs? Please keep it concise.', ['gemma'], new_thread=True)
    passed &= _check(r, ['gemma'])

    conv_id, r = _hop('T1-LLaMA', 'Can you search for any recent benchmarks comparing CPU-only vs GPU LLM inference speed and cost? Keep it brief.', ['llama'], conv_id=conv_id, relay_from='gemma')
    passed &= _check(r, ['llama'])

    conv_id, r = _hop('T1-Qwen', 'Gemma gave trade-offs and LLaMA found benchmarks. Please analyse — what conclusion would you draw for a CPU-only home server? One paragraph max.', ['qwen'], conv_id=conv_id, relay_from='llama')
    passed &= _check(r, ['qwen'])

    conv_id, r = _hop('T1-LLaMA-final', 'Qwen gave an analysis above. Can you verify it with any recent sources and give a one-sentence verdict?', ['llama'], conv_id=conv_id, relay_from='qwen')
    passed &= _check(r, ['llama'])

    result = _g('PASS') if passed else _r('FAIL')
    print(f'\n  Thread 1 result: {result}')
    return passed


# ── THREAD 2: LLaMA (start) → Gemma → LLaMA (end) ───────────────────────

def thread2():
    print(_b('\n══ THREAD 2: LLaMA → Gemma → LLaMA ══'))
    passed = True
    conv_id = None

    conv_id, r = _hop('T2-LLaMA-start', 'What is the current capital of Australia, and who is the current Prime Minister? Quick answer only.', ['llama'], new_thread=True)
    passed &= _check(r, ['llama'])

    conv_id, r = _hop('T2-Gemma', 'LLaMA just answered above. Please synthesise the response and flag anything uncertain or worth verifying.', ['gemma'], conv_id=conv_id, relay_from='llama')
    passed &= _check(r, ['gemma'])

    conv_id, r = _hop('T2-LLaMA-end', 'Gemma flagged something for verification. Can you do a quick check and confirm the final facts?', ['llama'], conv_id=conv_id, relay_from='gemma')
    passed &= _check(r, ['llama'])

    result = _g('PASS') if passed else _r('FAIL')
    print(f'\n  Thread 2 result: {result}')
    return passed


# ── THREAD 3: Mistral (start) → LLaMA → Mistral (end) ──────────────────

def thread3():
    print(_b('\n══ THREAD 3: Mistral → LLaMA → Mistral ══'))
    passed = True
    conv_id = None

    conv_id, r = _hop('T3-Mistral-start', 'Reason through the key risks of running AI inference models on a machine with no GPU and 33GB RAM. Structured list, max 5 points.', ['mistral'], new_thread=True)
    passed &= _check(r, ['mistral'])

    conv_id, r = _hop('T3-LLaMA', 'Mistral listed risks above. Can you find any real-world forum posts or articles where people share experience with CPU-only local AI setups?', ['llama'], conv_id=conv_id, relay_from='mistral')
    passed &= _check(r, ['llama'])

    conv_id, r = _hop('T3-Mistral-end', 'LLaMA shared real-world experiences. Update your risk analysis with any new evidence. Has anything changed in your assessment?', ['mistral'], conv_id=conv_id, relay_from='llama')
    passed &= _check(r, ['mistral'])

    result = _g('PASS') if passed else _r('FAIL')
    print(f'\n  Thread 3 result: {result}')
    return passed


# ── THREAD 4: Include Eight ───────────────────────────────────────────────

def thread4():
    print(_b('\n══ THREAD 4: Eight included ══'))
    passed = True
    conv_id = None

    conv_id, r = _hop('T4-Gemma', 'We need to discuss SAP HCM payroll processing. Can you introduce the topic and route to Eight for the detailed analysis?', ['gemma'], new_thread=True)
    passed &= _check(r, ['gemma'])

    conv_id, r = _hop('T4-Eight', 'What is the correct processing sequence for a payroll run in SAP HCM, and what schema controls it? Brief technical answer.', ['eight'], conv_id=conv_id, relay_from='gemma')
    passed &= _check(r, ['eight'])

    conv_id, r = _hop('T4-Gemma-close', 'Eight gave a technical answer on SAP payroll. Synthesise it for a non-SAP audience in two sentences.', ['gemma'], conv_id=conv_id, relay_from='eight')
    passed &= _check(r, ['gemma'])

    result = _g('PASS') if passed else _r('FAIL')
    print(f'\n  Thread 4 result: {result}')
    return passed


# ── THREAD 5: Gemma → Mistral → LLaMA → Mistral (full analyst round-trip) ─

def thread5():
    print(_b('\n══ THREAD 5: Gemma → Mistral → LLaMA → Mistral ══'))
    passed = True
    conv_id = None

    conv_id, r = _hop('T5-Gemma', 'Briefly introduce the topic of quantisation in local LLMs — what is it and why does it matter? Two sentences max.', ['gemma'], new_thread=True)
    passed &= _check(r, ['gemma'])

    conv_id, r = _hop('T5-Mistral', 'Gemma introduced LLM quantisation above. Analyse the trade-offs between Q4, Q5, and Q8 quantisation levels for a CPU-only machine. Structured, concise.', ['mistral'], conv_id=conv_id, relay_from='gemma')
    passed &= _check(r, ['mistral'])

    conv_id, r = _hop('T5-LLaMA', 'Mistral analysed quantisation levels above. Can you find any benchmark data or community experience on real-world performance differences between these levels?', ['llama'], conv_id=conv_id, relay_from='mistral')
    passed &= _check(r, ['llama'])

    conv_id, r = _hop('T5-Mistral-final', 'LLaMA found real-world benchmarks. Update your analysis — does the evidence confirm or challenge your earlier assessment? One paragraph.', ['mistral'], conv_id=conv_id, relay_from='llama')
    passed &= _check(r, ['mistral'])

    result = _g('PASS') if passed else _r('FAIL')
    print(f'\n  Thread 5 result: {result}')
    return passed


# ── main ───────────────────────────────────────────────────────────────────

def main():
    print(_b('=== Relay Chain Test Suite ==='))
    print(f'Server: {BASE}')
    print(f'Job timeout: {JOB_TIMEOUT}s per hop\n')

    # Quick connectivity check
    try:
        r = requests.get(f'{BASE}/api/activity', timeout=5)
        r.raise_for_status()
        print(_g('Server reachable ✓\n'))
    except Exception as e:
        print(_r(f'Server unreachable: {e}'))
        sys.exit(1)

    results = {}
    threads = [
        ('Thread 1 (Gemma→LLaMA→Qwen→LLaMA)',         thread1),
        ('Thread 2 (LLaMA→Gemma→LLaMA)',               thread2),
        ('Thread 3 (Mistral→LLaMA→Mistral)',           thread3),
        ('Thread 4 (includes Eight)',                   thread4),
        ('Thread 5 (Gemma→Mistral→LLaMA→Mistral)',     thread5),
    ]

    for name, fn in threads:
        try:
            ok = fn()
        except Exception as e:
            print(_r(f'\n  EXCEPTION in {name}: {e}'))
            import traceback; traceback.print_exc()
            ok = False
        results[name] = ok
        if not ok:
            print(_y(f'\n  {name} FAILED — check output above for root cause.'))

    print(_b('\n\n=== SUMMARY ==='))
    all_pass = True
    for name, ok in results.items():
        icon = _g('✓ PASS') if ok else _r('✗ FAIL')
        print(f'  {icon}  {name}')
        if not ok:
            all_pass = False
    print()
    if all_pass:
        print(_g('All relay chains passed.'))
    else:
        print(_r('One or more chains failed — see output above.'))
    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
