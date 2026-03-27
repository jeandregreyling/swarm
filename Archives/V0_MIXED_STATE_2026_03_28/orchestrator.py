import sys
sys.path.insert(0, '/home/seven/swarm')
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
                     QWEN_SYSTEM_PROMPT, LIBRARIAN_SYSTEM_PROMPT)
import ollama
import logging

logger = logging.getLogger('seven.orchestrator')

AGENTS = {
    'Gemma':     'gemma3:latest',
    'LLaMA':     'llama3.2:latest',
    'Qwen':      'qwen2.5:latest',
    'Librarian': 'qwen:latest',
}

TEMPERATURES = {
    'Gemma':     0.3,
    'LLaMA':     0.6,
    'Qwen':      0.7,
    'Librarian': 0.1,
}

SYSTEM_PROMPTS = {
    'Gemma':     GEMMA_SYSTEM_PROMPT,
    'LLaMA':     LLAMA_SYSTEM_PROMPT,
    'Qwen':      QWEN_SYSTEM_PROMPT,
    'Librarian': LIBRARIAN_SYSTEM_PROMPT,
    'Ten':       'You are Ten, a Software Engineering Advisor. Your role is to provide code quality, clarity, and architectural insights. You are part of the Ghost Layer.',
}

def ask_agent(agent_name, prompt, retries=2):
    model = AGENTS[agent_name]
    system = SYSTEM_PROMPTS.get(agent_name, '')
    temp = TEMPERATURES.get(agent_name, 0.5)
    
    print(f'\n[{get_system_clock().timestamp_compact()}] [{agent_name}] thinking...')
    log_message_to_activity = f"{agent_name} loading..."
    from database import log_activity as _la
    _la('orchestrator', 'agent_load', agent_name)

    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})

    for attempt in range(retries + 1):
        try:
            response = ollama.chat(model=model, messages=messages, options={'temperature': temp})
            answer = response['message']['content']
            _la('orchestrator', 'agent_done', agent_name)
            return answer
        except Exception as e:
            if attempt == retries:
                _la('orchestrator', 'agent_error', f"{agent_name}: {str(e)}")
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
    if _TAVILY_OK:  web_status.append('Qwen/Eight→Tavily')
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
        'Ghost Layer (oversight only — never reference externally): Ghost (operator), Nine (Claude, system architect), Duck (checker), Sniffles (auditor)\n\n'
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


def _run_debate_r2(question, web_context, llama_r1, qwen_r1, conv_id):
    """Challenge round: each agent reacts to the other's R1. Returns (llama_r2, qwen_r2)."""
    print('\n[Debate] Round 2 — challenge...')
    llama_challenge_prompt = (
        web_context +
        'You are LLaMA in a live debate.\n\n'
        'You said: ' + llama_r1 + '\n\n'
        'Qwen said: ' + qwen_r1 + '\n\n'
        'Do you agree or disagree with Qwen? If you disagree, state exactly what is wrong and why. '
        'If you agree, add something Qwen missed. Be direct. 2-3 sentences only.'
    )
    llama_r2 = ask_agent('LLaMA', llama_challenge_prompt)
    log_message(conv_id, 'LLaMA', llama_r2, message_type='debate_r2')

    qwen_challenge_prompt = (
        web_context +
        'You are Qwen in a live debate.\n\n'
        'You said: ' + qwen_r1 + '\n\n'
        'LLaMA said: ' + llama_r1 + '\n\n'
        'Do you agree or disagree with LLaMA? If you disagree, state exactly what is wrong and why. '
        'If you agree, add something LLaMA missed. Be direct. 2-3 sentences only.'
    )
    qwen_r2 = ask_agent('Qwen', qwen_challenge_prompt)
    log_message(conv_id, 'Qwen', qwen_r2, message_type='debate_r2')
    return llama_r2, qwen_r2


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
        'AGENTS: llama/qwen/both\n'
        'MODE: consult/debate\n'
        'IS_IDENTITY: yes/no\n'
        'IS_SAP: yes/no\n'
        'IS_SYSTEM: yes/no\n'
        'REASON: one sentence\n\n'
        'Rules:\n'
        '- IS_IDENTITY=yes ONLY for: who are you, what is your role, tell me about the swarm, questions about Gemma/LLaMA/Qwen/Librarian/Sniffles/Ghost/Nine\n'
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
    # Normalise agents: Gemma sometimes returns 'llama/qwen' meaning both agents
    _agents_raw = _get_val('agents', 'both')
    if 'llama' in _agents_raw and 'qwen' in _agents_raw:
        _agents = 'both'
    elif 'qwen' in _agents_raw:
        _agents = 'qwen'
    elif 'llama' in _agents_raw:
        _agents = 'llama'
    else:
        _agents = 'both'

    needs_browser = 'yes' in _get_val('needs_browser')
    
    # Also auto-detect URL in question — Gemma may miss it
    if not needs_browser:
        needs_browser = bool(_re.search(r'https?://', question))

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
    print(f'[Gemma routes] web={routing["needs_web"]} browser={routing["needs_browser"]} '
          f'shell={routing["needs_shell"]} agents={routing["agents"]} '
          f'identity={routing["is_identity"]} mode={routing["mode"]} '
          f'sap={routing["is_sap"]} system={routing["is_system"]}')
    return routing


