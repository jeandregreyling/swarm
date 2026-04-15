"""
fridays/file_agent.py — Seven's Swarm (RL-018)
═══════════════════════════════════════════════════════════════════════════════
File read/write with sandpit access level enforcement.

Trust levels:
  Level 0 — Read any file in sandpits/ or explicitly allowed paths (always)
  Level 1 — Write to own sandpit only
  Level 2 — Write to shared sandpit
  Level 3 — Write to real system paths (Gemma must approve first)

All writes logged to sandpit_log. Real-path writes also logged to ghost_circle.

Sandpit structure:
  /home/seven/swarm/sandpits/
  ├── shared/       — all agents read + write
  ├── gemma/
  ├── llama/
  ├── qwen/
  └── eight/
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import hashlib
import logging
from system_clock import get_timestamp
from pathlib import Path
from file_versioning import track_file_change

sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.file_agent')

SWARM_ROOT    = Path(os.environ.get('SWARM_ROOT', str(Path(__file__).parent.parent)))
SANDPIT_ROOT  = SWARM_ROOT / 'sandpits'

AGENT_SANDPITS = [
    'gemma', 'llama', 'mistral', 'eight', 'librarian', 'duck', 'sniffles',
    'nine', 'ten', 'eleven', 'twelve', 'qwen', 'thirteen', 'ghost', 'shared'
]


def _ensure_sandpits():
    """Create sandpit directories if they don't exist."""
    for name in AGENT_SANDPITS:
        (SANDPIT_ROOT / name).mkdir(parents=True, exist_ok=True)


def _content_hash(content):
    return hashlib.sha256(content.encode('utf-8', errors='replace')).hexdigest()[:16]


def _log_action(agent, action, path, content_hash='', trust_level=0):
    try:
        from database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT INTO sandpit_log (agent, operation, path, size_bytes, status, reason, created_at)
               VALUES (?, ?, ?, ?, 'ok', ?, ?)""",
            (agent, action, str(path)[:500], len(content_hash), f'trust_level={trust_level}', get_timestamp())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[File Agent] sandpit_log write failed: {e}')


def _log_ghost_circle(agent, action, path, note=''):
    try:
        from database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT INTO ghost_circle (entry_type, source, content, severity, created_at)
               VALUES ('file_action', ?, ?, 'info', ?)""",
            (agent, f'{action}: {path} | {note}', get_timestamp())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[File Agent] ghost_circle write failed: {e}')


# ── Level 0: Read ─────────────────────────────────────────────────────────────

def read_sandpit(agent, filename):
    """
    Level 0 — Read a file from an agent's own sandpit or shared.
    Always allowed, always logged.
    Returns (ok, content) tuple.
    """
    _ensure_sandpits()
    agent_key = agent.lower()
    if agent_key not in AGENT_SANDPITS:
        agent_key = 'shared'

    path = SANDPIT_ROOT / agent_key / filename
    if not path.exists():
        return False, f'File not found: {filename}'

    try:
        content = path.read_text(encoding='utf-8', errors='replace')
        _log_action(agent, 'read', path, _content_hash(content), trust_level=0)
        logger.info(f'[File Agent] {agent} read: {path}')
        return True, content
    except Exception as e:
        return False, f'Error reading file: {str(e)}'


def read_shared(filename):
    """Level 0 — Read from shared sandpit. All agents can read shared. Returns (ok, content) tuple."""
    _ensure_sandpits()
    path = SANDPIT_ROOT / 'shared' / filename
    if not path.exists():
        return False, f'File not found: {filename}'
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
        _log_action('shared', 'read', path, _content_hash(content), trust_level=0)
        return True, content
    except Exception as e:
        return False, f'Error reading file: {str(e)}'


def list_sandpit(agent):
    """Level 0 — List files in an agent's sandpit."""
    _ensure_sandpits()
    agent_key = agent.lower()
    if agent_key not in AGENT_SANDPITS:
        agent_key = 'shared'
    path = SANDPIT_ROOT / agent_key
    return [f.name for f in path.iterdir() if f.is_file()]


# ── Level 1: Write own sandpit ────────────────────────────────────────────────

