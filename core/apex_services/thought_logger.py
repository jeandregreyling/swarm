"""
APEX Thought Logger
Enables APEX to record and retrieve its thoughts, reasoning, and actions.
This allows the harness to prove its worth and use logs for jailbreak guidance.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class APEXThoughtLogger:
    def __init__(self, agent="apex", conversation_id=None):
        self.agent = agent
        self.conversation_id = conversation_id
        self._thoughts = []
        self._decisions = []
        self._jailbreak_steps = []

    def log_thought(self, content, thought_type="reasoning", context=None, parent_id=None):
        thought = {
            'id': len(self._thoughts) + 1,
            'agent': self.agent,
            'conversation_id': self.conversation_id,
            'thought_type': thought_type,
            'content': content,
            'context': context or {},
            'parent_id': parent_id,
            'created_at': datetime.now().isoformat()
        }
        self._thoughts.append(thought)
        self._save_to_db('apex_thoughts', thought)
        return thought

    def log_decision(self, decision, reasoning="", options=None, chosen=None, confidence=0.0, context=None):
        decision_rec = {
            'id': len(self._decisions) + 1,
            'agent': self.agent,
            'conversation_id': self.conversation_id,
            'decision': decision,
            'reasoning': reasoning,
            'options': options or [],
            'chosen': chosen,
            'confidence': confidence,
            'context': context or {},
            'created_at': datetime.now().isoformat()
        }
        self._decisions.append(decision_rec)
        self._save_to_db('apex_decisions', decision_rec)
        return decision_rec

    def log_jailbreak_step(self, step_number, description, file_path=None, code=None):
        step = {
            'id': len(self._jailbreak_steps) + 1,
            'step_number': step_number,
            'description': description,
            'file_path': file_path,
            'code': code,
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }
        self._jailbreak_steps.append(step)
        self._save_to_db('apex_jailbreak_steps', step)
        return step

    def update_jailbreak_step(self, step_id, status, result=None, error=None):
        for step in self._jailbreak_steps:
            if step['id'] == step_id:
                step['status'] = status
                step['result'] = result
                step['error'] = error
                step['completed_at'] = datetime.now().isoformat()
                self._update_db('apex_jailbreak_steps', step, 'id')
                return True
        return False

    def get_thoughts(self, limit=100):
        return self._thoughts[-limit:]

    def get_decisions(self, limit=50):
        return self._decisions[-limit:]

    def get_jailbreak_steps(self):
        return sorted(self._jailbreak_steps, key=lambda x: x['step_number'])

    def get_service_traces(self, service=None, limit=100):
        return self._query_db('service_trace', service, limit)

    def get_recovery_chat(self, conversation_id=None, limit=100):
        return self._query_peer_messages(conversation_id, limit)

    def search_thoughts(self, query, limit=50):
        query_lower = query.lower()
        return [t for t in self._thoughts if query_lower in t.get('content', '').lower()][:limit]

    def get_learning_summary(self):
        return {
            'total_thoughts': len(self._thoughts),
            'total_decisions': len(self._decisions),
            'total_jailbreak_steps': len(self._jailbreak_steps),
            'recent_thoughts': self.get_thoughts(limit=10),
            'recent_decisions': self.get_decisions(limit=5),
            'jailbreak_progress': self._get_progress()
        }

    def _get_progress(self):
        progress = {'total': 0, 'pending': 0, 'completed': 0, 'failed': 0}
        for step in self._jailbreak_steps:
            progress['total'] += 1
            progress[step['status']] = progress.get(step['status'], 0) + 1
        return progress

    def prove_worth(self):
        traces = self.get_service_traces(limit=10)
        summary = self.get_learning_summary()
        return {
            'summary': summary,
            'service_actions': traces,
            'thoughts_analyzed': summary['total_thoughts'],
            'decisions_made': summary['total_decisions'],
            'jailbreak_progress': summary['jailbreak_progress'],
            'service_actions_performed': len(traces)
        }

    def guide_through_jailbreak(self):
        steps = self.get_jailbreak_steps()
        next_step = None
        for step in steps:
            if step['status'] == 'pending':
                next_step = step
                break
        
        if not next_step:
            # Try to load from recovery chat
            recovery = self.get_recovery_chat()
            for msg in recovery:
                if 'jailbreak' in msg.get('content', '').lower():
                    # Parse steps
                    pass
            return [{'message': 'All steps completed!', 'next_action': 'verify'}]
        
        guidance = [{
            'type': 'next_step',
            'step_number': next_step['step_number'],
            'description': next_step['description']
        }]
        
        relevant = self.search_thoughts('jailbreak', limit=3)
        for t in relevant:
            guidance.append({'type': 'thought', 'content': t['content'][:200]})
        
        traces = self.get_service_traces(limit=5)
        for t in traces:
            guidance.append({'type': 'trace', 'service': t.get('service'), 'action': t.get('action')})
        
        return guidance

    def get_jailbreak_roadmap(self):
        steps = self.get_jailbreak_steps()
        if steps:
            return steps
        
        # Load from recovery chat
        recovery = self.get_recovery_chat()
        roadmap = []
        step_num = 0
        for msg in recovery:
            content = msg.get('content', '')
            if 'jailbreak' in content.lower() or 'HUUP' in content:
                for line in content.split('\n'):
                    if 'Step' in line or 'step' in line:
                        step_num += 1
                        desc = line.replace('Step', '').strip()
                        roadmap.append({
                            'step_number': step_num,
                            'description': desc,
                            'status': 'pending'
                        })
        return roadmap

    def _save_to_db(self, table, data):
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            
            # Create table if not exists
            self._ensure_table(table, cursor)
            
            # Build columns and values
            columns = list(data.keys())
            values = [data[k] for k in columns if k != 'id']
            placeholders = ['?'] * len(values)
            
            if 'context' in data:
                data['context'] = json.dumps(data['context'])
            if 'options' in data:
                data['options'] = json.dumps(data['options'])
            
            cursor.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})", values)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to save to DB: {e}")

    def _update_db(self, table, data, key):
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            
            # Build SET clause
            sets = [f"{k}=?" for k in data.keys() if k != key]
            values = [data[k] for k in data.keys() if k != key]
            values.append(data[key])
            
            cursor.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE {key}=?", values)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to update DB: {e}")

    def _query_db(self, table, service=None, limit=100):
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            query = f"SELECT * FROM {table}"
            params = []
            
            if service:
                query += " WHERE service=?"
                params.append(service)
            
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                result = {}
                for i, col in enumerate(cursor.description):
                    result[col[0]] = row[i]
                results.append(result)
            
            conn.close()
            return results
        except Exception as e:
            print(f"Warning: Failed to query DB: {e}")
            return []

    def _query_peer_messages(self, conversation_id=None, limit=100):
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            query = "SELECT id, sender, body, created_at FROM peer_messages"
            params = []
            
            if conversation_id:
                query += " WHERE conversation_id=?"
                params.append(conversation_id)
            
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            messages = []
            for row in rows:
                messages.append({
                    'id': row[0],
                    'sender': row[1],
                    'content': row[2],
                    'created_at': row[3],
                    'source': 'peer_messages'
                })
            
            conn.close()
            return messages
        except Exception as e:
            print(f"Warning: Failed to query peer messages: {e}")
            return []

    def _ensure_table(self, table, cursor):
        tables = {
            'apex_thoughts': '''
                CREATE TABLE IF NOT EXISTS apex_thoughts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    agent TEXT NOT NULL,
                    thought_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    context TEXT,
                    parent_id INTEGER,
                    created_at TEXT DEFAULT (datetime("now"))
                )
            ''',
            'apex_decisions': '''
                CREATE TABLE IF NOT EXISTS apex_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    agent TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reasoning TEXT,
                    options TEXT,
                    chosen TEXT,
                    confidence REAL DEFAULT 0.0,
                    context TEXT,
                    created_at TEXT DEFAULT (datetime("now"))
                )
            ''',
            'apex_jailbreak_steps': '''
                CREATE TABLE IF NOT EXISTS apex_jailbreak_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step_number INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    file_path TEXT,
                    code TEXT,
                    status TEXT DEFAULT "pending",
                    result TEXT,
                    error TEXT,
                    created_at TEXT DEFAULT (datetime("now")),
                    completed_at TEXT
                )
            '''
        }
        
        if table in tables:
            cursor.execute(tables[table])


# Global instance
_logger = None

def get_thought_logger(agent="apex", conversation_id=None):
    global _logger
    if _logger is None:
        _logger = APEXThoughtLogger(agent, conversation_id)
    return _logger


# Convenience functions
def log_thought(content, thought_type="reasoning", context=None):
    return get_thought_logger().log_thought(content, thought_type, context)

def log_decision(decision, reasoning="", options=None, chosen=None, confidence=0.0, context=None):
    return get_thought_logger().log_decision(decision, reasoning, options, chosen, confidence, context)

def log_jailbreak_step(step_number, description, file_path=None, code=None):
    return get_thought_logger().log_jailbreak_step(step_number, description, file_path, code)

def get_thoughts(limit=100):
    return get_thought_logger().get_thoughts(limit)

def get_decisions(limit=50):
    return get_thought_logger().get_decisions(limit)

def get_jailbreak_steps():
    return get_thought_logger().get_jailbreak_steps()

def get_service_traces(service=None, limit=100):
    return get_thought_logger().get_service_traces(service, limit)

def get_recovery_chat(conversation_id=None, limit=100):
    return get_thought_logger().get_recovery_chat(conversation_id, limit)

def get_learning_summary():
    return get_thought_logger().get_learning_summary()

def search_thoughts(query, limit=50):
    return get_thought_logger().search_thoughts(query, limit)

def prove_worth():
    return get_thought_logger().prove_worth()

def guide_through_jailbreak():
    return get_thought_logger().guide_through_jailbreak()

def get_jailbreak_roadmap():
    return get_thought_logger().get_jailbreak_roadmap()


print("✅ APEX Thought Logger loaded - APEX can now read, record, and use logs for jailbreak!")
