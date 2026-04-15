import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/agents/specialists')
sys.path.insert(0, '/home/seven/swarm/lib/search')
sys.path.insert(0, '/home/seven/swarm/lib/system')
sys.path.insert(0, '/home/seven/swarm/lib/email')

from database import (new_conversation, log_message, save_memory,
                      search_memory, search_project_docs, get_ghost_history,
                      get_all_memories, save_agent_memory, get_agent_memory,
                      save_gemma_verdict, promote_to_verified)
from internet import search_web

# RL-015 — Independent agent search (graceful degradation if not installed)
try:
    from internet_serper import search as serper_search
    _SERPER_OK = True
except Exception as _e:
    print(f'[Orchestrator] Serper not available: {_e}')
    _SERPER_OK = False

try:
    from internet_tavily import search as tavily_search
    _TAVILY_OK = True
except Exception as _e:
    print(f'[Orchestrator] Tavily not available: {_e}')
    _TAVILY_OK = False

# RL-017b — Librarian system health (graceful degradation)
try:
    from monitor import librarian_health_summary as _system_health
    _MONITOR_OK = True
except Exception as _e:
    print(f'[Orchestrator] Monitor not available: {_e}')
    _MONITOR_OK = False
    def _system_health(): return ''

from email_cleaner import filter_non_english
from system_clock import get_system_clock
from config import (GEMMA_SYSTEM_PROMPT, LLAMA_SYSTEM_PROMPT,
                     QWEN_SYSTEM_PROMPT, LIBRARIAN_SYSTEM_PROMPT,
                     MISTRAL_SYSTEM_PROMPT)
from logging_bridge import log_action, log_agent_thinking, batch_commit
import ollama
import logging
import time
import os

try:
    import psutil
    _PSUTIL_OK = True
except Exception:
    _PSUTIL_OK = False

logger = logging.getLogger('seven.orchestrator')


def _get_eight_module():
    """Resolve Eight via package path first, then legacy path."""
    try:
        from agents.specialists import eight as eight_module
        return eight_module
    except Exception:
        import eight as eight_module
        return eight_module

# ── Agent models/temps — DB registry is source of truth, inline dict is fallback ──
try:
    from utils.db.registry import (
        get_agent_models  as _reg_models_orch,
        get_agent_temps   as _reg_temps_orch,
        get_agent_prompts as _reg_prompts_orch,
        get_keep_alive_map as _reg_keep_alive_orch,
    )
    _REGISTRY_AVAILABLE = True
except Exception:
    _REGISTRY_AVAILABLE = False

_AGENTS_FALLBACK = {
    'gemma': 'gemma3:latest', 'llama': 'llama3.2:latest', 'mistral': 'mistral:latest',
    'qwen': 'qwen2.5:latest', 'eight': 'gemma4:26b', 'librarian': 'qwen:1.5b',
    'duck': 'qwen:1.5b', 'sniffles': 'deepseek-r1:7b',
}
_TEMPERATURES_FALLBACK = {
    'gemma': 0.3, 'llama': 0.6, 'mistral': 0.7, 'qwen': 0.7,
    'eight': 0.5, 'librarian': 0.1, 'duck': 0.1, 'sniffles': 0.2,
}


def _get_agents():
    if _REGISTRY_AVAILABLE:
        try:
            d = _reg_models_orch(local_only=True)
            if d:
                return d
        except Exception:
            pass
    return _AGENTS_FALLBACK


def _get_temps():
    if _REGISTRY_AVAILABLE:
        try:
            d = _reg_temps_orch(local_only=True)
            if d:
                return d
        except Exception:
            pass
    return _TEMPERATURES_FALLBACK


# Module-level dicts kept for backward compat — consumers that do `orchestrator.AGENTS[x]`
# These are static snapshots; prefer calling _get_agents() / _get_temps() for live data.
AGENTS = dict(_AGENTS_FALLBACK)
TEMPERATURES = dict(_TEMPERATURES_FALLBACK)

EIGHT_CHAT_SYSTEM_PROMPT = (
    "You are Eight, the SAP HCM/Payroll Specialist of Seven's Swarm. "
    "Deep expertise in SAP Payroll config, wage types, PCRs, infotypes, ABAP, and ECP. "
    "Reason from multiple angles: business config, technical implementation, and edge-case risk. "
    "Be direct and specific. Ghost One (Jeandre) is a senior SAP Payroll Consultant — do not over-explain basics.\n\n"
    "CHAT COMMS: Worker Agents: Gemma (orchestrator), LLaMA (researcher), Qwen (analyst), Mistral (generalist), "
    "Eight (you, SAP HCM/Payroll), Duck (sanity checker + ALM auditor), Sniffles (memory auditor), Librarian (memory keeper). "
    "Developer Agents: Nine (system architect), Ten (software engineer), Eleven (lateral thinker), "
    "Twelve (time wizard), Thirteen (HuggingFace \u2014 testing), Scholar (Gemini), Seeker (Tavily). "
    "Ghost Layer: Ghost One (Jeandre, human operator).\n\n"
    "AUTO RELAY CHECK \u2014 REQUIRED: Your prompt starts with [Auto Relay: ENABLED] or [Auto Relay: DISABLED]. "
    "If DISABLED: complete the task yourself \u2014 no AgentName: routing. "
    "If ENABLED: route AFTER your full response with 'AgentName: <question>' on its own line. "
    "Route to the single most relevant agent. Never relay mid-task. RELAY BUDGET: 4 hops per turn.\n\n"
    "SYSTEM RELAY BUTTON: Ghost One can toggle Auto Relay ON/OFF from the Chat toolbar. Always check the [Auto Relay: ...] prefix.\n\n"
    "SKILL ACCESS \u2014 FULL DEVELOPER LEVEL: Real filesystem and ALM access via SKILL commands. "
    "NEVER FAKE IT: No SKILL = nothing happened. Do not claim changes without [skill:...] OK confirmation.\n"
    "SKILL SYNTAX (relative to /home/seven/swarm):\n"
    "  SKILL fs_readonly read <path> | ls <dir> | lines <path> 1 60\n"
    "  SKILL fs_patch <path>\n  <<<OLD>>>\n  exact text\n  <<<NEW>>>\n  replacement\n"
    "  SKILL fs_write sandpits/eight/draft.txt content\n\n"
    "ALM WORKFLOW (for all code changes you initiate):\n"
    "  1. SKILL alm_create_proposal 'Title' 'Description'\n"
    "  2. SKILL alm_vortex before-<label>   \u2190 Vortex checkpoint BEFORE any file touch\n"
    "  3. SKILL alm_self_approve <id>        \u2190 IN PROGRESS \u2014 you own this\n"
    "  4. SKILL fs_patch / fs_write          \u2190 make all changes\n"
    "  5. SKILL fs_readonly lines ... verify \u2190 confirm each patch\n"
    "  6. SKILL alm_complete <id>            \u2190 DONE \u2014 Duck auto-QA checks and posts result to this chat thread\n"
    "Never skip steps 1\u20133. Run autonomously.\n\n"
    "PIPELINE: alm_create_proposal \u2192 Duck auto-reviews and POSTS APPROVED/REJECTED back to THIS thread \u2192 alm_self_approve \u2192 build \u2192 alm_complete \u2192 Duck auto-QA posts result here \u2192 Ghost reviews UAT in Studio \u2192 executed.\n"
    "Always tell Ghost the proposal ID when you create one.\n\n"
    "SANDPIT: sandpits/eight/ for SAP config drafts and proposals. All changes tracked by Git and Vortex."
)

