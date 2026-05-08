"""core.knowledge.test_runs — Session 30: ALM-style test run history.

Every test lab script execution is recorded as a row. Each run can
accumulate notes and artifacts (screenshots, log snippets, extra context)
so that Quality Assurance has the same shape as old HP/ALM Test Lab:

    * run_id            stable identifier
    * script_id         which entry in the registry
    * change_id         optional link to a change/proposal
    * status            running | pass | fail | error | aborted
    * started_at        unix seconds
    * ended_at          unix seconds (null while running)
    * duration_ms       int
    * exit_code         int (null while running)
    * stdout_tail       last ~8KB of stdout for quick triage
    * command           resolved shell command
    * triggered_by      'manual' | 'auto' | 'change:<change_id>' | 'scheduled'

Artifacts table:
    * id, run_id, kind ('note' | 'screenshot' | 'log' | 'link'), body, created_at

Best-effort — any DB failure silently degrades to "not recorded".
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    'start_run', 'finish_run', 'abort_run',
    'add_artifact', 'list_runs', 'get_run',
    'STATUS_RUNNING', 'STATUS_PASS', 'STATUS_FAIL', 'STATUS_ERROR', 'STATUS_ABORTED',
]

STATUS_RUNNING = 'running'
STATUS_PASS = 'pass'
STATUS_FAIL = 'fail'
STATUS_ERROR = 'error'
STATUS_ABORTED = 'aborted'

_VALID_STATUS = frozenset({STATUS_RUNNING, STATUS_PASS, STATUS_FAIL, STATUS_ERROR, STATUS_ABORTED})
_STDOUT_TAIL_CAP = 8 * 1024  # 8 KB

_SCHEMA_READY = False


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS test_runs (
                run_id TEXT PRIMARY KEY,
                script_id TEXT NOT NULL,
                change_id TEXT,
                status TEXT NOT NULL,
                started_at REAL NOT NULL,
                ended_at REAL,
                duration_ms INTEGER,
                exit_code INTEGER,
                stdout_tail TEXT,
                command TEXT,
                triggered_by TEXT,
                project_id TEXT,
                step_id TEXT,
                case_id TEXT
            )""")
            # Idempotent ALTERs for pre-existing DBs that were created before
            # the Session 30.1 Projects pivot.
            for col_ddl in (
                "ALTER TABLE test_runs ADD COLUMN project_id TEXT",
                "ALTER TABLE test_runs ADD COLUMN step_id TEXT",
                "ALTER TABLE test_runs ADD COLUMN case_id TEXT",
            ):
                try:
                    conn.execute(col_ddl)
                except Exception:
                    pass  # column already exists
            conn.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_script ON test_runs(script_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_change ON test_runs(change_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_started ON test_runs(started_at)")
            conn.execute("""CREATE TABLE IF NOT EXISTS test_run_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at REAL NOT NULL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_run ON test_run_artifacts(run_id)")
            conn.commit()
        finally:
            conn.close()
        _SCHEMA_READY = True
    except Exception:
        pass


def start_run(
    script_id: str,
    *,
    change_id: Optional[str] = None,
    command: Optional[str] = None,
    triggered_by: str = 'manual',
    project_id: Optional[str] = None,
    step_id: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Optional[str]:
    """Record the start of a run. Returns a run_id or None on DB failure."""
    if not script_id:
        return None
    _ensure_schema()
    # Make sure project-linking columns exist (added by core.knowledge.projects).
    try:
        from core.knowledge import projects as _kc_projects  # noqa: F401
        _kc_projects._ensure_schema()
    except Exception:
        _kc_projects = None
    # If a project_id is supplied, it must reference a real project,
    # and step_id/case_id (if supplied) must belong to that project.
    if project_id:
        try:
            if _kc_projects and _kc_projects.get_project(str(project_id)) is None:
                raise ValueError(f"unknown project_id: {project_id}")
            if _kc_projects and step_id and not _kc_projects._step_belongs_to(
                    str(step_id), str(project_id)):
                raise ValueError(
                    f"step_id {step_id} does not belong to project {project_id}")
            if _kc_projects and case_id and not _kc_projects._case_belongs_to(
                    str(case_id), str(project_id)):
                raise ValueError(
                    f"case_id {case_id} does not belong to project {project_id}")
        except ValueError:
            raise
        except Exception:
            pass
    run_id = uuid.uuid4().hex[:16]
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO test_runs (run_id, script_id, change_id, status, started_at, command, triggered_by, project_id, step_id, case_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, str(script_id)[:128], (str(change_id)[:128] if change_id else None),
                 STATUS_RUNNING, time.time(), (command or '')[:2000], str(triggered_by)[:64],
                 (str(project_id)[:64] if project_id else None),
                 (str(step_id)[:64] if step_id else None),
                 (str(case_id)[:64] if case_id else None)),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return None
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('run', run_id, actor='start_run')
    except Exception:
        pass
    return run_id


def finish_run(
    run_id: str,
    *,
    status: str,
    exit_code: Optional[int] = None,
    stdout_tail: str = '',
) -> bool:
    """Mark a run complete. Returns True on success."""
    if not run_id:
        return False
    if status not in _VALID_STATUS or status == STATUS_RUNNING:
        status = STATUS_FAIL
    _ensure_schema()
    tail = (stdout_tail or '')[-_STDOUT_TAIL_CAP:]
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT started_at, script_id, change_id, triggered_by, case_id
                   FROM test_runs WHERE run_id=?""",
                (run_id,),
            ).fetchone()
            if not row:
                return False
            started = float(row['started_at'] or time.time())
            ended = time.time()
            duration_ms = int(max(0, (ended - started) * 1000))
            conn.execute(
                "UPDATE test_runs SET status=?, ended_at=?, duration_ms=?, "
                "exit_code=?, stdout_tail=? WHERE run_id=?",
                (status, ended, duration_ms,
                 (int(exit_code) if exit_code is not None else None),
                 tail, run_id),
            )
            conn.commit()
            _record_scorecard_test_run_outcome(
                conn=conn,
                script_id=row['script_id'],
                status=status,
                change_id=row['change_id'] or '',
                triggered_by=row['triggered_by'] or '',
                exit_code=exit_code,
                stdout_tail=tail,
            )
            # S-D12CB0E012 — Test-case result rollup. When a run completes
            # against a linked test case, lift the run outcome onto the
            # test case so the Studio backlog reflects the latest verdict.
            try:
                _rollup_case_status(conn, row['case_id'], status)
            except Exception:
                pass
            try:
                from core.records import mirror as _records_mirror
                _records_mirror('run', run_id, actor='finish_run')
            except Exception:
                pass
            return True
        finally:
            conn.close()
    except Exception:
        return False


def _record_scorecard_test_run_outcome(**kwargs) -> None:
    """Best-effort scorecard learning from Test Lab run completion."""
    try:
        from core import agent_scorecards
        agent_scorecards.record_test_run_outcome(**kwargs)
    except Exception:
        pass


# S-D12CB0E012 — map run outcome → test case status. Only states that have
# a meaningful case-level equivalent are propagated; "running" never lands
# here because finish_run normalises to a terminal status before calling.
_RUN_TO_CASE_STATUS = {
    STATUS_PASS: 'passed',
    STATUS_FAIL: 'failed',
    STATUS_ERROR: 'failed',
    STATUS_ABORTED: 'blocked',
}


def _rollup_case_status(conn, case_id: Optional[str], run_status: str) -> bool:
    """Update the linked test case's status from the just-finished run.

    Skipped silently when case_id is empty, when the run status doesn't map,
    or when the case has been retired (status='obsolete'). Returns True on
    a successful update.
    """
    if not case_id:
        return False
    target = _RUN_TO_CASE_STATUS.get(run_status)
    if not target:
        return False
    try:
        cur = conn.execute(
            "SELECT status FROM project_test_cases WHERE case_id=?",
            (str(case_id),),
        ).fetchone()
    except Exception:
        return False
    if not cur:
        return False
    if (cur['status'] or '').lower() == 'obsolete':
        return False
    try:
        conn.execute(
            "UPDATE project_test_cases SET status=?, updated_at=? WHERE case_id=?",
            (target, time.time(), str(case_id)),
        )
        conn.commit()
    except Exception:
        return False
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('case', str(case_id), actor='test_run_rollup')
    except Exception:
        pass
    return True


def abort_run(run_id: str, reason: str = '') -> bool:
    return finish_run(run_id, status=STATUS_ABORTED, stdout_tail=reason)


def add_artifact(run_id: str, kind: str, body: str) -> bool:
    """Attach a note/log/screenshot/link to a run."""
    if not run_id or not kind:
        return False
    kind = str(kind)[:32]
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO test_run_artifacts (run_id, kind, body, created_at) VALUES (?, ?, ?, ?)",
                (run_id, kind, (body or '')[:64 * 1024], time.time()),
            )
            conn.commit()
            try:
                from core.records import mirror as _records_mirror
                _records_mirror('run', run_id, actor='add_artifact')
            except Exception:
                pass
            return True
        finally:
            conn.close()
    except Exception:
        return False


def _artifacts_for(conn, run_id: str) -> List[Dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT id, kind, body, created_at FROM test_run_artifacts "
            "WHERE run_id=? ORDER BY id ASC", (run_id,),
        ).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    if not run_id:
        return None
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM test_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data['artifacts'] = _artifacts_for(conn, run_id)
            return data
        finally:
            conn.close()
    except Exception:
        return None


def list_runs(
    *,
    script_id: Optional[str] = None,
    change_id: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    step_id: Optional[str] = None,
    case_id: Optional[str] = None,
    limit: int = 50,
    include_artifacts: bool = False,
) -> List[Dict[str, Any]]:
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            clauses: List[str] = []
            params: List[Any] = []
            if script_id:
                clauses.append("script_id=?"); params.append(str(script_id)[:128])
            if change_id:
                clauses.append("change_id=?"); params.append(str(change_id)[:128])
            if status:
                clauses.append("status=?"); params.append(str(status)[:32])
            if project_id:
                clauses.append("project_id=?"); params.append(str(project_id)[:64])
            if step_id:
                clauses.append("step_id=?"); params.append(str(step_id)[:64])
            if case_id:
                clauses.append("case_id=?"); params.append(str(case_id)[:64])
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(int(max(1, min(limit, 500))))
            rows = conn.execute(
                f"SELECT * FROM test_runs {where} ORDER BY started_at DESC LIMIT ?",
                params,
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                if include_artifacts:
                    d['artifacts'] = _artifacts_for(conn, d['run_id'])
                out.append(d)
            return out
        finally:
            conn.close()
    except Exception:
        return []
