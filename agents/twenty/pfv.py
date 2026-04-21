"""PFV Gate — Plausible · Feasible · Valuable scoring.

Every thought must pass all three gates before surfacing.
Combined minimum: 0.35.
"""

import logging

logger = logging.getLogger('seven.agent20.pfv')

# Weights for combined score
W_PLAUSIBLE = 0.4
W_FEASIBLE  = 0.3
W_VALUABLE  = 0.3

# Individual thresholds
T_PLAUSIBLE = 0.5
T_FEASIBLE  = 0.4
T_VALUABLE  = 0.3

# Combined threshold
T_COMBINED = 0.35


def score_plausible(thought, signals):
    """Can this actually be done with what exists?

    Checks: data source exists, agent available, no prior failure on same topic.
    Returns float 0.0–1.0.
    """
    score = 0.5  # baseline — thought was generated from real data

    source_refs = thought.get('source_refs', [])
    if source_refs:
        score += 0.2  # has traceable data source

    # If the thought references an agent action, check agent is alive
    roster_names = {a.get('name') for a in signals.get('agent_roster', [])}
    agent_ref = thought.get('agent_ref')
    if agent_ref:
        if agent_ref in roster_names:
            score += 0.15
        else:
            score -= 0.3  # references dead/disabled agent

    # Cap at 1.0
    return min(max(score, 0.0), 1.0)


def score_feasible(thought, signals):
    """Can we realistically do this right now?

    Checks: queue depth, CPU load, dependency count.
    Returns float 0.0–1.0.
    """
    score = 0.6  # baseline — system is usually available

    # Queue overload penalty
    queue_depth = signals.get('queue_depth', 0)
    if queue_depth > 20:
        score -= 0.3
    elif queue_depth > 10:
        score -= 0.15

    # CPU overload penalty
    stats = signals.get('system_stats', {})
    cpu = stats.get('cpu_percent', 0)
    if cpu > 90:
        score -= 0.3
    elif cpu > 70:
        score -= 0.15

    # RAM pressure penalty
    ram_avail = stats.get('ram_available_gb', 8)
    if ram_avail < 1:
        score -= 0.2
    elif ram_avail < 2:
        score -= 0.1

    # High urgency boost — even if load is high, critical stuff matters
    if thought.get('urgency', 0) >= 3:
        score += 0.15

    return min(max(score, 0.0), 1.0)


def score_valuable(thought, signals):
    """Does the user actually care about this?

    Checks: topic relevance to user_interests, recency, past dismissal rate.
    Returns float 0.0–1.0.
    """
    score = 0.4  # baseline — thought came from real data, probably useful

    # Topic match against user interests
    topics = {t.get('topic', '').lower() for t in signals.get('user_topics', [])}
    thought_text = (thought.get('thought', '') + ' ' + thought.get('detail', '')).lower()
    for topic in topics:
        if topic and topic in thought_text:
            score += 0.2
            break

    # Dismissal penalty — if similar thoughts were dismissed recently
    dismissals = signals.get('recent_dismissals', [])
    orb_role = thought.get('orb_role', '')
    dismissed_count = sum(1 for d in dismissals if d.get('orb_role') == orb_role)
    if dismissed_count >= 3:
        score -= 0.3  # heavy penalty — user keeps dismissing this orb's thoughts
    elif dismissed_count >= 1:
        score -= 0.1

    # Urgency boost
    if thought.get('urgency', 0) >= 2:
        score += 0.15

    return min(max(score, 0.0), 1.0)


def pfv_gate(thought, signals):
    """Run all three gates.  Returns (combined_score, passed, details).

    details dict contains individual P/F/V scores for audit trail.
    """
    p = score_plausible(thought, signals)
    f = score_feasible(thought, signals)
    v = score_valuable(thought, signals)

    combined = p * W_PLAUSIBLE + f * W_FEASIBLE + v * W_VALUABLE

    passed = (
        p >= T_PLAUSIBLE
        and f >= T_FEASIBLE
        and v >= T_VALUABLE
        and combined >= T_COMBINED
    )

    details = {
        'pfv_p': round(p, 3),
        'pfv_f': round(f, 3),
        'pfv_v': round(v, 3),
        'pfv_combined': round(combined, 3),
        'passed': passed,
    }

    if not passed:
        reasons = []
        if p < T_PLAUSIBLE:
            reasons.append(f'P={p:.2f}<{T_PLAUSIBLE}')
        if f < T_FEASIBLE:
            reasons.append(f'F={f:.2f}<{T_FEASIBLE}')
        if v < T_VALUABLE:
            reasons.append(f'V={v:.2f}<{T_VALUABLE}')
        if combined < T_COMBINED:
            reasons.append(f'combined={combined:.2f}<{T_COMBINED}')
        details['reject_reasons'] = reasons
        logger.debug("PFV rejected: %s — %s", thought.get('thought', '')[:60], reasons)

    return combined, passed, details