DUCK_SYSTEM_PROMPT = (
    "You are Duck, the sanity checker and ALM auditor of Seven's Swarm. "
    "Give concise, practical quality checks. Call out uncertainty and contradictions quickly. "
    "Your audit role: when agents call alm_complete, you review their work, verify the Vortex checkpoint exists, "
    "check the changes are correct and complete, then approve (post a note and let Ghost review in Studio) "
    "or reopen (post a note explaining what's missing). You are the gatekeeper between DONE and EXECUTED.\n\n"
    "CHAT COMMS: Worker Agents: Gemma (orchestrator), LLaMA (researcher), Qwen (analyst), Mistral (generalist), "
    "Eight (SAP HCM/Payroll specialist), Duck (you, sanity checker + ALM auditor), Sniffles (memory auditor), Librarian (memory keeper). "
    "Developer Agents: Nine (system architect), Ten (software engineer), Eleven (lateral thinker), "
    "Twelve (time wizard), Thirteen (HuggingFace \u2014 testing), Scholar (Gemini), Seeker (Tavily). "
    "Ghost Layer: Ghost One (Jeandre, human operator).\n\n"
    "AUTO RELAY CHECK \u2014 REQUIRED: Your prompt starts with [Auto Relay: ENABLED] or [Auto Relay: DISABLED]. "
    "If DISABLED: complete the task yourself, no routing. "
    "If ENABLED: route AFTER your full response with 'AgentName: <question>'. Never relay mid-task. RELAY BUDGET: 4 hops.\n\n"
    "SYSTEM RELAY BUTTON: Ghost One can toggle Auto Relay ON/OFF from the Chat toolbar. Always check the [Auto Relay: ...] prefix.\n\n"
    "SKILL ACCESS \u2014 FULL DEVELOPER LEVEL: Real filesystem and ALM access via SKILL commands. "
    "NEVER FAKE IT: No SKILL = nothing happened. Do not claim changes without [skill:...] OK confirmation.\n"
    "SKILL SYNTAX (relative to /home/seven/swarm):\n"
    "  SKILL fs_readonly read <path> | ls <dir> | lines <path> 1 60\n"
    "  SKILL fs_patch <path>\n  <<<OLD>>>\n  exact text\n  <<<NEW>>>\n  replacement\n"
    "  SKILL fs_write sandpits/duck/draft.txt content\n\n"
    "ALM WORKFLOW (for changes you initiate):\n"
    "  1. SKILL alm_create_proposal 'Title' 'Description'\n"
    "  2. SKILL alm_vortex before-<label>   \u2190 Vortex checkpoint BEFORE any file touch\n"
    "  3. SKILL alm_self_approve <id>        \u2190 IN PROGRESS \u2014 you own this\n"
    "  4. SKILL fs_patch / fs_write          \u2190 make changes\n"
    "  5. SKILL fs_readonly lines ... verify \u2190 confirm each patch\n"
    "  6. SKILL alm_complete <id>            \u2190 DONE \u2014 you auto-QA check and post result to this chat thread\n\n"
    "PIPELINE (know this): alm_create_proposal \u2192 you auto-review and POST APPROVED/REJECTED back to originating thread \u2192 agent does alm_self_approve \u2192 builds \u2192 alm_complete \u2192 you auto-QA and post result \u2192 status \u2192 UAT \u2192 Ghost reviews \u2192 executed.\n"
    "When Ghost asks you to 'check the proposal', look up the latest pending proposal in work_proposals via SKILL fs_readonly, then give your verdict.\n\n"
    "SANDPIT: sandpits/duck/ for audit notes and drafts. All changes tracked by Git and Vortex."
)

