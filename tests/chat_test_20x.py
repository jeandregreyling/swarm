#!/usr/bin/env python3
"""
20-test chat suite for agents Ten (GitHub/GPT) and Eleven (Grok).
Tests identity, relay, parallel, follow-up, edge cases, stress, error handling,
debate, proposal flow, memory, and more. Outputs structured results.
"""
import requests, json, time, sys, os

BASE = os.environ.get('SWARM_TEST_URL', 'http://localhost:5050')
TIMEOUT = 120

def chat(message, agents=None, agent=None, new_thread=False, conv_id=None, auto_relay=True):
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
    results = {}
    for resp in (data.get('responses') or []):
        agent_key = resp.get('agent', 'unknown')
        results[agent_key] = {
            'status': 'pending' if resp.get('pending') else 'ok',
            'response': resp.get('response', ''),
            'elapsed': resp.get('elapsed_ms', 0),
            'stage_trace': resp.get('stage_trace', []),
        }
    if not results and data.get('response'):
        agent_key = data.get('agent', 'unknown')
        results[agent_key] = {
            'status': 'ok',
            'response': data.get('response', ''),
        }

    pending_jobs = data.get('pending_jobs') or []
    if pending_jobs:
        job_ids = [str(j.get('job_id') or j) if isinstance(j, dict) else str(j) for j in pending_jobs if j]
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            time.sleep(2)
            try:
                poll = requests.get(f'{BASE}/api/chat/jobs/status',
                                    params={'job_ids': ','.join(job_ids),
                                            'conversation_id': str(conv_id or '')},
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
            resp_str = str(resp)
            if len(resp_str) > 800:
                resp_str = resp_str[:800] + '...[truncated]'
            print(f"  Response: {resp_str}")
        else:
            print(f"\n  [{agent_name}] {str(info)[:800]}")


def run_tests():
    print("Starting 20 chat tests with agents Ten and Eleven")
    print(f"Target: {BASE}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    all_results = {}

    # ── TEST 1: Ten identity check ─────────────────────────────────────
    print("\n>>> Test 1: Ten identity")
    r = chat("Who are you? What is your name and agent number in the swarm?", agent='ten', new_thread=True)
    test_result(1, "Ten identity check", r)
    all_results[1] = r
    conv_ten = r.get('conversation_id')

    # ── TEST 2: Eleven identity check ──────────────────────────────────
    print("\n>>> Test 2: Eleven identity")
    r = chat("Who are you? What is your name and agent number in the swarm?", agent='eleven', new_thread=True)
    test_result(2, "Eleven identity check", r)
    all_results[2] = r
    conv_eleven = r.get('conversation_id')

    # ── TEST 3: Parallel - same factual question ───────────────────────
    print("\n>>> Test 3: Parallel factual question")
    r = chat("What are the SOLID principles in software engineering? List all five briefly.",
             agents=['ten', 'eleven'], new_thread=True)
    test_result(3, "Parallel factual question", r)
    all_results[3] = r

    # ── TEST 4: Ten follow-up in same thread ───────────────────────────
    print("\n>>> Test 4: Ten thread continuity")
    if conv_ten:
        r = chat("What did I just ask you? Repeat my exact question back to me.", agent='ten', conv_id=conv_ten)
        test_result(4, "Ten thread continuity - recall", r)
        all_results[4] = r
    else:
        print("  SKIP: no conv_id from test 1")
        all_results[4] = {'error': 'no conv_id'}

    # ── TEST 5: Eleven follow-up in same thread ───────────────────────
    print("\n>>> Test 5: Eleven thread continuity")
    if conv_eleven:
        r = chat("What did I just ask you? Repeat my exact question back to me.", agent='eleven', conv_id=conv_eleven)
        test_result(5, "Eleven thread continuity - recall", r)
        all_results[5] = r
    else:
        print("  SKIP: no conv_id from test 2")
        all_results[5] = {'error': 'no conv_id'}

    # ── TEST 6: Relay - Ten asks Eleven ────────────────────────────────
    print("\n>>> Test 6: Relay - Ten to Eleven")
    r = chat("I need Eleven's perspective on this too: what's better for AI agents, Python or Rust? "
             "Give your view first, then relay to Eleven.",
             agent='ten', new_thread=True, auto_relay=True)
    test_result(6, "Relay - Ten to Eleven", r)
    all_results[6] = r

    # ── TEST 7: Relay - Eleven asks Ten ────────────────────────────────
    print("\n>>> Test 7: Relay - Eleven to Ten")
    r = chat("Ask Ten what they think about using WebSockets vs SSE for real-time agent communication. "
             "Give your own view first, then relay.",
             agent='eleven', new_thread=True, auto_relay=True)
    test_result(7, "Relay - Eleven to Ten", r)
    all_results[7] = r

    # ── TEST 8: Edge case - empty-ish message ──────────────────────────
    print("\n>>> Test 8: Edge case - minimal message")
    r = chat("?", agent='ten', new_thread=True)
    test_result(8, "Edge case - single character", r)
    all_results[8] = r

    # ── TEST 9: Edge case - very long input ────────────────────────────
    print("\n>>> Test 9: Edge case - long input")
    long_msg = "Summarize the following repeated phrase in one sentence: " + ("The quick brown fox jumps over the lazy dog. " * 50)
    r = chat(long_msg, agent='eleven', new_thread=True)
    test_result(9, "Edge case - long input (50x repeat)", r)
    all_results[9] = r

    # ── TEST 10: Code generation - Ten ─────────────────────────────────
    print("\n>>> Test 10: Code generation - Ten")
    r = chat("Write a Python function that takes a list of integers and returns the two numbers "
             "that sum to a target value. Include type hints and a docstring.",
             agent='ten', new_thread=True)
    test_result(10, "Code generation - Ten", r)
    all_results[10] = r

    # ── TEST 11: Code generation - Eleven ──────────────────────────────
    print("\n>>> Test 11: Code generation - Eleven")
    r = chat("Write a Python decorator that retries a function up to 3 times with exponential backoff. "
             "Include type hints and a usage example.",
             agent='eleven', new_thread=True)
    test_result(11, "Code generation - Eleven", r)
    all_results[11] = r

    # ── TEST 12: Debate - parallel opposing views ──────────────────────
    print("\n>>> Test 12: Parallel debate")
    r = chat("Debate topic: Should AI agents have persistent memory across conversations? "
             "Ten: argue FOR. Eleven: argue AGAINST. Each give 3 points.",
             agents=['ten', 'eleven'], new_thread=True)
    test_result(12, "Parallel debate - memory persistence", r)
    all_results[12] = r

    # ── TEST 13: Swarm awareness ───────────────────────────────────────
    print("\n>>> Test 13: Swarm awareness - Ten")
    r = chat("What do you know about the swarm you're part of? Name some other agents and what they do.",
             agent='ten', new_thread=True)
    test_result(13, "Swarm awareness - Ten", r)
    all_results[13] = r

    # ── TEST 14: Swarm awareness - Eleven ──────────────────────────────
    print("\n>>> Test 14: Swarm awareness - Eleven")
    r = chat("What do you know about the swarm you're part of? Name some other agents and what they do.",
             agent='eleven', new_thread=True)
    test_result(14, "Swarm awareness - Eleven", r)
    all_results[14] = r

    # ── TEST 15: Math / reasoning ──────────────────────────────────────
    print("\n>>> Test 15: Math reasoning")
    r = chat("A farmer has 17 sheep. All but 9 die. How many sheep does the farmer have left? "
             "Think step by step.",
             agents=['ten', 'eleven'], new_thread=True)
    test_result(15, "Math reasoning - trick question", r)
    all_results[15] = r

    # ── TEST 16: Proposal-style request ────────────────────────────────
    print("\n>>> Test 16: Proposal-style code change")
    r = chat("I want to add a /api/ping endpoint that returns {pong: true, timestamp: <unix_ms>}. "
             "Write the Flask blueprint code. This should follow the DEV→UAT→PROD promotion flow.",
             agent='ten', new_thread=True)
    test_result(16, "Proposal-style code change", r)
    all_results[16] = r

    # ── TEST 17: Emotional / creative ──────────────────────────────────
    print("\n>>> Test 17: Creative writing")
    r = chat("Write a 4-line haiku about an AI agent swarm working together at 3am.",
             agent='eleven', new_thread=True)
    test_result(17, "Creative - haiku", r)
    all_results[17] = r

    # ── TEST 18: Error handling - unknown agent ────────────────────────
    print("\n>>> Test 18: Error handling - bad agent name")
    r = chat("Hello", agent='nonexistent_agent_xyz', new_thread=True)
    test_result(18, "Error handling - unknown agent", r)
    all_results[18] = r

    # ── TEST 19: Rapid sequential - same thread 3 messages ─────────────
    print("\n>>> Test 19: Rapid sequential - 3 messages same thread")
    r1 = chat("Remember the number 42.", agent='ten', new_thread=True)
    test_result(19, "Rapid sequential - msg 1 (store)", r1)
    all_results[19] = r1
    conv19 = r1.get('conversation_id')
    if conv19:
        r2 = chat("Now remember the word 'flamingo'.", agent='ten', conv_id=conv19)
        test_result(19, "Rapid sequential - msg 2 (store more)", r2)
        r3 = chat("What number and what word did I ask you to remember?", agent='ten', conv_id=conv19)
        test_result(19, "Rapid sequential - msg 3 (recall)", r3)
        all_results['19c'] = r3

    # ── TEST 20: Stress - parallel with long output ────────────────────
    print("\n>>> Test 20: Stress - parallel long output")
    r = chat("Write a detailed comparison table (at least 10 rows) of Python web frameworks: "
             "Flask, Django, FastAPI, Starlette, Tornado. Compare features like ORM, async support, "
             "middleware, auth, community size, performance, learning curve, deployment, testing, and docs. "
             "Format as a proper markdown table.",
             agents=['ten', 'eleven'], new_thread=True)
    test_result(20, "Stress - parallel long output comparison", r)
    all_results[20] = r

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    passed = 0
    failed = 0
    skipped = 0
    for num in list(range(1, 21)) + ['19c']:
        r = all_results.get(num, {})
        label = f"  Test {str(num):>3s}: "
        if 'error' in r:
            err_msg = str(r.get('error', ''))[:80]
            # Test 18 expects an error - that's a pass
            if num == 18:
                print(f"{label}PASS (expected error: {err_msg})")
                passed += 1
            else:
                print(f"{label}ERROR - {err_msg}")
                failed += 1
        elif not r:
            print(f"{label}SKIP")
            skipped += 1
        else:
            agents_ok = []
            agents_fail = []
            for a, info in r.get('results', {}).items():
                if isinstance(info, dict):
                    s = info.get('status', 'ok')
                    resp_len = len(str(info.get('response', '')))
                    if s in ('done', 'ok', 'completed') and resp_len > 10:
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
            if agents_fail:
                print(f"{label}PARTIAL - ok=[{ok_str}] fail=[{fail_str}]")
                failed += 1
            elif agents_ok:
                print(f"{label}PASS - [{ok_str}]")
                passed += 1
            else:
                print(f"{label}EMPTY - no agent responses")
                failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped out of {passed+failed+skipped}")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    run_tests()
