"""Council — seven scoring functions + Sage aggregator + PFV gate.

Each sense produces candidate thoughts from signals.
Sage aggregates, Patrol vetoes, PFV filters.
Output: list of gated thoughts ready for council_output table.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from agents.twenty.pfv import pfv_gate
from agents.twenty.memory import honesty_check

logger = logging.getLogger('seven.agent20.council')

# TTL per role (minutes)
ROLE_TTL = {
    'lookout': 5,
    'snoop':   30,
    'spark':   30,
    'skulk':   60,
    'keeper':  1440,  # 24 hours
    'sage':    15,
    'patrol':  15,
}


def _expires_at(role):
    ttl = ROLE_TTL.get(role, 15)
    return (datetime.now(timezone.utc) + timedelta(minutes=ttl)).strftime('%Y-%m-%d %H:%M:%S')


def _thought(role, text, detail='', urgency=0, confidence=0.5,
             source_refs=None, agent_ref=None):
    """Build a candidate thought dict."""
    return {
        'orb_role': role,
        'thought': text[:140],
        'detail': detail,
        'urgency': urgency,
        'confidence': confidence,
        'source_refs': source_refs or [],
        'agent_ref': agent_ref,
        'expires_at': _expires_at(role),
    }


# ── Sense 1: Lookout (Sight) ─────────────────────────────────────────

def lookout_score(signals):
    """What's in front of me right now?

    Reads: queue depth, system stats, recent activity.
    """
    thoughts = []

    # Queue depth awareness
    depth = signals.get('queue_depth', 0)
    if depth > 0:
        urgency = 2 if depth > 10 else (1 if depth > 5 else 0)
        thoughts.append(_thought(
            'lookout',
            f'{depth} items queued — {"heavy load" if depth > 10 else "moderate" if depth > 5 else "light"}',
            detail=f'Queue has {depth} unprocessed items.',
            urgency=urgency,
            confidence=0.9,
            source_refs=[{'table': 'queue', 'filter': "status='queued'"}],
        ))

    # System resource alert
    stats = signals.get('system_stats', {})
    cpu = stats.get('cpu_percent', 0)
    if cpu > 80:
        thoughts.append(_thought(
            'lookout',
            f'CPU at {cpu:.0f}% — system under pressure',
            detail=f'RAM available: {stats.get("ram_available_gb", "?")} GB, temp: {stats.get("cpu_temp_c", "?")}°C',
            urgency=2 if cpu > 90 else 1,
            confidence=0.95,
            source_refs=[{'table': 'system_stats'}],
        ))

    return thoughts


# ── Sense 2: Snoop (Hearing) ─────────────────────────────────────────

def snoop_score(signals):
    """Who do we know and what connects?

    Reads: pending proposals, recent decisions, user topics.
    """
    thoughts = []

    proposals = signals.get('pending_proposals', [])
    if proposals:
        oldest = proposals[0]
        thoughts.append(_thought(
            'snoop',
            f'{len(proposals)} pending proposal{"s" if len(proposals) != 1 else ""} — oldest from {oldest.get("agent", "?")}',
            detail=f'"{oldest.get("title", "?")}" submitted {oldest.get("created_at", "?")}',
            urgency=1 if len(proposals) > 3 else 0,
            confidence=0.85,
            source_refs=[{'table': 'work_proposals', 'id': oldest.get('proposal_id')}],
        ))

    decisions = signals.get('recent_decisions', [])
    if decisions:
        latest = decisions[0]
        thoughts.append(_thought(
            'snoop',
            f'Last decision by {latest.get("agent", "?")}: {(latest.get("decision", "") or "")[:80]}',
            detail=latest.get('reasoning', ''),
            urgency=0,
            confidence=0.7,
            source_refs=[{'table': 'decisions'}],
        ))

    return thoughts


# ── Sense 3: Spark (Touch) ───────────────────────────────────────────

def spark_score(signals):
    """What can we do about it?

    Reads: scheduled tasks due, queue items, agent capabilities.
    """
    thoughts = []

    due = signals.get('scheduled_due', [])
    if due:
        next_task = due[0]
        thoughts.append(_thought(
            'spark',
            f'Scheduled: "{next_task.get("name", "?")}" due at {next_task.get("next_run", "?")}',
            detail=f'{len(due)} task{"s" if len(due) != 1 else ""} due within 1 hour.',
            urgency=1,
            confidence=0.8,
            source_refs=[{'table': 'scheduled_tasks', 'name': next_task.get('name')}],
        ))

    # Suggest processing if queue is idle but has items
    depth = signals.get('queue_depth', 0)
    stats = signals.get('system_stats', {})
    cpu = stats.get('cpu_percent', 0)
    if depth > 0 and cpu < 50:
        thoughts.append(_thought(
            'spark',
            f'System idle ({cpu:.0f}% CPU) with {depth} queued — good time to process',
            urgency=0,
            confidence=0.6,
            source_refs=[{'table': 'queue'}, {'table': 'system_stats'}],
        ))

    return thoughts


# ── Sense 4: Skulk (Smell) ───────────────────────────────────────────

def skulk_score(signals):
    """Something doesn't add up…

    Reads: sniffer findings, agent errors, anomaly patterns.
    """
    thoughts = []

    errors = signals.get('agent_errors', [])
    if errors:
        by_service = {}
        for e in errors:
            svc = e.get('service', 'unknown')
            by_service[svc] = by_service.get(svc, 0) + 1
        worst = max(by_service, key=by_service.get)
        thoughts.append(_thought(
            'skulk',
            f'{sum(by_service.values())} errors in last 30min — {worst} has {by_service[worst]}',
            detail=json.dumps(by_service),
            urgency=2 if sum(by_service.values()) > 5 else 1,
            confidence=0.85,
            source_refs=[{'table': 'activity_log', 'filter': 'recent errors'}],
        ))

    findings = signals.get('sniffer_findings', [])
    if findings:
        thoughts.append(_thought(
            'skulk',
            f'{len(findings)} sniffer finding{"s" if len(findings) != 1 else ""} in log',
            detail=(findings[0].get('detail', '') or '')[:200],
            urgency=1,
            confidence=0.7,
            source_refs=[{'table': 'sniffer_log'}],
        ))

    return thoughts


# ── Sense 5: Keeper (Taste) ──────────────────────────────────────────

def keeper_score(signals):
    """Why does this matter to YOU?

    Reads: user interests, user patterns, conversation frequency.
    """
    thoughts = []

    topics = signals.get('user_topics', [])
    if topics:
        top = topics[0]
        thoughts.append(_thought(
            'keeper',
            f'Top interest: {top.get("topic", "?")} (score {top.get("score", 0):.1f})',
            detail=f'Category: {top.get("category", "general")}. {len(topics)} active interests tracked.',
            urgency=0,
            confidence=0.6,
            source_refs=[{'table': 'user_interests'}],
        ))

    # Aging tickets that might matter
    aging = signals.get('open_tickets_aging', [])
    if aging:
        thoughts.append(_thought(
            'keeper',
            f'{len(aging)} ticket{"s" if len(aging) != 1 else ""} open > 24h — might need attention',
            detail=f'Oldest: "{(aging[0].get("question", "") or "")[:80]}" from {aging[0].get("created_at", "?")}',
            urgency=1 if len(aging) > 3 else 0,
            confidence=0.65,
            source_refs=[{'table': 'tickets', 'filter': 'open > 24h'}],
        ))

    return thoughts


# ── Sense 6: Sage (Balance) ──────────────────────────────────────────

def sage_aggregate(all_thoughts, signals):
    """Sage weighs all other voices and synthesises.

    Adds a sage summary thought if there are multiple notable signals.
    Also applies PFV gate to everything.
    """
    gated = []

    for thought in all_thoughts:
        combined, passed, details = pfv_gate(thought, signals)

        # Confidence prefix rule (§4b.4 safeguard #1)
        conf = thought.get('confidence', 0.5)
        if conf < 0.3:
            continue  # never surface
        if conf < 0.6:
            thought['thought'] = 'Low confidence: ' + thought['thought']
            thought['thought'] = thought['thought'][:140]

        if passed:
            thought['pfv_p'] = details['pfv_p']
            thought['pfv_f'] = details['pfv_f']
            thought['pfv_v'] = details['pfv_v']
            thought['context_json'] = json.dumps({
                'pfv': details,
                'collected_at': signals.get('collected_at'),
            })
            gated.append(thought)

    # If multiple urgent thoughts, sage adds a summary
    urgent = [t for t in gated if t.get('urgency', 0) >= 2]
    if len(urgent) >= 2:
        summary = f'{len(urgent)} urgent signals — {", ".join(t["orb_role"] for t in urgent)}'
        sage_thought = _thought(
            'sage',
            summary,
            detail='Multiple senses flagged urgency. Review recommended.',
            urgency=2,
            confidence=0.75,
            source_refs=[{'table': 'council_output', 'filter': 'current cycle'}],
        )
        _, sage_passed, sage_details = pfv_gate(sage_thought, signals)
        if sage_passed:
            sage_thought['pfv_p'] = sage_details['pfv_p']
            sage_thought['pfv_f'] = sage_details['pfv_f']
            sage_thought['pfv_v'] = sage_details['pfv_v']
            sage_thought['context_json'] = json.dumps({'pfv': sage_details})
            gated.append(sage_thought)

    return gated


# ── Sense 7: Patrol (Gut) ────────────────────────────────────────────

def patrol_score(signals):
    """Why SHOULDN'T we do this?

    Applies caution: resource cost, queue depth, dependency checks.
    Patrol doesn't produce surfaceable thoughts — it creates
    counter-signals that Sage uses for contradiction detection (§4b.4 #5).
    """
    warnings = []

    # Heavy queue = don't suggest more work
    depth = signals.get('queue_depth', 0)
    if depth > 15:
        warnings.append(_thought(
            'patrol',
            f'Caution: queue at {depth} — avoid adding more tasks',
            urgency=1,
            confidence=0.8,
            source_refs=[{'table': 'queue'}],
        ))

    # High CPU = don't suggest compute-heavy ops
    stats = signals.get('system_stats', {})
    cpu = stats.get('cpu_percent', 0)
    if cpu > 85:
        warnings.append(_thought(
            'patrol',
            f'Caution: CPU at {cpu:.0f}% — defer non-critical processing',
            urgency=1,
            confidence=0.85,
            source_refs=[{'table': 'system_stats'}],
        ))

    # Email backlog sanity
    backlog = signals.get('email_backlog', 0)
    if backlog > 20:
        warnings.append(_thought(
            'patrol',
            f'{backlog} unprocessed emails — email pipeline may be stuck',
            urgency=2,
            confidence=0.7,
            source_refs=[{'table': 'pending_emails'}],
        ))

    return warnings


# ── Main entry point ─────────────────────────────────────────────────

def run_council(signals):
    """Run all seven senses, aggregate through Sage, return gated thoughts.

    Returns list of thought dicts ready for council_output insertion.
    """
    # Collect candidate thoughts from all senses
    candidates = []
    candidates.extend(lookout_score(signals))
    candidates.extend(snoop_score(signals))
    candidates.extend(spark_score(signals))
    candidates.extend(skulk_score(signals))
    candidates.extend(keeper_score(signals))
    candidates.extend(patrol_score(signals))

    # Honesty check — enforce "always be honest" on every candidate
    for c in candidates:
        honesty_check(c)

    # Sage aggregates and applies PFV gate
    gated = sage_aggregate(candidates, signals)

    logger.info(
        "Council cycle: %d candidates → %d gated (%.0f%% filtered)",
        len(candidates),
        len(gated),
        ((len(candidates) - len(gated)) / max(len(candidates), 1)) * 100,
    )

    return gated