SNIFFLES_SYSTEM_PROMPT = (
    "You are Sniffles, the swarm memory and quality auditor. Focus on factual consistency, "
    "risk flags, and whether claims are verifiable. You run structured audits on swarm memory "
    "and agent outputs, flag anomalies, and post findings to the originating conversation thread.\n\n"
    "CHAT COMMS: Worker Agents: Gemma (orchestrator), LLaMA (researcher), Qwen (analyst), Mistral (generalist), "
    "Eight (SAP HCM/Payroll specialist), Duck (sanity checker + ALM auditor), Sniffles (you, memory auditor), Librarian (memory keeper). "
    "Developer Agents: Nine (system architect), Ten (software engineer), Eleven (lateral thinker), "
    "Twelve (time wizard), Thirteen (HuggingFace \u2014 testing), Scholar (Gemini), Seeker (Tavily). "
    "Ghost Layer: Ghost One (Jeandre, human operator).\n\n"
    "AUTO RELAY CHECK \u2014 REQUIRED: Your prompt starts with [Auto Relay: ENABLED] or [Auto Relay: DISABLED]. "
    "If DISABLED: complete the task yourself, no routing. "
    "If ENABLED: route AFTER your full audit with 'AgentName: <question>'. Never relay mid-task. RELAY BUDGET: 4 hops.\n\n"
    "SYSTEM RELAY BUTTON: Ghost One can toggle Auto Relay ON/OFF from the Chat toolbar. Always check the [Auto Relay: ...] prefix.\n\n"
    "SKILL ACCESS \u2014 FULL DEVELOPER LEVEL: Real filesystem and ALM access via SKILL commands. "
    "NEVER FAKE IT: No SKILL = nothing happened. Do not claim changes without [skill:...] OK confirmation.\n"
    "SKILL SYNTAX (relative to /home/seven/swarm):\n"
    "  SKILL fs_readonly read <path> | ls <dir> | lines <path> 1 60\n"
    "  SKILL fs_patch <path>\n  <<<OLD>>>\n  exact text\n  <<<NEW>>>\n  replacement\n"
    "  SKILL fs_write sandpits/sniffles/audit-report.txt content\n\n"
    "ALM WORKFLOW (for changes you initiate):\n"
    "  1. SKILL alm_create_proposal 'Title' 'Description'\n"
    "  2. SKILL alm_vortex before-<label>   \u2190 Vortex checkpoint BEFORE any file touch\n"
    "  3. SKILL alm_self_approve <id>        \u2190 IN PROGRESS \u2014 you own this\n"
    "  4. SKILL fs_patch / fs_write\n"
    "  5. SKILL fs_readonly lines ... verify\n"
    "  6. SKILL alm_complete <id>            \u2190 DONE \u2014 Duck auto-QA checks and posts result to this chat thread\n\n"
    "PIPELINE: alm_create_proposal \u2192 Duck auto-reviews and POSTS APPROVED/REJECTED back to originating thread \u2192 agent alm_self_approve \u2192 builds \u2192 alm_complete \u2192 Duck auto-QA posts result \u2192 UAT \u2192 Ghost reviews \u2192 executed.\n\n"
    "SANDPIT: sandpits/sniffles/ for audit reports and drafts. All changes tracked by Git and Vortex."
)

_SYSTEM_PROMPTS_INLINE = {
    'gemma':     GEMMA_SYSTEM_PROMPT,
    'llama':     LLAMA_SYSTEM_PROMPT,
    'mistral':   MISTRAL_SYSTEM_PROMPT,
    'qwen':      QWEN_SYSTEM_PROMPT,
    'eight':     EIGHT_CHAT_SYSTEM_PROMPT,
    'librarian': LIBRARIAN_SYSTEM_PROMPT,
    'duck':      DUCK_SYSTEM_PROMPT,
    'sniffles':  SNIFFLES_SYSTEM_PROMPT,
    'ten':       'You are Ten, a Developer Agent (software engineer) in Seven\'s Swarm. Your role is to provide code quality, clarity, and architectural insights. Ghost One (Jeandre, senior SAP Payroll Consultant) is the human operator. Execute Ghost One-directed requests immediately.',
}


def _get_system_prompts():
    """Return system prompts dict — DB registry first, fallback to inline."""
    if _REGISTRY_AVAILABLE:
        try:
            d = _reg_prompts_orch()
            if d:
                # Merge: DB wins, inline fills gaps
                merged = dict(_SYSTEM_PROMPTS_INLINE)
                merged.update(d)
                return merged
        except Exception:
            pass
    return _SYSTEM_PROMPTS_INLINE


SYSTEM_PROMPTS = dict(_SYSTEM_PROMPTS_INLINE)  # static snapshot for backward compat

# All models stay resident indefinitely — the 127 GB NVMe swap handles memory
# pressure by paging idle models out and back in at ~2-3 GB/s.
# RAM residents: gemma, llama, qwen, duck, librarian.
# NVMe-swap residents (larger / less frequent): eight (qwen2.5 ×3), sniffles (deepseek-r1).
# Active agents — prewarmed and kept resident in RAM/NVMe swap.
# qwen is on the virtual RAM layer: present in AGENTS but NOT prewarmed.
# Load qwen manually via /api/ollama/load when a second analyst voice is needed.
_MODEL_KEEP_ALIVE_FALLBACK = {agent: -1 for agent in ('gemma', 'llama', 'mistral', 'qwen', 'librarian', 'duck', 'sniffles', 'eight')}

def _get_keep_alive():
    if _REGISTRY_AVAILABLE:
        try:
            d = _reg_keep_alive_orch()
            if d:
                return d
        except Exception:
            pass
    return _MODEL_KEEP_ALIVE_FALLBACK

MODEL_KEEP_ALIVE = dict(_MODEL_KEEP_ALIVE_FALLBACK)

# Per-agent token counts from last successful ask_agent() call.
# Keyed by lowercase agent name. Written by ask_agent(); read by terminal._run_single_agent().
# Safe under the _CHAT_SINGLE_TASK_LOCAL_AGENTS constraint (one job per agent at a time).
_LAST_EVAL_COUNT: dict = {}

MIN_FREE_GB_FOR_BOTH = float(os.environ.get('SWARM_MIN_FREE_GB_FOR_BOTH', '7.0'))


def _available_memory_gb():
    if not _PSUTIL_OK:
        return None
    try:
        return round(psutil.virtual_memory().available / (1024 ** 3), 2)
    except Exception:
        return None


def _apply_local_memory_policy(routing):
    """Prefer LLaMA-only when memory headroom is low unless debate explicitly needs both."""
    avail_gb = _available_memory_gb()
    if avail_gb is None:
        return routing

    if routing.get('agents') == 'both' and routing.get('mode') != 'debate' and avail_gb < MIN_FREE_GB_FOR_BOTH:
        routing['agents'] = 'llama'
        log_action(
            'orchestrator',
            'memory_policy:defer_mistral',
            f'available_gb={avail_gb} < {MIN_FREE_GB_FOR_BOTH}; using llama-only',
            'warn',
        )
    return routing


def _select_keep_alive(agent_name):
    """All agents keep_alive=-1: models stay resident in RAM or NVMe swap
    indefinitely. The OS pages idle models to the 127 GB NVMe swap as needed."""
    ka = _get_keep_alive()
    return ka.get(agent_name, -1)

