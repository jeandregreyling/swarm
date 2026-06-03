"""kc_overview.py — KC introspection ("what does Swarm know?").

Y.48. Surfaces a compact, useful summary of the Knowledge Center across:

* media curriculum    (`kc_media_curriculum`) — counts + by-kind breakdown
* media trace         (`kc_media_trace`)      — provenance row count
* user interests      (`user_interests`)      — total + seed count by category
* App Center pillar   (`app_projects`)        — total + by-kind
* Synth board pillar  (`synth_board_projects`)
* Video editor pillar (`video_timelines`)
* knowledge_sources   (if the table exists) — ingested doc count

Single endpoint::

    GET /api/kc/overview

Returns a JSON object the chat surface, settings panel, or onboarding card
can consume to answer "what's in here?".
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import sqlite3

from flask import Blueprint, jsonify

from services import get_connection

kc_overview_bp = Blueprint('kc_overview', __name__)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def _count(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    try:
        return int(conn.execute(sql, args).fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def _group_count(conn: sqlite3.Connection, sql: str) -> dict:
    try:
        return {row[0]: int(row[1]) for row in conn.execute(sql).fetchall()}
    except sqlite3.OperationalError:
        return {}


def _scalar(conn: sqlite3.Connection, sql: str, args: tuple = (), default=None):
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else default
    except sqlite3.OperationalError:
        return default


def _parse_dt(value):
    raw = str(value or '').strip()
    if not raw:
        return None
    for fmt, width in (('%Y-%m-%d %H:%M:%S', 19), ('%Y-%m-%dT%H:%M:%S', 19), ('%Y-%m-%d', 10)):
        try:
            return datetime.strptime(raw[:width], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def _age_hours(value, now=None):
    dt = _parse_dt(value)
    if not dt:
        return None
    now = now or datetime.now()
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def _finding(findings, severity, area, message, detail=None):
    findings.append({
        'severity': severity,
        'area': area,
        'message': message,
        'detail': detail or {},
    })


def _status_from_findings(findings):
    severities = {f.get('severity') for f in findings}
    if 'critical' in severities:
        return 'critical'
    if 'warn' in severities:
        return 'warn'
    return 'healthy'


def _hive_db_path():
    return os.environ.get(
        'SWARM_HIVE_DB',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), 'swarm_hive.db'),
    )


def build_brain_health(conn: sqlite3.Connection, *, hive_db_path: str | None = None,
                       now: datetime | None = None) -> dict:
    """Read-only KC brain health contract used by UI, Tasker, and tests."""
    if now is None:
        now = datetime.now()
        db_now = datetime.now(timezone.utc).replace(tzinfo=None)
    elif now.tzinfo:
        db_now = now.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        db_now = now
    findings = []
    checks = {}

    counts = {}
    for table in (
        'project_docs', 'knowledge_sources', 'knowledge_chunks',
        'swarm_knowledge', 'memory', 'user_interests',
        'watched_topic_settings', 'watched_topic_evidence',
        'research_sessions', 'research_evidence',
        'newsletter_article_feedback',
    ):
        counts[table] = _count(conn, f'SELECT COUNT(*) FROM {table}') if _table_exists(conn, table) else 0
    checks['counts'] = counts

    checks['knowledge'] = {
        'project_docs': counts['project_docs'],
        'knowledge_sources': counts['knowledge_sources'],
        'knowledge_chunks': counts['knowledge_chunks'],
        'swarm_knowledge': counts['swarm_knowledge'],
        'latest_doc_updated_at': _scalar(conn, 'SELECT MAX(updated_at) FROM project_docs')
            if _table_exists(conn, 'project_docs') else None,
        'latest_fact_updated_at': _scalar(conn, 'SELECT MAX(updated_at) FROM swarm_knowledge')
            if _table_exists(conn, 'swarm_knowledge') else None,
    }
    if counts['project_docs'] and not counts['knowledge_chunks']:
        _finding(findings, 'warn', 'knowledge', 'project_docs exist but no knowledge_chunks are indexed')
    if counts['knowledge_sources'] and not counts['knowledge_chunks']:
        _finding(findings, 'warn', 'knowledge', 'knowledge_sources exist but chunk index is empty')
    if not counts['swarm_knowledge']:
        _finding(findings, 'warn', 'knowledge', 'swarm_knowledge has no durable facts')

    memory_tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'memory%' ORDER BY name"
    ).fetchall()]
    memory_counts = {}
    for table in memory_tables:
        try:
            memory_counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] or 0)
        except sqlite3.OperationalError:
            memory_counts[table] = 0
    checks['memory'] = {
        'tables': memory_counts,
        'table_count': len(memory_tables),
        'nonempty_table_count': sum(1 for v in memory_counts.values() if v > 0),
    }
    if 'memory' not in memory_counts:
        _finding(findings, 'critical', 'memory', 'shared memory table is missing')
    if checks['memory']['nonempty_table_count'] == 0:
        _finding(findings, 'warn', 'memory', 'no memory tables contain rows')

    interest_sources = _group_count(
        conn,
        "SELECT COALESCE(source,'') AS source, COUNT(*) FROM user_interests "
        "WHERE active=1 GROUP BY COALESCE(source,'') ORDER BY source",
    ) if _table_exists(conn, 'user_interests') else {}
    interest_categories = _group_count(
        conn,
        "SELECT COALESCE(category,'general') AS category, COUNT(*) FROM user_interests "
        "WHERE active=1 GROUP BY COALESCE(category,'general') ORDER BY category",
    ) if _table_exists(conn, 'user_interests') else {}
    active_interests = sum(interest_sources.values())
    durable_sources = sum(v for k, v in interest_sources.items() if k in {'user', 'manual', 'seed', 'newsletter_feedback'})
    checks['interests'] = {
        'active': active_interests,
        'by_source': interest_sources,
        'by_category': interest_categories,
        'durable_source_count': durable_sources,
        'watched_topic_settings': counts['watched_topic_settings'],
    }
    if active_interests and durable_sources == 0:
        _finding(findings, 'warn', 'interests', 'active interests exist but none are durable user/seed/newsletter rows',
                 {'by_source': interest_sources})
    if counts['watched_topic_settings'] and active_interests == 0:
        _finding(findings, 'warn', 'interests', 'watched-topic settings exist without active interests')

    newsletter_docs = []
    if _table_exists(conn, 'project_docs'):
        newsletter_docs = [dict(r) for r in conn.execute(
            "SELECT doc_name, tags, updated_at FROM project_docs "
            "WHERE tags LIKE '%newsletter%' OR doc_name LIKE '%NEWSLETTER%' "
            "ORDER BY updated_at DESC LIMIT 8"
        ).fetchall()]
    latest_newsletter = newsletter_docs[0] if newsletter_docs else None
    latest_newsletter_age = _age_hours(latest_newsletter.get('updated_at') if latest_newsletter else None, db_now)
    checks['newsletter'] = {
        'doc_count': len(newsletter_docs),
        'latest': latest_newsletter,
        'latest_age_hours': latest_newsletter_age,
        'feedback_rows': counts['newsletter_article_feedback'],
    }
    if not latest_newsletter:
        _finding(findings, 'critical', 'newsletter', 'no newsletter artifact found in project_docs')
    elif latest_newsletter_age is not None and latest_newsletter_age > 48:
        _finding(findings, 'warn', 'newsletter', 'latest newsletter artifact is older than 48 hours',
                 {'age_hours': round(latest_newsletter_age, 1), 'doc': latest_newsletter})

    stale_tasks = []
    newsletter_tasks = []
    if _table_exists(conn, 'scheduled_tasks'):
        task_rows = conn.execute(
            "SELECT id, name, schedule, action_type, action_data, enabled, last_run, next_run "
            "FROM scheduled_tasks WHERE enabled=1 ORDER BY id"
        ).fetchall()
        for row in task_rows:
            item = dict(row)
            action = f"{item.get('name') or ''} {item.get('action_data') or ''}".lower()
            if 'newsletter' in action or 'interest_research_update' in action or 'sap' in action:
                newsletter_tasks.append(item)
            next_dt = _parse_dt(item.get('next_run'))
            if next_dt and next_dt < now:
                stale_tasks.append(item)
    checks['scheduler'] = {
        'newsletter_or_interest_tasks': len(newsletter_tasks),
        'stale_enabled_tasks': stale_tasks[:20],
        'stale_enabled_task_count': len(stale_tasks),
    }
    if newsletter_tasks and stale_tasks:
        _finding(findings, 'warn', 'scheduler', 'enabled scheduled tasks have next_run in the past',
                 {'stale_count': len(stale_tasks), 'examples': stale_tasks[:5]})

    latest_evidence_updated = _scalar(conn, 'SELECT MAX(updated_at) FROM watched_topic_evidence') \
        if _table_exists(conn, 'watched_topic_evidence') else None
    evidence_age = _age_hours(latest_evidence_updated, db_now)
    checks['watched_topics'] = {
        'settings': counts['watched_topic_settings'],
        'evidence': counts['watched_topic_evidence'],
        'latest_evidence_updated_at': latest_evidence_updated,
        'latest_evidence_age_hours': evidence_age,
        'qualified': _count(conn, 'SELECT COUNT(*) FROM watched_topic_evidence WHERE qualified=1')
            if _table_exists(conn, 'watched_topic_evidence') else 0,
    }
    if counts['watched_topic_settings'] and not counts['watched_topic_evidence']:
        _finding(findings, 'warn', 'watched_topics', 'watched topics are configured but have no evidence rows')
    elif evidence_age is not None and evidence_age > 168:
        _finding(findings, 'warn', 'watched_topics', 'watched-topic evidence is older than 7 days',
                 {'age_hours': round(evidence_age, 1)})

    task_failures_24h = 0
    if _table_exists(conn, 'task_run_log'):
        task_failures_24h = _count(
            conn,
            "SELECT COUNT(*) FROM task_run_log "
            "WHERE lower(status) IN ('error','failed','failure','timeout') "
            "AND datetime(run_at) >= datetime('now','-1 day')",
        )
    checks['tasker'] = {'failures_24h': task_failures_24h}
    if task_failures_24h:
        _finding(findings, 'warn', 'tasker', 'Tasker has failed runs in the last 24 hours',
                 {'failures_24h': task_failures_24h})

    hive = {'db_path': hive_db_path or _hive_db_path(), 'available': False}
    try:
        hconn = sqlite3.connect(hive['db_path'])
        hconn.row_factory = sqlite3.Row
        try:
            now_ts = int(now.replace(tzinfo=timezone.utc).timestamp()) if now.tzinfo else int(now.timestamp())
            node_rows = hconn.execute(
                "SELECT node_id, platform, last_seen_ts FROM hive_nodes ORDER BY last_seen_ts DESC"
            ).fetchall()
            live_nodes = [
                dict(r) for r in node_rows
                if r['last_seen_ts'] and now_ts - int(r['last_seen_ts']) <= 90
            ]
            hive.update({
                'available': True,
                'nodes': len(node_rows),
                'live_nodes': len(live_nodes),
                'latest_node': dict(node_rows[0]) if node_rows else None,
                'jobs': _count(hconn, 'SELECT COUNT(*) FROM hive_jobs'),
                'pending_jobs': _count(hconn, "SELECT COUNT(*) FROM hive_jobs WHERE status='pending'"),
            })
        finally:
            hconn.close()
    except Exception as exc:
        hive.update({'error': str(exc)})
    checks['hive'] = hive
    if not hive.get('available'):
        _finding(findings, 'warn', 'hive', 'hive database is unavailable', {'db_path': hive.get('db_path')})
    elif hive.get('nodes', 0) and hive.get('live_nodes', 0) == 0:
        _finding(findings, 'warn', 'hive', 'hive has known nodes but none are live')

    status = _status_from_findings(findings)
    return {
        'ok': status != 'critical',
        'status': status,
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'checks': checks,
        'findings': findings,
    }


@kc_overview_bp.route('/api/kc/overview', methods=['GET'])
def overview():
    conn = get_connection()
    try:
        out: dict = {'ok': True, 'pillars': {}, 'curriculum': {}, 'user_interests': {}}

        # ── Media curriculum ───────────────────────────────────────────────
        if _table_exists(conn, 'kc_media_curriculum'):
            total = _count(conn, 'SELECT COUNT(*) FROM kc_media_curriculum')
            by_kind = _group_count(
                conn,
                'SELECT kind, COUNT(*) FROM kc_media_curriculum GROUP BY kind ORDER BY kind',
            )
            top_topics = [
                {'topic': r[0], 'tools': int(r[1])}
                for r in conn.execute(
                    "SELECT topic, COUNT(*) AS c FROM kc_media_curriculum "
                    "GROUP BY topic ORDER BY c DESC, topic ASC LIMIT 10"
                ).fetchall()
            ]
            out['curriculum'] = {
                'total': total, 'by_kind': by_kind, 'top_topics': top_topics,
            }
        if _table_exists(conn, 'kc_media_trace'):
            out['curriculum']['traces'] = _count(conn, 'SELECT COUNT(*) FROM kc_media_trace')

        # ── User interests ────────────────────────────────────────────────
        if _table_exists(conn, 'user_interests'):
            total = _count(conn, 'SELECT COUNT(*) FROM user_interests WHERE active=1')
            seeded = _count(
                conn, "SELECT COUNT(*) FROM user_interests WHERE source='seed' AND active=1"
            )
            by_category = _group_count(
                conn,
                "SELECT category, COUNT(*) FROM user_interests "
                "WHERE active=1 GROUP BY category ORDER BY category",
            )
            out['user_interests'] = {
                'total_active': total, 'seeded': seeded, 'by_category': by_category,
            }

        # ── App Center (Y.47) ─────────────────────────────────────────────
        if _table_exists(conn, 'app_projects'):
            out['pillars']['app_center'] = {
                'projects': _count(conn, 'SELECT COUNT(*) FROM app_projects'),
                'by_kind': _group_count(
                    conn,
                    'SELECT kind, COUNT(*) FROM app_projects GROUP BY kind ORDER BY kind',
                ),
                'builds': _count(conn, 'SELECT COUNT(*) FROM app_builds')
                    if _table_exists(conn, 'app_builds') else 0,
            }

        # ── Synth board (Y.43) ────────────────────────────────────────────
        if _table_exists(conn, 'synth_board_projects'):
            out['pillars']['synth_board'] = {
                'projects': _count(conn, 'SELECT COUNT(*) FROM synth_board_projects'),
                'revisions': _count(conn, 'SELECT COUNT(*) FROM synth_board_revisions')
                    if _table_exists(conn, 'synth_board_revisions') else 0,
            }

        # ── Video editor (Y.43) ───────────────────────────────────────────
        if _table_exists(conn, 'video_timelines'):
            out['pillars']['video_editor'] = {
                'timelines': _count(conn, 'SELECT COUNT(*) FROM video_timelines'),
                'render_jobs': _count(conn, 'SELECT COUNT(*) FROM video_render_jobs')
                    if _table_exists(conn, 'video_render_jobs') else 0,
            }

        # ── knowledge_sources (informational) ─────────────────────────────
        if _table_exists(conn, 'knowledge_sources'):
            out['pillars']['knowledge_sources'] = {
                'count': _count(conn, 'SELECT COUNT(*) FROM knowledge_sources'),
            }

        return jsonify(out)
    finally:
        conn.close()


@kc_overview_bp.route('/api/kc/brain/health', methods=['GET'])
def brain_health():
    conn = get_connection()
    try:
        return jsonify(build_brain_health(conn))
    finally:
        conn.close()
