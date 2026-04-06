"""
sandpits.py — Fridays / Seven's Swarm
Clean version with trust ladder and proposal system.
"""

import os
import sys
sys.path.insert(0, '/home/seven/swarm')
from database import get_connection
from datetime import datetime

SANDPIT_BASE = '/home/seven/swarm/sandpits'
SHARED_DIR = os.path.join(SANDPIT_BASE, 'shared')
PROPOSALS_DIR = os.path.join(SHARED_DIR, 'proposals')

AGENTS = ['gemma', 'llama', 'mistral', 'eight', 'librarian', 'sniffles', 'nine', 'grok']

# Trust ladder
_DEFAULT_TRUST = {
    'gemma': 2,
    'llama': 2,
    'mistral': 2,
    'eight': 2,
    'librarian': 1,
    'sniffles': 0,
    'nine': 3,
    'grok': 3
}

def _agent_dir(agent):
    return os.path.join(SANDPIT_BASE, agent.lower())

def _safe_path(base_dir, filename):
    path = os.path.normpath(os.path.join(base_dir, filename))
    if not path.startswith(os.path.normpath(base_dir)):
        raise ValueError(f'Path traversal attempt blocked: {filename}')
    return path

def _log(agent, operation, path, size_bytes=0, status='ok', reason=''):
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO sandpit_log (agent, operation, path, size_bytes, status, reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent, operation, path, size_bytes, status, reason)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Sandpit Log Error] {e}")

def get_trust_level(agent):
    return _DEFAULT_TRUST.get(agent.lower(), 1)

# Read operations (Level 0 — always allowed)
def read_file(agent, filename, requester=None):
    reader = requester or agent
    path = _safe_path(_agent_dir(agent), filename)
    if not os.path.exists(path):
        _log(reader, 'read', path, status='not_found')
        return None
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    _log(reader, 'read', path, size_bytes=len(content))
    return content

def read_shared(filename, requester='unknown'):
    path = _safe_path(SHARED_DIR, filename)
    if not os.path.exists(path):
        _log(requester, 'read_shared', path, status='not_found')
        return None
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    _log(requester, 'read_shared', path, size_bytes=len(content))
    return content

def list_proposals():
    if not os.path.isdir(PROPOSALS_DIR):
        return []
    proposals = []
    for fname in sorted(os.listdir(PROPOSALS_DIR)):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(PROPOSALS_DIR, fname)
        if os.path.isfile(fpath):
            stat = os.stat(fpath)
            agent = fname.split('_')[0] if '_' in fname else 'unknown'
            proposals.append({
                'filename': fname,
                'agent': agent,
                'path': fpath,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
            })
    return proposals

def read_proposal(filename):
    if '..' in filename or '/' in filename:
        return None
    path = os.path.join(PROPOSALS_DIR, filename)
    if not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def delete_proposal(filename):
    if '..' in filename or '/' in filename:
        return False
    path = os.path.join(PROPOSALS_DIR, filename)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False

# Write operations
def write_file(agent, filename, content):
    trust = get_trust_level(agent)
    if trust < 1:
        _log(agent, 'write', filename, status='denied')
        return False, f'trust level {trust} — write denied'
    d = _agent_dir(agent)
    os.makedirs(d, exist_ok=True)
    path = _safe_path(d, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    _log(agent, 'write', path, size_bytes=len(content))
    return True, path

def write_proposal(agent, content):
    trust = get_trust_level(agent)
    if trust < 2:
        _log(agent, 'write_proposal', 'proposals/', status='denied')
        return False, f'trust level {trust} — proposal write requires Level 2'
    os.makedirs(PROPOSALS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{agent.lower()}_{timestamp}.md'
    path = os.path.join(PROPOSALS_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    _log(agent, 'write_proposal', path, size_bytes=len(content))
    return True, path

# Sniffles audit interface - clean single version
def get_all_sandpit_files():
    results = []
    for agent in AGENTS + ['shared']:
        base = SHARED_DIR if agent == 'shared' else _agent_dir(agent)
        if not os.path.isdir(base):
            continue
        for fname in os.listdir(base):
            fpath = os.path.join(base, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    results.append({
                        'agent': agent,
                        'filename': fname,
                        'path': fpath,
                        'content': content
                    })
                except Exception as e:
                    _log("sniffles", "audit_read_error", fpath, status="error", reason=str(e))
    return results

# Ensure proposals dir exists
os.makedirs(PROPOSALS_DIR, exist_ok=True)

def get_sandpit_stats():
    """Return stats about active sandpits indexed by agent."""
    stats = {}
    for agent in AGENTS:
        work_dir = os.path.join(SANDPIT_BASE, agent, 'work')
        files = 0
        total_bytes = 0
        if os.path.isdir(work_dir):
            try:
                for f in os.listdir(work_dir):
                    filepath = os.path.join(work_dir, f)
                    if os.path.isfile(filepath):
                        files += 1
                        try:
                            total_bytes += os.path.getsize(filepath)
                        except (OSError, FileNotFoundError):
                            pass
            except (OSError, FileNotFoundError):
                pass  # Skip if directory is inaccessible
        stats[agent] = {'files': files, 'bytes': total_bytes}
    stats['_total'] = {'files': sum(s['files'] for s in stats.values()), 'bytes': sum(s['bytes'] for s in stats.values())}
    return stats

def get_recent_log(limit=50):
    """Return recent sandpit activity log."""
    return []  # Stub: replaced by real audit log later

if __name__ == '__main__':
    print("Sandpits module loaded cleanly.")
    print("Grok trust level:", get_trust_level("grok"))