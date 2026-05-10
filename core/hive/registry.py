"""core.hive.registry — persistent node registry.

Stores enrolled hive nodes plus their most recent telemetry. Backed by
SQLite at ``$SWARM_HIVE_DB`` (default ``swarm_hive.db`` next to the main
swarm.db). Schema is intentionally narrow — telemetry history beyond the
last sample lives elsewhere; this table is the live state.

Single-process safe; multi-process safe under SQLite's default WAL.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Iterable

from .contract import (
    POLICY_CONTRACT,
    TELEMETRY_CONTRACT,
    validate_policy,
    validate_telemetry,
)

DEFAULT_DB = os.environ.get(
    'SWARM_HIVE_DB',
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'swarm_hive.db'),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hive_nodes (
    node_id        TEXT PRIMARY KEY,
    platform       TEXT NOT NULL,
    enrolled_ts    INTEGER NOT NULL,
    last_seen_ts   INTEGER,
    telemetry_json TEXT,
    policy_json    TEXT,
    label          TEXT,
    notes          TEXT
);

CREATE INDEX IF NOT EXISTS idx_hive_nodes_last_seen
    ON hive_nodes (last_seen_ts);

CREATE TABLE IF NOT EXISTS hive_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,
    node_id   TEXT NOT NULL,
    kind      TEXT NOT NULL,
    detail    TEXT
);

CREATE INDEX IF NOT EXISTS idx_hive_events_ts ON hive_events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_hive_events_node ON hive_events (node_id, ts DESC);

CREATE TABLE IF NOT EXISTS hive_jobs (
    job_id        TEXT PRIMARY KEY,
    node_id       TEXT,
    kind          TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    result_json   TEXT,
    created_ts    INTEGER NOT NULL,
    claimed_ts    INTEGER,
    completed_ts  INTEGER,
    capability_req TEXT
);

CREATE INDEX IF NOT EXISTS idx_hive_jobs_status ON hive_jobs (status, created_ts);
CREATE INDEX IF NOT EXISTS idx_hive_jobs_node ON hive_jobs (node_id, status);
"""


