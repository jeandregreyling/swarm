import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/lib/search')
from database import (new_conversation, log_message, save_memory,
                      search_memory, get_ghost_history, get_all_memories)
from internet import search_web

AGENTS = {
    'Gemma':     'gemma3:latest',
    'LLaMA':     'llama3.2:latest',
    'Mistral':   'mistral:latest',
    'Qwen':      'qwen2.5:latest',
    'Librarian': 'qwen:latest',
}

# Try to pull live models from registry
try:
    from utils.db.registry import get_agent_models as _reg_debate_models
    def _get_debate_agents():
        live = _reg_debate_models(local_only=True)
        if live:
            return {k.capitalize() if k != 'llama' else 'LLaMA': v
                    for k, v in live.items()
                    if k in ('gemma', 'llama', 'mistral', 'qwen', 'librarian')}
        return AGENTS
except Exception:
    def _get_debate_agents():
        return AGENTS

def ask_agent(agent_name, prompt):
    agents = _get_debate_agents()
    model = agents.get(agent_name) or AGENTS.get(agent_name)
    if not model:
        raise KeyError(f'Unknown debate agent: {agent_name}')
    print(f'\n[{agent_name}] thinking...')
    from core import llm as _llm
    answer, _tokens = _llm.chat(
        model,
        [{'role': 'user', 'content': prompt}],
    )
    print(f'[{agent_name}] {answer}')
    return answer

def build_context(question):
    ghost_history = get_ghost_history(limit=10)
    relevant_memories = search_memory(query=question, min_importance=5)
    context = ''
    if relevant_memories:
        context += '=== Relevant memories ===\n'
        for m in relevant_memories:
            tags = str(m['tags'])
            subj = str(m['subject'])
            cont = str(m['content'])
            context += '- [' + tags + '] ' + subj + ': ' + cont + '\n'
        context += '\n'
    if ghost_history:
        context += '=== What the Ghost has asked previously ===\n'
        for h in ghost_history:
            context += '- [' + str(h['created_at']) + '] Ghost asked: ' + str(h['content']) + '\n'
        context += '\n'
    return context

def librarian_index(conv_id, subject, content):
    prompt = 'You are a librarian indexing information. Given this content: "' + content + '" Reply with only a comma-separated list of 3-5 single word tags. Only the tags, nothing else.'
    tags = ask_agent('Librarian', prompt).strip()
    save_memory('Librarian', subject, content, tags=tags, importance=8)
    log_message(conv_id, 'Librarian',
                'Indexed: ' + subject + ' | tags: ' + tags,
                message_type='index')
    return tags

