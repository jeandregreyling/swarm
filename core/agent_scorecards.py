"""Durable capability scorecards for swarm agents.

The scorecard is intentionally small: it gives routing and prompts a visible,
updatable memory of which agents are strongest for common kinds of work. It is
not a hidden ranking; it is operational state the swarm can improve over time.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


CAPABILITY_ALIASES = {
    'analyse': 'analysis',
    'analyze': 'analysis',
    'architecture': 'architecture',
    'architect': 'architecture',
    'audit': 'audit',
    'code': 'coding',
    'coder': 'coding',
    'dev': 'coding',
    'develop': 'coding',
    'implementation': 'coding',
    'implement': 'coding',
    'memory': 'memory',
    'orchestrate': 'orchestration',
    'coordinate': 'orchestration',
    'payroll': 'sap_payroll',
    'sap': 'sap_payroll',
    'research': 'research',
    'search': 'research',
    'web': 'web_research',
    'qa': 'testing',
    'test': 'testing',
    'tests': 'testing',
    'recovery': 'recovery',
    'relay': 'recovery',
    'synthesise': 'synthesis',
    'synthesize': 'synthesis',
}


DEFAULT_SCORECARDS = [
    {'agent': 'eight', 'capability': 'sap_payroll', 'score': 0.95, 'confidence': 0.85, 'notes': 'SAP HCM/Payroll and Australian payroll specialist.'},
    {'agent': 'ten', 'capability': 'coding', 'score': 0.92, 'confidence': 0.72, 'notes': 'Software engineering advisor for implementation and code quality.'},
    {'agent': 'nine', 'capability': 'architecture', 'score': 0.90, 'confidence': 0.70, 'notes': 'System architecture and integration design.'},
    {'agent': 'duck', 'capability': 'audit', 'score': 0.92, 'confidence': 0.82, 'notes': 'Sanity checker, ALM auditor, regression risk review.'},
    {'agent': 'librarian', 'capability': 'memory', 'score': 0.90, 'confidence': 0.78, 'notes': 'Memory keeper and continuity retrieval.'},
    {'agent': 'seeker', 'capability': 'web_research', 'score': 0.90, 'confidence': 0.72, 'notes': 'Tavily/web-search specialist.'},
    {'agent': 'scholar', 'capability': 'research', 'score': 0.88, 'confidence': 0.70, 'notes': 'Structured research and synthesis.'},
    {'agent': 'llama', 'capability': 'research', 'score': 0.78, 'confidence': 0.62, 'notes': 'Fast local research and first-pass answers.'},
    {'agent': 'qwen', 'capability': 'analysis', 'score': 0.80, 'confidence': 0.62, 'notes': 'Local deep reasoning and analysis.'},
    {'agent': 'mistral', 'capability': 'analysis', 'score': 0.74, 'confidence': 0.58, 'notes': 'General analysis and alternate phrasing.'},
    {'agent': 'gemma', 'capability': 'orchestration', 'score': 0.84, 'confidence': 0.68, 'notes': 'Local coordination, routing, and synthesis.'},
    {'agent': 'gemma', 'capability': 'synthesis', 'score': 0.82, 'confidence': 0.64, 'notes': 'Combines agent outputs into concise final answers.'},
    {'agent': 'duck', 'capability': 'recovery', 'score': 0.84, 'confidence': 0.70, 'notes': 'Relay recovery review and risk spotting.'},
    {'agent': 'librarian', 'capability': 'recovery', 'score': 0.82, 'confidence': 0.70, 'notes': 'Relay recovery continuity and context lookup.'},
    {'agent': 'thirteen', 'capability': 'testing', 'score': 0.82, 'confidence': 0.60, 'notes': 'Testing-oriented HuggingFace agent.'},
    {'agent': 'sniffles', 'capability': 'audit', 'score': 0.78, 'confidence': 0.66, 'notes': 'Memory and consistency auditor.'},
]


def normalize_capability(capability: str) -> str:
    key = str(capability or '').strip().lower().replace('-', '_').replace(' ', '_')
    return CAPABILITY_ALIASES.get(key, key)


def ensure_schema(conn=None) -> None:
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_capability_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                capability TEXT NOT NULL,
                score REAL DEFAULT 0.5,
                confidence REAL DEFAULT 0.5,
                evidence_count INTEGER DEFAULT 0,
                source TEXT DEFAULT 'seed',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(agent, capability)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_capability_scores_capability "
            "ON agent_capability_scores(capability, score DESC)"
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def seed_default_scorecards(conn=None) -> int:
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()
    inserted = 0
    try:
        ensure_schema(conn)
        for item in DEFAULT_SCORECARDS:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO agent_capability_scores
                    (agent, capability, score, confidence, evidence_count, source, notes)
                VALUES (?, ?, ?, ?, 1, 'seed', ?)
                """,
                (
                    item['agent'],
                    normalize_capability(item['capability']),
                    float(item['score']),
                    float(item['confidence']),
                    item.get('notes', ''),
                ),
            )
            inserted += int(cur.rowcount or 0)
        conn.commit()
        return inserted
    finally:
        if own:
            conn.close()