class HiveRegistry:
    """SQLite-backed Hive node registry. Thread-safe for single-process use.

    A new connection is opened per call (SQLite is fine with this and it
    avoids cross-thread cursor sharing); a process-wide lock guards
    write paths so we don't lose telemetry under concurrent updates.
    """

    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ensure_schema()

    # -- schema ----------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
        except sqlite3.DatabaseError:
            pass
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    # -- enrolment / lifecycle -------------------------------------------
    def enrol(self, node_id: str, platform: str, *,
              label: str | None = None, notes: str | None = None) -> dict:
        """Insert or refresh a node row. Idempotent."""
        if not node_id or not isinstance(node_id, str):
            raise ValueError('node_id must be a non-empty string')
        if not platform:
            raise ValueError('platform required')
        now = int(time.time())
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                'SELECT enrolled_ts FROM hive_nodes WHERE node_id=?',
                (node_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    'UPDATE hive_nodes SET platform=?, label=COALESCE(?, label), '
                    'notes=COALESCE(?, notes) WHERE node_id=?',
                    (platform, label, notes, node_id),
                )
                kind = 're-enrolled'
            else:
                conn.execute(
                    'INSERT INTO hive_nodes (node_id, platform, enrolled_ts, '
                    'label, notes) VALUES (?,?,?,?,?)',
                    (node_id, platform, now, label, notes),
                )
                kind = 'enrolled'
            conn.execute(
                'INSERT INTO hive_events (ts, node_id, kind, detail) '
                'VALUES (?,?,?,?)',
                (now, node_id, kind, platform),
            )
            conn.commit()
        return {'ok': True, 'node_id': node_id, 'platform': platform,
                'kind': kind}

    def remove(self, node_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute('DELETE FROM hive_nodes WHERE node_id=?',
                               (node_id,))
            conn.execute(
                'INSERT INTO hive_events (ts, node_id, kind, detail) '
                'VALUES (?,?,?,?)',
                (int(time.time()), node_id, 'removed', None),
            )
            conn.commit()
            return cur.rowcount > 0

    # -- telemetry -------------------------------------------------------
    def record_telemetry(self, payload: dict) -> dict:
        """Validate + persist a telemetry envelope.

        Auto-enrols the node if it's not already known. Updates
        ``last_seen_ts`` and the cached ``telemetry_json``.
        """
        validate_telemetry(payload)
        node_id = payload['node_id']
        platform = payload['platform']
        ts = int(payload.get('ts') or time.time())
        encoded = json.dumps(payload, separators=(',', ':'))
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT node_id FROM hive_nodes WHERE node_id=?',
                (node_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    'INSERT INTO hive_nodes (node_id, platform, enrolled_ts, '
                    'last_seen_ts, telemetry_json) VALUES (?,?,?,?,?)',
                    (node_id, platform, ts, ts, encoded),
                )
                conn.execute(
                    'INSERT INTO hive_events (ts, node_id, kind, detail) '
                    'VALUES (?,?,?,?)',
                    (ts, node_id, 'auto-enrolled', platform),
                )
            else:
                conn.execute(
                    'UPDATE hive_nodes SET platform=?, last_seen_ts=?, '
                    'telemetry_json=? WHERE node_id=?',
                    (platform, ts, encoded, node_id),
                )
            conn.commit()
        return {'ok': True, 'node_id': node_id, 'ts': ts}

    def latest_telemetry(self, node_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT telemetry_json FROM hive_nodes WHERE node_id=?',
                (node_id,),
            ).fetchone()
        if not row or not row['telemetry_json']:
            return None
        try:
            return json.loads(row['telemetry_json'])
        except (json.JSONDecodeError, TypeError):
            return None

    # -- policy ----------------------------------------------------------
    def set_policy(self, payload: dict) -> dict:
        validate_policy(payload)
        node_id = payload['node_id']
        encoded = json.dumps(payload, separators=(',', ':'))
        ts = int(payload.get('ts') or time.time())
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT node_id FROM hive_nodes WHERE node_id=?',
                (node_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f'unknown node: {node_id}')
            conn.execute(
                'UPDATE hive_nodes SET policy_json=? WHERE node_id=?',
                (encoded, node_id),
            )
            conn.execute(
                'INSERT INTO hive_events (ts, node_id, kind, detail) '
                'VALUES (?,?,?,?)',
                (ts, node_id, 'policy-set',
                 json.dumps(payload.get('policy') or {})),
            )
            conn.commit()
        return {'ok': True, 'node_id': node_id, 'ts': ts}

    def latest_policy(self, node_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT policy_json FROM hive_nodes WHERE node_id=?',
                (node_id,),
            ).fetchone()
        if not row or not row['policy_json']:
            return None
        try:
            return json.loads(row['policy_json'])
        except (json.JSONDecodeError, TypeError):
            return None

    # -- listing ---------------------------------------------------------
    def list_nodes(self, *, max_age_s: int | None = None) -> list:
        """Return all enrolled nodes with their most recent telemetry.

        ``max_age_s`` filters out nodes whose ``last_seen_ts`` is older
        than the threshold (use ``None`` to include everything).
        """
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT node_id, platform, enrolled_ts, last_seen_ts, '
                'telemetry_json, policy_json, label, notes '
                'FROM hive_nodes ORDER BY COALESCE(last_seen_ts, 0) DESC',
            ).fetchall()
        now = int(time.time())
        out = []
        for r in rows:
            last_seen = r['last_seen_ts']
            if max_age_s is not None and (
                last_seen is None or now - last_seen > max_age_s
            ):
                continue
            try:
                telem = json.loads(r['telemetry_json']) \
                    if r['telemetry_json'] else None
            except (json.JSONDecodeError, TypeError):
                telem = None
            try:
                policy = json.loads(r['policy_json']) \
                    if r['policy_json'] else None
            except (json.JSONDecodeError, TypeError):
                policy = None
            out.append({
                'node_id': r['node_id'],
                'platform': r['platform'],
                'enrolled_ts': r['enrolled_ts'],
                'last_seen_ts': last_seen,
                'age_s': (now - last_seen) if last_seen else None,
                'label': r['label'],
                'notes': r['notes'],
                'telemetry': telem,
                'policy': policy,
            })
        return out

    def get_node(self, node_id: str) -> dict | None:
        for n in self.list_nodes():
            if n['node_id'] == node_id:
                return n
        return None

    # -- events ----------------------------------------------------------
    def recent_events(self, *, node_id: str | None = None,
                      limit: int = 50) -> list:
        sql = ('SELECT id, ts, node_id, kind, detail FROM hive_events '
               'WHERE 1=1 ')
        args: list = []
        if node_id:
            sql += 'AND node_id=? '
            args.append(node_id)
        sql += 'ORDER BY ts DESC LIMIT ?'
        args.append(int(max(1, min(500, limit))))
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # -- maintenance -----------------------------------------------------
    def prune_events(self, *, older_than_s: int = 7 * 86400) -> int:
        cutoff = int(time.time()) - older_than_s
        with self._lock, self._connect() as conn:
            cur = conn.execute('DELETE FROM hive_events WHERE ts<?',
                               (cutoff,))
            conn.commit()
            return cur.rowcount

    # -- jobs ------------------------------------------------------------
    def submit_job(self, kind: str, payload: dict, *,
                   capability_req: str | None = None) -> str:
        """Submit a job to the queue. Returns job_id."""
        job_id = f"job-{int(time.time())}-{os.urandom(4).hex()}"
        encoded = json.dumps(payload, separators=(',', ':'))
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                'INSERT INTO hive_jobs (job_id, kind, payload_json, '
                'status, created_ts, capability_req) VALUES (?,?,?,?,?,?)',
                (job_id, kind, encoded, 'pending', now, capability_req),
            )
            conn.commit()
        return job_id

    def claim_next_job(self, node_id: str, capabilities: list[str]) -> dict | None:
        """Atomically claim the next pending job matching node capabilities."""
        now = int(time.time())
        with self._lock, self._connect() as conn:
            # Find jobs: either unassigned or assigned to this node,
            # pending, and capability match (or no specific req)
            rows = conn.execute(
                "SELECT job_id, kind, payload_json, capability_req "
                "FROM hive_jobs WHERE status='pending' "
                "AND (node_id IS NULL OR node_id=?) "
                "ORDER BY created_ts ASC",
                (node_id,),
            ).fetchall()
            for r in rows:
                req = r['capability_req']
                if req is None or req in capabilities:
                    job_id = r['job_id']
                    conn.execute(
                        "UPDATE hive_jobs SET status='claimed', "
                        "node_id=?, claimed_ts=? WHERE job_id=?",
                        (node_id, now, job_id),
                    )
                    conn.execute(
                        'INSERT INTO hive_events (ts, node_id, kind, detail) '
                        'VALUES (?,?,?,?)',
                        (now, node_id, 'job-claimed', job_id),
                    )
                    conn.commit()
                    return {
                        'job_id': job_id,
                        'kind': r['kind'],
                        'payload': json.loads(r['payload_json']),
                    }
        return None

    def report_job_result(self, job_id: str, result: dict) -> bool:
        """Mark a job completed with result."""
        now = int(time.time())
        encoded = json.dumps(result, separators=(',', ':'))
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE hive_jobs SET status='completed', result_json=?, "
                "completed_ts=? WHERE job_id=? AND status='claimed'",
                (encoded, now, job_id),
            )
            if cur.rowcount:
                conn.execute(
                    'INSERT INTO hive_events (ts, node_id, kind, detail) '
                    'VALUES (?,?,?,?)',
                    (now, '', 'job-completed', job_id),
                )
                conn.commit()
                return True
            return False

    def list_jobs(self, *, status: str | None = None, limit: int = 100) -> list:
        sql = ('SELECT job_id, node_id, kind, status, created_ts, '
               'claimed_ts, completed_ts, capability_req '
               'FROM hive_jobs WHERE 1=1 ')
        args: list = []
        if status:
            sql += "AND status=? "
            args.append(status)
        sql += 'ORDER BY created_ts DESC LIMIT ?'
        args.append(int(max(1, min(500, limit))))
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def prune_stale_nodes(self, *, older_than_s: int = 30 * 86400) -> list:
        cutoff = int(time.time()) - older_than_s
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                'SELECT node_id FROM hive_nodes '
                'WHERE last_seen_ts IS NOT NULL AND last_seen_ts < ?',
                (cutoff,),
            ).fetchall()
            removed = [r['node_id'] for r in rows]
            for nid in removed:
                conn.execute('DELETE FROM hive_nodes WHERE node_id=?',
                             (nid,))
                conn.execute(
                    'INSERT INTO hive_events (ts, node_id, kind, detail) '
                    'VALUES (?,?,?,?)',
                    (int(time.time()), nid, 'pruned-stale', None),
                )
            conn.commit()
        return removed


_SINGLETON: HiveRegistry | None = None
_SINGLETON_LOCK = threading.Lock()


def get_registry(db_path: str | None = None) -> HiveRegistry:
    """Return a process-wide registry singleton.

    Tests pass a path to override; production code calls without args.
    Re-reads ``$SWARM_HIVE_DB`` at call time so test fixtures can
    redirect the registry without re-importing the module.
    """
    global _SINGLETON
    if db_path is not None:
        return HiveRegistry(db_path)
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            env_path = os.environ.get('SWARM_HIVE_DB') or DEFAULT_DB
            _SINGLETON = HiveRegistry(env_path)
    return _SINGLETON


def reset_singleton() -> None:
    """Test helper — drop the cached singleton."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


__all__ = ['HiveRegistry', 'get_registry', 'reset_singleton', 'DEFAULT_DB']