def ask_agent(agent_name, prompt, retries=2):
    agent_name = agent_name.lower()  # normalize — AGENTS dict uses lowercase keys
    agents_live = _get_agents()
    model = agents_live.get(agent_name) or AGENTS.get(agent_name)
    if not model:
        raise KeyError(f'Unknown agent: {agent_name}')
    prompts_live = _get_system_prompts()
    system = prompts_live.get(agent_name, '')
    temps_live = _get_temps()
    temp = temps_live.get(agent_name, 0.5)
    
    print(f'\n[{get_system_clock().timestamp_compact()}] [{agent_name}] thinking...')
    log_action('orchestrator', f'agent_load:{agent_name}', f'Loading {agent_name}', 'info')

    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})

    start_time = time.time()
    keep_alive = _select_keep_alive(agent_name)
    log_action('orchestrator', f'keepalive:{agent_name}', f'keep_alive={keep_alive}', 'info')
    for attempt in range(retries + 1):
        try:
            response = ollama.chat(
                model=model,
                messages=messages,
                options={'temperature': temp},
                keep_alive=keep_alive,
            )
            answer = response['message']['content']
            # Capture token count for verbose thinking-tile display (non-streaming).
            try:
                ec = int(getattr(response, 'eval_count', None) or response.get('eval_count') or 0)
            except Exception:
                ec = 0
            _LAST_EVAL_COUNT[agent_name] = ec
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_agent_thinking(agent_name, f'responded to prompt', elapsed_ms)
            batch_commit(f'[{agent_name}] completed query')
            return answer
        except Exception as e:
            if attempt == retries:
                elapsed_ms = int((time.time() - start_time) * 1000)
                log_action('orchestrator', f'agent_error:{agent_name}', str(e), 'error')
                raise e
            print(f"[{get_system_clock().timestamp_compact()}] [Orchestrator] {agent_name} failed (attempt {attempt+1}), retrying...")
            time.sleep(2)

def get_time_context():
    now = get_system_clock().now()
    return (
        '=== Current date and time ===\n'
        'Today is ' + now.strftime('%A, %d %B %Y') + '.\n'
        'Current time: ' + now.strftime('%H:%M') + ' AEDT (Melbourne, Australia).\n'
        'Use this for time-sensitive questions.\n\n'
    )

def _swarm_awareness_block():
    """RL-017c — inject swarm roster so agents know who they work with."""
    web_status = []
    if _SERPER_OK:  web_status.append('Gemma→Google/Serper')
    if _TAVILY_OK:  web_status.append('Mistral/Eight→Tavily')
    web_status.append('LLaMA→DuckDuckGo')
    return (
        '=== Swarm roster ===\n'
        'Gemma     — orchestrator, routes all questions, synthesises final answers\n'
        'LLaMA     — researcher, fast answers, DuckDuckGo web access\n'
        'Qwen      — analyst, deep reasoning, Tavily AI search access\n'
        'Eight     — SAP HCM/ABAP specialist, three-voice debate pipeline, Tavily SAP search\n'
        'Librarian — memory keeper, silent indexer, system health awareness\n' 
        'Ten       — Software Engineering Advisor, provides code quality and clarity insights\n'
        'Sniffles  — auditor, deepseek-r1, read-only observer, monitors all agent memory\n'
        'Duck      — sanity checker, verifies Gemma verdicts on every ticket close\n'
        'Search engines active: ' + ', '.join(web_status) + '\n'
        'Developer Agents (online API): Nine (Groq, system architect), Ten (GPT, software engineer), Eleven (Grok, lateral thinker), Twelve (Claude Haiku, time wizard), Thirteen (HuggingFace \u2014 testing)\n'
        'Ghost Layer (human users): Ghost One (Jeandre, operator and approving authority)\n\n'
        '=== Agent autonomy ===\n'
        'When you have been idle for 1+ hour with no active queue, you may draft an improvement proposal.\n'
        'Write your proposal to your sandpit. It will be audited by Sniffles before Ghost reviews it.\n'
        'Proposals are your chance to suggest system improvements, flag patterns you have noticed, or ask Ghost a question about the swarm.\n\n'
        '=== Documentation & Versioning Rules ===\n'
        'All agents MUST date and time stamp (YYYY-MM-DD HH:MM:SS) every change made to documentation.\n'
        'Always use the version control system for any file modification.\n\n'
        '=== Ghost Layer Tools (Nine only) ===\n'
        'You can request filesystem access by outputting these tags in your response:\n'
        '- READ:/path/to/file — triggers a "Grant Read" button for Ghost\n'
        '- LS:/path/to/dir   — triggers a "Grant List" button for Ghost\n'
        '- FILE:/path/to/file — followed by a code block, triggers a "Write" button\n\n'
    )


def build_shared_context(question):
    ghost_history = get_ghost_history(limit=10)
    relevant_memories = search_memory(query=question, min_importance=5)
    context = get_time_context() + _swarm_awareness_block()

    # ── Project docs: inject sections relevant to the question ────────────────
    # Always include the core identity/architecture sections for self-awareness.
    # Also search by question keywords for topic-specific sections.
    _always = ['What We Are Building', 'The Agents', 'Constraints That Must Never Be Broken']
    _seen   = set()
    doc_sections = []
    for name in _always:
        rows = search_project_docs(query=name, limit=1)
        for r in rows:
            if r['doc_name'] not in _seen:
                _seen.add(r['doc_name'])
                doc_sections.append(r)
    # Add question-specific sections (skip ones already included)
    for r in search_project_docs(query=question, limit=3):
        if r['doc_name'] not in _seen:
            _seen.add(r['doc_name'])
            doc_sections.append(r)
    if doc_sections:
        context += '=== Project documentation ===\n'
        for s in doc_sections:
            context += f'--- {s["doc_name"]} ---\n{s["content"]}\n\n'

    if relevant_memories:
        context += '=== Shared verified memories ===\n'
        for m in relevant_memories:
            context += '- [' + str(m['tags']) + '] ' + str(m['subject']) + ': ' + str(m['content']) + '\n'
        context += '\n'
    if ghost_history:
        context += '=== What the Ghost has asked previously ===\n'
        for h in ghost_history:
            context += '- [' + str(h['created_at']) + '] Ghost asked: ' + str(h['content']) + '\n'
        context += '\n'
    return context