def debate(question):
    print('\n=== Ghost calls a debate: ' + question + ' ===')

    conv_id = new_conversation(question, source='debate')
    log_message(conv_id, 'Ghost', question, to_agent='Gemma',
                message_type='chat')

    context = build_context(question)

    print('\n[Internet] searching...')
    web_results = search_web(question)
    print('[Internet] got results')

    # Round 1 - Independent answers
    print('\n--- Round 1: Independent answers ---')

    llama_prompt = context + '=== Live web results ===\n' + web_results + '\n\n=== The Ghost asks ===\n' + question + '\n\nYou are LLaMA. Give your best answer in 3-4 sentences. Be confident and specific. State facts, not hedges.'

    llama_r1 = ask_agent('LLaMA', llama_prompt)
    log_message(conv_id, 'LLaMA', llama_r1, message_type='debate_r1')

    mistral_prompt = context + '=== Live web results ===\n' + web_results + '\n\n=== The Ghost asks ===\n' + question + '\n\nYou are Mistral. Give your best answer in 3-4 sentences. Be confident and specific. State facts, not hedges.'

    mistral_r1 = ask_agent('Mistral', mistral_prompt)
    log_message(conv_id, 'Mistral', mistral_r1, message_type='debate_r1')

    # Round 2 - Challenge
    print('\n--- Round 2: Challenge ---')

    llama_challenge = 'You are LLaMA in a debate.\n\nYou said: ' + llama_r1 + '\n\nMistral said: ' + mistral_r1 + '\n\nDo you agree or disagree with Mistral? If you disagree, state specifically what is wrong and why. If you agree, add something Mistral missed. Be direct. 2-3 sentences only.'

    llama_r2 = ask_agent('LLaMA', llama_challenge)
    log_message(conv_id, 'LLaMA', llama_r2, message_type='debate_r2')

    mistral_challenge = 'You are Mistral in a debate.\n\nYou said: ' + mistral_r1 + '\n\nLLaMA said: ' + llama_r1 + '\n\nDo you agree or disagree with LLaMA? If you disagree, state specifically what is wrong and why. If you agree, add something LLaMA missed. Be direct. 2-3 sentences only.'

    mistral_r2 = ask_agent('Mistral', mistral_challenge)
    log_message(conv_id, 'Mistral', mistral_r2, message_type='debate_r2')

    # Round 3 - Gemma judges
    print('\n--- Round 3: Gemma rules ---')

    gemma_prompt = context + '=== Live web results ===\n' + web_results + '\n\n=== The Ghost asked ===\n' + question + '\n\n=== The debate ===\n\nLLaMA round 1: ' + llama_r1 + '\nMistral round 1: ' + mistral_r1 + '\n\nLLaMA challenge: ' + llama_r2 + '\nMistral challenge: ' + mistral_r2 + '\n\nYou are Gemma, the judge. Review the debate and the web results. Decide who made the stronger case or where both were right or wrong. Deliver one clear final verdict to the Ghost. Be direct. No pleasantries. 3-4 sentences maximum.'

    verdict = ask_agent('Gemma', gemma_prompt)
    log_message(conv_id, 'Gemma', verdict,
                to_agent='Ghost', message_type='verdict')

    librarian_index(conv_id, question[:50], verdict)

    print('\n=== Gemma verdict for the Ghost ===')
    print('\nQuestion: ' + question)
    print('\nLLaMA (R1): ' + llama_r1)
    print('\nMistral (R1): ' + mistral_r1)
    print('\nLLaMA challenges: ' + llama_r2)
    print('\nMistral challenges: ' + mistral_r2)
    print('\nVerdict: ' + verdict)

    return verdict

if __name__ == '__main__':
    print('\nYou are the Ghost. Call a debate.')
    print('The agents will argue, then Gemma will judge.\n')
    question = input('Ghost calls a debate on: ')
    debate(question)


# ══════════════════════════════════════════════════════════════════════════════
# Autonomous debate protocol — DB-backed, no Ghost intervention needed
# Agents deliberate, reach consensus, auto-create proposal or escalate to Ghost
# ══════════════════════════════════════════════════════════════════════════════

import sys as _sys
_sys.path.insert(0, '/home/seven/swarm')

from datetime import datetime as _dt

_MAX_ROUNDS = 3


def _db():
    from database import get_connection
    return get_connection()


def _add_turn(debate_id, agent, position, round_num):
    c = _db()
    c.execute(
        "INSERT INTO debate_turns (debate_id, agent, position, round) VALUES (?,?,?,?)",
        (debate_id, agent, position[:2000], round_num)
    )
    c.commit(); c.close()


def _resolve(debate_id, status, consensus=''):
    c = _db()
    c.execute(
        "UPDATE debates SET status=?, consensus=?, rounds=rounds+1, closed_at=datetime('now') WHERE id=?",
        (status, consensus[:500], debate_id)
    )
    c.commit(); c.close()


def open_debate(topic, initiator='nine'):
    """Create a debate record. Returns debate_id."""
    c = _db()
    c.execute("INSERT INTO debates (topic, initiator, status) VALUES (?,?,?)", (topic, initiator, 'open'))
    c.commit()
    debate_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.close()
    from database import log_activity
    log_activity('debate', 'opened', f'id={debate_id} | {topic[:80]}')
    print(f'[Debate] Opened #{debate_id}: {topic}')
    return debate_id


