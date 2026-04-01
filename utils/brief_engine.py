"""
brief_engine.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Ghost Brief — swarm intelligence synthesis.
Reads full swarm state, calls Nine (Claude API), produces a structured brief.

Usage:
  from brief_engine import generate_brief, get_latest_brief
  brief = generate_brief(trigger='manual')
  latest = get_latest_brief()
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import json
import logging
from datetime import datetime, timedelta

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/lib/system')

logger = logging.getLogger('seven.brief_engine')


def gather_swarm_state():
    """Read full swarm state and return a structured context dict."""
    from database import get_connection

    conn = get_connection()
    state = {}

    try:
        # ── Tickets (last 7 days) ────────────────────────────────────────────
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        tickets = conn.execute(
            """SELECT ticket_number, question, tags, status, agents_assigned,
                      final_answer IS NOT NULL AS answered, created_at
               FROM tickets
               WHERE created_at >= ?
               ORDER BY created_at DESC""",
            (cutoff,)
        ).fetchall()

        state['tickets'] = {
            'total_7d': len(tickets),
            'open': sum(1 for t in tickets if t['status'] != 'closed'),
            'answered': sum(1 for t in tickets if t['answered']),
            'recent': [
                {
                    'id': t['ticket_number'],
                    'question': (t['question'] or '')[:200],
                    'tags': t['tags'],
                    'status': t['status'],
                    'agent': t['agents_assigned'],
                    'date': t['created_at'][:10],
                }
                for t in tickets[:15]
            ]
        }

        # ── Memory highlights (importance >= 7) ─────────────────────────────
        highlights = []
        pools = [
            ('memory_nine',   'Nine',    True),
            ('memory_grok',   'Grok',    True),
            ('memory_twelve', 'Twelve',  False),   # no subject column
            ('memory_gemma',  'Gemma',   True),
            ('memory_llama',  'LLaMA',   True),
            ('memory_eight',  'Eight',   True),
        ]
        for tbl, name, has_subject in pools:
            try:
                if has_subject:
                    rows = conn.execute(
                        f"""SELECT '{name}' AS agent, subject, content, importance, created_at
                            FROM {tbl}
                            WHERE importance >= 7 AND archived = 0
                            ORDER BY created_at DESC LIMIT 5"""
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""SELECT '{name}' AS agent, '' AS subject, content, importance, created_at
                            FROM {tbl}
                            WHERE importance >= 7 AND archived = 0
                            ORDER BY created_at DESC LIMIT 5"""
                    ).fetchall()
                for r in rows:
                    highlights.append({
                        'agent':      r['agent'],
                        'subject':    r['subject'],
                        'content':    (r['content'] or '')[:300],
                        'importance': r['importance'],
                        'date':       r['created_at'][:10],
                    })
            except Exception:
                pass
        highlights.sort(key=lambda x: x['importance'], reverse=True)
        state['memory_highlights'] = highlights[:20]

        # ── Memory pool sizes ────────────────────────────────────────────────
        pool_sizes = {}
        for tbl, name, _ in pools:
            try:
                n = conn.execute(f'SELECT COUNT(*) FROM {tbl} WHERE archived=0').fetchone()[0]
                pool_sizes[name] = n
            except Exception:
                pool_sizes[name] = 0
        state['memory_pool_sizes'] = pool_sizes

        # ── Recent decisions (Twelve) ────────────────────────────────────────
        try:
            decisions = conn.execute(
                """SELECT decision_id, title, status, proposed_at, executed_at, agent
                   FROM decisions ORDER BY proposed_at DESC LIMIT 10"""
            ).fetchall()
            state['decisions'] = [dict(d) for d in decisions]
        except Exception:
            state['decisions'] = []

        # ── Duck log (last 10) ───────────────────────────────────────────────
        duck_rows = conn.execute(
            """SELECT ticket_number, result, reason, created_at
               FROM duck_log ORDER BY created_at DESC LIMIT 10"""
        ).fetchall()
        state['duck_log'] = {
            'recent': [dict(d) for d in duck_rows],
            'flagged': sum(1 for d in duck_rows if d['result'] == 'NO'),
        }

        # ── Ghost Circle events ──────────────────────────────────────────────
        gc_rows = conn.execute(
            """SELECT entry_type, source, content, severity, created_at
               FROM ghost_circle ORDER BY created_at DESC LIMIT 10"""
        ).fetchall()
        state['ghost_circle'] = [dict(g) for g in gc_rows]

        # ── Activity log (last 24h) ──────────────────────────────────────────
        since = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        activity = conn.execute(
            "SELECT service, event, detail, created_at FROM activity_log WHERE created_at >= ? ORDER BY created_at DESC",
            (since,)
        ).fetchall()
        state['activity_24h'] = [dict(a) for a in activity]

        # ── Sniffer patterns ─────────────────────────────────────────────────
        try:
            patterns = conn.execute(
                """SELECT agent_name, pattern_type, description, occurrence_count, escalation_level
                   FROM sniffer_memory ORDER BY occurrence_count DESC LIMIT 5"""
            ).fetchall()
            state['sniffer_patterns'] = [dict(p) for p in patterns]
        except Exception:
            state['sniffer_patterns'] = []

        # ── Work proposals (pipeline state) ──────────────────────────────────
        try:
            proposal_rows = conn.execute(
                """SELECT proposal_id, agent, title, status, created_at, updated_at
                   FROM work_proposals
                   WHERE status NOT IN ('executed', 'rejected')
                   ORDER BY created_at DESC LIMIT 20"""
            ).fetchall()
            counts = conn.execute(
                """SELECT status, COUNT(*) AS n FROM work_proposals GROUP BY status"""
            ).fetchall()
            state['proposals'] = {
                'counts': {r['status']: r['n'] for r in counts},
                'active': [dict(r) for r in proposal_rows],
            }
        except Exception:
            state['proposals'] = {'counts': {}, 'active': []}

        # ── Deferred / pinned items ───────────────────────────────────────────
        try:
            deferred_rows = conn.execute(
                """SELECT id, content, source, created_at
                   FROM deferred_items WHERE resolved=0
                   ORDER BY created_at ASC LIMIT 20"""
            ).fetchall()
            state['deferred'] = [dict(r) for r in deferred_rows]
        except Exception:
            state['deferred'] = []

    finally:
        conn.close()

    # ── System services ──────────────────────────────────────────────────────
    import subprocess
    services = {}
    for svc in ['swarm-terminal', 'swarm-listener', 'swarm-discord', 'swarm-telegram']:
        try:
            r = subprocess.run(
                ['systemctl', 'is-active', svc],
                capture_output=True, text=True, timeout=3
            )
            services[svc] = r.stdout.strip()
        except Exception:
            services[svc] = 'unknown'
    state['services'] = services

    state['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return state


def _build_prompt(state):
    """Build the synthesis prompt from swarm state."""
    from system_clock import get_full_time_string

    lines = []
    lines.append(f"You are Nine, system architect of Seven's Swarm. Today is {state['generated_at']} AEST.")
    lines.append("Generate a Ghost Brief — a structured intelligence report for Ghost (the human operator).")
    lines.append("Be direct, specific, and genuinely useful. This replaces Ghost having to manually read everything.")
    lines.append("")
    lines.append("═══ SWARM STATE DATA ═══")
    lines.append("")

    # Tickets
    t = state['tickets']
    lines.append(f"TICKETS (last 7 days): {t['total_7d']} total, {t['answered']} answered, {t['open']} open")
    for tk in t['recent'][:10]:
        lines.append(f"  [{tk['date']}] {tk['id']} | {tk['agent'] or '?'} | {(tk['question'] or '')[:120]}")
    lines.append("")

    # Memory highlights
    lines.append(f"MEMORY HIGHLIGHTS ({len(state['memory_highlights'])} high-importance entries):")
    for m in state['memory_highlights'][:12]:
        subj = f" — {m['subject']}" if m['subject'] else ""
        lines.append(f"  [{m['agent']}] i={m['importance']}{subj}: {m['content'][:200]}")
    lines.append("")

    # Memory pool sizes
    lines.append("POOL SIZES: " + " | ".join(f"{k}:{v}" for k,v in state['memory_pool_sizes'].items()))
    lines.append("")

    # Decisions
    if state['decisions']:
        lines.append(f"TWELVE DECISIONS ({len(state['decisions'])} total):")
        for d in state['decisions'][:5]:
            lines.append(f"  [{d.get('status','?')}] {d.get('decision_id','?')} — {d.get('title','?')}")
        lines.append("")

    # Duck
    duck = state['duck_log']
    lines.append(f"DUCK LOG (last 10): {duck['flagged']} flagged")
    for d in duck['recent'][:5]:
        if d['result'] == 'NO':
            lines.append(f"  ⚠️ [{d['ticket_number']}] {(d['reason'] or '')[:100]}")
    lines.append("")

    # Services
    lines.append("SERVICES: " + " | ".join(f"{k.replace('swarm-','')}:{v}" for k,v in state['services'].items()))
    lines.append("")

    # Sniffer
    if state['sniffer_patterns']:
        lines.append("SNIFFER PATTERNS:")
        for p in state['sniffer_patterns']:
            lines.append(f"  [{p['escalation_level']}] {p['agent_name']}: {p['pattern_type']} — {p['description'][:80]}")
        lines.append("")

    # Work proposals pipeline
    props = state.get('proposals', {})
    counts = props.get('counts', {})
    if counts:
        summary = " | ".join(f"{s}:{n}" for s,n in counts.items())
        lines.append(f"WORK PROPOSALS: {summary}")
        for p in props.get('active', [])[:8]:
            lines.append(f"  [{p['status'].upper()}] {p['proposal_id']} — {p['title'][:80]} (by {p['agent']})")
        lines.append("")

    # Deferred / pinned items
    deferred = state.get('deferred', [])
    if deferred:
        lines.append(f"PINNED / DEFERRED ITEMS ({len(deferred)} unresolved):")
        for d in deferred:
            lines.append(f"  [{d['source']}] {d['content'][:120]}")
        lines.append("")

    lines.append("═══ END STATE DATA ═══")
    lines.append("")
    lines.append("Now generate the Ghost Brief. Use exactly this structure:")
    lines.append("")
    lines.append("SITUATION")
    lines.append("[2-3 sentences. What's been happening. Overall swarm health. Tone: direct, no waffle.]")
    lines.append("")
    lines.append("TICKET PATTERNS")
    lines.append("[What Ghost has been asking about. Clusters and themes. Which agents handled what. Anything unusual.]")
    lines.append("")
    lines.append("MEMORY HIGHLIGHTS")
    lines.append("[Curate — don't dump. What's high value that Ghost should see. Max 5 items, each 1-2 lines.]")
    lines.append("")
    lines.append("OPEN ITEMS")
    lines.append("[Unresolved tickets, pending decisions, Duck flags, active proposals. If nothing — say so.]")
    lines.append("")
    lines.append("SYSTEM HEALTH")
    lines.append("[Services status, any warnings, memory pool growth trends, proposal pipeline state.]")
    lines.append("")
    lines.append("NINE'S TAKE")
    lines.append("[One honest paragraph. What's working well. What needs attention. Architectural perspective. No flattery.]")
    lines.append("")
    lines.append("NEXT 24H")
    lines.append("[Pull from the PINNED/DEFERRED items above — these are explicit things Ghost has flagged. Add any Nine expects from patterns. Specific, not generic. If there are pinned items, list them first.]")

    return "\n".join(lines)


def generate_brief(trigger='on_demand'):
    """Generate a new Ghost Brief via Claude API. Returns the brief dict."""
    from database import get_connection

    logger.info(f"[Brief] Generating brief — trigger: {trigger}")

    state = gather_swarm_state()
    prompt = _build_prompt(state)

    # Call Claude
    try:
        import os
        try:
            import anthropic
        except ImportError:
            logger.error("[Brief] anthropic not installed")
            return None

        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            try:
                with open('/etc/environment') as f:
                    for line in f:
                        if line.strip().startswith('ANTHROPIC_API_KEY='):
                            api_key = line.strip().split('=', 1)[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass

        if not api_key:
            logger.error("[Brief] ANTHROPIC_API_KEY not found")
            return None

        from utils.config import NINE_SYSTEM_PROMPT
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2048,
            system=NINE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

    except Exception as e:
        logger.error(f"[Brief] Claude API call failed: {e}")
        return None

    # Wrap with header/footer
    now = datetime.now()
    header = (
        f"{'═'*55}\n"
        f"GHOST BRIEF — {now.strftime('%A, %d %B %Y · %H:%M')} AEST\n"
        f"Generated by Nine · Seven's Swarm\n"
        f"Trigger: {trigger} · Tokens: {tokens}\n"
        f"{'═'*55}\n\n"
    )
    full_brief = header + content

    # Store in DB
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO ghost_briefs (brief_type, content, raw_data_snapshot, tokens_used, triggered_by)
               VALUES (?, ?, ?, ?, ?)""",
            (trigger, full_brief, json.dumps(state, default=str)[:8000], tokens, trigger)
        )
        conn.commit()
        brief_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    finally:
        conn.close()

    logger.info(f"[Brief] Brief #{brief_id} generated — {tokens} tokens")

    # Discord ping — pull headline numbers from state so Ghost knows at a glance
    try:
        import sys as _sys
        _sys.path.insert(0, '/home/seven/swarm/lib/system')
        import discord_notify
        t = state.get('tickets', {})
        duck = state.get('duck_log', {})
        proposals = state.get('proposals', {})
        active_props = sum(
            v for k, v in proposals.get('counts', {}).items()
            if k not in ('executed', 'rejected')
        )
        # Pull first SITUATION paragraph as a preview
        situation_line = ''
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('SITUATION') and len(line) > 30:
                situation_line = line
                break
        discord_notify.notify_brief_ready(
            brief_summary=situation_line,
            trigger=trigger,
            tokens=tokens,
            open_proposals=active_props,
            duck_flags=duck.get('flagged', 0),
            open_tickets=t.get('open', 0),
        )
    except Exception as e:
        logger.warning(f"[Brief] Discord ping failed: {e}")

    return {
        'id': brief_id,
        'content': full_brief,
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'tokens_used': tokens,
        'triggered_by': trigger,
    }


def get_latest_brief():
    """Return the most recently generated brief, or None."""
    from database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT id, generated_at, brief_type, content, tokens_used, triggered_by
               FROM ghost_briefs ORDER BY generated_at DESC LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_brief_history(limit=10):
    """Return list of past briefs (content omitted for performance)."""
    from database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, generated_at, brief_type, tokens_used, triggered_by,
                      substr(content, 1, 200) AS preview
               FROM ghost_briefs ORDER BY generated_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_brief_stale(max_age_hours=6):
    """Return True if no brief exists or the latest is older than max_age_hours."""
    latest = get_latest_brief()
    if not latest:
        return True
    try:
        gen_at = datetime.strptime(latest['generated_at'], '%Y-%m-%d %H:%M:%S')
        return (datetime.now() - gen_at).total_seconds() > max_age_hours * 3600
    except Exception:
        return True


if __name__ == '__main__':
    import sys as _sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
    trigger = _sys.argv[1] if len(_sys.argv) > 1 else 'cli'
    print(f'[Brief] Generating brief (trigger: {trigger})...')
    result = generate_brief(trigger=trigger)
    if result:
        print(result['content'])
        print(f'\n[Brief] Done — {result["tokens_used"]} tokens, id #{result["id"]}')
    else:
        print('[Brief] Generation failed — check logs')
        _sys.exit(1)
