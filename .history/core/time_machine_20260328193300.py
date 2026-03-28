"""
TIME MACHINE — Agent Twelve's Core Capability
Tracks all system state changes, agent executions, memory mutations.
Provides replay, rewind, and temporal analysis functionality.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import hashlib

DB_PATH = Path(__file__).parent.parent / 'swarm_memory.db'

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
        conn.commit()
        conn.close()
    
    def self_test(self):
        """Initialize schema on startup."""
        try:
            self.init_schema()
        except Exception as e:
            print(f"[TimeMachine] Schema init warning: {e}")
    
    def record_event(self, agent: str, action: str, event_type: str = 'action', 
                     target: str = '', details: dict = None, state_hash: str = '') -> int:
        """
        Record a timestamped event in the time journal.
        
        Returns: event ID
        """
        details = details or {}
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
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
        
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
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
        
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
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
    
    def get_sessions(self, agent: str = None, status: str = None) -> list:
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
        
        query += " ORDER BY timestamp DESC"
        
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
            try:
                r['full_state'] = json.loads(r['full_state'])
            except:
                pass
            return r
        
        return None
    
    def list_checkpoints(self, before_time: str = None, after_time: str = None) -> list:
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
        
        query += " ORDER BY timestamp DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(r) for r in rows]
    
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


# Global instance
time_wizard = TimeMachine()
