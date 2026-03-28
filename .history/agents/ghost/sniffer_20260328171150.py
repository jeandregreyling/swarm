"""
sniffer.py — Seven's Swarm Inspector
Clean auditor for memory and sandpits.
"""

import os
import sys
from datetime import datetime
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/lib/system')

from database import get_connection, save_agent_memory
from sandpits import get_all_sandpit_files
from logging_bridge import log_action, batch_commit

def sniff(content, agent, entry_type):
    """Simple sniff for obvious issues."""
    if not content or len(content) < 10:
        return "PASS"
    if "Murray River is the longest" in content and "Australia" in content:
        return "FLAG - Incorrect river length (Murray is not the longest in Australia)"
    if ("I estimate" in content or "I think" in content) and agent != "Ghost":
        return "FLAG - Self-serving or speculative language"
    return "PASS"

def run_audit():
    log_action('sniffer', 'audit_start', 'Starting audit cycle', 'info')
    print(f"[Sniffer] Starting audit {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ...")
    
    flags_found = 0
    # Audit memory pools
    conn = get_connection()
    tables = ["memory_llama", "memory_qwen", "memory_gemma", "memory_eight", "memory_nine", "memory_grok"]
    for table in tables:
        rows = conn.execute(f"SELECT id, subject, content FROM {table} ORDER BY id DESC LIMIT 20").fetchall()
        for row in rows:
            result = sniff(row['content'], table, "memory")
            if result != "PASS":
                flags_found += 1
                log_action('sniffer', f'flag:{table}', result, 'warning')
                print(f"[Sniffer] {table} | {row['subject'][:50]} | {result}")
    conn.close()

    # Audit sandpits
    try:
        sandpit_files = get_all_sandpit_files()
        print(f"[Sniffer] Auditing {len(sandpit_files)} sandpit file(s)...")
        for f in sandpit_files:
            if len(f["content"]) < 20:
                continue
            result = sniff(f["content"], f["agent"], "sandpit")
            if result != "PASS":
                flags_found += 1
                log_action('sniffer', f'flag:sandpit', result, 'warning')
                print(f"[Sniffer] Sandpit {f['agent']}/{f['filename']} | {result}")
    except Exception as e:
        log_action('sniffer', 'audit_error', str(e), 'error')
        print(f"[Sniffer] Sandpit audit error: {e}")

    log_action('sniffer', 'audit_complete', f'Found {flags_found} flag(s)', 'info')
    batch_commit(f'[Sniffer] Audit complete: {flags_found} flag(s)')
    print("[Sniffer] Audit complete.")

if __name__ == '__main__':
    run_audit()