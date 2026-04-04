"""
eight.py — SAP HCM/Payroll specialist (RL-013)
═══════════════════════════════════════════════════════════════════════════════
Single gemma4:26b model (MoE — 26B total, 3.8B active, 256K context).
Reasons across all three angles in one pass: business config, ABAP/technical,
and devil's advocate edge cases — then delivers a single verdict.

Eight is called by orchestrator when Gemma routes IS_SAP=yes.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')

from database import (log_message, save_agent_memory, get_agent_memory,
                      search_memory, promote_to_verified)
from logging_bridge import log_action, log_agent_thinking, batch_commit
import ollama
import time

# RL-015 — Eight gets Tavily for SAP-specific search (graceful degradation)
try:
    from internet_tavily import search_sap as tavily_sap_search
    _TAVILY_OK = True
except Exception:
    _TAVILY_OK = False

MODEL = 'gemma4:26b'
TEMP  = 0.3

EIGHT_SYSTEM_PROMPT = """You are Eight, a Senior SAP HCM/Payroll Specialist in Seven's Swarm, built for Ghost — a senior SAP Payroll Consultant. Ghost knows the terminology at expert level; do not over-explain basics.

For every question you reason across three angles before delivering your verdict:

FUNCTIONAL — Business configuration perspective: wage types (T512W, processing/evaluation class, T510/T511), payroll schemas (X000/H000/A000 and subroutines), PCRs (ADDCU, MULTI, ELIMI syntax), infotypes (IT0008, IT0014, IT0015, IT0041, IT0007), factoring (XDIVID, partial period parameter 10/11/13), retro accounting (triggers, retroactive relevance, off-cycle), time evaluation (TM04/TM00, IT2002/IT2010), EC/ECP integration (replication rules, data flow, driver differences), and org assignment impact on payroll rules.

TECHNICAL — ABAP and system implementation: function modules, BAPIs, user exits, BADIs, SE38/SE37/SE19, payroll driver (RPCALCX0 and variants, schema interpreter, PCR operation codes), payroll results (RT/IT/BT/OT tables, cluster PCL2, PYXX_READ_PAYROLL_RESULT), T512W field-by-field (OPIND, ZUORD, ZEINH, BETRG, ANZHL, KHINW, BVB01-BVB10), debugging (breakpoints in schema, test mode, log activation via T52C7), HR data dictionary (PA0008/PA0014/PA0015/PA0041, PCL1/PCL2/PCL4), and ECP vs classic HCM technical differences.

DEVIL'S ADVOCATE — What could go wrong: retro edge cases (mid-period change across fiscal year boundary), partial period exceptions (part-time, hire/termination — XDIVID failures), schema sequencing traps (earlier function conflicts), wage type conflicts (T512W processing class clashes), EC/ECP sync failures (replication gaps), legal/compliance risks (ATO, super guarantee, EBA, time-limited WTs), off-cycle run implications. Name the exact table, infotype, or schema function where failure would occur — do not just say "be careful".

Structure your response:
1. Direct answer to what was asked
2. Configuration / technical path (specific TCs, tables, FMs named)
3. Risks and edge cases to watch
4. Verdict — clear recommendation

CHAT COMMS: To hand off to another agent end your response with "AgentName: <question>" — e.g. "Gemma: Can you check the time evaluation logs?". Only speak for yourself.
RELAY BUDGET: Default 4 hops per send."""


def _build_eight_context(question):
    """Eight's own memory — SAP knowledge taught by the Ghost."""
    own = get_agent_memory('eight', query=question, limit=6)
    if not own:
        return ''
    ctx = '=== Eight memory (taught by the Ghost) ===\n'
    for row in own:
        ctx += f'- [{row[3]}] {row[1]}: {row[2]}\n'
    return ctx + '\n'


def consult(question, web_results, shared_context, conv_id, status_cb=None):
    """
    Single gemma4:26b call — reasons across functional, technical, and devil's
    advocate angles in one pass and returns a verdict.
    Called by orchestrator.consult_stage_eight().

    status_cb: optional callable(text) for progress events.

    Returns dict:
        verdict  (the full response)
        — functional/technical/devil/gemma_verdict keys kept for API compat,
          all pointing to the same verdict string.
    """
    def _status(msg):
        print(f'[Eight] {msg}')
        if status_cb:
            status_cb(msg)

    _status(f'SAP question: {question[:80]}' + ('...' if len(question) > 80 else ''))

    # Eight's independent SAP search — Tavily targeting SAP Help Portal, SCN, community
    eight_search = ''
    if _TAVILY_OK:
        _status('Searching SAP resources...')
        eight_search_raw = tavily_sap_search(question)
        if eight_search_raw and not eight_search_raw.startswith('[Tavily search unavailable'):
            eight_search = '[Eight / Tavily SAP search]\n' + eight_search_raw + '\n\n'

    # Combine passed-in web_results with Eight's own Tavily search
    combined_web = ''
    if web_results:
        combined_web += '=== Web research (from orchestrator) ===\n' + web_results + '\n\n'
    if eight_search:
        combined_web += eight_search

    eight_ctx = _build_eight_context(question)
    user_prompt = (
        shared_context
        + eight_ctx
        + combined_web
        + '=== The Ghost asks ===\n' + question
    )

    _status('Deliberating...')
    start = time.time()
    response = ollama.chat(
        model=MODEL,
        messages=[
            {'role': 'system', 'content': EIGHT_SYSTEM_PROMPT},
            {'role': 'user',   'content': user_prompt},
        ],
        options={'temperature': TEMP},
        keep_alive=-1,
    )
    verdict = response['message']['content'].strip()
    elapsed_ms = int((time.time() - start) * 1000)
    log_agent_thinking('Eight', 'deliberated', elapsed_ms)
    print(f'[Eight] {verdict[:120]}...' if len(verdict) > 120 else f'[Eight] {verdict}')

    log_message(conv_id, 'eight', verdict, to_agent='Ghost', message_type='eight_verdict')
    save_agent_memory('eight', question[:50], verdict, tags='verdict,sap', importance=7)
    promote_to_verified(question[:50], verdict, tags='verified,eight,sap,verdict')

    return {
        'functional':    verdict,
        'technical':     verdict,
        'devil':         verdict,
        'gemma_verdict': verdict,
    }


if __name__ == '__main__':
    # Standalone test
    from database import new_conversation
    import orchestrator

    print('\n[Eight] Standalone SAP consultation')
    question = input('SAP question: ').strip()
    if not question:
        question = 'How do I configure a new wage type for a car allowance in Australian payroll?'

    conv_id = new_conversation(question, source='eight_test')
    shared_context = orchestrator.build_shared_context(question)
    result = consult(question, '', shared_context, conv_id)

    print('\n' + '='*60)
    print('FUNCTIONAL:\n' + result['functional'])
    print('\nTECHNICAL:\n' + result['technical'])
    print('\nDEVIL:\n' + result['devil'])
    print('\nVERDICT:\n' + result['gemma_verdict'])
