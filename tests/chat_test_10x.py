#!/usr/bin/env python3
"""
10-test chat suite for agents Ten (GitHub/GPT) and Eleven (Grok).
Tests: relay awareness, main vs tile chat, thinking display, proposal flow,
and various edge cases. Outputs structured results for bug analysis.
"""
import requests, json, time, sys, os

BASE = os.environ.get('SWARM_TEST_URL', 'http://localhost:5050')
TIMEOUT = 120  # seconds per test

def chat(message, agents=None, agent=None, new_thread=False, conv_id=None, auto_relay=True):
    """Send chat and poll for results."""
    payload = {'message': message, 'auto_relay': auto_relay}
    if agents:
        payload['agents'] = agents
    elif agent:
        payload['agent'] = agent
    if new_thread:
        payload['new_thread'] = True
    if conv_id:
        payload['conversation_id'] = conv_id

    r = requests.post(f'{BASE}/api/chat', json=payload, timeout=30)
    data = r.json()
    if not data.get('ok'):
        return {'error': data, 'status': r.status_code}

    conv_id = data.get('conversation_id')

    # Build results from responses array (actual API format)
    results = {}
    for resp in (data.get('responses') or []):
        agent_key = resp.get('agent', 'unknown')
        results[agent_key] = {
            'status': 'pending' if resp.get('pending') else 'ok',
            'response': resp.get('response', ''),
            'elapsed': resp.get('elapsed_ms', 0),
            'stage_trace': resp.get('stage_trace', []),
        }
    # Fallback: single response format
    if not results and data.get('response'):
        agent_key = data.get('agent', 'unknown')
        results[agent_key] = {
            'status': 'ok',
            'response': data.get('response', ''),
        }

    # Poll for pending jobs (actual API format: pending_jobs list of {job_id, agent})
    pending_jobs = data.get('pending_jobs') or []
    if pending_jobs:
        job_ids = [str(j.get('job_id') or j) for j in pending_jobs if j]
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            time.sleep(2)
            try:
                poll = requests.get(f'{BASE}/api/chat/jobs/status',
                                    params={
                                        'job_ids': ','.join(job_ids),
                                        'conversation_id': str(conv_id or ''),
                                    },
                                    timeout=10)
                poll_data = poll.json()
                all_done = True
                for job in (poll_data.get('jobs') or []):
                    status = job.get('status', '')
                    agent_key = job.get('agent', job.get('job_id', '?'))
                    if status in ('completed', 'failed', 'cancelled'):
                        results[agent_key] = {
                            'status': status,
                            'response': job.get('response', ''),
                            'stage': job.get('stage', ''),
                            'elapsed': job.get('elapsed_ms', 0),
                            'stage_trace': job.get('stage_trace', []),
                        }
                    else:
                        all_done = False
                if all_done:
                    break
            except Exception as e:
                print(f"  poll error: {e}")
                time.sleep(2)

    return {'conversation_id': conv_id, 'results': results}


def test_result(num, name, result):
    """Print formatted test result."""
    print(f"\n{'='*80}")
    print(f"TEST {num}: {name}")
    print(f"{'='*80}")
    if 'error' in result:
        print(f"  ERROR: {json.dumps(result['error'], indent=2)[:500]}")
        return

    conv = result.get('conversation_id', '?')
    print(f"  Conversation: {conv}")
    for agent_name, info in result.get('results', {}).items():
        if isinstance(info, dict):
            status = info.get('status', 'ok')
            resp = info.get('response', str(info))
            elapsed = info.get('elapsed', '?')
            print(f"\n  [{agent_name}] status={status} elapsed={elapsed}s")
            # Truncate long responses
            resp_str = str(resp)
            if len(resp_str) > 800:
                resp_str = resp_str[:800] + '...[truncated]'
            print(f"  Response: {resp_str}")
        else:
            resp_str = str(info)[:800]
            print(f"\n  [{agent_name}] {resp_str}")