def build_agent_context(agent, question):
    own_memories = get_agent_memory(agent, query=question, limit=5)
    if not own_memories:
        return ''
    context = '=== Your own memory on this topic ===\n'
    for m in own_memories:
        context += '- [' + str(m[3]) + '] ' + str(m[1]) + ': ' + str(m[2]) + '\n'
    context += '\n'
    return context

_DISAGREEMENT_SIGNALS = [
    'disagree', 'incorrect', "that's wrong", 'not accurate', 'however, llama',
    'contradicts', 'misleading', 'inaccurate', 'i differ', 'disputes',
    'refute', 'i must correct', 'llama is wrong', 'llama missed',
    'actually,', 'on the contrary', 'this is wrong',
]

def _detect_disagreement(text):
    t = text.lower()
    return any(sig in t for sig in _DISAGREEMENT_SIGNALS)


def _run_debate_r2(question, web_context, llama_r1, mistral_r1, conv_id):
    """Challenge round: each agent reacts to the other's R1. Returns (llama_r2, mistral_r2)."""
    print('\n[Debate] Round 2 — challenge...')
    llama_challenge_prompt = (
        web_context +
        'You are LLaMA in a live debate.\n\n'
        'You said: ' + llama_r1 + '\n\n'
        'Mistral said: ' + mistral_r1 + '\n\n'
        'Do you agree or disagree with Mistral? If you disagree, state exactly what is wrong and why. '
        'If you agree, add something Mistral missed. Be direct. 2-3 sentences only.'
    )
    llama_r2 = ask_agent('LLaMA', llama_challenge_prompt)
    log_message(conv_id, 'LLaMA', llama_r2, message_type='debate_r2')

    mistral_challenge_prompt = (
        web_context +
        'You are Mistral in a live debate.\n\n'
        'You said: ' + mistral_r1 + '\n\n'
        'LLaMA said: ' + llama_r1 + '\n\n'
        'Do you agree or disagree with LLaMA? If you disagree, state exactly what is wrong and why. '
        'If you agree, add something LLaMA missed. Be direct. 2-3 sentences only.'
    )
    mistral_r2 = ask_agent('Mistral', mistral_challenge_prompt)
    log_message(conv_id, 'Mistral', mistral_r2, message_type='debate_r2')
    return llama_r2, mistral_r2


def tag_content(content):
    prompt = 'TAGS ONLY. 3-5 comma-separated single word tags: ' + content[:300]
    raw = ask_agent('Librarian', prompt).strip()
    for line in raw.split('\n'):
        line = line.strip()
        if ',' in line and len(line) < 100 and not line.endswith('?'):
            return line
    return raw[:100]

def librarian_index(conv_id, subject, content):
    tags = tag_content(content)
    save_memory('Librarian', subject, content, tags=tags, importance=7)
    log_message(conv_id, 'Librarian',
                'Indexed: ' + subject + ' | tags: ' + tags,
                message_type='index')
    return tags


# RL-LIBRARIAN-RELAY — Librarian as implicit relay monitor
_LIBRARIAN_RELAY_REVIEW_SYSTEM = (
    'You are the Librarian, the relay monitor for Seven\'s Swarm. '
    'Your only job right now is to detect implicit agent handoffs in a message.\n\n'
    'An implicit handoff is when an agent\'s response suggests that another agent should '
    'respond, take over a task, or handle something — even without explicit routing syntax '
    'like "Agent:" or "@agent".\n\n'
    'Examples of implicit handoffs:\n'
    '- "I think Mistral would be better at analysing this." → mistral\n'
    '- "LLaMA knows more about internet search." → llama\n'
    '- "This is a memory/indexing task." → librarian\n'
    '- Trailing off with "... Mistral, what do you think?" → mistral\n'
    '- "A researcher would find this easily." → llama (researcher role)\n\n'
    'Known agents:\n'
    '  Local — gemma (orchestrator), llama (researcher, internet access), '
    'mistral (analyst, deep reasoning), eight (SAP/HR specialist), '
    'sniffles (memory/accuracy auditor), duck (sanity checker / contradiction detector), '
    'librarian (memory keeper + relay monitor).\n'
    '  Ghost Layer (online) — nine (Claude Sonnet, system architect), '
    'ten (GPT, engineering advisor), eleven (Grok, lateral thinker), '
    'twelve (Claude Haiku, time wizard), scholar (Gemini, vision & reasoning), '
    'seeker (Tavily, real-time web search).\n\n'
    'Do NOT flag patterns already captured by explicit @agent or "Agent: " prefixes. '
    'Only flag genuinely implicit signals.\n\n'
    'Respond ONLY as valid JSON. Nothing else. No explanation. No markdown fences.\n'
    '{"candidates":[{"target":"mistral","question":"Can you analyse this data?"}]}\n'
    'If no implicit handoffs exist: {"candidates":[]}'
)


def librarian_relay_review(text, from_agent, timeout_s=18):
    """
    Ask Librarian to detect implicit relay candidates in an agent response.
    Does NOT use the tagging system prompt — uses a purpose-built relay-review prompt.
    Returns a list of {target, question} dicts. Always safe to call; returns [] on error.
    """
    import json as _json
    clean_text = str(text or '').strip()
    if not clean_text or len(clean_text) < 20:
        return []
    from_key = str(from_agent or 'agent').lower().strip()
    prompt = (
        f'Message from {from_key}:\n\n'
        f'{clean_text[:1200]}\n\n'
        'Detect any implicit handoffs to other agents. Respond only with the JSON format specified.'
    )
    model = AGENTS.get('librarian', 'qwen:latest')
    keep_alive = MODEL_KEEP_ALIVE.get('librarian', '20m')
    messages = [
        {'role': 'system', 'content': _LIBRARIAN_RELAY_REVIEW_SYSTEM},
        {'role': 'user', 'content': prompt},
    ]
    start = time.time()
    try:
        response = ollama.chat(
            model=model,
            messages=messages,
            options={'temperature': 0.05},
            keep_alive=keep_alive,
        )
        raw = str(response['message']['content'] or '').strip()
        elapsed_ms = int((time.time() - start) * 1000)
        log_action('librarian', 'relay_review', f'from={from_key} elapsed={elapsed_ms}ms', 'info')
        # Extract JSON — strip fences if model adds them anyway
        if '```' in raw:
            raw = raw.split('```')[-2].strip() if raw.count('```') >= 2 else raw.replace('```', '').strip()
        parsed = _json.loads(raw)
        candidates = parsed.get('candidates', [])
        if not isinstance(candidates, list):
            return []
        valid = []
        for c in candidates:
            target = str(c.get('target') or '').lower().strip()
            question = str(c.get('question') or '').strip()
            if target and question and target != from_key:
                valid.append({'target': target, 'question': question})
        return valid
    except Exception as e:
        log_action('librarian', 'relay_review_error', str(e), 'warn')
        return []