def run_debate(debate_id):
    """
    Run autonomous debate rounds for debate_id.
    Returns dict: {status, consensus, rounds, proposal_file?}
    """
    c = _db()
    row = c.execute("SELECT topic, initiator FROM debates WHERE id=?", (debate_id,)).fetchone()
    c.close()
    if not row:
        return {'status': 'error', 'consensus': 'debate not found'}

    topic, initiator = row[0], row[1]
    print(f'\n[Debate #{debate_id}] Topic: {topic}')

    # ── Round 1: Independent positions ───────────────────────────────────────
    print(f'[Debate #{debate_id}] Round 1 — positions...')
    llama_r1 = ask_agent('LLaMA',
        f'SWARM DEBATE — no web search needed.\nTOPIC: {topic}\n\n'
        f'State your position in 2-3 sentences. Be specific. No preamble.'
    )
    _add_turn(debate_id, 'LLaMA', llama_r1, 1)

    qwen_r1 = ask_agent('Qwen',
        f'SWARM DEBATE — no web search needed.\nTOPIC: {topic}\n\n'
        f'State your position in 2-3 sentences. Be specific. No preamble.'
    )
    _add_turn(debate_id, 'Qwen', qwen_r1, 1)

    # ── Round 2: Challenge ────────────────────────────────────────────────────
    print(f'[Debate #{debate_id}] Round 2 — challenge...')
    llama_r2 = ask_agent('LLaMA',
        f'TOPIC: {topic}\nYou said: {llama_r1}\nQwen said: {qwen_r1}\n\n'
        f'Agree or disagree with Qwen? If disagree state exactly what is wrong. '
        f'If agree add what Qwen missed. 2 sentences max.'
    )
    _add_turn(debate_id, 'LLaMA', llama_r2, 2)

    qwen_r2 = ask_agent('Qwen',
        f'TOPIC: {topic}\nYou said: {qwen_r1}\nLLaMA said: {llama_r1}\n\n'
        f'Agree or disagree with LLaMA? If disagree state exactly what is wrong. '
        f'If agree add what LLaMA missed. 2 sentences max.'
    )
    _add_turn(debate_id, 'Qwen', qwen_r2, 2)

    # ── Gemma arbitrates ──────────────────────────────────────────────────────
    print(f'[Debate #{debate_id}] Gemma arbitrating...')
    verdict = ask_agent('Gemma',
        f'Arbitrate this swarm debate.\nTOPIC: {topic}\n\n'
        f'LLaMA R1: {llama_r1}\nQwen R1:  {qwen_r1}\n'
        f'LLaMA R2: {llama_r2}\nQwen R2:  {qwen_r2}\n\n'
        f'Do they agree on the core conclusion?\n'
        f'Reply with exactly one of:\n'
        f'CONSENSUS: <one sentence — what they agreed on>\n'
        f'ESCALATE: <one sentence — unresolved disagreement>\n'
        f'Nothing else.'
    )
    _add_turn(debate_id, 'Gemma', verdict, 3)

    from database import log_activity
    log_activity('debate', 'arbitrated', f'id={debate_id} | {verdict[:100]}')

    # ── Parse outcome ─────────────────────────────────────────────────────────
    upper = verdict.upper()
    if 'CONSENSUS:' in upper:
        idx  = upper.index('CONSENSUS:')
        text = verdict[idx + 10:].strip().split('\n')[0].strip()

        # Auto-write proposal to shared sandpit
        from sandpits import write_proposal
        body = (
            f'# Autonomous Debate Proposal\n\n'
            f'**Topic:** {topic}\n\n'
            f'**Consensus:** {text}\n\n'
            f'## LLaMA\n{llama_r1}\n\n'
            f'## Qwen\n{qwen_r1}\n\n'
            f'## Gemma verdict\n{verdict}\n\n'
            f'*Debate #{debate_id} · initiated by {initiator} · {_dt.now().strftime("%Y-%m-%d %H:%M")}*\n'
        )
        proposal_file = write_proposal(initiator, body)
        _resolve(debate_id, 'consensus', text)

        print(f'[Debate #{debate_id}] CONSENSUS → proposal: {proposal_file}')
        return {'status': 'consensus', 'consensus': text, 'rounds': 3,
                'proposal_file': proposal_file, 'debate_id': debate_id}

    else:
        idx  = upper.index('ESCALATE:') if 'ESCALATE:' in upper else 0
        text = verdict[idx + 9:].strip().split('\n')[0].strip() if idx else verdict.strip()
        _resolve(debate_id, 'escalated', text)
        log_activity('debate', 'escalated', f'id={debate_id} | {text[:80]}')

        print(f'[Debate #{debate_id}] ESCALATED → needs Ghost review')
        return {'status': 'escalated', 'consensus': text, 'rounds': 3, 'debate_id': debate_id}


def run_and_resolve(topic, initiator='nine'):
    """Convenience wrapper: open + run in one call."""
    debate_id = open_debate(topic, initiator)
    return run_debate(debate_id)