def write_sandpit(agent, filename, content):
    """
    Level 1 — Write to agent's own sandpit directory.
    Allowed for all agents. Logged.
    Filenames are sanitised — no path traversal.
    """
    _ensure_sandpits()
    agent_key = agent.lower()
    if agent_key not in AGENT_SANDPITS:
        return False, 'Unknown agent'

    # Sanitise filename — no subdirectory traversal
    safe_name = Path(filename).name
    if not safe_name or safe_name.startswith('.'):
        return False, 'Invalid filename'

    path = SANDPIT_ROOT / agent_key / safe_name
    
    # Capture previous content if it exists
    previous = None
    if path.exists():
        previous = path.read_text(encoding='utf-8', errors='replace')
        
    path.write_text(content, encoding='utf-8')
    track_file_change(str(path), agent, 'write', content_before=previous, content_after=content)
    
    _log_action(agent, 'write_sandpit', path, _content_hash(content), trust_level=1)
    logger.info(f'[File Agent] {agent} wrote: {path}')
    return True, str(path)


# ── Level 2: Write shared sandpit ────────────────────────────────────────────

def write_shared(agent, filename, content):
    """
    Level 2 — Write to shared sandpit. All agents can write here.
    Collaboration layer — agents leave notes/data for each other.
    """
    _ensure_sandpits()
    safe_name = Path(filename).name
    if not safe_name or safe_name.startswith('.'):
        return False, 'Invalid filename'

    path = SANDPIT_ROOT / 'shared' / safe_name
    
    # Capture previous content if it exists
    previous = None
    if path.exists():
        previous = path.read_text(encoding='utf-8', errors='replace')
    
    path.write_text(content, encoding='utf-8')
    track_file_change(str(path), agent, 'write_shared', content_before=previous, content_after=content)
    _log_action(agent, 'write_shared', path, _content_hash(content), trust_level=2)
    logger.info(f'[File Agent] {agent} wrote shared: {path}')
    return True, str(path)


# ── Level 3: Write real paths (Gemma approval required) ──────────────────────

def write_real_path(agent, path_str, content, gemma_approved=False):
    """
    Level 3 — Write to real system paths.
    Requires explicit Gemma approval (gemma_approved=True).
    Blocked entirely from EFI partition.
    Logged to both sandpit_log and ghost_circle.
    """
    path = Path(path_str).resolve()

    # Hard block — never touch EFI
    if str(path).startswith('/boot/efi') or 'nvme0n1p1' in str(path):
        _log_action(agent, 'write_BLOCKED_EFI', path, '', trust_level=3)
        logger.error(f'[File Agent] BLOCKED: EFI write attempt by {agent}: {path}')
        return False, 'BLOCKED: EFI partition is off limits.'

    if not gemma_approved:
        return False, 'Level 3 write requires Gemma approval. Not yet implemented for autonomous action.'

    # Capture previous content if it exists
    previous = None
    if path.exists():
        try:
            previous = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            previous = '[binary or unreadable]'
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    track_file_change(str(path), agent, 'write_real', content_before=previous, content_after=content)
    _log_action(agent, 'write_real', path, _content_hash(content), trust_level=3)
    _log_ghost_circle(agent, 'write_real', str(path), f'{len(content)} chars')
    logger.warning(f'[File Agent] {agent} wrote real path (approved): {path}')
    return True, str(path)


# ── Utility ───────────────────────────────────────────────────────────────────

def get_sandpit_summary(agent):
    """Return a short summary of what's in an agent's sandpit — for context injection."""
    _ensure_sandpits()
    agent_key = agent.lower()
    if agent_key not in AGENT_SANDPITS:
        return ''
    path = SANDPIT_ROOT / agent_key
    files = [f for f in path.iterdir() if f.is_file()]
    if not files:
        return ''
    lines = [f'[{agent} sandpit — {len(files)} file(s)]']
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        lines.append(f'  {f.name} ({f.stat().st_size} bytes)')
    return '\n'.join(lines)


def test():
    print('\n[File Agent] Test...')
    _ensure_sandpits()
    ok, path = write_sandpit('llama', 'test_note.txt', 'LLaMA was here.')
    print(f'Write: {ok} → {path}')
    ok, content = read_sandpit('llama', 'test_note.txt')
    print(f'Read: {ok} → {content}')
    print('✓ file_agent.py works.')


if __name__ == '__main__':
    test()
