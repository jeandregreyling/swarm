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
