"""
logging_bridge.py — Seven's Swarm Unified Logging
═══════════════════════════════════════════════════════════════════════════════
Central logging that writes to:
1. Database (activity_log table) — queryable history
2. Git commits (auto-staged changes) — audit trail
3. Fridays dashboard — real-time visibility

Every agent action → logged here → tracked forever
═══════════════════════════════════════════════════════════════════════════════
"""

import os as _os
import sys
import subprocess
from datetime import datetime
from pathlib import Path as _Path

_SWARM_ROOT = _os.environ.get('SWARM_ROOT',
              str(_Path(__file__).resolve().parent.parent.parent))
from system_clock import get_timestamp

sys.path.insert(0, '/home/seven/swarm')

def log_action(service, event, detail='', severity='info'):
    """
    Log an action across all three systems.
    
    Args:
        service: 'listener', 'orchestrator', 'terminal', 'duck', 'eight', etc.
        event: 'email_received', 'agent_loaded', 'ticket_closed', etc.
        detail: human-readable detail (max 500 chars)
        severity: 'info' | 'warning' | 'error' | 'critical'
    """
    from database import log_activity
    
    # 1. Log to database (queryable, persistent)
    try:
        log_activity(service, event, detail, severity)
    except Exception as e:
        print(f'[LoggingBridge] Warning: DB log failed: {e}')
    
    # 2. Log to console (immediate feedback)
    ts = get_timestamp()
    severity_marker = {
        'info': '📝',
        'warning': '⚠️ ',
        'error': '❌',
        'critical': '🚨'
    }.get(severity, 'ℹ️')
    
    print(f'{severity_marker} [{ts}] {service} — {event} | {detail[:100]}')


def log_ticket_lifecycle(ticket_number, stage, agent='', detail=''):
    """Log a ticket through its lifecycle with full traceability."""
    stages = {
        'created': 'Ticket created',
        'intake': 'Librarian intake',
        'read': 'Gemma read receipt',
        'stage1': 'LLaMA fast response',
        'stage2': 'Qwen + Gemma full',
        'debate': 'Debate triggered',
        'eight': 'Eight SAP specialist',
        'duck': 'Duck sanity check',
        'closed': 'Librarian closed',
    }
    
    msg = stages.get(stage, stage)
    if agent:
        msg += f' — {agent}'
    if detail:
        msg += f' | {detail}'
    
    log_action('ticket', ticket_number, msg, severity='info')


def log_agent_thinking(agent_name, action, duration_ms=0):
    """Log when an agent starts/finishes thinking."""
    detail = f'{action}'
    if duration_ms > 0:
        detail += f' ({duration_ms}ms)'
    log_action('agent', agent_name, detail)


def batch_commit(message):
    """
    Batch commit to git when a major milestone happens.
    Called after ticket closes, after debate finishes, etc.
    """
    try:
        ts = get_timestamp()
        full_msg = f'[{ts}] {message}'
        
        # Stage all changes
        subprocess.run(
            ['git', 'add', '-A'],
            cwd=_SWARM_ROOT,
            capture_output=True,
            timeout=10
        )
        
        # Check if there's anything to commit
        status = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=_SWARM_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if status.stdout.strip():
            subprocess.run(
                ['git', 'commit', '-m', full_msg],
                cwd=_SWARM_ROOT,
                capture_output=True,
                timeout=10
            )
            print(f'✓ [Git] Committed: {full_msg}')
            return True
        return False
            
    except Exception as e:
        print(f'[LoggingBridge] Git commit failed: {e}')
        return False


if __name__ == '__main__':
    print("[LoggingBridge] Module loaded")
    log_action('system', 'logging_bridge_start', 'Unified logging initialized')
