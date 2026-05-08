# DEPRECATED: This file is no longer maintained or used.
# The active skills registry and logic is in fridays/skills.py.
# Do not edit or use this file. All new skill code must go in fridays/skills.py.
"""
skills.py — Seven's Swarm Skills Framework
Expanded for useful build phase.
"""

import os
import subprocess
from sandpits import list_proposals, get_all_sandpit_files
from database import get_digest_stats

ALLOWED_COMMANDS = {
    "df": "df -h",
    "free": "free -h",
    "top": "top -b -n 1 | head -15",
    "ps": "ps aux --sort=-%cpu | head -10",
    "ls": "ls -la ~/swarm",
    "sandpits": "ls -la ~/swarm/sandpits",
    "proposals": "list_proposals",
    "digest": "get_digest_stats",
    "sandpit_files": "get_all_sandpit_files",
    "status": "echo 'Use run free or run top for system status'",
    "ollama": "ollama list",
}

def run_skill(skill_name, args=None):
    if skill_name not in ALLOWED_COMMANDS:
        return f"Unknown skill: {skill_name}. Allowed: {list(ALLOWED_COMMANDS.keys())}"

    cmd = ALLOWED_COMMANDS[skill_name]

    try:
        if cmd == "list_proposals":
            props = list_proposals()
            return f"Found {len(props)} proposals:\n" + "\n".join([f"  - {p.get('filename')} by {p.get('agent')}" for p in props])
        elif cmd == "get_digest_stats":
            stats = get_digest_stats()
            return f"Daily Digest:\n  Opened: {stats['opened']}\n  Closed: {stats['closed']}\n  Open: {stats['open']}\n  Proposals: {len(list_proposals())}"
        elif cmd == "get_all_sandpit_files":
            files = get_all_sandpit_files()
            return f"{len(files)} sandpit files found."
        else:
            # 2026-05-02 (S-A539F21C70) — drop shell=True. cmd comes from
            # ALLOWED_COMMANDS allowlist (literal strings, no user input), so
            # this was already safe, but shlex.split + shell=False removes the
            # whole class of risk and silences the audit grep.
            import shlex as _shlex
            result = subprocess.check_output(_shlex.split(cmd), text=True, timeout=10)
            return result.strip()
    except Exception as e:
        return f"Skill error: {e}"

if __name__ == '__main__':
    print("Skills framework loaded.")
    print("Available skills:", list(ALLOWED_COMMANDS.keys()))