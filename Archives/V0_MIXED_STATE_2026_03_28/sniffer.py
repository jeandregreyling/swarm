"""
sniffer.py — Seven's Swarm Inspector
Clean auditor for memory and sandpits.
"""

import os
import sys
from datetime import datetime
sys.path.insert(0, '/home/seven/swarm')

from database import get_connection, save_agent_memory
from sandpits import get_all_sandpit_files

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
    print(f"[Sniffer] Starting audit {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ...")
    
    # Audit memory pools
    conn = get_connection()
    tables = ["memory_llama", "memory_qwen", "memory_gemma", "memory_eight", "memory_nine", "memory_grok"]
    for table in tables:
        rows = conn.execute(f"SELECT id, subject, content FROM {table} ORDER BY id DESC LIMIT 20").fetchall()
        for row in rows:
            result = sniff(row['content'], table, "memory")
            if result != "PASS":
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
                print(f"[Sniffer] Sandpit {f['agent']}/{f['filename']} | {result}")
    except Exception as e:
        print(f"[Sniffer] Sandpit audit error: {e}")

    print("[Sniffer] Audit complete.")

if __name__ == '__main__':
    run_audit()