def list_scorecards(
    *,
    capability: Optional[str] = None,
    agents: Optional[Iterable[str]] = None,
    limit: int = 50,
    conn=None,
) -> List[Dict[str, Any]]:
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()
    try:
        seed_default_scorecards(conn)
        clauses = []
        params: List[Any] = []
        if capability:
            clauses.append('capability=?')
            params.append(normalize_capability(capability))
        agent_set = {str(a).strip().lower() for a in (agents or []) if str(a).strip()}
        if agent_set:
            placeholders = ','.join('?' for _ in agent_set)
            clauses.append(f'agent IN ({placeholders})')
            params.extend(sorted(agent_set))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        capped = max(1, min(int(limit or 50), 200))
        rows = conn.execute(
            f"""SELECT agent, capability, score, confidence, evidence_count,
                       source, notes, updated_at
                FROM agent_capability_scores
                {where}
                ORDER BY score DESC, confidence DESC, evidence_count DESC, agent ASC
                LIMIT ?""",
            params + [capped],
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if own:
            conn.close()


def best_agent_for_capability(
    capability: str,
    *,
    candidates: Optional[Iterable[str]] = None,
    fallback: Optional[str] = None,
    conn=None,
) -> Optional[str]:
    rows = list_scorecards(
        capability=capability,
        agents=candidates,
        limit=1,
        conn=conn,
    )
    if rows:
        return str(rows[0]['agent'])
    return fallback


def record_capability_result(
    agent: str,
    capability: str,
    *,
    success: bool,
    quality_delta: float = 0.0,
    source: str = 'manual',
    notes: str = '',
    conn=None,
) -> Dict[str, Any]:
    agent = str(agent or '').strip().lower()
    cap = normalize_capability(capability)
    if not agent or not cap:
        raise ValueError('agent and capability are required')
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()
    try:
        seed_default_scorecards(conn)
        row = conn.execute(
            """SELECT score, confidence, evidence_count
               FROM agent_capability_scores
               WHERE agent=? AND capability=?""",
            (agent, cap),
        ).fetchone()
        if row:
            base_score = float(row['score'] or 0.5)
            evidence_count = int(row['evidence_count'] or 0)
            base_confidence = float(row['confidence'] or 0.5)
        else:
            base_score = 0.55
            evidence_count = 0
            base_confidence = 0.35

        signal = 0.75 if success else 0.25
        signal = max(0.0, min(signal + float(quality_delta or 0.0), 1.0))
        weight = 0.25 if evidence_count < 5 else 0.15
        score = round((base_score * (1.0 - weight)) + (signal * weight), 3)
        confidence = round(min(1.0, base_confidence + 0.05), 3)
        evidence_count += 1
        merged_notes = str(notes or '').strip()[:500]

        conn.execute(
            """
            INSERT INTO agent_capability_scores
                (agent, capability, score, confidence, evidence_count, source, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(agent, capability) DO UPDATE SET
                score=excluded.score,
                confidence=excluded.confidence,
                evidence_count=excluded.evidence_count,
                source=excluded.source,
                notes=CASE WHEN excluded.notes != '' THEN excluded.notes ELSE agent_capability_scores.notes END,
                updated_at=datetime('now')
            """,
            (agent, cap, score, confidence, evidence_count, source[:80], merged_notes),
        )
        conn.commit()
        return {
            'agent': agent,
            'capability': cap,
            'score': score,
            'confidence': confidence,
            'evidence_count': evidence_count,
        }
    finally:
        if own:
            conn.close()


def record_task_outcome(
    task_name: str,
    *,
    args: str = '',
    success: bool,
    output: str = '',
    category: str = '',
    conn=None,
) -> List[Dict[str, Any]]:
    """Convert a meaningful Tasker outcome into capability scorecard signals."""
    inferred = infer_task_outcome_signals(
        task_name,
        args=args,
        success=success,
        output=output,
        category=category,
    )
    results = []
    for signal in inferred:
        results.append(record_capability_result(conn=conn, **signal))
    return results


def record_duck_proposal_outcome(
    *,
    proposal_id: str,
    title: str = '',
    agent: str = '',
    phase: str,
    verdict: str,
    conn=None,
) -> List[Dict[str, Any]]:
    """Record scorecard signals from Duck proposal review and QA.

    Duck rejecting a weak proposal is a successful audit signal for Duck, not a
    failure. Builder agents only learn from the QA/execute phases where work
    quality has actually been checked or shipped.
    """
    phase = str(phase or '').strip().lower()
    verdict = str(verdict or '').strip().lower()
    builder = str(agent or '').strip().lower()
    label = str(title or proposal_id or '').strip()
    signals: List[Dict[str, Any]] = []

    if phase in {'intake', 'qa'} and verdict:
        signals.append({
            'agent': 'duck',
            'capability': 'audit',
            'success': True,
            'quality_delta': 0.06 if verdict in {'rejected', 'fail'} else 0.04,
            'source': f'proposal:duck_{phase}',
            'notes': f'Duck {phase} verdict {verdict} for {proposal_id}: {label}'[:500],
        })

    if phase == 'qa' and builder and verdict in {'pass', 'fail'}:
        signals.append({
            'agent': builder,
            'capability': 'coding',
            'success': verdict == 'pass',
            'quality_delta': 0.06 if verdict == 'pass' else -0.08,
            'source': 'proposal:duck_qa',
            'notes': f'Duck QA {verdict} for {proposal_id}: {label}'[:500],
        })

    if phase == 'execute' and builder:
        signals.append({
            'agent': builder,
            'capability': 'coding',
            'success': True,
            'quality_delta': 0.04,
            'source': 'proposal:closed',
            'notes': f'Proposal shipped/closed {proposal_id}: {label}'[:500],
        })

    results = []
    for signal in signals:
        results.append(record_capability_result(conn=conn, **signal))
    return results


def record_test_run_outcome(
    *,
    script_id: str,
    status: str,
    change_id: str = '',
    triggered_by: str = '',
    exit_code: Optional[int] = None,
    stdout_tail: str = '',
    conn=None,
) -> List[Dict[str, Any]]:
    """Teach scorecards from Test Lab runs linked to a proposal/change.

    Manual unlinked test runs are ignored because they do not identify which
    agent should learn from the result.
    """
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()
    try:
        status = str(status or '').strip().lower()
        if status not in {'pass', 'fail', 'error'}:
            return []
        agent, title = _agent_for_change_id(change_id, conn=conn)
        if not agent:
            agent = _agent_from_triggered_by(triggered_by)
        if not agent:
            return []

        success = status == 'pass'
        script = str(script_id or '').strip()
        notes = f'Test Lab {status} for {change_id or triggered_by or "manual"} via {script}: {title}'[:500]
        caps = ['testing']
        if _script_suggests_coding(script, stdout_tail):
            caps.append('coding')

        results = []
        for cap in caps:
            results.append(record_capability_result(
                agent,
                cap,
                success=success,
                quality_delta=0.07 if success else -0.10,
                source='testlab:run',
                notes=notes,
                conn=conn,
            ))
        return results
    finally:
        if own:
            conn.close()


def infer_task_outcome_signals(
    task_name: str,
    *,
    args: str = '',
    success: bool,
    output: str = '',
    category: str = '',
) -> List[Dict[str, Any]]:
    """Infer agent/capability updates from Tasker output without over-learning.

    We only emit signals for tasks where the result is meaningful enough to
    teach routing. Dry-runs, empty watched-topic runs, and deferred work are
    intentionally ignored so the scorecard doesn't learn from noise.
    """
    task = str(task_name or '').strip().lower()
    text = str(output or '').strip()
    lower_text = text.lower()
    opts = _parse_task_args(args)
    signals: List[Dict[str, Any]] = []

    if task == 'interest_research_update':
        if not success or 'qualified new evidence' not in lower_text or 'email sent' not in lower_text:
            return []
        agent = (opts.get('agent') or 'eight').strip().lower()
        topic = opts.get('topic') or ''
        signals.append({
            'agent': agent,
            'capability': 'research',
            'success': True,
            'quality_delta': 0.08,
            'source': 'tasker:interest_research_update',
            'notes': f'Qualified watched-topic evidence emailed for {topic}'[:500],
        })
        if _topic_is_sap_payroll(topic):
            signals.append({
                'agent': agent,
                'capability': 'sap_payroll',
                'success': True,
                'quality_delta': 0.08,
                'source': 'tasker:interest_research_update',
                'notes': f'Qualified SAP/payroll watched-topic evidence emailed for {topic}'[:500],
            })
        return signals

    if task == 'relay_recovery_sweep':
        run_agents = str(opts.get('run_agents') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
        if not success or not run_agents or 'reviewed ' not in lower_text or 'relay recoveries' not in lower_text:
            return []
        agents = [
            item.strip().lower()
            for item in str(opts.get('agents') or 'librarian,duck').split(',')
            if item.strip()
        ] or ['librarian', 'duck']
        for agent in agents:
            signals.append({
                'agent': agent,
                'capability': 'recovery',
                'success': True,
                'quality_delta': 0.05,
                'source': 'tasker:relay_recovery_sweep',
                'notes': 'Reviewed stalled relay recovery card via Tasker',
            })
        return signals

    if task == 'idle_research':
        if not success or 'started research session' not in lower_text:
            return []
        signals.append({
            'agent': opts.get('agent') or 'scholar',
            'capability': 'research',
            'success': True,
            'quality_delta': 0.03,
            'source': 'tasker:idle_research',
            'notes': text[:500],
        })
        return signals

    return signals


def _parse_task_args(args: str) -> Dict[str, str]:
    import shlex

    opts: Dict[str, str] = {}
    try:
        tokens = shlex.split(str(args or ''))
    except Exception:
        tokens = str(args or '').split()
    for token in tokens:
        if '=' not in token:
            continue
        key, value = token.split('=', 1)
        key = key.strip().lower().strip("'\"")
        value = value.strip().strip("'\"")
        if key:
            opts[key] = value
    return opts


def _topic_is_sap_payroll(topic: str) -> bool:
    tokens = str(topic or '').lower()
    return any(part in tokens for part in ('sap', 'payroll', 'hcm', 'successfactors', 'ecp'))


def _agent_for_change_id(change_id: str, *, conn=None) -> tuple[str, str]:
    change = str(change_id or '').strip()
    if not change or conn is None:
        return '', ''
    candidates = [change]
    if not change.startswith('INTERNAL-'):
        candidates.append(f'INTERNAL-{change}')
    try:
        placeholders = ','.join('?' for _ in candidates)
        row = conn.execute(
            f"""SELECT agent, title
                FROM work_proposals
                WHERE proposal_id IN ({placeholders}) OR ticket_number IN ({placeholders})
                ORDER BY updated_at DESC
                LIMIT 1""",
            candidates + candidates,
        ).fetchone()
    except Exception:
        return '', ''
    if not row:
        return '', ''
    return str(row['agent'] or '').strip().lower(), str(row['title'] or '').strip()


def _agent_from_triggered_by(triggered_by: str) -> str:
    raw = str(triggered_by or '').strip().lower()
    for prefix in ('agent:', 'proposal-agent:'):
        if raw.startswith(prefix):
            return raw[len(prefix):].strip()
    return ''


def _script_suggests_coding(script_id: str, stdout_tail: str = '') -> bool:
    text = f'{script_id} {stdout_tail}'.lower()
    return any(token in text for token in (
        'pytest', 'py_compile', 'node', 'eslint', 'tsc', 'compile',
        'integration', 'smoke', 'unit', 'regression', 'frontend',
    ))


def scorecard_context_block(
    *,
    capabilities: Optional[Iterable[str]] = None,
    limit: int = 10,
    conn=None,
) -> str:
    caps = [normalize_capability(c) for c in (capabilities or []) if str(c).strip()]
    rows: List[Dict[str, Any]] = []
    if caps:
        per_cap = max(1, int(limit or 10) // max(1, len(caps)))
        for cap in caps:
            rows.extend(list_scorecards(capability=cap, limit=per_cap, conn=conn))
    else:
        rows = list_scorecards(limit=limit, conn=conn)
    if not rows:
        return ''

    seen = set()
    lines = ['=== Agent capability scorecards ===']
    for row in rows[:max(1, int(limit or 10))]:
        key = (row['agent'], row['capability'])
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"- {row['capability']}: {row['agent']} "
            f"score={float(row['score']):.2f} confidence={float(row['confidence']):.2f}"
        )
    return '\n'.join(lines) + '\n\n'
