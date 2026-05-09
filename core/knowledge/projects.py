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
import json as _json
from typing import Any, Dict, List, Optional


def _normalize_tags(value: Any) -> List[str]:
    """Coerce caller-supplied tags into a clean, deduped list of slug-ish
    strings. Accepts list/tuple, JSON string, or comma-separated string."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith('['):
            try:
                value = _json.loads(value)
            except Exception:
                value = [v.strip() for v in value.split(',')]
        else:
            value = [v.strip() for v in value.split(',')]
    if not isinstance(value, (list, tuple)):
        return []
    out: List[str] = []
    seen: set = set()
    for raw in value:
        s = str(raw or '').strip()
        if not s:
            continue
        s = s.lower().replace(' ', '-')[:48]
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= 24:  # hard cap, prevents abuse
            break
    return out

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
    'add_step_dependency', 'remove_step_dependency',
    'list_step_dependencies', 'list_step_blockers',
    'bulk_add_steps',
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
            message=summary,
            severity=getattr(spine.Severity, severity.upper(), spine.Severity.INFO),
            source='projects',
            payload=detail,
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

            # 2026-05-02 (S-0474A4BE17) — priority column for ordering urgent projects
            try:
                _cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
                if 'priority' not in _cols:
                    conn.execute(
                        "ALTER TABLE projects ADD COLUMN priority "
                        "INTEGER NOT NULL DEFAULT 0")
                if 'tags' not in _cols:
                    # S-4BCE8CF667 — JSON-array of project tags. Stored as
                    # TEXT so the value survives any SQLite version.
                    conn.execute(
                        "ALTER TABLE projects ADD COLUMN tags TEXT "
                        "NOT NULL DEFAULT '[]'")
            except Exception:
                pass

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

            # S-98FA0FAEFE — explicit step dependencies. Many-to-many table
            # so a step can declare zero or more prerequisite steps.
            conn.execute("""CREATE TABLE IF NOT EXISTS project_step_deps (
                step_id      TEXT NOT NULL,
                depends_on   TEXT NOT NULL,
                created_at   REAL NOT NULL,
                PRIMARY KEY (step_id, depends_on)
            )""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_step_deps_step ON project_step_deps(step_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_step_deps_blocker ON project_step_deps(depends_on)"
            )

            # S-64552DDFEA — residual_risk on project_steps. Free-form short
            # note about residual exposure when status='partial' or 'done'.
            # Capped at 240 chars by the writer; nullable to keep legacy
            # rows intact.
            try:
                _step_cols = {r[1] for r in conn.execute("PRAGMA table_info(project_steps)").fetchall()}
                if 'residual_risk' not in _step_cols:
                    conn.execute("ALTER TABLE project_steps ADD COLUMN residual_risk TEXT")
                if 'owner_route' not in _step_cols:
                    # S-58C4823367 — explicit owner_route slug for routing
                    # work to a specific agent/team independent of the
                    # 'owner' display column.
                    conn.execute("ALTER TABLE project_steps ADD COLUMN owner_route TEXT")
            except Exception:
                pass

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
    idempotency_key: str = '',
    tags: Any = None,
) -> Optional[str]:
    """Create a project. Returns project_id (or None on DB failure).

    2026-05-02 (S-C533209A6F) — when ``idempotency_key`` is non-empty and a
    project already exists with that exact (name, owner) pair (case-insensitive
    name match), return the existing id instead of duplicating. The key is
    stored as a marker in the description prefix so retries are deterministic.
    """
    name = (name or '').strip()
    if not name:
        raise ValueError("project name is required")
    if methodology not in METHODOLOGIES:
        raise ValueError(f"methodology must be one of {METHODOLOGIES}")
    _ensure_schema()
    if idempotency_key:
        try:
            from utils.db._connection import get_connection
            _conn = get_connection()
            try:
                _row = _conn.execute(
                    "SELECT project_id FROM projects "
                    "WHERE LOWER(name)=LOWER(?) AND owner=? AND status!='archived' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (name[:200], (owner or DEFAULT_OWNER)[:64]),
                ).fetchone()
                if _row is not None:
                    return _row[0]
            finally:
                _conn.close()
        except Exception:
            pass
    project_id = 'P-' + uuid.uuid4().hex[:10].upper()
    now = time.time()
    tags_json = _json.dumps(_normalize_tags(tags))
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, description, methodology, status, owner, created_at, updated_at, tags) "
                "VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)",
                (project_id, name[:200], (description or '')[:4000], methodology,
                 (owner or DEFAULT_OWNER)[:64], now, now, tags_json),
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
            # Decode tags JSON for callers; tolerate legacy/invalid rows.
            try:
                project['tags'] = _json.loads(project.get('tags') or '[]')
                if not isinstance(project['tags'], list):
                    project['tags'] = []
            except Exception:
                project['tags'] = []
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