def run_tests():
    print("Starting 10 chat tests with agents Ten and Eleven")
    print(f"Target: {BASE}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    all_results = {}

    # ── TEST 1: Basic single-agent Ten ─────────────────────────────────
    print("\n>>> Test 1: Single agent Ten - basic prompt")
    r = chat("Hello, this is a test. Please reply with exactly one sentence about yourself and what you can do.", agent='ten', new_thread=True)
    test_result(1, "Single agent Ten - basic prompt", r)
    all_results[1] = r
    conv1 = r.get('conversation_id')

    # ── TEST 2: Basic single-agent Eleven ──────────────────────────────
    print("\n>>> Test 2: Single agent Eleven - basic prompt")
    r = chat("Hello, this is a test. Please reply with exactly one sentence about yourself and what you can do.", agent='eleven', new_thread=True)
    test_result(2, "Single agent Eleven - basic prompt", r)
    all_results[2] = r

    # ── TEST 3: Multi-agent parallel (Ten + Eleven) ────────────────────
    print("\n>>> Test 3: Parallel Ten + Eleven - same question")
    r = chat("What are the key differences between functional and object-oriented programming? Keep it to 3 bullet points each.",
             agents=['ten', 'eleven'], new_thread=True)
    test_result(3, "Parallel Ten + Eleven - same question", r)
    all_results[3] = r

    # ── TEST 4: Relay awareness test ───────────────────────────────────
    print("\n>>> Test 4: Relay awareness - ask Ten to involve Eleven")
    r = chat("I need two perspectives on this: should a Python web app use async or sync? "
             "Please give your view, then ask Eleven (Grok) for their perspective using the relay system.",
             agent='ten', new_thread=True, auto_relay=True)
    test_result(4, "Relay awareness - Ten asked to relay to Eleven", r)
    all_results[4] = r

    # ── TEST 5: Thinking/reasoning display test ────────────────────────
    print("\n>>> Test 5: Complex reasoning - triggers thinking display")
    r = chat("Analyze this step by step: If we have a Flask app with 18 agents, each running on different LLM providers, "
             "and we need to add circuit breakers, retry logic, and rate limiting - what's the architecture? "
             "Think through each layer carefully before answering.",
             agent='ten', new_thread=True)
    test_result(5, "Complex reasoning - thinking display", r)
    all_results[5] = r

    # ── TEST 6: Proposal creation via chat ─────────────────────────────
    print("\n>>> Test 6: Ask Ten to describe a code change (proposal-style)")
    r = chat("I want to add a health check endpoint at /api/health that returns {status: 'ok', uptime: seconds}. "
             "Write the code as a Flask blueprint. This should go through the proposal workflow - DEV first, then UAT, then PROD.",
             agent='ten', new_thread=True)
    test_result(6, "Proposal-style code request", r)
    all_results[6] = r

    # ── TEST 7: Follow-up in same thread (thread continuity) ──────────
    print("\n>>> Test 7: Follow-up in Test 1's thread")
    if conv1:
        r = chat("Now tell me: do you remember what I asked you in my first message? What was it?",
                 agent='ten', conv_id=conv1)
        test_result(7, "Thread continuity - follow-up", r)
        all_results[7] = r
    else:
        print("  SKIP: No conversation_id from test 1")
        all_results[7] = {'error': 'no conv_id from test 1'}

    # ── TEST 8: Edge case - very short message ─────────────────────────
    print("\n>>> Test 8: Edge case - minimal message")
    r = chat("?", agent='eleven', new_thread=True)
    test_result(8, "Edge case - single character message", r)
    all_results[8] = r

    # ── TEST 9: Multi-agent with relay chain ───────────────────────────
    print("\n>>> Test 9: Multi-agent conversation with cross-talk")
    r = chat("Debate: Is TypeScript worth the overhead for small projects? "
             "Ten, take the pro side. Eleven, take the con side. "
             "Then respond to each other's points.",
             agents=['ten', 'eleven'], new_thread=True, auto_relay=True)
    test_result(9, "Multi-agent debate with relay", r)
    all_results[9] = r

    # ── TEST 10: Long context / "chat dies" stress ─────────────────────
    print("\n>>> Test 10: Stress test - long detailed request")
    r = chat("Write a detailed technical specification for the following system: "
             "A multi-agent AI orchestrator that manages 18 different LLM agents across "
             "5 providers (Ollama local, Groq, GitHub Models, xAI, Anthropic). "
             "Include: agent lifecycle, message routing, relay chains, circuit breakers, "
             "resource gating, conversation persistence, and the DEV→UAT→PROD promotion flow. "
             "Format it as a proper spec document with sections. "
             "This is specifically testing whether long responses complete fully or die mid-stream.",
             agent='ten', new_thread=True)
    test_result(10, "Stress test - long detailed request", r)
    all_results[10] = r

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    for num in range(1, 11):
        r = all_results.get(num, {})
        if 'error' in r:
            print(f"  Test {num:2d}: ERROR")
        else:
            agents_ok = []
            agents_fail = []
            for a, info in r.get('results', {}).items():
                if isinstance(info, dict):
                    s = info.get('status', 'ok')
                    resp_len = len(str(info.get('response', '')))
                    if s in ('done', 'ok') and resp_len > 10:
                        agents_ok.append(f"{a}({resp_len}ch)")
                    else:
                        agents_fail.append(f"{a}({s},{resp_len}ch)")
                else:
                    resp_len = len(str(info))
                    if resp_len > 10:
                        agents_ok.append(f"{a}({resp_len}ch)")
                    else:
                        agents_fail.append(f"{a}({resp_len}ch)")
            ok_str = ', '.join(agents_ok) if agents_ok else 'none'
            fail_str = ', '.join(agents_fail) if agents_fail else 'none'
            print(f"  Test {num:2d}: OK=[{ok_str}] FAIL=[{fail_str}]")

    return all_results


if __name__ == '__main__':
    results = run_tests()