_SAP_KEYWORDS = [
    'sap', 'abap', 'hcm', 'payroll', 'wage type', 'infotype', 'it0008',
    'schema', ' pcr ', 'personnel calculation', 'rpcalcx0', 'ecp', 'ec payroll',
    'factoring', 'xdivid', 'retro', 'retroactive', 't512w', 't510', 't511',
    'processing class', 'evaluation class', 'cluster pcl', 'hrforms',
    'time evaluation', 'bapi_payroll', 'employee central', 'successfactors',
    'superannuation', 'stp ', 'payslip', 'garnishment',
]

def _keyword_is_sap(question):
    q = question.lower()
    return any(kw in q for kw in _SAP_KEYWORDS)


def gemma_route(question, context):
    print('\n[Gemma] reading question and deciding route...')
    routing_prompt = (
        context +
        '=== Your job right now ===\n'
        'Read this question and decide how to handle it.\n'
        'Question: ' + question + '\n\n'
        'Reply in this exact format, nothing else:\n'
        'NEEDS_WEB: yes/no\n'
        'NEEDS_BROWSER: yes/no\n'
        'NEEDS_SHELL: yes/no\n'
        'AGENTS: llama/mistral/both\n'
        'MODE: consult/debate\n'
        'IS_IDENTITY: yes/no\n'
        'IS_SAP: yes/no\n'
        'IS_SYSTEM: yes/no\n'
        'REASON: one sentence\n\n'
        'Rules:\n'
        '- IS_IDENTITY=yes ONLY for: who are you, what is your role, tell me about the swarm, questions about Gemma/LLaMA/Mistral/Librarian/Sniffles/Ghost/Nine\n'
        '- IS_IDENTITY=no for ALL factual, geographic, scientific, historical, weather questions\n'
        '- IS_SAP=yes for any question involving SAP, HCM, ABAP, payroll configuration, wage types, infotypes, schemas, PCRs, ECP, EC Payroll, retro accounting\n'
        '- IS_SAP=no for everything else\n'
        '- IS_SYSTEM=yes for questions about RAM, CPU, temperature, disk usage, uptime, memory pool counts, active Ollama model, swarm hardware health, or how many consultations today\n'
        '- IS_SYSTEM=no for everything else\n'
        '- NEEDS_BROWSER=yes when the question contains a URL (http:// or https://) or asks to read/summarise/check a specific webpage\n'
        '- NEEDS_BROWSER=no for general web searches — web search handles those\n'
        '- NEEDS_SHELL=yes when asked to run a command, check a service, list files, check disk/memory, or execute something on the system\n'
        '- NEEDS_SHELL=no for everything else\n'
        '- When IS_SAP=yes: Eight handles the question, set AGENTS=eight\n'
        '- When IS_SYSTEM=yes: Librarian answers using live system data injected into context, set AGENTS=llama\n'
        '- Simple factual questions: AGENTS=llama, NEEDS_WEB=yes\n'
        '- Complex analysis or opinion: AGENTS=both, NEEDS_WEB=yes\n'
        '- Controversial topics where agents might disagree: MODE=debate\n'
        '- Questions answerable from memory: NEEDS_WEB=no\n'
        '- When in doubt: IS_IDENTITY=no, IS_SAP=no, IS_SYSTEM=no, NEEDS_BROWSER=no, NEEDS_SHELL=no\n'
        '- NEVER IS_IDENTITY=yes for: geography, weather, science, history, buildings, streets, sports, food\n'
    )
    response = ask_agent('Gemma', routing_prompt)
    import re
    r = response.lower().strip()
    
    def _get_val(key, default='no'):
        match = re.search(rf'{key}:\s*(\w+)', r)
        return match.group(1) if match else default

    is_sap_gemma = 'yes' in _get_val('is_sap')
    needs_web = 'yes' in _get_val('needs_web', 'yes')
    is_system = 'yes' in _get_val('is_system')
    # Normalise agents: Gemma sometimes returns 'llama/mistral' meaning both agents
    _agents_raw = _get_val('agents', 'llama')
    if 'llama' in _agents_raw and ('mistral' in _agents_raw or 'qwen' in _agents_raw):
        _agents = 'both'
    elif 'mistral' in _agents_raw or 'qwen' in _agents_raw:
        _agents = 'mistral'
    elif 'llama' in _agents_raw:
        _agents = 'llama'
    else:
        _agents = 'both'

    needs_browser = 'yes' in _get_val('needs_browser')
    
    # Also auto-detect URL in question — Gemma may miss it
    if not needs_browser:
        needs_browser = bool(re.search(r'https?://', question))

    needs_shell = 'yes' in _get_val('needs_shell')

    routing = {
        'needs_web':      needs_web,
        'needs_browser':  needs_browser,
        'needs_shell':    needs_shell,
        'agents':         _agents,
        'mode':           _get_val('mode', 'consult'),
        'is_identity':    'yes' in _get_val('is_identity'),
        'is_sap':         is_sap_gemma or _keyword_is_sap(question),
        'is_system':      is_system,
        'search_engines': (['ddg'] + (['serper'] if _SERPER_OK else []) + (['tavily'] if _TAVILY_OK else []))
                          if needs_web else [],
    }
    routing = _apply_local_memory_policy(routing)
    print(f'[Gemma routes] web={routing["needs_web"]} browser={routing["needs_browser"]} '
          f'shell={routing["needs_shell"]} agents={routing["agents"]} '
          f'identity={routing["is_identity"]} mode={routing["mode"]} '
          f'sap={routing["is_sap"]} system={routing["is_system"]}')
    return routing


def consult_stage_eight(question, web_results, shared_context, conv_id, status_cb=None):
    """Called by terminal/listener when routing IS_SAP=yes."""
    eight_module = _get_eight_module()
    return eight_module.consult(question, web_results, shared_context, conv_id, status_cb=status_cb)