def list_projects(*, status: Optional[str] = None, limit: int = 100,
                  tag: Optional[str] = None) -> List[Dict[str, Any]]:
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            clauses: List[str] = []
            params: List[Any] = []
            if status:
                clauses.append("status=?"); params.append(status)
            if tag:
                # Tags are stored as a JSON array of slugs. SQLite LIKE with
                # quoted match is sufficient for this lightweight surface.
                clauses.append("tags LIKE ?")
                params.append(f'%"{_normalize_tags([tag])[0] if _normalize_tags([tag]) else ""}"%')
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(int(max(1, min(limit, 500))))
            rows = conn.execute(
                f"SELECT p.*, "
                f"(SELECT COUNT(*) FROM project_steps WHERE project_id=p.project_id) AS step_count, "
                f"(SELECT COUNT(*) FROM project_test_cases WHERE project_id=p.project_id) AS case_count, "
                f"(SELECT COUNT(*) FROM project_steps WHERE project_id=p.project_id AND status='done') AS steps_done, "
                f"(SELECT COUNT(*) FROM project_blackboard_notes WHERE project_id=p.project_id AND status='active') AS blackboard_count "
                f"FROM projects p {where} ORDER BY p.priority DESC, p.created_at DESC LIMIT ?",
                params,
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                # Decode tags JSON for callers; tolerate legacy/invalid rows.
                try:
                    d['tags'] = _json.loads(d.get('tags') or '[]')
                    if not isinstance(d['tags'], list):
                        d['tags'] = []
                except Exception:
                    d['tags'] = []
                out.append(d)
            return out
        finally:
            conn.close()
    except Exception:
        return []


def update_project(project_id: str, **fields: Any) -> bool:
    allowed = {'name', 'description', 'methodology', 'status', 'owner', 'priority', 'tags'}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not project_id or not updates:
        return False
    if 'methodology' in updates and updates['methodology'] not in METHODOLOGIES:
        raise ValueError(f"methodology must be one of {METHODOLOGIES}")
    if 'status' in updates and updates['status'] not in PROJECT_STATUSES:
        raise ValueError(f"status must be one of {PROJECT_STATUSES}")
    if 'priority' in updates:
        try:
            updates['priority'] = max(0, min(int(updates['priority']), 9))
        except (TypeError, ValueError):
            raise ValueError("priority must be an integer 0..9")
    if 'tags' in updates:
        updates['tags'] = _json.dumps(_normalize_tags(updates['tags']))
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
        # S-7BA9955A6D — project status automation. When the last open
        # step closes (all done/skipped), nudge the project to 'archived'.
        # Only flips active→archived; never reopens a manual archive.
        try:
            _maybe_auto_archive_project(step_id)
        except Exception:
            pass
    return ok


def _maybe_auto_archive_project(step_id: str) -> None:
    """If every step under the parent project is done/skipped and the
    project is still 'active', flip the project to 'archived'.
    S-7BA9955A6D — keeps closed work from cluttering active dashboards.
    """
    from utils.db._connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT project_id FROM project_steps WHERE step_id=?",
            (step_id,),
        ).fetchone()
        if not row:
            return
        pid = row['project_id']
        proj = conn.execute(
            "SELECT status FROM projects WHERE project_id=?", (pid,),
        ).fetchone()
        if not proj or proj['status'] != 'active':
            return
        rows = conn.execute(
            "SELECT status FROM project_steps WHERE project_id=?", (pid,),
        ).fetchall()
        if not rows:
            return
        if any(r['status'] not in ('done', 'skipped') for r in rows):
            return
        conn.execute(
            "UPDATE projects SET status=?, updated_at=? WHERE project_id=?",
            ('archived', time.time(), pid),
        )
        conn.commit()
    finally:
        conn.close()
    _emit_spine(f"Project auto-archived: {pid}", {'project_id': pid}, severity='info')


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
    residual_risk: Optional[str] = None,
    owner_route: Optional[str] = None,
) -> bool:
    """Rename / re-describe / re-assign a step. Status changes go through
    ``update_step_status`` which already emits spine events per transition.

    S-64552DDFEA: ``residual_risk`` accepts ``None`` (unchanged), ``""``
    (clear), or up to 240 chars of text describing exposure left after a
    partial/done close-out.
    S-58C4823367: ``owner_route`` accepts a short slug used by routing
    rules to dispatch the step to a specific agent/team. Independent of
    the user-facing ``owner`` column.
    """
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
    if residual_risk is not None:
        rr = (residual_risk or '').strip()
        updates['residual_risk'] = rr[:240] if rr else None
    if owner_route is not None:
        route = (owner_route or '').strip().lower()
        # slug: replace whitespace + slashes with underscores, drop other
        # non-alnum/dash chars, collapse repeats, max 48 chars.
        import re as _re
        route = _re.sub(r'[\s/\\]+', '_', route)
        route = ''.join(c for c in route if c.isalnum() or c in ('-', '_'))
        route = _re.sub(r'_+', '_', route).strip('_-')
        updates['owner_route'] = route[:48] if route else None
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


# ── Step dependencies (S-98FA0FAEFE) ────────────────────────────────────────

def add_step_dependency(step_id: str, depends_on: str) -> bool:
    """Declare that ``step_id`` cannot start until ``depends_on`` is done.

    Both step_ids must exist. Self-loops and direct cycles (A→B and B→A)
    are rejected. Idempotent: re-adding the same edge returns True.
    """
    sid, dep = (step_id or '').strip(), (depends_on or '').strip()
    if not sid or not dep:
        return False
    if sid == dep:
        raise ValueError("a step cannot depend on itself")
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            for x in (sid, dep):
                if conn.execute(
                    "SELECT 1 FROM project_steps WHERE step_id=?", (x,)
                ).fetchone() is None:
                    raise ValueError(f"unknown step_id: {x}")
            # Reject the simple A↔B cycle. Deeper cycles are rare and the
            # caller can run a topological check on top.
            inverse = conn.execute(
                "SELECT 1 FROM project_step_deps WHERE step_id=? AND depends_on=?",
                (dep, sid),
            ).fetchone()
            if inverse:
                raise ValueError(
                    f"adding {sid} → {dep} would create a cycle with the "
                    f"existing {dep} → {sid} dependency")
            conn.execute(
                "INSERT OR IGNORE INTO project_step_deps (step_id, depends_on, created_at) "
                "VALUES (?, ?, ?)",
                (sid, dep, time.time()),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except ValueError:
        raise
    except Exception:
        return False


def remove_step_dependency(step_id: str, depends_on: str) -> bool:
    sid, dep = (step_id or '').strip(), (depends_on or '').strip()
    if not sid or not dep:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            cur = conn.execute(
                "DELETE FROM project_step_deps WHERE step_id=? AND depends_on=?",
                (sid, dep),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False


def list_step_dependencies(step_id: str) -> List[Dict[str, Any]]:
    """Return the steps that *step_id* depends on (its prerequisites)."""
    if not step_id:
        return []
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT s.step_id, s.title, s.status "
                "FROM project_step_deps d "
                "JOIN project_steps s ON s.step_id = d.depends_on "
                "WHERE d.step_id=? "
                "ORDER BY s.order_idx ASC, s.created_at ASC",
                (step_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def list_step_blockers(step_id: str) -> List[Dict[str, Any]]:
    """Return the steps that depend on *step_id* (downstream consumers)."""
    if not step_id:
        return []
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT s.step_id, s.title, s.status "
                "FROM project_step_deps d "
                "JOIN project_steps s ON s.step_id = d.step_id "
                "WHERE d.depends_on=? "
                "ORDER BY s.order_idx ASC, s.created_at ASC",
                (step_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def bulk_add_steps(
    project_id: str,
    items: List[Dict[str, Any]],
    *,
    atomic: bool = True,
) -> Dict[str, Any]:
    """Insert many steps under one project in a single transaction.

    S-EECAFCA218 — rollback safety for bulk project import.

    Behaviour:
      * Validates the project exists; otherwise ``{"ok": False, "error": ...}``.
      * Iterates *items* in order. Each item is ``{"title", "description", "owner"}``.
      * Skips duplicates by case-insensitive title within the project.
      * If ``atomic=True`` (default) and any insert raises, the whole
        transaction is rolled back and **no** steps are persisted; the
        return payload reports ``rolled_back=True`` and a ``failed`` entry
        identifying the offending item.
      * If ``atomic=False``, behaves like the legacy per-item commit.

    Returns ``{"ok": bool, "created": [...], "skipped": [...],
              "failed": Optional[dict], "rolled_back": bool}``.
    """
    if not project_id:
        return {"ok": False, "error": "project_id required",
                "created": [], "skipped": [], "failed": None,
                "rolled_back": False}
    if not isinstance(items, list):
        return {"ok": False, "error": "items must be a list",
                "created": [], "skipped": [], "failed": None,
                "rolled_back": False}
    _ensure_schema()
    if not _project_exists(project_id):
        return {"ok": False, "error": f"unknown project_id: {project_id}",
                "created": [], "skipped": [], "failed": None,
                "rolled_back": False}

    from utils.db._connection import get_connection
    conn = get_connection()
    created: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    failed: Optional[Dict[str, Any]] = None
    try:
        existing_titles = {
            (r['title'] or '').strip().lower()
            for r in conn.execute(
                "SELECT title FROM project_steps WHERE project_id=?",
                (project_id,),
            ).fetchall()
        }
        next_idx_row = conn.execute(
            "SELECT COALESCE(MAX(order_idx), -1) AS m FROM project_steps WHERE project_id=?",
            (project_id,),
        ).fetchone()
        next_idx = int(next_idx_row['m']) + 1 if next_idx_row else 0

        if atomic:
            conn.execute("SAVEPOINT bulk_add_steps")

        try:
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    skipped.append({"index": i, "reason": "not an object"})
                    continue
                title = str(item.get('title') or '').strip()
                if not title:
                    skipped.append({"index": i, "reason": "title required"})
                    continue
                if title.lower() in existing_titles:
                    skipped.append({"index": i, "title": title,
                                    "reason": "duplicate title"})
                    continue
                step_id = 'S-' + uuid.uuid4().hex[:10].upper()
                now = time.time()
                conn.execute(
                    "INSERT INTO project_steps (step_id, project_id, title, description, status, owner, order_idx, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'todo', ?, ?, ?, ?)",
                    (step_id, project_id, title[:200],
                     str(item.get('description') or '')[:4000],
                     str(item.get('owner') or DEFAULT_OWNER)[:64],
                     int(next_idx), now, now),
                )
                created.append({"index": i, "step_id": step_id, "title": title})
                existing_titles.add(title.lower())
                next_idx += 1
        except Exception as e:
            failed = {"index": len(created) + len(skipped),
                      "reason": str(e) or e.__class__.__name__}
            if atomic:
                conn.execute("ROLLBACK TO SAVEPOINT bulk_add_steps")
                conn.execute("RELEASE SAVEPOINT bulk_add_steps")
                conn.commit()
                return {"ok": False, "created": [], "skipped": skipped,
                        "failed": failed, "rolled_back": True}
            # non-atomic: just stop
            conn.commit()
            return {"ok": False, "created": created, "skipped": skipped,
                    "failed": failed, "rolled_back": False}

        if atomic:
            conn.execute("RELEASE SAVEPOINT bulk_add_steps")
        conn.commit()
    finally:
        conn.close()

    # Mirror records outside the lock (best effort; never block success).
    for c in created:
        try:
            from core.records import mirror as _records_mirror
            _records_mirror('step', c['step_id'], actor='bulk_add_steps')
        except Exception:
            pass
        _emit_spine(f"Step added (bulk): {c['title']}",
                    {'project_id': project_id, 'step_id': c['step_id']})

    return {"ok": True, "created": created, "skipped": skipped,
            "failed": None, "rolled_back": False}
