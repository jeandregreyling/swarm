"""Dashboard API Blueprint - Unified Chat View

Provides a unified API endpoint for fetching messages from all sources
(User, APEX, Mistral Vibe) for the dashboard view.
"""

from flask import Blueprint, jsonify
import sqlite3
import json
import os
from datetime import datetime

from utils.db._connection import get_connection

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


def get_db_path(db_name):
    """Get full path to database file"""
    swarm_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(swarm_root, db_name)


@dashboard_bp.route('/messages/unified')
def get_unified_messages():
    """Get unified messages from all sources"""
    messages = []
    
    try:
        # Fetch from swarm_memory.db
        conn = get_connection()
        cursor = conn.cursor()
        
        # Messages table
        cursor.execute("""
            SELECT id, from_agent, to_agent, content, created_at, message_type 
            FROM messages 
            WHERE from_agent IN ('user', 'apex', 'mistral-vibe', 'ghost')
            ORDER BY id DESC
            LIMIT 200
        """)
        
        for row in cursor.fetchall():
            msg_id, sender, recipient, content, created_at, msg_type = row
            messages.append({
                'id': f"msg-{msg_id}",
                'sender': sender,
                'recipient': recipient,
                'content': content,
                'timestamp': created_at,
                'type': msg_type,
                'source': 'swarm_memory.messages'
            })
        
        # Peer messages table
        cursor.execute("""
            SELECT id, sender, body, created_at 
            FROM peer_messages 
            WHERE sender IN ('user', 'apex', 'mistral-vibe', 'ghost')
            ORDER BY id DESC
            LIMIT 200
        """)
        
        for row in cursor.fetchall():
            msg_id, sender, body, created_at = row
            messages.append({
                'id': f"peer-{msg_id}",
                'sender': sender,
                'recipient': None,
                'content': body,
                'timestamp': created_at,
                'type': 'peer',
                'source': 'swarm_memory.peer_messages'
            })
        
        conn.close()
        
        # Fetch from mind.db
        mind_db_path = get_db_path('mind.db')
        if os.path.exists(mind_db_path):
            conn_mind = sqlite3.connect(mind_db_path)
            cursor_mind = conn_mind.cursor()
            
            cursor_mind.execute("""
                SELECT id, conversation_id, agent, user_message, reply, created_at 
                FROM exchanges 
                WHERE agent IN ('apex', 'mistral-vibe') OR agent LIKE '%gemma%' 
                ORDER BY id DESC
                LIMIT 100
            """)
            
            for row in cursor_mind.fetchall():
                msg_id, conv_id, agent, user_msg, reply, created_at = row
                if user_msg:
                    messages.append({
                        'id': f"mind-{msg_id}-user",
                        'sender': 'user',
                        'recipient': agent,
                        'content': user_msg,
                        'timestamp': created_at,
                        'type': 'user_message',
                        'source': 'mind.exchanges'
                    })
                if reply:
                    messages.append({
                        'id': f"mind-{msg_id}-reply",
                        'sender': agent,
                        'recipient': 'user',
                        'content': reply,
                        'timestamp': created_at,
                        'type': 'reply',
                        'source': 'mind.exchanges'
                    })
            
            conn_mind.close()
        
        # Deduplicate by content + timestamp
        seen = set()
        unique_messages = []
        for msg in messages:
            key = f"{msg.get('sender', '')}-{msg.get('content', '')[:80]}-{msg.get('timestamp', '')}"
            if key not in seen:
                seen.add(key)
                unique_messages.append(msg)
        
        # Sort by timestamp (newest first)
        def parse_ts(ts):
            if not ts:
                return 0
            try:
                if isinstance(ts, str):
                    if 'T' in ts or '+' in ts or ts.endswith('Z'):
                        return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                    elif ts.isdigit():
                        return float(ts)
                    else:
                        return datetime.fromisoformat(ts).timestamp()
                return float(ts)
            except:
                return 0
        
        unique_messages.sort(key=lambda x: parse_ts(x.get('timestamp', 0)), reverse=True)
        
        # Calculate stats
        stats = {'total': len(unique_messages)}
        for sender in ['user', 'apex', 'mistral-vibe']:
            count = sum(1 for m in unique_messages if m.get('sender', '').lower() == sender)
            stats[sender] = count
        
        return jsonify({
            'ok': True,
            'messages': unique_messages[:100],  # Limit to 100 most recent
            'stats': stats,
            'fetched_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'ok': False,
            'error': str(e),
            'messages': [],
            'stats': {}
        })


@dashboard_bp.route('/fetch_messages')
def fetch_messages_legacy():
    """Legacy endpoint for fetch_messages.py compatibility"""
    return get_unified_messages()