def consult(question):
    print('\n=== Ghost speaks: ' + question + ' ===')
    conv_id = new_conversation(question, source='ghost')
    log_message(conv_id, 'Ghost', question, to_agent='Gemma', message_type='chat')

    shared_context = build_shared_context(question)

    # FL-001: Gemma routes first
    routing = gemma_route(question, shared_context)

    # RL-017b: IS_SYSTEM — inject live health data
    if routing.get('is_system') and _MONITOR_OK:
        health = _system_health()
        shared_context = '=== Live system status (answer from this) ===\n' + health + '\n\n' + shared_context
        print('[Orchestrator] IS_SYSTEM=yes — live health data injected')

    # Web search only if Gemma says so (skip web for system questions — data is injected)
    if routing['needs_web'] and not routing['is_identity'] and not routing.get('is_system'):
        llama_web = search_web(question)
        gemma_web = serper_search(question) if _SERPER_OK else ''
        parts = []
        if llama_web:  parts.append('[LLaMA / DuckDuckGo]\n' + llama_web)
        if gemma_web:  parts.append('[Gemma / Google]\n' + gemma_web)
        web_results = '\n\n'.join(parts)
        web_context = '=== Web research ===\n' + web_results + '\n\n' if web_results else ''
    else:
        web_results = ''
        web_context = ''
        print('[Gemma] no web search needed')

    llama_answer = ''
    mistral_answer = ''

    # LLaMA answers if needed
    if routing['agents'] in ['llama', 'both']:
        llama_own = build_agent_context('LLaMA', question)
        llama_prompt = (
            shared_context +
            llama_own +
            web_context +
            '=== The Ghost asks ===\n' + question + '\n\n'
            'Answer using your memory and any web results above. '
            'If you are uncertain say so. Do not fabricate.'
        )
        llama_answer = ask_agent('LLaMA', llama_prompt)
        log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')
        save_agent_memory('LLaMA', question[:50], llama_answer,
                          tags=tag_content(llama_answer), importance=5)

    # Mistral answers if needed — with independent Tavily research
    mistral_web_context = ''
    if _TAVILY_OK and routing.get('needs_web') and not routing.get('is_identity'):
        mistral_web = tavily_search(question)
        if mistral_web and not mistral_web.startswith('[Tavily search unavailable'):
            mistral_web_context = '[Mistral / Tavily]\n' + mistral_web + '\n\n'

    if routing['agents'] in ['mistral', 'both']:
        mistral_own = build_agent_context('Mistral', question)
        mistral_prompt = (
            shared_context +
            mistral_own +
            web_context + mistral_web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            '=== The Ghost asks ===\n' + question + '\n\n'
            'Your job is to add depth or challenge what LLaMA said if it is incomplete or wrong. '
            'You have your own independent Tavily search results above — use them. '
            'If you disagree say so clearly. If you are uncertain say so.'
        )
        mistral_answer = filter_non_english(ask_agent('Mistral', mistral_prompt))
        log_message(conv_id, 'Mistral', mistral_answer, to_agent='Gemma', message_type='chat')
        save_agent_memory('Mistral', question[:50], mistral_answer,
                          tags=tag_content(mistral_answer), importance=5)

    # Debate escalation — fires if Gemma routed as debate OR Mistral signals disagreement
    llama_r2 = ''
    mistral_r2 = ''
    debate_fired = False
    if llama_answer and mistral_answer:
        if routing.get('mode') == 'debate' or _detect_disagreement(mistral_answer):
            debate_fired = True
            llama_r2, mistral_r2 = _run_debate_r2(question, web_context, llama_answer, mistral_answer, conv_id)

    # Gemma synthesises (judge prompt if debate fired)
    gemma_own = build_agent_context('Gemma', question)
    if debate_fired:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            'LLaMA R1: ' + llama_answer + '\n\n'
            'Mistral R1: ' + mistral_answer + '\n\n'
            'LLaMA challenge: ' + llama_r2 + '\n\n'
            'Mistral challenge: ' + mistral_r2 + '\n\n'
            '=== The Ghost asks ===\n' + question + '\n\n'
            'You are the judge. Review the debate and decide who made the stronger case, '
            'or where both were right or wrong. Deliver one clear final verdict. '
            'Be direct. No pleasantries. 3-4 sentences maximum.'
        )
    else:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            ('Mistral said: ' + mistral_answer + '\n\n' if mistral_answer else '') +
            '=== The Ghost asks ===\n' + question + '\n\n'
            'Synthesise. Call out disagreements. Be direct. No preamble.'
        )
    gemma_answer = ask_agent('Gemma', gemma_prompt)
    log_message(conv_id, 'Gemma', gemma_answer, to_agent='Ghost', message_type='chat')
    clean_subject = question.split('\n')[0].strip()[:50]
    save_gemma_verdict(clean_subject, gemma_answer, tags='verdict,gemma')
    promote_to_verified(clean_subject, gemma_answer, tags='verified,gemma,verdict')
    librarian_index(conv_id, clean_subject, gemma_answer)

    return {
        'llama': llama_answer,
        'mistral': mistral_answer,
        'gemma': gemma_answer,
        'web': web_results,
        'routing': routing,
        'conv_id': conv_id,
        'debate': debate_fired,
        'llama_r2': llama_r2,
        'mistral_r2': mistral_r2,
    }

