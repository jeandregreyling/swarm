"""
eight.py — SAP HCM/Payroll specialist (RL-013)
═══════════════════════════════════════════════════════════════════════════════
Three internal voices reason from different angles:
  Functional  — business/config logic (wage types, schemas, PCRs, infotypes)
  Technical   — ABAP/system implementation (FMs, BAPIs, PCL2, debug paths)
  Devil       — edge cases, risks, retro traps, ECP sync gaps

Gemma synthesises into a single verdict for the Ghost.
Eight is called by orchestrator when Gemma routes IS_SAP=yes.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')

from database import (log_message, save_agent_memory, get_agent_memory,
                      search_memory, promote_to_verified)
from config import (EIGHT_FUNCTIONAL_PROMPT, EIGHT_TECHNICAL_PROMPT,
                    EIGHT_DEVIL_PROMPT, EIGHT_SYNTHESIS_PROMPT)
import ollama

# RL-015 — Eight gets Tavily for SAP-specific search (graceful degradation)
try:
    from internet_tavily import search_sap as tavily_sap_search
    _TAVILY_OK = True
except Exception:
    _TAVILY_OK = False

# Eight uses qwen2.5 for all three voices — same base model, different persona
# and temperature. Functional/Technical are precise (0.2), Devil is looser (0.6).
MODEL      = 'qwen2.5:latest'
TEMP_PRECISE = 0.2
TEMP_DEVIL   = 0.6


def _ask_voice(voice_name, system_prompt, user_prompt, temperature):
    print(f'\n[Eight/{voice_name}] thinking...')
    response = ollama.chat(
        model=MODEL,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user',   'content': user_prompt},
        ],
        options={'temperature': temperature}
    )
    answer = response['message']['content'].strip()
    print(f'[Eight/{voice_name}] {answer[:120]}...' if len(answer) > 120 else f'[Eight/{voice_name}] {answer}')
    return answer


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
    Run Eight's three-voice deliberation and return all outputs.
    Called by orchestrator.consult_stage_eight().

    status_cb: optional callable(text) — called between voices so callers
               (e.g. terminal.py) can push progress events without blocking.

    Returns dict:
        functional, technical, devil, gemma_verdict
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

    # Combine passed-in web_results (LLaMA's DDG) with Eight's own Tavily search
    combined_web = ''
    if web_results:
        combined_web += '=== Web research (from orchestrator) ===\n' + web_results + '\n\n'
    if eight_search:
        combined_web += eight_search

    web_ctx   = combined_web
    eight_ctx = _build_eight_context(question)
    base      = shared_context + eight_ctx + web_ctx + '=== The Ghost asks ===\n' + question + '\n\n'

    # ── Voice 1: Functional ───────────────────────────────────────────────────
    _status('Eight/Functional deliberating...')
    functional = _ask_voice(
        'Functional',
        EIGHT_FUNCTIONAL_PROMPT,
        base + 'Reason from the business configuration perspective. Trace the dependency chain.',
        TEMP_PRECISE
    )
    log_message(conv_id, 'Eight/Functional', functional, message_type='eight_voice')
    save_agent_memory('eight', question[:50], functional,
                      tags='functional,config', importance=7)

    # ── Voice 2: Technical ────────────────────────────────────────────────────
    _status('Eight/Technical deliberating...')
    technical = _ask_voice(
        'Technical',
        EIGHT_TECHNICAL_PROMPT,
        base +
        'Functional voice said:\n' + functional + '\n\n'
        'Now reason from the ABAP and system implementation perspective. '
        'Name the specific objects, TCs, FMs, tables involved.',
        TEMP_PRECISE
    )
    log_message(conv_id, 'Eight/Technical', technical, message_type='eight_voice')
    save_agent_memory('eight', question[:50], technical,
                      tags='technical,abap', importance=7)

    # ── Voice 3: Devil's Advocate ─────────────────────────────────────────────
    _status("Eight/Devil's Advocate deliberating...")
    devil = _ask_voice(
        'Devil',
        EIGHT_DEVIL_PROMPT,
        base +
        'Functional voice said:\n' + functional + '\n\n'
        'Technical voice said:\n' + technical + '\n\n'
        'Find the edge cases, risks, and gaps. Be specific about where things break.',
        TEMP_DEVIL
    )
    log_message(conv_id, 'Eight/Devil', devil, message_type='eight_voice')

    # ── Gemma synthesises ─────────────────────────────────────────────────────
    _status('Gemma synthesising SAP verdict...')
    synthesis_prompt = (
        EIGHT_SYNTHESIS_PROMPT + '\n\n'
        '=== The Ghost asks ===\n' + question + '\n\n'
        '=== Functional voice ===\n' + functional + '\n\n'
        '=== Technical voice ===\n' + technical + '\n\n'
        '=== Devil\'s Advocate ===\n' + devil + '\n\n'
        'Deliver the final SAP verdict.'
    )
    response = ollama.chat(
        model='gemma3:latest',
        messages=[{'role': 'user', 'content': synthesis_prompt}],
        options={'temperature': 0.3}
    )
    gemma_verdict = response['message']['content'].strip()
    print(f'[Eight/Gemma] {gemma_verdict[:120]}...' if len(gemma_verdict) > 120 else f'[Eight/Gemma] {gemma_verdict}')

    log_message(conv_id, 'Eight/Gemma', gemma_verdict, to_agent='Ghost', message_type='eight_verdict')
    promote_to_verified(question[:50], gemma_verdict, tags='verified,eight,sap,verdict')

    return {
        'functional': functional,
        'technical':  technical,
        'devil':      devil,
        'gemma_verdict': gemma_verdict,
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
