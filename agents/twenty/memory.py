"""Memory — Agent 20's persistent learning and recall.

Reads/writes memory_twenty table.  Learns patterns from repeated signals,
decays stale memories, and enforces the honesty rule: never suppress,
downplay, or spin information.  If it's bad news, surface it louder.

This is NOT an LLM memory — it's a structured fact store with importance
weighting, tag-based retrieval, and automatic consolidation.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from utils.db._connection import get_connection

logger = logging.getLogger('seven.agent20.memory')

# ── Constants ─────────────────────────────────────────────────────────

# Memory importance scale: 1 (trivial) → 10 (critical system event)
IMPORTANCE_TRIVIAL = 1
IMPORTANCE_LOW = 3
IMPORTANCE_NORMAL = 5
IMPORTANCE_HIGH = 7
IMPORTANCE_CRITICAL = 9

# Honesty rule — core constraint
HONESTY_RULE = (
    'Always be honest.  Never suppress, minimise, or spin bad news.  '
    'If a signal is negative, surface it with higher urgency, not lower.'
)

# Decay: memories below this importance lose relevance after DECAY_DAYS
DECAY_THRESHOLD = 4
DECAY_DAYS = 14

# Max memories before consolidation triggers
MAX_ACTIVE_MEMORIES = 200
CONSOLIDATION_BATCH = 50


# ── Write ─────────────────────────────────────────────────────────────

def remember(subject, content, tags='', importance=IMPORTANCE_NORMAL,
             source='council', ticket_ref='', conn=None):
    """Write a new memory.  Returns the row id."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        cur = conn.execute(
            """INSERT INTO memory_twenty
               (agent, subject, content, tags, importance, source, ticket_ref)
               VALUES ('twenty', ?, ?, ?, ?, ?, ?)""",
            (subject[:200], content[:2000], tags[:500], importance, source, ticket_ref),
        )
        conn.commit()
        mid = cur.lastrowid
        logger.debug("Memory stored: id=%d subject=%s importance=%d", mid, subject[:40], importance)
        return mid
    finally:
        if close:
            conn.close()


def remember_pattern(pattern_type, pattern_key, pattern_value, confidence=0.5,
                     conn=None):
    """Upsert into user_patterns — tracks recurring behaviours."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        existing = conn.execute(
            "SELECT id, occurrences, confidence FROM user_patterns WHERE pattern_type=? AND pattern_key=?",
            (pattern_type, pattern_key),
        ).fetchone()
        if existing:
            new_occ = existing['occurrences'] + 1
            # Confidence grows with repetition but caps at 0.95
            new_conf = min(0.95, existing['confidence'] + 0.05)
            conn.execute(
                "UPDATE user_patterns SET occurrences=?, confidence=?, pattern_value=?, last_seen=datetime('now') WHERE id=?",
                (new_occ, new_conf, pattern_value, existing['id']),
            )
        else:
            conn.execute(
                "INSERT INTO user_patterns (pattern_type, pattern_key, pattern_value, confidence) VALUES (?, ?, ?, ?)",
                (pattern_type, pattern_key, pattern_value, confidence),
            )
        conn.commit()
    finally:
        if close:
            conn.close()


# ── Read / Recall ─────────────────────────────────────────────────────

def recall(subject_like=None, tags_like=None, min_importance=1, limit=20,
           conn=None):
    """Retrieve memories by subject/tag/importance.  Returns list of dicts."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        clauses = ["archived = 0"]
        params = []
        if subject_like:
            clauses.append("subject LIKE ?")
            params.append(f'%{subject_like}%')
        if tags_like:
            clauses.append("tags LIKE ?")
            params.append(f'%{tags_like}%')
        if min_importance > 1:
            clauses.append("importance >= ?")
            params.append(min_importance)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT id, subject, content, tags, importance, source, ticket_ref, created_at "
            f"FROM memory_twenty WHERE {where} "
            f"ORDER BY importance DESC, created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close:
            conn.close()


