#!/usr/bin/env python3
"""
10 relay/auto-relay focused tests for agents Nineteen and Eleven.
Tests how agents hand off to each other, structure relay responses,
multi-turn back-and-forth, relay chains, and auto_relay on/off behavior.
"""
import requests, json, time, sys, os, re

BASE = os.environ.get('SWARM_TEST_URL', 'http://localhost:5050')
TIMEOUT = 120
passed = 0
failed = 0
errors = []


def chat(message, agents=None, agent=None, new_thread=False, conv_id=None,
         auto_relay=True, relay_from=None):
    payload = {'message': message, 'auto_relay': auto_relay}
    if agents:
        payload['agents'] = agents
    elif agent:
        payload['agent'] = agent
    if new_thread:
        payload['new_thread'] = True
    if conv_id:
        payload['conversation_id'] = conv_id
    if relay_from:
        payload['relay_from'] = relay_from

    r = requests.post(f'{BASE}/api/chat', json=payload, timeout=30)
    data = r.json()
    if not data.get('ok'):
        return {'error': data, 'status': r.status_code}

    conv = data.get('conversation_id')
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
        job_ids = [str(j.get('job_id') or j) if isinstance(j, dict) else str(j)
                   for j in pending_jobs if j]
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            time.sleep(2)
            try:
                poll = requests.get(f'{BASE}/api/chat/jobs/status',
                                    params={'job_ids': ','.join(job_ids),
                                            'conversation_id': str(conv or '')},
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

    return {'conversation_id': conv, 'results': results}


def get_response_text(result, agent=None):
    """Extract response text from a result, optionally for a specific agent."""
    if 'error' in result:
        return ''
    results = result.get('results', {})
    if agent and agent in results:
        return str(results[agent].get('response', ''))
    # Return first non-empty response
    for k, v in results.items():
        resp = str(v.get('response', ''))
        if resp:
            return resp
    return ''


def has_agent_mention(text, agent_name):
    """Check if response mentions another agent by name."""
    patterns = {
        'ten': r'\b(?:ten|github|gpt)\b',
        'nineteen': r'\b(?:nineteen|o4.mini|github)\b',
        'eleven': r'\b(?:eleven|grok)\b',
        'nine': r'\b(?:nine|groq)\b',
        'twelve': r'\b(?:twelve|claude)\b',
    }
    pat = patterns.get(agent_name, rf'\b{agent_name}\b')
    return bool(re.search(pat, text, re.IGNORECASE))


def print_result(num, name, result, checks=None):
    global passed, failed, errors
    print(f"\n{'='*80}")
    print(f"TEST {num}: {name}")
    print(f"{'='*80}")
    if 'error' in result:
        print(f"  ERROR: {json.dumps(result['error'], indent=2)[:500]}")
        failed += 1
        errors.append(f"Test {num}: API error")
        return False

    conv = result.get('conversation_id', '?')
    print(f"  Conversation: {conv}")
    for agent_name, info in result.get('results', {}).items():
        if isinstance(info, dict):
            status = info.get('status', 'ok')
            resp = str(info.get('response', ''))
            elapsed = info.get('elapsed', '?')
            print(f"\n  [{agent_name}] status={status} elapsed={elapsed}s len={len(resp)}ch")
            display = resp[:600] + '...[truncated]' if len(resp) > 600 else resp
            print(f"  Response: {display}")
        else:
            print(f"\n  [{agent_name}] {str(info)[:600]}")

    # Run validation checks
    if checks:
        all_ok = True
        for check_name, check_fn in checks.items():
            try:
                ok = check_fn(result)
            except Exception as e:
                ok = False
                print(f"  CHECK ERROR [{check_name}]: {e}")
            status_str = "OK" if ok else "FAIL"
            print(f"  Check [{check_name}]: {status_str}")
            if not ok:
                all_ok = False
        if all_ok:
            passed += 1
            return True
        else:
            failed += 1
            errors.append(f"Test {num}: check failed")
            return False
    else:
        # No checks — pass if we got a non-empty response
        has_response = any(
            len(str(v.get('response', ''))) > 0
            for v in result.get('results', {}).values()
            if isinstance(v, dict)
        )
        if has_response:
            passed += 1
            return True
        else:
            failed += 1
            errors.append(f"Test {num}: empty response")
            return False


def run_tests():
    global passed, failed, errors
    print("=" * 80)
    print("RELAY / AUTO-RELAY TEST SUITE — 10 tests")
    print(f"Target: {BASE}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # ── TEST 1: Basic relay — Ten relays to Eleven ───────────────────
    print("\n>>> Test 1: Nineteen explicitly relays to Eleven")
    r = chat(
        "Nineteen, analyze this from an engineering perspective first, then ask Eleven "
        "to give a creative/lateral perspective: What's the best architecture for "
        "a multi-agent AI system?",
        agent='nineteen', new_thread=True, auto_relay=True
    )
    print_result(1, "Nineteen→Eleven relay (explicit request)", r, checks={
        'nineteen_responded': lambda r: len(get_response_text(r, 'nineteen')) > 50,
    })
    conv1 = r.get('conversation_id')

    # ── TEST 2: Basic relay — Eleven relays to Ten ───────────────────
    print("\n>>> Test 2: Eleven explicitly relays to Ten")
    r = chat(
        "Eleven, brainstorm 3 unusual approaches to error handling in Python, "
        "then ask Nineteen to evaluate which approach is most practical.",
        agent='eleven', new_thread=True, auto_relay=True
    )
    print_result(2, "Eleven→Ten relay (explicit request)", r, checks={
        'eleven_responded': lambda r: len(get_response_text(r, 'eleven')) > 50,
    })
    conv2 = r.get('conversation_id')

    # ── TEST 3: Auto-relay OFF — agent should NOT relay ──────────────
    print("\n>>> Test 3: Auto-relay OFF — no relay should happen")
    r = chat(
        "I need both Nineteen and Eleven's opinions on microservices vs monolith. "
        "Ask Eleven what they think about it.",
        agent='nineteen', new_thread=True, auto_relay=False
    )
    print_result(3, "Auto-relay OFF — Nineteen only, no relay", r, checks={
        'nineteen_responded': lambda r: len(get_response_text(r, 'nineteen')) > 30,
        'no_eleven': lambda r: 'eleven' not in r.get('results', {}),
    })

    # ── TEST 4: Multi-turn relay chain — Nineteen→Eleven→follow-up ───────
    print("\n>>> Test 4: Multi-turn relay thread")
    r1 = chat(
        "Ten, what are 3 security risks of using eval() in Python? "
        "After your analysis, relay to Nineteen for creative mitigation ideas.",
        agent='nineteen', new_thread=True, auto_relay=True
    )
    print_result(4, "Multi-turn relay chain — turn 1 (Nineteen starts)", r1, checks={
        'nineteen_responded': lambda r: len(get_response_text(r, 'nineteen')) > 50,
    })
    conv4 = r1.get('conversation_id')

    # Follow up in the same thread to test context preservation
    if conv4:
        print("\n>>> Test 4b: Follow-up in relay thread")
        r2 = chat(
            "Now both of you: which of those risks is the most dangerous in a "
            "production swarm system like ours?",
            agents=['nineteen', 'eleven'], conv_id=conv4, auto_relay=True
        )
        print_result(4, "Multi-turn relay chain — turn 2 (both respond)", r2, checks={
            'has_responses': lambda r: len(r.get('results', {})) >= 1,
        })

    # ── TEST 5: Parallel with relay context ──────────────────────────
    print("\n>>> Test 5: Parallel dispatch with relay awareness")
    r = chat(
        "Both Nineteen and Eleven: Propose a name for a new Swarm feature that "
        "auto-summarizes conversations. Each of you give 3 name ideas. "
        "Then comment on each other's suggestions.",
        agents=['nineteen', 'eleven'], new_thread=True, auto_relay=True
    )
    print_result(5, "Parallel — both respond with cross-reference", r, checks={
        'both_responded': lambda r: len([
            k for k, v in r.get('results', {}).items()
            if isinstance(v, dict) and len(str(v.get('response', ''))) > 20
        ]) >= 2,
    })

    # ── TEST 6: Relay with relay_from parameter ──────────────────────
    print("\n>>> Test 6: Simulated relay_from (as if Nineteen relayed)")
    r = chat(
        "Eleven, Nineteen just analyzed a Flask blueprint and found 3 potential "
        "issues with error handling. Can you suggest creative patterns "
        "to solve error propagation in Flask blueprints?",
        agent='eleven', new_thread=True, auto_relay=True,
        relay_from='nineteen'
    )
    print_result(6, "relay_from=nineteen — Eleven responds to relay", r, checks={
        'eleven_responded': lambda r: len(get_response_text(r, 'eleven')) > 50,
    })

    # ── TEST 7: Agent references other agent by name in response ─────
    print("\n>>> Test 7: Response structure — does agent reference the other?")
    r = chat(
        "Nineteen, compare your strengths with Eleven's strengths. "
        "What tasks would you handle vs what you'd relay to Nineteen?",
        agent='nineteen', new_thread=True, auto_relay=True
    )
    ten_text = get_response_text(r, 'nineteen')
    print_result(7, "Nineteen references Eleven in structured comparison", r, checks={
        'nineteen_responded': lambda r: len(get_response_text(r, 'nineteen')) > 50,
        'mentions_eleven': lambda r: has_agent_mention(get_response_text(r, 'nineteen'), 'eleven'),
    })

    # ── TEST 8: Relay chain — 3-turn back and forth ──────────────────
    print("\n>>> Test 8: 3-turn back-and-forth thread")
    # Turn 1: Nineteen starts
    r1 = chat(
        "Nineteen, propose a database schema for storing agent conversation history. "
        "Keep it to 3-4 tables max.",
        agent='nineteen', new_thread=True, auto_relay=True
    )
    print_result(8, "3-turn thread — turn 1 (Nineteen: schema proposal)", r1)
    conv8 = r1.get('conversation_id')

    if conv8:
        # Turn 2: Eleven critiques
        r2 = chat(
            "Eleven, review Nineteen's schema proposal above. What would you change "
            "or improve? Be specific about which tables/columns.",
            agent='eleven', conv_id=conv8, auto_relay=True
        )
        print_result(8, "3-turn thread — turn 2 (Eleven: critique)", r2, checks={
            'eleven_responded': lambda r: len(get_response_text(r, 'eleven')) > 50,
        })

        # Turn 3: Nineteen responds to critique
        r3 = chat(
            "Nineteen, respond to Eleven's feedback. Do you agree with their changes? "
            "Give a final revised schema.",
            agent='nineteen', conv_id=conv8, auto_relay=True
        )
        print_result(8, "3-turn thread — turn 3 (Nineteen: revised schema)", r3, checks={
            'nineteen_responded': lambda r: len(get_response_text(r, 'nineteen')) > 50,
        })

    # ── TEST 9: Auto-relay detects relay language in prompt ──────────
    print("\n>>> Test 9: Natural relay language — 'ask Eleven'")
    r = chat(
        "What's the difference between asyncio and threading in Python? "
        "After you explain, ask Eleven for a creative analogy to explain it "
        "to a non-technical person.",
        agent='nineteen', new_thread=True, auto_relay=True
    )
    print_result(9, "Natural relay language — 'ask Eleven'", r, checks={
        'nineteen_responded': lambda r: len(get_response_text(r, 'nineteen')) > 50,
    })

    # ── TEST 10: Both agents debate with structured turns ────────────
    print("\n>>> Test 10: Structured debate with back-and-forth")
    # Turn 1: Both give opening positions
    r1 = chat(
        "Debate topic: 'AI agents should be stateless between conversations.' "
        "Nineteen argues FOR statelessness, Eleven argues AGAINST. "
        "Each give 2 strong arguments in your opening statement.",
        agents=['nineteen', 'eleven'], new_thread=True, auto_relay=True
    )
    print_result(10, "Debate — opening statements", r1, checks={
        'both_responded': lambda r: len([
            k for k, v in r.get('results', {}).items()
            if isinstance(v, dict) and len(str(v.get('response', ''))) > 30
        ]) >= 2,
    })
    conv10 = r1.get('conversation_id')

    if conv10:
        # Turn 2: Each rebuts the other
        r2 = chat(
            "Now each of you: rebut the other agent's strongest argument. "
            "Reference what they specifically said and explain why you disagree.",
            agents=['nineteen', 'eleven'], conv_id=conv10, auto_relay=True
        )
        print_result(10, "Debate — rebuttals", r2, checks={
            'has_responses': lambda r: len([
                k for k, v in r.get('results', {}).items()
                if isinstance(v, dict) and len(str(v.get('response', ''))) > 20
            ]) >= 1,
        })

    # ── SUMMARY ──────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("RELAY TEST SUMMARY")
    print(f"{'='*80}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    if errors:
        for e in errors:
            print(f"  - {e}")
    print(f"\nFinished: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    return failed


if __name__ == '__main__':
    exit_code = run_tests()
    sys.exit(exit_code)
