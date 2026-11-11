#!/usr/bin/env python3
"""
Unified Message Fetcher for Mistral Vibe Dashboard
Fetches messages from all data sources and returns unified JSON
"""

import sys
import sqlite3
import json
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, '/mnt/archive/projects/swarm')

from utils.db._connection import get_connection


def get_db_path(db_name):
    """Get full path to database file"""
    swarm_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(swarm_root, db_name)


def fetch_swarm_memory_messages():
    """Fetch messages from swarm_memory.db"""
    messages = []
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get messages from messages table
        cursor.execute("""
            SELECT id, from_agent, to_agent, content, created_at, message_type 
            FROM messages 
            WHERE from_agent IN ('user', 'apex', 'mistral-vibe', 'ghost')
            ORDER BY id DESC
            LIMIT 100
        """)
        
        for row in cursor.fetchall():
            msg_id, sender, recipient, content, created_at, msg_type = row
            messages.append({
                'id': msg_id,
                'sender': sender,
                'recipient': recipient,
                'content': content,
                'timestamp': created_at,
                'type': msg_type,
                'source': 'swarm_memory.messages'
            })
        
        # Get peer messages
        cursor.execute("""
            SELECT id, sender, body, created_at 
            FROM peer_messages 
            WHERE sender IN ('user', 'apex', 'mistral-vibe', 'ghost')
            ORDER BY id DESC
            LIMIT 100
        """)
        
        for row in cursor.fetchall():
            msg_id, sender, body, created_at = row
            messages.append({
                'id': msg_id,
                'sender': sender,
                'recipient': None,
                'content': body,
                'timestamp': created_at,
                'type': 'peer',
                'source': 'swarm_memory.peer_messages'
            })
        
        conn.close()
    except Exception as e:
        print(f"Error reading swarm_memory.db: {e}")
    
    return messages


def fetch_mind_db_messages():
    """Fetch messages from mind.db"""
    messages = []
    try:
        mind_db_path = get_db_path('mind.db')
        if not os.path.exists(mind_db_path):
            return messages
        
        conn = sqlite3.connect(mind_db_path)
        cursor = conn.cursor()
        
        # Get exchanges
        cursor.execute("""
            SELECT id, conversation_id, agent, user_message, reply, created_at 
            FROM exchanges 
            WHERE agent IN ('apex', 'mistral-vibe') OR agent LIKE '%gemma%' 
            ORDER BY id DESC
            LIMIT 100
        """)
        
        for row in cursor.fetchall():
            msg_id, conv_id, agent, user_msg, reply, created_at = row
            # Both user message and reply
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
        
        conn.close()
    except Exception as e:
        print(f"Error reading mind.db: {e}")
    
    return messages


def fetch_recovery_chat_messages():
    """Fetch messages from recovery chat files"""
    messages = []
    try:
        chat_dir = get_db_path('runtime/chat-continuity')
        if not os.path.exists(chat_dir):
            return messages
        
        import glob
        for json_file in glob.glob(os.path.join(chat_dir, '*.json')):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    chat_messages = data.get('messages', [])
                    
                    for msg in chat_messages:
                        sender = msg.get('sender', 'unknown')
                        content = msg.get('content', '')
                        timestamp = msg.get('created_at', '')
                        
                        if sender.lower() in ['user', 'apex', 'mistral-vibe', 'ghost']:
                            messages.append({
                                'id': f"recovery-{data.get('id', 'unknown')}-{msg.get('id', 0)}",
                                'sender': sender,
                                'recipient': msg.get('to_agent'),
                                'content': content,
                                'timestamp': timestamp,
                                'type': 'recovery',
                                'source': f'chat-continuity/{os.path.basename(json_file)}'
                            })
            except Exception as e:
                print(f"Error reading {json_file}: {e}")
    except Exception as e:
        print(f"Error reading recovery chat: {e}")
    
    return messages


def deduplicate_messages(messages):
    """Remove duplicate messages"""
    seen = set()
    unique_messages = []
    
    for msg in messages:
        # Create a unique key based on content and timestamp
        key = f"{msg.get('sender', '')}-{msg.get('content', '')[:50]}-{msg.get('timestamp', '')}"
        if key not in seen:
            seen.add(key)
            unique_messages.append(msg)
    
    return unique_messages


def sort_messages(messages):
    """Sort messages by timestamp"""
    def parse_timestamp(ts):
        if not ts:
            return 0
        try:
            if isinstance(ts, str):
                # Try to parse various timestamp formats
                if ts.endswith('Z') or '+' in ts:
                    return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                elif ts.isdigit():
                    return float(ts)
                else:
                    return datetime.fromisoformat(ts).timestamp()
            return float(ts)
        except:
            return 0
    
    return sorted(messages, key=lambda x: parse_timestamp(x.get('timestamp', 0)), reverse=True)


def calculate_stats(messages):
    """Calculate message statistics"""
    stats = {'total': len(messages)}
    
    for sender in ['user', 'apex', 'mistral-vibe']:
        count = sum(1 for m in messages if m.get('sender', '').lower() == sender)
        stats[sender] = count
    
    return stats


def main():
    """Main function - fetch all messages and return JSON"""
    # Collect messages from all sources
    all_messages = []
    
    # Add separator for clarity
    print("🔍 Fetching messages from all sources...")
    
    # Fetch from each source
    swarm_messages = fetch_swarm_memory_messages()
    print(f"  ✓ swarm_memory.db: {len(swarm_messages)} messages")
    all_messages.extend(swarm_messages)
    
    mind_messages = fetch_mind_db_messages()
    print(f"  ✓ mind.db: {len(mind_messages)} messages")
    all_messages.extend(mind_messages)
    
    recovery_messages = fetch_recovery_chat_messages()
    print(f"  ✓ Recovery chat: {len(recovery_messages)} messages")
    all_messages.extend(recovery_messages)
    
    # Deduplicate and sort
    unique_messages = deduplicate_messages(all_messages)
    sorted_messages = sort_messages(unique_messages)
    
    # Calculate stats
    stats = calculate_stats(sorted_messages)
    
    # Return JSON
    result = {
        'ok': True,
        'messages': sorted_messages,
        'stats': stats,
        'sources': {
            'swarm_memory': len(swarm_messages),
            'mind': len(mind_messages),
            'recovery': len(recovery_messages)
        },
        'fetched_at': datetime.now().isoformat()
    }
    
    # Pretty print for debugging
    print(json.dumps(result, indent=2))
    
    return result


if __name__ == '__main__':
    # When run directly, output JSON
    result = main()
    print(json.dumps(result, indent=2))