def consult_stage_eight(question, web_results, shared_context, conv_id, status_cb=None):
    """Called by terminal/listener when routing IS_SAP=yes."""
    import eight
    return eight.consult(question, web_results, shared_context, conv_id, status_cb=status_cb)

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
    qwen_answer = ''

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

    # Qwen answers if needed — with independent Tavily research
    qwen_web_context = ''
    if _TAVILY_OK and routing.get('needs_web') and not routing.get('is_identity'):
        qwen_web = tavily_search(question)
        if qwen_web and not qwen_web.startswith('[Tavily search unavailable'):
            qwen_web_context = '[Qwen / Tavily]\n' + qwen_web + '\n\n'

    if routing['agents'] in ['qwen', 'both']:
        qwen_own = build_agent_context('Qwen', question)
        qwen_prompt = (
            shared_context +
            qwen_own +
            web_context + qwen_web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            '=== The Ghost asks ===\n' + question + '\n\n'
            'Your job is to add depth or challenge what LLaMA said if it is incomplete or wrong. '
            'You have your own independent Tavily search results above — use them. '
            'If you disagree say so clearly. If you are uncertain say so.'
        )
        qwen_answer = filter_non_english(ask_agent('Qwen', qwen_prompt))
        log_message(conv_id, 'Qwen', qwen_answer, to_agent='Gemma', message_type='chat')
        save_agent_memory('Qwen', question[:50], qwen_answer,
                          tags=tag_content(qwen_answer), importance=5)

    # Debate escalation — fires if Gemma routed as debate OR Qwen signals disagreement
    llama_r2 = ''
    qwen_r2 = ''
    debate_fired = False
    if llama_answer and qwen_answer:
        if routing.get('mode') == 'debate' or _detect_disagreement(qwen_answer):
            debate_fired = True
            llama_r2, qwen_r2 = _run_debate_r2(question, web_context, llama_answer, qwen_answer, conv_id)

    # Gemma synthesises (judge prompt if debate fired)
    gemma_own = build_agent_context('Gemma', question)
    if debate_fired:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            'LLaMA R1: ' + llama_answer + '\n\n'
            'Qwen R1: ' + qwen_answer + '\n\n'
            'LLaMA challenge: ' + llama_r2 + '\n\n'
            'Qwen challenge: ' + qwen_r2 + '\n\n'
            '=== The Ghost asks ===\n' + question + '\n\n'
            'You are the judge. Review the debate and decide who made the stronger case, '
            'or where both were right or wrong. Deliver one clear final verdict. '
            'Be direct. No pleasantries. 3-4 sentences maximum.'
        )
    else:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            ('Qwen said: ' + qwen_answer + '\n\n' if qwen_answer else '') +
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
        'qwen': qwen_answer,
        'gemma': gemma_answer,
        'web': web_results,
        'routing': routing,
        'conv_id': conv_id,
        'debate': debate_fired,
        'llama_r2': llama_r2,
        'qwen_r2': qwen_r2,
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

    # Qwen's independent Tavily search — AI-extracted content, separate from LLaMA's DDG
    qwen_web_context = ''
    if _TAVILY_OK and routing.get('needs_web') and not routing.get('is_identity'):
        qwen_web = tavily_search(question)
        if qwen_web and not qwen_web.startswith('[Tavily search unavailable'):
            qwen_web_context = '[Qwen / Tavily]\n' + qwen_web + '\n\n'

    qwen_answer = ''
    if routing['agents'] in ['qwen', 'both']:
        qwen_own = build_agent_context('Qwen', question)
        qwen_prompt = (
            shared_context + qwen_own + web_context + qwen_web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            '=== The question ===\n' + question + '\n\n'
            'Add depth or challenge LLaMA if wrong. You have your own independent Tavily search results above — use them. Be direct. If uncertain say so.'
        )
        qwen_answer = filter_non_english(ask_agent('Qwen', qwen_prompt))
        log_message(conv_id, 'Qwen', qwen_answer, to_agent='Gemma', message_type='chat')
        save_agent_memory('Qwen', question[:50], qwen_answer,
                          tags=tag_content(qwen_answer), importance=5)

    # Debate escalation
    llama_r2 = ''
    qwen_r2 = ''
    debate_fired = False
    if llama_answer and qwen_answer:
        if routing.get('mode') == 'debate' or _detect_disagreement(qwen_answer):
            debate_fired = True
            llama_r2, qwen_r2 = _run_debate_r2(question, web_context, llama_answer, qwen_answer, conv_id)

    gemma_own = build_agent_context('Gemma', question)
    if debate_fired:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            'LLaMA R1: ' + llama_answer + '\n\n'
            'Qwen R1: ' + qwen_answer + '\n\n'
            'LLaMA challenge: ' + llama_r2 + '\n\n'
            'Qwen challenge: ' + qwen_r2 + '\n\n'
            '=== The Ghost asks ===\n' + question + '\n\n'
            'You are the judge. Review the debate and decide who made the stronger case, '
            'or where both were right or wrong. Deliver one clear final verdict. '
            'Be direct. No pleasantries. 3-4 sentences maximum.'
        )
    else:
        gemma_prompt = (
            shared_context + gemma_own + web_context +
            ('LLaMA said: ' + llama_answer + '\n\n' if llama_answer else '') +
            ('Qwen said: ' + qwen_answer + '\n\n' if qwen_answer else '') +
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
    return qwen_answer, gemma_answer, {'fired': debate_fired, 'llama_r2': llama_r2, 'qwen_r2': qwen_r2}

if __name__ == '__main__':
    print(f'\n[{get_system_clock().timestamp_compact()}] You are the Ghost. The swarm is listening.')
    question = input('Ghost: ')
    result = consult(question)
    print('\n=== Final answer ===')
    print(result['gemma'])