def recall_patterns(pattern_type=None, min_confidence=0.3, limit=20,
                    conn=None):
    """Retrieve learned patterns.  Returns list of dicts."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        clauses = ["confidence >= ?"]
        params = [min_confidence]
        if pattern_type:
            clauses.append("pattern_type = ?")
            params.append(pattern_type)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT id, pattern_type, pattern_key, pattern_value, confidence, "
            f"occurrences, first_seen, last_seen FROM user_patterns "
            f"WHERE {where} ORDER BY confidence DESC, occurrences DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close:
            conn.close()


# ── Honesty enforcement ──────────────────────────────────────────────

def honesty_check(thought):
    """Apply honesty rule to a thought dict.

    If signals are negative (errors, failures, overload) but urgency is low,
    boost the urgency.  Never allows downgrading severity.

    Returns the thought dict (mutated in place).
    """
    text = (thought.get('thought', '') + ' ' + thought.get('detail', '')).lower()

    negative_signals = [
        'error', 'fail', 'crash', 'stuck', 'overload', 'timeout',
        'broken', 'missing', 'lost', 'corrupt', 'dead', 'unreachable',
        'backlog', 'stale', 'expired', 'blocked', 'rejected',
    ]
    hit_count = sum(1 for word in negative_signals if word in text)

    if hit_count >= 2 and thought.get('urgency', 0) < 1:
        thought['urgency'] = 1
        thought['detail'] = (thought.get('detail', '') +
                             ' [honesty: negative signals detected, urgency raised]')
    elif hit_count >= 3 and thought.get('urgency', 0) < 2:
        thought['urgency'] = 2
        thought['detail'] = (thought.get('detail', '') +
                             ' [honesty: multiple negative signals, urgency raised to 2]')

    # Never allow confidence inflation on negative signals
    if hit_count >= 2 and thought.get('confidence', 0.5) > 0.9:
        thought['confidence'] = min(thought['confidence'], 0.85)
        thought['detail'] = (thought.get('detail', '') +
                             ' [honesty: confidence capped on negative signal]')

    return thought


# ── Decay & consolidation ────────────────────────────────────────────

def decay_stale_memories(conn=None):
    """Archive low-importance memories older than DECAY_DAYS.

    Returns count of archived rows.
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=DECAY_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
        result = conn.execute(
            "UPDATE memory_twenty SET archived = 1 WHERE archived = 0 AND importance <= ? AND created_at < ?",
            (DECAY_THRESHOLD, cutoff),
        )
        conn.commit()
        count = result.rowcount
        if count > 0:
            logger.info("Memory decay: archived %d stale memories (importance<=%d, age>%dd)",
                        count, DECAY_THRESHOLD, DECAY_DAYS)
        return count
    finally:
        if close:
            conn.close()


def consolidate_if_needed(conn=None):
    """If active memory count exceeds MAX, archive the oldest low-importance batch.

    Returns count of archived rows (0 if no consolidation needed).
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_twenty WHERE archived = 0"
        ).fetchone()[0]
        if count <= MAX_ACTIVE_MEMORIES:
            return 0
        # Archive oldest low-importance batch
        result = conn.execute(
            """UPDATE memory_twenty SET archived = 1
               WHERE id IN (
                   SELECT id FROM memory_twenty
                   WHERE archived = 0 AND importance <= ?
                   ORDER BY created_at ASC LIMIT ?
               )""",
            (IMPORTANCE_NORMAL, CONSOLIDATION_BATCH),
        )
        conn.commit()
        archived = result.rowcount
        if archived > 0:
            logger.info("Memory consolidation: archived %d (was %d active, max %d)",
                        archived, count, MAX_ACTIVE_MEMORIES)
        return archived
    finally:
        if close:
            conn.close()


# ── Learning from signals ─────────────────────────────────────────────

def learn_from_cycle(signals, thoughts, conn=None):
    """Extract learnable facts from a council cycle and persist them.

    Called at the end of each scheduler cycle.
    - Detects repeating error patterns
    - Tracks queue trends
    - Notes user interest shifts
    - Records decision patterns
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        learned = 0

        # 1. Error pattern detection
        errors = signals.get('agent_errors', [])
        if errors:
            by_service = {}
            for e in errors:
                svc = e.get('service', 'unknown')
                by_service[svc] = by_service.get(svc, 0) + 1
            for svc, count in by_service.items():
                remember_pattern(
                    'error_frequency', svc,
                    json.dumps({'count': count, 'at': signals.get('collected_at', '')}),
                    confidence=min(0.3 + count * 0.1, 0.9),
                    conn=conn,
                )
                learned += 1

        # 2. Queue depth trend
        depth = signals.get('queue_depth', 0)
        if depth > 0:
            remember_pattern(
                'queue_depth', 'current',
                json.dumps({'depth': depth, 'at': signals.get('collected_at', '')}),
                confidence=0.3,
                conn=conn,
            )
            learned += 1

        # 3. High-importance events get full memory entries
        for t in thoughts:
            if t.get('urgency', 0) >= 2:
                remember(
                    subject=f"urgent:{t['orb_role']}",
                    content=t['thought'],
                    tags=f"urgency:{t['urgency']},role:{t['orb_role']}",
                    importance=IMPORTANCE_HIGH,
                    source='council',
                    conn=conn,
                )
                learned += 1

        # 4. System pressure patterns
        stats = signals.get('system_stats', {})
        cpu = stats.get('cpu_percent', 0)
        if cpu > 70:
            remember_pattern(
                'system_pressure', 'cpu_high',
                json.dumps({'cpu': cpu, 'at': signals.get('collected_at', '')}),
                confidence=min(0.4 + (cpu - 70) * 0.01, 0.9),
                conn=conn,
            )
            learned += 1

        # 5. Dismissal learning — what does the user NOT want to see?
        dismissals = signals.get('recent_dismissals', [])
        for d in dismissals[:5]:  # limit
            remember_pattern(
                'dismissal_trend', d.get('orb_role', 'unknown'),
                d.get('thought', '')[:200],
                confidence=0.3,
                conn=conn,
            )
            learned += 1

        # 6. Periodic maintenance
        decay_stale_memories(conn=conn)
        consolidate_if_needed(conn=conn)

        if learned > 0:
            logger.debug("Memory learned %d facts from cycle", learned)
        return learned

    finally:
        if close:
            conn.close()
