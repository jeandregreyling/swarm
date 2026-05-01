"""core.knowledge.projects — Session 30.1: Projects, Steps, Test Cases.

The request: projects are first-class. Each project can use Agile /
Waterfall / Prince2 (mixed) methodology. Every project owns:

    * steps           — ordered plan items (analogous to stories, phases, or
                        WBS items). Seven is the default owner of each step.
    * test_cases      — test cases attached to the project and optionally
                        a specific step. Each case can reference a test-lab
                        script_id so execution is a real recorded run.

Proposals link to projects via `proposal_projects` (many-to-one). Test runs
link to projects/steps/cases via new columns on the `test_runs` table.

Owner defaults to 'seven' per the user's directive: "update Seven as the
owner of each step and each project".

Every CRUD mutation emits a spine TICKET-kind event so the activity flows
into Vortex automatically (zero extra wiring on the UI side).
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

__all__ = [
    'create_project', 'list_projects', 'get_project', 'update_project',
    'delete_project',
    'add_step', 'list_steps', 'update_step_status', 'update_step',
    'delete_step',
    'add_test_case', 'list_test_cases', 'update_case_status',
    'update_test_case', 'delete_test_case',
    'add_blackboard_note', 'list_blackboard_notes',
    'update_blackboard_note_status',
    'link_proposal', 'list_proposals_for_project',
    'METHODOLOGIES', 'STEP_STATUSES', 'CASE_STATUSES', 'PROJECT_STATUSES',
    'BLACKBOARD_KINDS', 'BLACKBOARD_STATUSES',
]

METHODOLOGIES = ('agile', 'waterfall', 'prince2', 'mixed')
# 'partial' — shipped with acknowledged scope cuts; description must carry
# the explicit deferral list. Separates "honest half-done" from "done" so the
# ALM stops lying when V-closeouts hide cuts behind a green tick.
STEP_STATUSES = ('todo', 'doing', 'blocked', 'partial', 'done', 'skipped')
CASE_STATUSES = ('draft', 'ready', 'passed', 'failed', 'blocked', 'obsolete')
PROJECT_STATUSES = ('active', 'archived', 'on_hold')
BLACKBOARD_KINDS = ('note', 'handoff', 'decision', 'risk', 'test', 'research', 'milestone')
BLACKBOARD_STATUSES = ('active', 'resolved', 'archived')
DEFAULT_OWNER = 'seven'

_SCHEMA_READY = False


def _project_exists(project_id: str) -> bool:
    if not project_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def _step_belongs_to(step_id: str, project_id: str) -> bool:
    if not step_id or not project_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM project_steps WHERE step_id=? AND project_id=?",
                (step_id, project_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def _case_belongs_to(case_id: str, project_id: str) -> bool:
    if not case_id or not project_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM project_test_cases WHERE case_id=? AND project_id=?",
                (case_id, project_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def _emit_spine(summary: str, detail: Dict[str, Any], severity: str = 'info') -> None:
    """Best-effort spine emit. Every project mutation shows up in Vortex."""
    try:
        from core import spine
        spine.log(
            kind=spine.EventKind.TICKET,
            summary=summary,
            detail=detail,
            severity=getattr(spine.Severity, severity.upper(), spine.Severity.INFO),
            source='projects',
        )
    except Exception:
        pass


def _ensure_blackboard_schema(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS project_blackboard_notes (
        note_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        author TEXT NOT NULL DEFAULT 'seven',
        kind TEXT NOT NULL DEFAULT 'note',
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at REAL NOT NULL,
        updated_at REAL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blackboard_project ON project_blackboard_notes(project_id, status, updated_at)")


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                methodology TEXT NOT NULL DEFAULT 'mixed',
                status TEXT NOT NULL DEFAULT 'active',
                owner TEXT NOT NULL DEFAULT 'seven',
                created_at REAL NOT NULL,
                updated_at REAL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")

            conn.execute("""CREATE TABLE IF NOT EXISTS project_steps (
                step_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'todo',
                owner TEXT NOT NULL DEFAULT 'seven',
                order_idx INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_steps_project ON project_steps(project_id, order_idx)")

            conn.execute("""CREATE TABLE IF NOT EXISTS project_test_cases (
                case_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                step_id TEXT,
                title TEXT NOT NULL,
                script_id TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                owner TEXT NOT NULL DEFAULT 'seven',
                created_at REAL NOT NULL,
                updated_at REAL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_project ON project_test_cases(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_step ON project_test_cases(step_id)")

            _ensure_blackboard_schema(conn)

            conn.execute("""CREATE TABLE IF NOT EXISTS proposal_projects (
                proposal_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (proposal_id, project_id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pp_project ON proposal_projects(project_id)")

            # Non-breaking ALTER on test_runs (ignore if columns already exist)
            for col_ddl in (
                "ALTER TABLE test_runs ADD COLUMN project_id TEXT",
                "ALTER TABLE test_runs ADD COLUMN step_id TEXT",
                "ALTER TABLE test_runs ADD COLUMN case_id TEXT",
            ):
                try:
                    conn.execute(col_ddl)
                except Exception:
                    pass  # column already exists

            conn.commit()
        finally:
            conn.close()
        _SCHEMA_READY = True
    except Exception:
        pass


# ── Projects ────────────────────────────────────────────────────────────────

def create_project(
    name: str,
    *,
    description: str = '',
    methodology: str = 'mixed',
    owner: str = DEFAULT_OWNER,
) -> Optional[str]:
    name = (name or '').strip()
    if not name:
        raise ValueError("project name is required")
    if methodology not in METHODOLOGIES:
        raise ValueError(f"methodology must be one of {METHODOLOGIES}")
    _ensure_schema()
    project_id = 'P-' + uuid.uuid4().hex[:10].upper()
    now = time.time()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, description, methodology, status, owner, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (project_id, name[:200], (description or '')[:4000], methodology,
                 (owner or DEFAULT_OWNER)[:64], now, now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return None
    _emit_spine(
        f"Project created: {name}",
        {'project_id': project_id, 'methodology': methodology, 'owner': owner},
    )
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('project', project_id, actor='create_project')
    except Exception:
        pass
    return project_id


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    if not project_id:
        return None
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
            if not row:
                return None
            project = dict(row)
            _ensure_blackboard_schema(conn)
            steps = [dict(r) for r in conn.execute(
                "SELECT * FROM project_steps WHERE project_id=? ORDER BY order_idx ASC, created_at ASC",
                (project_id,),
            ).fetchall()]
            test_cases = [dict(r) for r in conn.execute(
                "SELECT * FROM project_test_cases WHERE project_id=? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()]
            blackboard_notes = [dict(r) for r in conn.execute(
                "SELECT * FROM project_blackboard_notes WHERE project_id=? AND status='active' ORDER BY updated_at DESC LIMIT 20",
                (project_id,),
            ).fetchall()]
            proposals = [dict(r) for r in conn.execute(
                "SELECT proposal_id, created_at FROM proposal_projects WHERE project_id=? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()]
            return {
                "project": project,
                "steps": steps,
                "test_cases": test_cases,
                "blackboard_notes": blackboard_notes,
                "proposals": proposals,
            }
        finally:
            conn.close()
    except Exception:
        return None


def list_projects(*, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            clauses: List[str] = []
            params: List[Any] = []
            if status:
                clauses.append("status=?"); params.append(status)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(int(max(1, min(limit, 500))))
            rows = conn.execute(
                f"SELECT p.*, "
                f"(SELECT COUNT(*) FROM project_steps WHERE project_id=p.project_id) AS step_count, "
                f"(SELECT COUNT(*) FROM project_test_cases WHERE project_id=p.project_id) AS case_count, "
                f"(SELECT COUNT(*) FROM project_steps WHERE project_id=p.project_id AND status='done') AS steps_done "
                f"FROM projects p {where} ORDER BY p.created_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def update_project(project_id: str, **fields: Any) -> bool:
    allowed = {'name', 'description', 'methodology', 'status', 'owner'}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not project_id or not updates:
        return False
    if 'methodology' in updates and updates['methodology'] not in METHODOLOGIES:
        raise ValueError(f"methodology must be one of {METHODOLOGIES}")
    if 'status' in updates and updates['status'] not in PROJECT_STATUSES:
        raise ValueError(f"status must be one of {PROJECT_STATUSES}")
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            cols = ", ".join(f"{k}=?" for k in updates)
            params = list(updates.values()) + [time.time(), project_id]
            cur = conn.execute(
                f"UPDATE projects SET {cols}, updated_at=? WHERE project_id=?",
                params,
            )
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        _emit_spine(f"Project updated: {project_id}", {'project_id': project_id, 'fields': list(updates.keys())})
        try:
            from core.records import mirror as _records_mirror
            _records_mirror('project', project_id, actor='update_project')
        except Exception:
            pass
    return ok


# ── Steps ───────────────────────────────────────────────────────────────────

def add_step(
    project_id: str,
    title: str,
    *,
    description: str = '',
    owner: str = DEFAULT_OWNER,
    order_idx: Optional[int] = None,
) -> Optional[str]:
    if not project_id or not (title or '').strip():
        return None
    _ensure_schema()
    if not _project_exists(project_id):
        raise ValueError(f"unknown project_id: {project_id}")
    step_id = 'S-' + uuid.uuid4().hex[:10].upper()
    now = time.time()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            if order_idx is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(order_idx), -1) AS m FROM project_steps WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                order_idx = int(row['m']) + 1 if row else 0
            conn.execute(
                "INSERT INTO project_steps (step_id, project_id, title, description, status, owner, order_idx, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'todo', ?, ?, ?, ?)",
                (step_id, project_id, title.strip()[:200], (description or '')[:4000],
                 (owner or DEFAULT_OWNER)[:64], int(order_idx), now, now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return None
    _emit_spine(f"Step added: {title}", {'project_id': project_id, 'step_id': step_id, 'owner': owner})
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('step', step_id, actor='add_step')
    except Exception:
        pass
    return step_id


def list_steps(project_id: str) -> List[Dict[str, Any]]:
    if not project_id:
        return []
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM project_steps WHERE project_id=? ORDER BY order_idx ASC, created_at ASC",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def get_step(step_id: str) -> Optional[Dict[str, Any]]:
    """ALM detail surface — load one step with its linked test cases and
    most recent test runs so a UI can render an openable record view."""
    if not step_id:
        return None
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM project_steps WHERE step_id=?", (step_id,)
            ).fetchone()
            if not row:
                return None
            step = dict(row)
            try:
                cases = conn.execute(
                    "SELECT * FROM project_test_cases WHERE step_id=? ORDER BY created_at ASC",
                    (step_id,),
                ).fetchall()
                step['test_cases'] = [dict(c) for c in cases]
            except Exception:
                step['test_cases'] = []
            try:
                runs = conn.execute(
                    "SELECT * FROM test_runs WHERE step_id=? ORDER BY started_at DESC LIMIT 25",
                    (step_id,),
                ).fetchall()
                step['test_runs'] = [dict(r) for r in runs]
            except Exception:
                step['test_runs'] = []
            return step
        finally:
            conn.close()
    except Exception:
        return None


def update_step_status(step_id: str, status: str, *, owner: Optional[str] = None) -> bool:
    if not step_id:
        return False
    if status not in STEP_STATUSES:
        raise ValueError(f"status must be one of {STEP_STATUSES}")
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            if owner:
                cur = conn.execute(
                    "UPDATE project_steps SET status=?, owner=?, updated_at=? WHERE step_id=?",
                    (status, owner[:64], time.time(), step_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE project_steps SET status=?, updated_at=? WHERE step_id=?",
                    (status, time.time(), step_id),
                )
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        severity = 'warn' if status == 'blocked' else 'info'
        _emit_spine(f"Step → {status}: {step_id}", {'step_id': step_id, 'status': status}, severity=severity)
        try:
            from core.records import mirror as _records_mirror
            _records_mirror('step', step_id, actor='update_step_status')
        except Exception:
            pass
    return ok


# ── Test cases ──────────────────────────────────────────────────────────────

def add_test_case(
    project_id: str,
    title: str,
    *,
    step_id: Optional[str] = None,
    script_id: Optional[str] = None,
    owner: str = DEFAULT_OWNER,
) -> Optional[str]:
    if not project_id or not (title or '').strip():
        return None
    _ensure_schema()
    if not _project_exists(project_id):
        raise ValueError(f"unknown project_id: {project_id}")
    if step_id and not _step_belongs_to(step_id, project_id):
        raise ValueError(f"step_id {step_id} does not belong to {project_id}")
    case_id = 'C-' + uuid.uuid4().hex[:10].upper()
    now = time.time()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO project_test_cases (case_id, project_id, step_id, title, script_id, status, owner, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'ready', ?, ?, ?)",
                (case_id, project_id, (step_id[:64] if step_id else None),
                 title.strip()[:200], (script_id[:128] if script_id else None),
                 (owner or DEFAULT_OWNER)[:64], now, now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return None
    _emit_spine(f"Test case: {title}", {'project_id': project_id, 'case_id': case_id, 'script_id': script_id})
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('case', case_id, actor='add_test_case')
    except Exception:
        pass
    return case_id


def list_test_cases(
    project_id: str,
    *,
    step_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not project_id:
        return []
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            if step_id:
                rows = conn.execute(
                    "SELECT * FROM project_test_cases WHERE project_id=? AND step_id=? ORDER BY created_at ASC",
                    (project_id, step_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM project_test_cases WHERE project_id=? ORDER BY created_at ASC",
                    (project_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def get_test_case(case_id: str) -> Optional[Dict[str, Any]]:
    """ALM detail surface — load one test case with its parent step and
    most recent test runs so a UI can render an openable record view."""
    if not case_id:
        return None
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM project_test_cases WHERE case_id=?", (case_id,)
            ).fetchone()
            if not row:
                return None
            case = dict(row)
            if case.get('step_id'):
                try:
                    step = conn.execute(
                        "SELECT step_id, title, status, owner FROM project_steps WHERE step_id=?",
                        (case['step_id'],),
                    ).fetchone()
                    case['step'] = dict(step) if step else None
                except Exception:
                    case['step'] = None
            try:
                runs = conn.execute(
                    "SELECT * FROM test_runs WHERE case_id=? ORDER BY started_at DESC LIMIT 25",
                    (case_id,),
                ).fetchall()
                case['test_runs'] = [dict(r) for r in runs]
            except Exception:
                case['test_runs'] = []
            return case
        finally:
            conn.close()
    except Exception:
        return None


def update_case_status(case_id: str, status: str, *, owner: Optional[str] = None) -> bool:
    if not case_id:
        return False
    if status not in CASE_STATUSES:
        raise ValueError(f"status must be one of {CASE_STATUSES}")
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            if owner:
                cur = conn.execute(
                    "UPDATE project_test_cases SET status=?, owner=?, updated_at=? WHERE case_id=?",
                    (status, owner[:64], time.time(), case_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE project_test_cases SET status=?, updated_at=? WHERE case_id=?",
                    (status, time.time(), case_id),
                )
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        severity = 'warn' if status in ('failed', 'blocked') else 'info'
        _emit_spine(f"Case → {status}: {case_id}", {'case_id': case_id, 'status': status}, severity=severity)
        try:
            from core.records import mirror as _records_mirror
            _records_mirror('case', case_id, actor='update_case_status')
        except Exception:
            pass
    return ok


# ── Project blackboard ──────────────────────────────────────────────────────

def add_blackboard_note(
    project_id: str,
    content: str,
    *,
    author: str = DEFAULT_OWNER,
    kind: str = 'note',
) -> Optional[str]:
    """Add a structured, visible project handoff note.

    Intended for agents to leave compact project context for one another:
    decisions, risks, test notes, handoffs, and research findings. This is
    visible continuity, not private chain-of-thought.
    """
    project_id = str(project_id or '').strip()
    content = str(content or '').strip()
    author = str(author or DEFAULT_OWNER).strip()[:64] or DEFAULT_OWNER
    kind = str(kind or 'note').strip().lower()
    if not project_id or not content:
        return None
    if kind not in BLACKBOARD_KINDS:
        raise ValueError(f"kind must be one of {BLACKBOARD_KINDS}")
    _ensure_schema()
    if not _project_exists(project_id):
        raise ValueError(f"unknown project_id: {project_id}")
    note_id = 'B-' + uuid.uuid4().hex[:10].upper()
    now = time.time()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            _ensure_blackboard_schema(conn)
            conn.execute(
                """INSERT INTO project_blackboard_notes
                   (note_id, project_id, author, kind, content, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                (note_id, project_id, author, kind, content[:4000], now, now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return None
    _emit_spine(
        f"Project blackboard note: {project_id}",
        {'project_id': project_id, 'note_id': note_id, 'kind': kind, 'author': author},
    )
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('note', note_id, actor='add_blackboard_note')
    except Exception:
        pass
    return note_id


def list_blackboard_notes(
    project_id: str,
    *,
    status: Optional[str] = 'active',
    limit: int = 20,
) -> List[Dict[str, Any]]:
    project_id = str(project_id or '').strip()
    if not project_id:
        return []
    if status is not None and status not in BLACKBOARD_STATUSES:
        raise ValueError(f"status must be one of {BLACKBOARD_STATUSES}")
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            _ensure_blackboard_schema(conn)
            capped = int(max(1, min(limit, 100)))
            if status is None:
                rows = conn.execute(
                    """SELECT * FROM project_blackboard_notes
                       WHERE project_id=?
                       ORDER BY updated_at DESC
                       LIMIT ?""",
                    (project_id, capped),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM project_blackboard_notes
                       WHERE project_id=? AND status=?
                       ORDER BY updated_at DESC
                       LIMIT ?""",
                    (project_id, status, capped),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def update_blackboard_note_status(note_id: str, status: str) -> bool:
    note_id = str(note_id or '').strip()
    status = str(status or '').strip().lower()
    if not note_id:
        return False
    if status not in BLACKBOARD_STATUSES:
        raise ValueError(f"status must be one of {BLACKBOARD_STATUSES}")
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            _ensure_blackboard_schema(conn)
            cur = conn.execute(
                "UPDATE project_blackboard_notes SET status=?, updated_at=? WHERE note_id=?",
                (status, time.time(), note_id),
            )
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        _emit_spine(
            f"Blackboard note → {status}: {note_id}",
            {'note_id': note_id, 'status': status},
        )
    return ok


# ── Proposal linkage ────────────────────────────────────────────────────────

def link_proposal(project_id: str, proposal_id: str) -> bool:
    if not proposal_id or not project_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO proposal_projects (proposal_id, project_id, created_at) VALUES (?, ?, ?)",
                (str(proposal_id)[:64], project_id, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return False
    _emit_spine(
        f"Proposal {proposal_id} → {project_id}",
        {'proposal_id': proposal_id, 'project_id': project_id},
    )
    return True


def list_proposals_for_project(project_id: str) -> List[Dict[str, Any]]:
    if not project_id:
        return []
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT proposal_id, created_at FROM proposal_projects WHERE project_id=? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


# ── Delete / edit (Phase 3) ────────────────────────────────────────────────

def delete_project(project_id: str) -> bool:
    """Delete a project and cascade-clean its steps, cases and proposal links.

    Test runs keep their project_id column for historical visibility — the
    runs table is never destroyed.
    """
    if not project_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            cur = conn.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM project_steps WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM project_test_cases WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM proposal_projects WHERE project_id=?", (project_id,))
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        _emit_spine(f"Project deleted: {project_id}", {'project_id': project_id}, severity='warn')
    return ok


def update_step(
    step_id: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    owner: Optional[str] = None,
) -> bool:
    """Rename / re-describe / re-assign a step. Status changes go through
    ``update_step_status`` which already emits spine events per transition."""
    if not step_id:
        return False
    updates: Dict[str, Any] = {}
    if title is not None:
        t = title.strip()
        if not t:
            raise ValueError("title cannot be empty")
        updates['title'] = t[:200]
    if description is not None:
        updates['description'] = description[:4000]
    if owner is not None:
        o = owner.strip()
        if o:
            updates['owner'] = o[:64]
    if not updates:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            cols = ", ".join(f"{k}=?" for k in updates)
            params = list(updates.values()) + [time.time(), step_id]
            cur = conn.execute(
                f"UPDATE project_steps SET {cols}, updated_at=? WHERE step_id=?",
                params,
            )
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        _emit_spine(f"Step edited: {step_id}", {'step_id': step_id, 'fields': list(updates.keys())})
    return ok


def delete_step(step_id: str) -> bool:
    """Delete a step. Test cases previously tied to the step keep their
    project link but lose their step_id (so they don't dangle)."""
    if not step_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE project_test_cases SET step_id=NULL, updated_at=? WHERE step_id=?",
                (time.time(), step_id),
            )
            cur = conn.execute("DELETE FROM project_steps WHERE step_id=?", (step_id,))
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        _emit_spine(f"Step deleted: {step_id}", {'step_id': step_id}, severity='warn')
    return ok


def update_test_case(
    case_id: str,
    *,
    title: Optional[str] = None,
    script_id: Optional[str] = None,
    step_id: Optional[str] = None,
    owner: Optional[str] = None,
) -> bool:
    """Edit a test case. Pass ``script_id=''`` or ``step_id=''`` to clear."""
    if not case_id:
        return False
    updates: Dict[str, Any] = {}
    if title is not None:
        t = title.strip()
        if not t:
            raise ValueError("title cannot be empty")
        updates['title'] = t[:200]
    if script_id is not None:
        updates['script_id'] = (script_id.strip()[:128] or None)
    if step_id is not None:
        updates['step_id'] = (step_id.strip()[:64] or None)
    if owner is not None:
        o = owner.strip()
        if o:
            updates['owner'] = o[:64]
    if not updates:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            cols = ", ".join(f"{k}=?" for k in updates)
            params = list(updates.values()) + [time.time(), case_id]
            cur = conn.execute(
                f"UPDATE project_test_cases SET {cols}, updated_at=? WHERE case_id=?",
                params,
            )
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        _emit_spine(f"Case edited: {case_id}", {'case_id': case_id, 'fields': list(updates.keys())})
    return ok


def delete_test_case(case_id: str) -> bool:
    if not case_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            cur = conn.execute("DELETE FROM project_test_cases WHERE case_id=?", (case_id,))
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False
    if ok:
        _emit_spine(f"Case deleted: {case_id}", {'case_id': case_id}, severity='warn')
    return ok


def scripts_for_step(step_id: str) -> List[Dict[str, Any]]:
    """Return Test Lab script_ids tied to cases of this step.

    Result: ``[{case_id, title, script_id, status}, ...]`` — UI posts the
    ``script_id`` list to ``/api/studio/testlab/resolve`` to get shell
    commands to execute.
    """
    if not step_id:
        return []
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT case_id, title, script_id, status FROM project_test_cases "
                "WHERE step_id=? AND script_id IS NOT NULL AND script_id != '' "
                "ORDER BY created_at ASC",
                (step_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []
