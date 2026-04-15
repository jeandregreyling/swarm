"""
TIME MACHINE — Agent Twelve's Core Capability
Tracks all system state changes, agent executions, memory mutations.
Provides replay, rewind, and temporal analysis functionality.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, UTC
from pathlib import Path
import hashlib
import re
import subprocess

DB_PATH = Path(__file__).parent.parent / 'swarm_memory.db'

# ── Git / worktree roots ──────────────────────────────────────────────────
_SWARM_PROD_ROOT = os.environ.get('SWARM_ROOT', str(Path(__file__).parent.parent))
_SWARM_UAT_ROOT  = os.environ.get('SWARM_UAT_ROOT', _SWARM_PROD_ROOT + '-uat')
_SWARM_DEV_ROOT  = os.environ.get('SWARM_DEV_ROOT', _SWARM_PROD_ROOT + '-dev')

def _git_cmd(args, cwd=None):
    """Run a git command. Returns (stdout+stderr, returncode)."""
    try:
        r = subprocess.run(
            ['git'] + args,
            capture_output=True, text=True, timeout=30,
            cwd=cwd or _SWARM_PROD_ROOT,
        )
        return (r.stdout + r.stderr).strip(), r.returncode
    except Exception as e:
        return str(e), 1

def _git_head_info(cwd=None):
    """Return (commit_hash, branch_name) for a worktree."""
    commit, rc1 = _git_cmd(['rev-parse', 'HEAD'], cwd=cwd)
    branch, rc2 = _git_cmd(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=cwd)
    return (commit.strip()[:12] if rc1 == 0 else '', branch.strip() if rc2 == 0 else '')

class TimeMachine:
    """Track system state across time. Enable temporal queries and replay."""
    
    def __init__(self):
        self.self_test()
    
    def init_schema(self):
        """Create time tracking tables if they don't exist."""
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS time_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                agent TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT DEFAULT '',
                state_hash TEXT DEFAULT '',
                details TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS time_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_name TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                description TEXT DEFAULT '',
                agent TEXT NOT NULL,
                full_state TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS time_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                phase TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._migrate_compat_schema(conn)
        conn.commit()
        conn.close()

    def _table_columns(self, conn, table_name: str) -> set:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}

    def _ensure_column(self, conn, table_name: str, column_name: str, definition: str):
        if column_name not in self._table_columns(conn, table_name):
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _migrate_compat_schema(self, conn):
        """Unify older temporal table shapes with the newer Vortex runtime model."""
        for name, definition in (
            ('timestamp', "TEXT DEFAULT ''"),
            ('action', "TEXT DEFAULT ''"),
            ('target', "TEXT DEFAULT ''"),
            ('state_hash', "TEXT DEFAULT ''"),
            ('details', "TEXT DEFAULT '{}'"),
        ):
            self._ensure_column(conn, 'time_events', name, definition)

        event_cols = self._table_columns(conn, 'time_events')
        if 'description' in event_cols:
            conn.execute(
                "UPDATE time_events SET action = description WHERE COALESCE(action, '') = '' AND COALESCE(description, '') != ''"
            )
        if 'metadata' in event_cols:
            conn.execute(
                "UPDATE time_events SET details = metadata WHERE COALESCE(details, '') IN ('', '{}') AND COALESCE(metadata, '') != ''"
            )
        if 'created_at' in event_cols:
            conn.execute(
                "UPDATE time_events SET timestamp = created_at WHERE COALESCE(timestamp, '') = '' AND COALESCE(created_at, '') != ''"
            )

        for name, definition in (
            ('timestamp', "TEXT DEFAULT ''"),
            ('session_id', "TEXT DEFAULT ''"),
            ('phase', "TEXT DEFAULT ''"),
            ('status', "TEXT DEFAULT 'active'"),
            ('notes', "TEXT DEFAULT ''"),
        ):
            self._ensure_column(conn, 'time_journal', name, definition)

        journal_cols = self._table_columns(conn, 'time_journal')
        if 'entry' in journal_cols:
            conn.execute(
                "UPDATE time_journal SET notes = entry WHERE COALESCE(notes, '') = '' AND COALESCE(entry, '') != ''"
            )
        if 'created_at' in journal_cols:
            conn.execute(
                "UPDATE time_journal SET timestamp = created_at WHERE COALESCE(timestamp, '') = '' AND COALESCE(created_at, '') != ''"
            )
        conn.execute(
            "UPDATE time_journal SET session_id = 'legacy_' || id WHERE COALESCE(session_id, '') = ''"
        )

        for name, definition in (
            ('checkpoint_name', "TEXT DEFAULT ''"),
            ('timestamp', "TEXT DEFAULT ''"),
            ('full_state', "TEXT DEFAULT '{}'"),
        ):
            self._ensure_column(conn, 'time_checkpoints', name, definition)

        checkpoint_cols = self._table_columns(conn, 'time_checkpoints')
        if 'name' in checkpoint_cols:
            conn.execute(
                "UPDATE time_checkpoints SET checkpoint_name = name WHERE COALESCE(checkpoint_name, '') = '' AND COALESCE(name, '') != ''"
            )
        if 'state_snapshot' in checkpoint_cols:
            conn.execute(
                "UPDATE time_checkpoints SET full_state = state_snapshot WHERE COALESCE(full_state, '') IN ('', '{}') AND COALESCE(state_snapshot, '') != ''"
            )
        if 'created_at' in checkpoint_cols:
            conn.execute(
                "UPDATE time_checkpoints SET timestamp = created_at WHERE COALESCE(timestamp, '') = '' AND COALESCE(created_at, '') != ''"
            )
    
    def self_test(self):
        """Initialize schema on startup."""
        try:
            self.init_schema()
        except Exception as e:
            print(f"[TimeMachine] Schema init warning: {e}")

    def _normalize_workflow_state(self, state: dict) -> dict:
        """Normalize checkpoint payloads across legacy and current schemas."""
        if not isinstance(state, dict):
            state = {}

        normalized = {
            'captured_at': state.get('captured_at') or datetime.now(UTC).isoformat() + 'Z',
            'counts': state.get('counts') if isinstance(state.get('counts'), dict) else {},
            'work_proposals': state.get('work_proposals') if isinstance(state.get('work_proposals'), list) else [],
            'decisions': state.get('decisions') if isinstance(state.get('decisions'), list) else [],
            'queue': state.get('queue') if isinstance(state.get('queue'), list) else [],
            'rollback_points': state.get('rollback_points') if isinstance(state.get('rollback_points'), list) else [],
            'git': state.get('git') if isinstance(state.get('git'), dict) else {},
            'git_tags': state.get('git_tags') if isinstance(state.get('git_tags'), dict) else {},
        }

        # Legacy bootstrap checkpoints stored scalar counts in top-level keys.
        for key in ('work_proposals', 'decisions', 'queue', 'rollback_points'):
            if key in state and isinstance(state.get(key), int):
                normalized['counts'][key] = state.get(key)

        # Backfill counts when missing so preview output is deterministic.
        for key in ('work_proposals', 'decisions', 'queue', 'rollback_points'):
            normalized['counts'].setdefault(key, len(normalized[key]))

        return normalized

    def _write_activity_log(self, event: str, detail: str):
        """Mirror critical Vortex actions into activity_log for ALM/audit traceability."""
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "INSERT INTO activity_log (service, event, detail) VALUES ('vortex', ?, ?)",
                (event, detail[:1200])
            )
            conn.commit()
        except Exception:
            # activity_log may not exist in some stripped-down test databases.
            pass
        finally:
            conn.close()
    
    def record_event(self, agent: str, action: str, event_type: str = 'action', 
                     target: str = '', details: dict = None, state_hash: str = '') -> int:
        """
        Record a timestamped event in the time journal.
        
        Returns: event ID
        """
        details = details or {}
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        timestamp = datetime.now(UTC).isoformat() + 'Z'
        
        cursor.execute("""
            INSERT INTO time_events (timestamp, event_type, agent, action, target, state_hash, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, event_type, agent, action, target, state_hash, json.dumps(details)))
        
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return event_id
    
    def create_checkpoint(self, checkpoint_name: str, agent: str, 
                         description: str = '', full_state: dict = None) -> int:
        """
        Create a named checkpoint — a snapshot of system state at a moment in time.
        Useful for recovery, comparison, temporal analysis.
        
        Returns: checkpoint ID
        """
        full_state = full_state or {}
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        timestamp = datetime.now(UTC).isoformat() + 'Z'
        
        try:
            cursor.execute("""
                INSERT INTO time_checkpoints (checkpoint_name, timestamp, description, agent, full_state)
                VALUES (?, ?, ?, ?, ?)
            """, (checkpoint_name, timestamp, description, agent, json.dumps(full_state)))
            
            checkpoint_id = cursor.lastrowid
            conn.commit()
            return checkpoint_id
        finally:
            conn.close()
    
    def start_session(self, agent: str, session_id: str, phase: str = 'init') -> int:
        """
        Start a new agent session with temporal tracking.
        Returns: journal entry ID
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        timestamp = datetime.now(UTC).isoformat() + 'Z'
        
        cursor.execute("""
            INSERT INTO time_journal (agent, timestamp, session_id, phase, status)
            VALUES (?, ?, ?, ?, 'active')
        """, (agent, timestamp, session_id, phase))
        
        journal_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return journal_id
    
    def end_session(self, session_id: str, status: str = 'completed', notes: str = '') -> bool:
        """Close an active session."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE time_journal
            SET status = ?, notes = ?
            WHERE session_id = ? AND status = 'active'
        """, (status, notes, session_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def get_timeline(self, agent: str = None, start_time: str = None, 
                     end_time: str = None, limit: int = 100) -> list:
        """
        Retrieve a timeline of events for analysis.
        
        Args:
            agent: Filter by agent (None = all agents)
            start_time: ISO format datetime (inclusive)
            end_time: ISO format datetime (inclusive)  
            limit: Max events to return
        
        Returns: List of event dicts
        """
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM time_events WHERE 1=1"
        params = []
        
        if agent:
            query += " AND agent = ?"
            params.append(agent)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(r) for r in rows]
    
    def get_sessions(self, agent: str = None, status: str = None, limit: int = 100) -> list:
        """
        List all temporal sessions for an agent.
        
        Returns: List of session dicts
        """
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM time_journal WHERE 1=1"
        params = []
        
        if agent:
            query += " AND agent = ?"
            params.append(agent)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(r) for r in rows]
    
    def get_checkpoint(self, checkpoint_name: str) -> dict:
        """Retrieve a specific checkpoint."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM time_checkpoints WHERE checkpoint_name = ?", 
                      (checkpoint_name,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            r = dict(row)
            if not r.get('checkpoint_name') and r.get('name'):
                r['checkpoint_name'] = r['name']
            if not r.get('timestamp') and r.get('created_at'):
                r['timestamp'] = r['created_at']
            if not r.get('full_state') and r.get('state_snapshot'):
                r['full_state'] = r['state_snapshot']
            try:
                r['full_state'] = json.loads(r['full_state'])
            except:
                pass
            return r
        
        return None
    
    def list_checkpoints(self, before_time: str = None, after_time: str = None, limit: int = 100) -> list:
        """List all checkpoints, optionally filtered by time range."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM time_checkpoints WHERE 1=1"
        params = []
        
        if after_time:
            query += " AND timestamp >= ?"
            params.append(after_time)
        
        if before_time:
            query += " AND timestamp <= ?"
            params.append(before_time)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        normalized = []
        for row in rows:
            item = dict(row)
            if not item.get('checkpoint_name') and item.get('name'):
                item['checkpoint_name'] = item['name']
            if not item.get('timestamp') and item.get('created_at'):
                item['timestamp'] = item['created_at']
            # Keep list payloads lightweight; detailed state is available via get_checkpoint().
            item.pop('full_state', None)
            item.pop('state_snapshot', None)
            normalized.append(item)
        return normalized

    def capture_workflow_state(self) -> dict:
        """Snapshot the Swarm-facing governance state for Vortex checkpoints."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        state = {
            'captured_at': datetime.now(UTC).isoformat() + 'Z',
            'counts': {},
            'work_proposals': [],
            'decisions': [],
            'queue': [],
            'rollback_points': [],
            'git': {},
        }

        # ── Git state across all worktrees ────────────────────────────────
        import os
        for label, root in [('prod', _SWARM_PROD_ROOT), ('uat', _SWARM_UAT_ROOT), ('dev', _SWARM_DEV_ROOT)]:
            if os.path.isdir(root):
                commit, branch = _git_head_info(cwd=root)
                state['git'][label] = {'commit': commit, 'branch': branch, 'root': root}

        try:
            if 'work_proposals' in tables:
                proposals = conn.execute(
                    "SELECT proposal_id, agent, title, status, ticket_number, queue_id, updated_at FROM work_proposals ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
                state['work_proposals'] = [dict(r) for r in proposals]
                state['counts']['work_proposals'] = len(state['work_proposals'])

            if 'decisions' in tables:
                decisions = conn.execute(
                    "SELECT decision_id, agent, component, proposal_file, decision, test_status, commit_hash, created_at FROM decisions ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
                state['decisions'] = [dict(r) for r in decisions]
                state['counts']['decisions'] = len(state['decisions'])

            if 'queue' in tables:
                queue_rows = conn.execute(
                    "SELECT id, status, priority, source_type, agent, created_at FROM queue ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
                state['queue'] = [dict(r) for r in queue_rows]
                state['counts']['queue'] = len(state['queue'])

            if 'time_machine' in tables:
                rollback_rows = conn.execute(
                    "SELECT checkpoint_id, agent, file_path, decision_id, commit_hash, created_at FROM time_machine WHERE is_rollback_point = 1 ORDER BY created_at DESC LIMIT 100"
                ).fetchall()
                state['rollback_points'] = [dict(r) for r in rollback_rows]
                state['counts']['rollback_points'] = len(state['rollback_points'])
        finally:
            conn.close()

        return state

    def create_workflow_checkpoint(self, label: str, agent: str = 'twelve', description: str = '') -> dict:
        safe_label = re.sub(r'[^a-z0-9]+', '-', (label or 'checkpoint').lower()).strip('-')[:48] or 'checkpoint'
        timestamp = datetime.now(UTC).strftime('%Y%m%d-%H%M%S')
        checkpoint_name = f'vortex-{timestamp}-{safe_label}'
        full_state = self.capture_workflow_state()

        # ── Git commit + tag for each active worktree (A.1.3) ─────────────
        import os
        git_tags = {}
        for wt_label, root in [('prod', _SWARM_PROD_ROOT), ('uat', _SWARM_UAT_ROOT), ('dev', _SWARM_DEV_ROOT)]:
            if os.path.isdir(os.path.join(root, '.git')) or os.path.isfile(os.path.join(root, '.git')):
                tag_name = f'{checkpoint_name}-{wt_label}'
                # Stage all changes and commit (no-op if working tree is clean)
                _git_cmd(['add', '-A'], cwd=root)
                commit_msg = f'[vortex] {checkpoint_name}\n\nAgent: {agent}\n{description or ""}'.strip()
                out_c, rc_c = _git_cmd(['commit', '-m', commit_msg, '--allow-empty'], cwd=root)
                if rc_c != 0 and 'nothing to commit' not in (out_c or '').lower():
                    print(f'[Vortex] git commit warning for {wt_label}: {out_c}')
                # Tag the current HEAD (whether we just committed or not)
                out, rc = _git_cmd(['tag', tag_name], cwd=root)
                if rc == 0:
                    git_tags[wt_label] = tag_name
                else:
                    print(f'[Vortex] git tag failed for {wt_label}: {out}')
        full_state['git_tags'] = git_tags

        checkpoint_id = self.create_checkpoint(checkpoint_name, agent, description, full_state)
        self.record_event(
            agent=agent,
            action='create_workflow_checkpoint',
            event_type='checkpoint',
            target=checkpoint_name,
            details={'checkpoint_id': checkpoint_id, 'description': description, 'counts': full_state.get('counts', {})}
        )
        self._write_activity_log(
            'checkpoint_created',
            f'{checkpoint_name} | agent={agent} | counts={json.dumps(full_state.get("counts", {}), ensure_ascii=True)}'
        )
        return {
            'checkpoint_id': checkpoint_id,
            'checkpoint_name': checkpoint_name,
            'timestamp': full_state['captured_at'],
            'counts': full_state.get('counts', {}),
            'git': full_state.get('git', {}),
            'git_tags': git_tags,
        }

    def preview_restore(self, checkpoint_name: str) -> dict:
        checkpoint = self.get_checkpoint(checkpoint_name)
        if not checkpoint:
            return None

        checkpoint_state = self._normalize_workflow_state(checkpoint.get('full_state') or {})
        current_state = self._normalize_workflow_state(self.capture_workflow_state())

        current_proposals = {row['proposal_id']: row for row in current_state.get('work_proposals', []) if row.get('proposal_id')}
        saved_proposals = {row['proposal_id']: row for row in checkpoint_state.get('work_proposals', []) if row.get('proposal_id')}
        proposal_changes = []
        for proposal_id, saved in saved_proposals.items():
            current = current_proposals.get(proposal_id)
            if not current:
                proposal_changes.append({'proposal_id': proposal_id, 'change': 'missing_now', 'checkpoint_status': saved.get('status'), 'current_status': None})
            elif (current.get('status') != saved.get('status')) or (current.get('ticket_number') != saved.get('ticket_number')):
                proposal_changes.append({
                    'proposal_id': proposal_id,
                    'change': 'status_drift',
                    'checkpoint_status': saved.get('status'),
                    'current_status': current.get('status'),
                    'checkpoint_ticket': saved.get('ticket_number'),
                    'current_ticket': current.get('ticket_number'),
                })
        for proposal_id, current in current_proposals.items():
            if proposal_id not in saved_proposals:
                proposal_changes.append({
                    'proposal_id': proposal_id,
                    'change': 'added_since_checkpoint',
                    'checkpoint_status': None,
                    'current_status': current.get('status'),
                    'checkpoint_ticket': None,
                    'current_ticket': current.get('ticket_number'),
                })

        current_decisions = {str(row['decision_id']): row for row in current_state.get('decisions', []) if row.get('decision_id') is not None}
        saved_decisions = {str(row['decision_id']): row for row in checkpoint_state.get('decisions', []) if row.get('decision_id') is not None}
        decision_changes = []
        for decision_id, saved in saved_decisions.items():
            current = current_decisions.get(decision_id)
            if not current:
                decision_changes.append({'decision_id': decision_id, 'change': 'missing_now', 'checkpoint_status': saved.get('test_status'), 'current_status': None})
            elif (current.get('test_status') != saved.get('test_status')) or (current.get('commit_hash') != saved.get('commit_hash')):
                decision_changes.append({
                    'decision_id': decision_id,
                    'change': 'decision_drift',
                    'checkpoint_status': saved.get('test_status'),
                    'current_status': current.get('test_status'),
                    'checkpoint_commit': saved.get('commit_hash'),
                    'current_commit': current.get('commit_hash'),
                })
        for decision_id, current in current_decisions.items():
            if decision_id not in saved_decisions:
                decision_changes.append({
                    'decision_id': decision_id,
                    'change': 'added_since_checkpoint',
                    'checkpoint_status': None,
                    'current_status': current.get('test_status'),
                    'checkpoint_commit': None,
                    'current_commit': current.get('commit_hash'),
                })

        current_queue = {str(row['id']): row for row in current_state.get('queue', []) if row.get('id') is not None}
        saved_queue = {str(row['id']): row for row in checkpoint_state.get('queue', []) if row.get('id') is not None}
        queue_changes = []
        for queue_id, saved in saved_queue.items():
            current = current_queue.get(queue_id)
            if not current:
                queue_changes.append({
                    'queue_id': queue_id,
                    'change': 'missing_now',
                    'checkpoint_status': saved.get('status'),
                    'current_status': None,
                })
            elif current.get('status') != saved.get('status') or current.get('priority') != saved.get('priority') or current.get('agent') != saved.get('agent'):
                queue_changes.append({
                    'queue_id': queue_id,
                    'change': 'queue_drift',
                    'checkpoint_status': saved.get('status'),
                    'current_status': current.get('status'),
                    'checkpoint_priority': saved.get('priority'),
                    'current_priority': current.get('priority'),
                    'checkpoint_agent': saved.get('agent'),
                    'current_agent': current.get('agent'),
                })
        for queue_id, current in current_queue.items():
            if queue_id not in saved_queue:
                queue_changes.append({
                    'queue_id': queue_id,
                    'change': 'added_since_checkpoint',
                    'checkpoint_status': None,
                    'current_status': current.get('status'),
                    'checkpoint_priority': None,
                    'current_priority': current.get('priority'),
                    'checkpoint_agent': None,
                    'current_agent': current.get('agent'),
                })

        return {
            'checkpoint_name': checkpoint.get('checkpoint_name') or checkpoint_name,
            'checkpoint_timestamp': checkpoint.get('timestamp'),
            'checkpoint_counts': checkpoint_state.get('counts', {}),
            'current_counts': current_state.get('counts', {}),
            'checkpoint_git': checkpoint_state.get('git', {}),
            'checkpoint_git_tags': checkpoint_state.get('git_tags', {}),
            'current_git': current_state.get('git', {}),
            'summary': {
                'proposal_changes': len(proposal_changes),
                'decision_changes': len(decision_changes),
                'queue_changes': len(queue_changes),
                'restorable': bool(proposal_changes or decision_changes or queue_changes),
                'has_git_tags': bool(checkpoint_state.get('git_tags')),
            },
            'changes': {
                'work_proposals': proposal_changes[:50],
                'decisions': decision_changes[:50],
                'queue': queue_changes[:50],
            },
        }

    def restore_workflow_state(self, checkpoint_name: str, actor: str = 'twelve', dry_run: bool = True) -> dict:
        preview = self.preview_restore(checkpoint_name)
        if not preview:
            raise ValueError(f'checkpoint not found: {checkpoint_name}')

        self.record_event(
            agent=actor,
            action='preview_restore_workflow_state' if dry_run else 'restore_workflow_state',
            event_type='restore_preview' if dry_run else 'restore',
            target=checkpoint_name,
            details={'dry_run': dry_run, 'summary': preview['summary']}
        )
        self._write_activity_log(
            'restore_preview' if dry_run else 'restore_apply_requested',
            f'checkpoint={checkpoint_name} | actor={actor} | summary={json.dumps(preview.get("summary", {}), ensure_ascii=True)}'
        )
        if dry_run:
            return {'ok': True, 'dry_run': True, **preview}

        safety = self.create_workflow_checkpoint(f'pre-restore-{checkpoint_name}', actor, f'Safety checkpoint before restoring {checkpoint_name}')
        checkpoint = self.get_checkpoint(checkpoint_name)
        saved_state = self._normalize_workflow_state(checkpoint.get('full_state') or {})

        conn = sqlite3.connect(DB_PATH)
        restored = {'work_proposals': 0, 'decisions': 0, 'queue': 0, 'deleted_work_proposals': 0, 'deleted_decisions': 0, 'deleted_queue': 0}
        try:
            saved_proposal_ids = {row.get('proposal_id') for row in saved_state.get('work_proposals', []) if row.get('proposal_id')}
            saved_decision_ids = {row.get('decision_id') for row in saved_state.get('decisions', []) if row.get('decision_id') is not None}
            saved_queue_ids = {row.get('id') for row in saved_state.get('queue', []) if row.get('id') is not None}

            if saved_proposal_ids:
                placeholders = ','.join('?' for _ in saved_proposal_ids)
                cursor = conn.execute(
                    f"DELETE FROM work_proposals WHERE proposal_id NOT IN ({placeholders})",
                    tuple(saved_proposal_ids)
                )
            else:
                cursor = conn.execute("DELETE FROM work_proposals")
            restored['deleted_work_proposals'] = cursor.rowcount

            if saved_decision_ids:
                placeholders = ','.join('?' for _ in saved_decision_ids)
                cursor = conn.execute(
                    f"DELETE FROM decisions WHERE decision_id NOT IN ({placeholders})",
                    tuple(saved_decision_ids)
                )
            else:
                cursor = conn.execute("DELETE FROM decisions")
            restored['deleted_decisions'] = cursor.rowcount

            if saved_queue_ids:
                placeholders = ','.join('?' for _ in saved_queue_ids)
                cursor = conn.execute(
                    f"DELETE FROM queue WHERE id NOT IN ({placeholders})",
                    tuple(saved_queue_ids)
                )
            else:
                cursor = conn.execute("DELETE FROM queue")
            restored['deleted_queue'] = cursor.rowcount

            for row in saved_state.get('work_proposals', []):
                # Route through governance with singleton bypass (system restore op)
                try:
                    import sys as _sys
                    _sys.path.insert(0, '/home/seven/swarm/utils')
                    from governance import transition_proposal, GovernanceError
                    transition_proposal(
                        row.get('proposal_id'), row.get('status', 'pending'),
                        'vortex', actor='vortex_restore',
                        note=f'restore from checkpoint {checkpoint_name}',
                        conn=conn, _skip_singleton=True,
                    )
                    restored['work_proposals'] += 1
                except GovernanceError:
                    # Fallback: direct update for illegal transitions during restore
                    cursor = conn.execute(
                        "UPDATE work_proposals SET status=?, ticket_number=?, updated_at=datetime('now') WHERE proposal_id=?",
                        (row.get('status', 'pending'), row.get('ticket_number', ''), row.get('proposal_id'))
                    )
                    restored['work_proposals'] += cursor.rowcount
                except Exception:
                    cursor = conn.execute(
                        "UPDATE work_proposals SET status=?, ticket_number=?, updated_at=datetime('now') WHERE proposal_id=?",
                        (row.get('status', 'pending'), row.get('ticket_number', ''), row.get('proposal_id'))
                    )
                    restored['work_proposals'] += cursor.rowcount

            for row in saved_state.get('decisions', []):
                cursor = conn.execute(
                    "UPDATE decisions SET test_status=?, commit_hash=? WHERE decision_id=?",
                    (row.get('test_status', 'PENDING'), row.get('commit_hash', ''), row.get('decision_id'))
                )
                restored['decisions'] += cursor.rowcount

            for row in saved_state.get('queue', []):
                cursor = conn.execute(
                    "UPDATE queue SET status=?, priority=?, agent=? WHERE id=?",
                    (row.get('status', 'queued'), row.get('priority', 5), row.get('agent', ''), row.get('id'))
                )
                restored['queue'] += cursor.rowcount

            conn.commit()
        finally:
            conn.close()

        # ── Git-level restore: revert worktrees to checkpoint tags (A.1.3) ──
        import os
        git_tags = saved_state.get('git_tags', {})
        git_restored = {}
        for wt_label, tag_name in git_tags.items():
            root_map = {'prod': _SWARM_PROD_ROOT, 'uat': _SWARM_UAT_ROOT, 'dev': _SWARM_DEV_ROOT}
            root = root_map.get(wt_label)
            if root and os.path.isdir(root):
                # Verify tag exists before reverting
                out, rc = _git_cmd(['tag', '-l', tag_name], cwd=root)
                if rc == 0 and tag_name in out:
                    # Safe revert: undo commits between tag and HEAD
                    out2, rc2 = _git_cmd(
                        ['revert', '--no-commit', f'{tag_name}..HEAD'],
                        cwd=root
                    )
                    if rc2 == 0:
                        # Commit the revert
                        revert_msg = (
                            f'[vortex-restore] Revert to {checkpoint_name}\n\n'
                            f'Actor: {actor}\n'
                            f'Tag: {tag_name}\n'
                            f'Safety checkpoint: {safety.get("checkpoint_name", "none")}'
                        )
                        out3, rc3 = _git_cmd(['commit', '-m', revert_msg, '--allow-empty'], cwd=root)
                        git_restored[wt_label] = {
                            'tag': tag_name, 'ok': True, 'method': 'revert',
                            'output': (out3 or out2)[:200],
                        }
                    else:
                        # Revert failed (conflicts etc) — abort and fall back to reset
                        _git_cmd(['revert', '--abort'], cwd=root)
                        out4, rc4 = _git_cmd(['reset', '--hard', tag_name], cwd=root)
                        git_restored[wt_label] = {
                            'tag': tag_name, 'ok': rc4 == 0, 'method': 'reset_fallback',
                            'output': (out4 or out2)[:200],
                        }
                else:
                    git_restored[wt_label] = {'tag': tag_name, 'ok': False, 'output': 'tag not found'}

        self.record_event(
            agent=actor,
            action='restore_workflow_state',
            event_type='restore',
            target=checkpoint_name,
            details={'restored': restored, 'git_restored': git_restored, 'safety_checkpoint': safety['checkpoint_name']}
        )
        self._write_activity_log(
            'restore_applied',
            f'checkpoint={checkpoint_name} | actor={actor} | restored={json.dumps(restored, ensure_ascii=True)} | git={json.dumps(git_restored, ensure_ascii=True)} | safety={safety.get("checkpoint_name", "")}'
        )
        return {
            'ok': True,
            'dry_run': False,
            'restored': restored,
            'git_restored': git_restored,
            'safety_checkpoint': safety,
            **preview,
        }
    
    def get_temporal_stats(self, agent: str) -> dict:
        """Get statistics about an agent's temporal activity."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Total events
        cursor.execute("SELECT COUNT(*) as count FROM time_events WHERE agent = ?", (agent,))
        total_events = cursor.fetchone()[0]
        
        # Sessions
        cursor.execute("SELECT COUNT(*) as count FROM time_journal WHERE agent = ?", (agent,))
        total_sessions = cursor.fetchone()[0]
        
        # Checkpoints
        cursor.execute("SELECT COUNT(*) as count FROM time_checkpoints WHERE agent = ?", (agent,))
        total_checkpoints = cursor.fetchone()[0]
        
        # Latest activity
        cursor.execute("""
            SELECT timestamp FROM time_events WHERE agent = ?
            ORDER BY timestamp DESC LIMIT 1
        """, (agent,))
        latest = cursor.fetchone()
        latest_activity = latest[0] if latest else None
        
        conn.close()
        
        return {
            'agent': agent,
            'total_events': total_events,
            'total_sessions': total_sessions,
            'total_checkpoints': total_checkpoints,
            'latest_activity': latest_activity
        }
    
    def bootstrap_session(self) -> str:
        """
        Initialize a new system session.
        Called on startup to create a tracking point for this session.
        Returns: session_id
        """
        import uuid
        session_id = f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        try:
            self.start_session(agent='twelve', session_id=session_id, phase='startup')
            self.record_event(
                agent='twelve',
                action='bootstrap_session',
                event_type='system',
                target='scheduler',
                details={'session_id': session_id, 'timestamp': datetime.now(UTC).isoformat() + 'Z'}
            )
            return session_id
        except Exception as e:
            print(f"[TimeMachine] Bootstrap error: {e}")
            return None
    
    def log_decision_execution(self, decision_id: str, agent: str, status: str = 'executed', 
                               details: dict = None) -> int:
        """
        Log a decision execution event (Decision-001, Decision-002, etc.)
        """
        details = details or {}
        return self.record_event(
            agent=agent,
            action=f'execute_decision_{decision_id}',
            event_type='decision',
            target=decision_id,
            details={'status': status, **details}
        )
    
    def get_decision_history(self, decision_id: str) -> list:
        """Get all events related to a specific decision."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM time_events WHERE target = ? ORDER BY timestamp DESC",
            (decision_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(r) for r in rows]


# Global instance
time_wizard = TimeMachine()
