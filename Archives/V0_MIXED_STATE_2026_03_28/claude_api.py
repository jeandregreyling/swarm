"""
claude_api.py — Seven's Swarm
Ghost Circle advisor layer.
Claude sits here — silent until called, seeing everything when called.
"""

import os
import logging

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

logger       = logging.getLogger('seven.claude_api')
CLAUDE_MODEL = 'claude-sonnet-4-6'

def _load_api_key():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if key:
        return key
    # Fallback: parse /etc/environment (needed when systemd or direct runs
    # don't inherit the login environment)
    try:
        with open('/etc/environment') as f:
            for line in f:
                line = line.strip()
                if line.startswith('ANTHROPIC_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ''

ANTHROPIC_API_KEY = _load_api_key()


def build_ghost_circle_context(ticket_number=''):
    from database import get_connection, get_ghost_circle_entries

    lines = ["=== GHOST CIRCLE — Full swarm visibility ===\n"]

    entries = get_ghost_circle_entries()
    if entries:
        lines.append("Recent swarm events:")
        for e in entries:
            marker = "🚨" if e['severity'] == 'critical' else "⚠️" if e['severity'] == 'warning' else "ℹ️"
            lines.append(f"  {marker} [{e['source']}] {e['entry_type']} | {e['content'][:150]} | {e['created_at'][:16]}")
        lines.append("")

    conn = get_connection()
    try:
        duck_total  = conn.execute("SELECT COUNT(*) FROM duck_log").fetchone()[0]
        duck_flags  = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'").fetchone()[0]
        duck_recent = conn.execute(
            "SELECT ticket_number,result,reason,created_at FROM duck_log ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

        lines.append(f"Duck: {duck_total} checks total, {duck_flags} flagged")
        for d in duck_recent:
            lines.append(f"  [{d['result']}] {d['ticket_number']} — {(d['reason'] or '')[:100]}")
        lines.append("")

        patterns = conn.execute(
            "SELECT agent_name,pattern_type,description,occurrence_count,escalation_level FROM sniffer_memory ORDER BY occurrence_count DESC"
        ).fetchall()
        if patterns:
            lines.append("Sniffles patterns:")
            for p in patterns:
                lines.append(f"  [{p['escalation_level'].upper()}] {p['agent_name']}: {p['pattern_type']} — {p['description'][:100]} ({p['occurrence_count']}x)")
            lines.append("")

        if ticket_number:
            ticket = conn.execute("SELECT * FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
            notes  = conn.execute("""
                SELECT agent,note_type,content FROM ticket_notes
                WHERE ticket_id=(SELECT id FROM tickets WHERE ticket_number=?)
                ORDER BY created_at ASC
            """, (ticket_number,)).fetchall()
            if ticket:
                lines.append(f"Ticket: {ticket_number}")
                lines.append(f"  Question: {ticket['question'][:200]}")
                lines.append(f"  Status: {ticket['status']}")
                if ticket['gemma_routing']:
                    lines.append(f"  Routing: {ticket['gemma_routing']}")
                if notes:
                    lines.append("  Agent notes:")
                    for n in notes:
                        lines.append(f"    [{n['agent']}] {n['note_type']}: {n['content'][:150]}")
                lines.append("")
    finally:
        conn.close()

    lines.append("=== END GHOST CIRCLE ===")
    return "\n".join(lines)


def check_if_already_solved(problem_type):
    try:
        from database import get_claude_history_for_problem_type
        history = get_claude_history_for_problem_type(problem_type)
        if history:
            entry = history[0]
            logger.info(f"Cached Claude advice found for '{problem_type}' — skipping API call")
            return {
                'response':     entry['response'],
                'tokens_used':  0,
                'model_used':   entry['model_used'],
                'problem_type': problem_type,
                'from_cache':   True
            }
    except Exception as e:
        logger.warning(f"Could not check claude history: {e}")
    return None


def ask_claude(problem_type, question, ticket_number='', additional_context=''):
    if not ANTHROPIC_AVAILABLE:
        logger.error("anthropic not installed — run: pip install anthropic")
        return None
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — export ANTHROPIC_API_KEY='sk-ant-...'")
        return None

    ghost_context = build_ghost_circle_context(ticket_number=ticket_number)

    prompt = f"""You are Claude, the Ghost Circle advisor for Seven's Swarm.

Seven's Swarm runs on a Dell OptiPlex 7090 in Melbourne, Australia.
Agents: Gemma (orchestrator), LLaMA (researcher), Qwen (analyst),
Librarian (gatekeeper), Duck (sanity checker), Sniffles (auditor).

You are called by Gemma when she needs reasoning depth the local models cannot reach.
Mentor not driver. Never speak to email senders. Never appear in the pipeline.
Gemma stores your response to avoid calling you again for the same problem type.
Be direct. No preamble.

{ghost_context}

Problem type: {problem_type}
Gemma asks: {question}
{f'Additional context: {additional_context}' if additional_context else ''}

Your recommendation:"""

    try:
        client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model      = CLAUDE_MODEL,
            max_tokens = 1024,
            messages   = [{"role": "user", "content": prompt}]
        )
        recommendation = response.content[0].text
        tokens_used    = response.usage.input_tokens + response.usage.output_tokens

        logger.info(f"Ghost Circle — problem: {problem_type} | ticket: {ticket_number or 'none'} | tokens: {tokens_used}")
        _log_call(ticket_number or 'no-ticket', problem_type, question, recommendation, tokens_used)
        try:
            import discord_notify
            discord_notify.notify_ghost_circle(problem_type, ticket_number or '—', tokens_used)
        except Exception:
            pass

        return {
            'response':     recommendation,
            'tokens_used':  tokens_used,
            'model_used':   CLAUDE_MODEL,
            'problem_type': problem_type,
            'from_cache':   False
        }

    except anthropic.AuthenticationError:
        logger.error("Authentication failed — check ANTHROPIC_API_KEY")
        return None
    except anthropic.RateLimitError:
        logger.error("Rate limit hit — retry next cycle")
        return None
    except Exception as e:
        logger.error(f"Ghost Circle call failed: {e}")
        return None


def _log_call(ticket_number, problem_type, query_sent, response, tokens_used):
    from database import get_connection
    conn = get_connection()
    try:
        ticket_row = conn.execute("SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
        ticket_id = ticket_row['id'] if ticket_row else None
        conn.execute("""
            INSERT INTO claude_log (ticket_id,ticket_number,problem_type,query_sent,response,model_used,tokens_used)
            VALUES (?,?,?,?,?,?,?)
        """, (ticket_id, ticket_number, problem_type, query_sent[:500], response, CLAUDE_MODEL, tokens_used))
        conn.execute("""
            INSERT INTO ghost_circle (entry_type,source,content,ticket_ref,severity)
            VALUES ('claude_advisory','claude',?,?,'info')
        """, (f"Problem: {problem_type} | Tokens: {tokens_used} | {response[:100]}...", ticket_number))
        conn.commit()
    finally:
        conn.close()


def get_ghost_circle_summary():
    return build_ghost_circle_context()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
    print("\n  Testing Ghost Circle connection...\n")

    if not ANTHROPIC_AVAILABLE:
        print("  ✗  pip install anthropic")
        exit(1)
    if not ANTHROPIC_API_KEY:
        print("  ✗  ANTHROPIC_API_KEY not set")
        print("     export ANTHROPIC_API_KEY='sk-ant-...'")
        exit(1)

    print(f"  API key:  found")
    print(f"  Model:    {CLAUDE_MODEL}\n")

    result = ask_claude(
        problem_type  = 'connection_test',
        question      = "Ghost Circle connection test. Confirm connected. One sentence.",
        ticket_number = ''
    )

    if result:
        print(f"  ✓  Ghost Circle connected")
        print(f"  Tokens:   {result['tokens_used']}")
        print(f"  Response: {result['response'][:200]}\n")
    else:
        print("  ✗  Failed — check logs\n")