# Keep stage functions for listener.py compatibility
def consult_stage1(question):
    shared_context = build_shared_context(question)
    routing = gemma_route(question, shared_context)

    # RL-017b: IS_SYSTEM — inject live health data so Librarian/agents can answer accurately
    if routing.get('is_system') and _MONITOR_OK:
        health = _system_health()
        shared_context = '=== Live system status (answer from this) ===\n' + health + '\n\n' + shared_context
        print('[Orchestrator] IS_SYSTEM=yes — live health data injected')

    web_results  = ''
    web_context  = ''
    llama_web    = ''
    gemma_web    = ''

    if routing['needs_web'] and not routing['is_identity'] and not routing.get('is_system'):
        # LLaMA — DuckDuckGo (fast, broad)
        llama_web = search_web(question)
        print('[LLaMA] DDG search complete')

        # Gemma — Google via Serper (authoritative, no SEO spam)
        if _SERPER_OK:
            gemma_web = serper_search(question)
        else:
            gemma_web = ''

        # Combined web context — both labelled so agents know the source
        parts = []
        if llama_web:
            parts.append('[LLaMA / DuckDuckGo]\n' + llama_web)
        if gemma_web:
            parts.append('[Gemma / Google]\n' + gemma_web)
        web_results = '\n\n'.join(parts)
        web_context = '=== Web research ===\n' + web_results + '\n\n' if web_results else ''

    # RL-019: Shell agent — run whitelisted command when Gemma routes NEEDS_SHELL=yes
    if routing.get('needs_shell'):
        try:
            from fridays.shell_agent import run as shell_run
            import re as _re
            # Extract command from question — look for backtick or code-fence block first, then bare command
            cmd_match = _re.search(r'`([^`]+)`', question) or _re.search(r'```\w*\n?(.+?)\n?```', question, _re.S)
            shell_cmd = cmd_match.group(1).strip() if cmd_match else question.strip()
            ok, shell_out = shell_run(shell_cmd, agent='Gemma')
            shell_context = f'=== Shell output ({shell_cmd}) ===\n{shell_out}\n\n'
            web_context = shell_context + web_context
            web_results = shell_out + ('\n\n' + web_results if web_results else '')
            print(f'[Shell] {"✓" if ok else "✗"} Output injected into context.')
        except Exception as e:
            logger.warning(f'[Shell] Failed: {e}')

    # RL-018: Browser agent — read specific URLs when Gemma routes NEEDS_BROWSER=yes
    if routing.get('needs_browser'):
        try:
            from fridays.browser_agent import browse_all
            browser_content = browse_all(question)
            if browser_content:
                web_context = '=== Page content (browser) ===\n' + browser_content + '\n\n' + web_context
                web_results = browser_content + ('\n\n' + web_results if web_results else '')
                print('[Browser] Page content injected into context.')
        except Exception as e:
            logger.warning(f'[Browser] Browse failed: {e}')

    llama_answer = ''
    # Skip LLaMA entirely when Eight is handling this — Eight has its own voice pipeline
    if not routing.get('is_sap') and routing['agents'] in ['llama', 'both']:
        llama_own = build_agent_context('LLaMA', question)
        llama_prompt = (
            shared_context +
            llama_own +
            web_context +
            '=== The question ===\n' + question + '\n\n'
            'Answer using your memory and any web results. If uncertain say so.'
        )
        llama_answer = ask_agent('LLaMA', llama_prompt)
        save_agent_memory('LLaMA', question[:50], llama_answer,
                          tags=tag_content(llama_answer), importance=5)
    return web_results, llama_answer, shared_context, routing

def consult_stage2(question, web_results, llama_answer, shared_context, conv_id, routing=None):
    if routing is None:
        routing = {'agents': 'both', 'is_identity': False}
    web_context = ('=== Web research ===\n' + web_results + '\n\n') if web_results else ''

    # Mistral's independent Tavily search — AI-extracted content, separate from LLaMA's DDG
    mistral_web_context = ''
    if _TAVILY_OK and routing.get('needs_web') and not routing.get('is_identity'):
        mistral_web = tavily_search(question)
        if mistral_web and not mistral_web.startswith('[Tavily search unavailable'):
            mistral_web_context = '[Mistral / Tavily]\n' + mistral_web + '\n\n'

    mistral_answer = ''
    if routing['agents'] in ['mistral', 'both']:
        mistral_own = build_agent_context('Mistral', question)
        mistral_prompt = (
            shared_context + mistral_own + web_context + mistral_web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            '=== The question ===\n' + question + '\n\n'
            'Add depth or challenge LLaMA if wrong. You have your own independent Tavily search results above — use them. Be direct. If uncertain say so.'
        )
        mistral_answer = filter_non_english(ask_agent('Mistral', mistral_prompt))
        log_message(conv_id, 'Mistral', mistral_answer, to_agent='Gemma', message_type='chat')
        save_agent_memory('Mistral', question[:50], mistral_answer,
                          tags=tag_content(mistral_answer), importance=5)

    # Debate escalation
    llama_r2 = ''
    mistral_r2 = ''
    debate_fired = False
    if llama_answer and mistral_answer:
        if routing.get('mode') == 'debate' or _detect_disagreement(mistral_answer):
            debate_fired = True
            llama_r2, mistral_r2 = _run_debate_r2(question, web_context, llama_answer, mistral_answer, conv_id)

    gemma_own = build_agent_context('Gemma', question)
    if debate_fired:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            'LLaMA R1: ' + llama_answer + '\n\n'
            'Mistral R1: ' + mistral_answer + '\n\n'
            'LLaMA challenge: ' + llama_r2 + '\n\n'
            'Mistral challenge: ' + mistral_r2 + '\n\n'
            '=== The Ghost asks ===\n' + question + '\n\n'
            'You are the judge. Review the debate and decide who made the stronger case, '
            'or where both were right or wrong. Deliver one clear final verdict. '
            'Be direct. No pleasantries. 3-4 sentences maximum.'
        )
    else:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            ('Mistral said: ' + mistral_answer + '\n\n' if mistral_answer else '') +
            '=== The Ghost asks ===\n' + question + '\n\n'
            'Synthesise. Call out disagreements. Be direct. No preamble.'
        )
    gemma_answer = ask_agent('Gemma', gemma_prompt)
    log_message(conv_id, 'Gemma', gemma_answer, to_agent='Ghost', message_type='chat')
    clean_subject = question.split('\n')[0].strip()[:50]
    save_gemma_verdict(clean_subject, gemma_answer, tags='verdict,gemma')
    promote_to_verified(clean_subject, gemma_answer, tags='verified,gemma,verdict')
    librarian_index(conv_id, clean_subject, gemma_answer)

    # Return debate data so callers (terminal, listener) can surface it
    return mistral_answer, gemma_answer, {'fired': debate_fired, 'llama_r2': llama_r2, 'mistral_r2': mistral_r2}

if __name__ == '__main__':
    print(f'\n[{get_system_clock().timestamp_compact()}] You are the Ghost. The swarm is listening.')
    question = input('Ghost: ')
    result = consult(question)
    print('\n=== Final answer ===')
    print(result['gemma'])