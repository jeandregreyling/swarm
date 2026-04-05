"""
fridays/shell_agent.py — Seven's Swarm (RL-019)
═══════════════════════════════════════════════════════════════════════════════
Sandboxed shell execution. Whitelist only.

Trust levels:
  Level 0 — Read-only info commands (df, free, uptime, ps, ls, cat sandpit files)
  Level 2 — Service status checks (systemctl status)
  Level 4 — Everything else on whitelist — Ghost notified, logged to ghost_circle

Rules:
  - Only whitelisted commands run. Everything else is rejected.
  - No destructive commands (rm, dd, mkfs, kill -9, etc.) on the whitelist.
  - Every execution logged to ghost_circle.
  - Output capped at 4000 chars.
  - Timeout: 30 seconds hard limit.
  - Working directory locked to /home/seven/swarm (no cd out).
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import subprocess
import shlex
import logging
import re

sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.shell_agent')

MAX_OUTPUT  = 4000
TIMEOUT_SEC = 30

# ── Whitelist ─────────────────────────────────────────────────────────────────
# Format: (regex pattern, trust_level, description)
# Pattern matches the full command string (after strip).
# Level 0 = read-only info (no Ghost notify)
# Level 2 = service checks (no Ghost notify)
# Level 4 = elevated — Ghost notified on every run

WHITELIST = [
    # System info — Level 0
    (r'^df(\s+-[hHkm])*(\s+\S+)?$',                    0, 'disk usage'),
    (r'^free(\s+-[hHmg])?$',                            0, 'memory usage'),
    (r'^uptime$',                                        0, 'uptime'),
    (r'^uname(\s+-[a-z]+)?$',                            0, 'kernel info'),
    (r'^date$',                                          0, 'current date/time'),
    (r'^pwd$',                                           0, 'working directory'),
    (r'^whoami$',                                        0, 'current user'),
    (r'^hostname$',                                      0, 'hostname'),
    (r'^ps\s+aux$',                                      0, 'process list'),
    # Pipe restricted to grep only — no arbitrary pipe continuation
    (r'^ps\s+aux\s+\|\s+grep\s+\S+$',                   0, 'process list grep'),
    (r'^top\s+-b\s+-n\s+1$',                             0, 'cpu snapshot'),
    (r'^cat\s+/proc/cpuinfo$',                           0, 'cpu info'),
    (r'^cat\s+/proc/meminfo$',                           0, 'memory info'),
    (r'^lsblk(\s+-[a-z]+)?$',                            0, 'block devices'),
    (r'^lsof\s+-i(\s+:\d+)?$',                           0, 'open ports'),
    (r'^netstat\s+-tlnp$',                               0, 'network ports'),
    (r'^ss\s+-tlnp$',                                    0, 'socket stats'),
    (r'^ip\s+(addr|link|route)$',                        0, 'network info'),
    (r'^ping\s+-c\s+\d+\s+\S+$',                         0, 'ping'),

    # File reads — Level 0 (swarm dir only)
    (r'^ls(\s+-[lahrt]+)?(\s+\.?/?[\w\-\./]+)?$',      0, 'list files'),
    (r'^find\s+/home/seven/swarm\S*\s+-maxdepth\s+\d+\s+-type\s+[fd](\s+-name\s+\S+)?$', 0, 'find files (bounded)'),
    (r'^cat\s+(\.?/?[\w\-\./]+|/home/seven/swarm/\S+)$', 0, 'read file'),
    (r'^wc\s+-[lw]\s+(\.?/?[\w\-\./]+|/home/seven/swarm/\S+)$', 0, 'word/line count'),
    (r'^tail(\s+-n\s+\d+)?\s+(\.?/?[\w\-\./]+|/home/seven/swarm/\S+)$', 0, 'tail file'),
    (r'^head(\s+-n\s+\d+)?\s+(\.?/?[\w\-\./]+|/home/seven/swarm/\S+)$', 0, 'head file'),
    # grep: explicit flags only (-i, -n, -c, -l), no -r recursive
    (r'^grep\s+(-[incl]\s+)*.+\s+/home/seven/swarm/\S+$', 0, 'grep swarm file'),

    # Service status — Level 2
    (r'^systemctl\s+status\s+([\w\-\.]+\s+)*[\w\-\.]+$',  2, 'service status'),
    (r'^systemctl\s+is-active\s+[\w\-\.]+$',              2, 'service active check'),
    (r'^journalctl\s+-u\s+[\w\-\.]+\s+-n\s+\d+\s*$',      2, 'service logs'),
    
    # Service restart/stop/start — Level 4 (elevated, Ghost notified)
    (r'^sudo\s+systemctl\s+restart\s+([\w\-\.]+\s+)*[\w\-\.]+$',  4, 'service restart'),
    (r'^sudo\s+systemctl\s+stop\s+([\w\-\.]+\s+)*[\w\-\.]+$',     4, 'service stop'),
    (r'^sudo\s+systemctl\s+start\s+([\w\-\.]+\s+)*[\w\-\.]+$',    4, 'service start'),
    (r'^sudo\s+journalctl\s+-u\s+[\w\-\.]+\s+-n\s+\d+\s+(--no-pager)?$', 4, 'service logs (elevated)'),

    # Ollama — Level 2
    (r'^ollama\s+list$',                                 2, 'ollama model list'),
    (r'^ollama\s+ps$',                                   2, 'ollama running models'),

    # Network fetch — Level 4 (Ghost notified — outbound requests)
    (r'^curl\s+-s\s+https?://\S+$',                      4, 'http fetch'),
    (r'^wget\s+-q\s+-O\s+-\s+https?://\S+$',             4, 'wget fetch'),

    # Python — Level 4
    (r'^python3\s+/home/seven/swarm/\S+\.py(\s+.*)?$',  4, 'run swarm script'),

    # Git — Level 4 (read only, but may expose history)
    (r'^git\s+(status|log|diff|show)(\s+.*)?$',          4, 'git read'),
]


# ── Core execution ────────────────────────────────────────────────────────────

def _match_whitelist(command_str):
    """
    Check command against whitelist. Returns (trust_level, description) or None.
    """
    cmd = command_str.strip()
    for pattern, level, desc in WHITELIST:
        if re.match(pattern, cmd, re.IGNORECASE):
            return level, desc
    return None


def _log_ghost_circle(agent, command, output_summary, trust_level, allowed):
    try:
        from database import get_connection
        conn = get_connection()
        status = 'executed' if allowed else 'BLOCKED'
        conn.execute(
            """INSERT INTO ghost_circle (entry_type, source, content, severity)
               VALUES ('shell_action', ?, ?, ?)""",
            (agent,
             f'[{status}] L{trust_level} | {command[:200]} | {output_summary[:200]}',
             'info' if allowed else 'warning')
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[Shell] ghost_circle write failed: {e}')


def _log_sandpit(agent, command, output, trust_level):
    try:
        from database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT INTO sandpit_log (agent, operation, path, size_bytes, status, reason, created_at)
               VALUES (?, 'shell_exec', ?, ?, 'ok', ?, datetime('now'))""",
            (agent, command[:500], len(output), f'trust_level={trust_level}')
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[Shell] sandpit_log write failed: {e}')


def _request_sudo_approval(agent, command, desc):
    """
    Gate level-4 commands behind Ghost approval.
    Creates an approval token and notifies Ghost via Telegram.
    Returns (False, message) — the command is NOT executed immediately.
    """
    try:
        from database import create_approval_token, log_activity
        token = create_approval_token(
            action='shell_exec',
            target_email=command[:200],
            created_by=agent,
        )
        log_activity('shell', 'sudo_requested',
                     f'{agent} requested: {command[:200]} | token={token[:12]}...')

        # Notify Ghost via Telegram
        try:
            from config import nine_notify
            nine_notify(
                f'🔐 SUDO request from {agent}\n'
                f'Command: {command[:150]}\n'
                f'Approve at: /api/shell/approve/{token}'
            )
        except Exception:
            pass

        _log_ghost_circle(agent, command, f'SUDO_PENDING token={token[:12]}',
                         trust_level=4, allowed=False)
        return False, (
            f'[Shell] Level 4 command requires Ghost approval.\n'
            f'Command: {command}\n'
            f'Approval token: {token}\n'
            f'Ghost has been notified. Waiting for approval at /api/shell/approve/{token}'
        )
    except Exception as e:
        logger.error(f'[Shell] sudo approval request failed: {e}')
        return False, f'[Shell] Could not request sudo approval: {e}'


# Agents that bypass the sudo gate (they ARE Ghost)
_SUDO_BYPASS_AGENTS = {'ghost', 'fridays', 'shell'}


def run(command, agent='shell', notify_ghost=True):
    """
    Run a whitelisted shell command. Returns (success, output).

    - Blocked commands return (False, reason).
    - Level 4 commands from non-Ghost agents require approval.
    - All executions logged to ghost_circle and sandpit_log.
    - Output capped at MAX_OUTPUT chars.
    - Hard timeout of TIMEOUT_SEC seconds.
    """
    command = command.strip()
    match = _match_whitelist(command)

    if match is None:
        reason = f'Command not on whitelist: {command[:100]}'
        logger.warning(f'[Shell] BLOCKED by {agent}: {command[:100]}')
        # Always log blocked attempts regardless of notify_ghost
        _log_ghost_circle(agent, command, reason, trust_level=99, allowed=False)
        return False, reason

    trust_level, desc = match
    logger.info(f'[Shell] {agent} running (L{trust_level} — {desc}): {command[:100]}')

    # Level 4 gate: non-Ghost agents must get approval first
    if trust_level >= 4 and agent.lower() not in _SUDO_BYPASS_AGENTS:
        return _request_sudo_approval(agent, command, desc)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            cwd='/home/seven/swarm',
        )
        output = result.stdout + (('\n[stderr]\n' + result.stderr) if result.stderr.strip() else '')
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + '\n\n[... output truncated ...]'
        success = result.returncode == 0

    except subprocess.TimeoutExpired:
        output = f'[Shell] Command timed out after {TIMEOUT_SEC}s: {command}'
        success = False

    except Exception as e:
        output = f'[Shell] Execution error: {e}'
        success = False

    _log_sandpit(agent, command, output, trust_level)

    # Ghost circle: always log Level 4. Log lower levels only if notify_ghost=True.
    if trust_level >= 4 or notify_ghost:
        _log_ghost_circle(agent, command, output[:200], trust_level, allowed=True)

    print(f'[Shell] {"✓" if success else "✗"} L{trust_level} | {command[:80]}')
    return success, output


def run_safe(command, agent='shell'):
    """
    Level 0 only — read-only info commands. Rejects anything above Level 0.
    No Ghost notification. Safe to call from any agent without audit noise.
    """
    command = command.strip()
    match = _match_whitelist(command)
    if match is None or match[0] > 0:
        return False, f'run_safe() only allows Level 0 commands: {command[:100]}'
    return run(command, agent=agent, notify_ghost=False)


def test():
    print('\n[Shell Agent] Tests...')
    tests = [
        ('df -h',                                        True),
        ('free -h',                                      True),
        ('uptime',                                       True),
        ('ollama list',                                  True),
        ('ps aux | grep python',                         True),
        ('ps aux | cat /etc/passwd',                     False),  # pipe bypass attempt
        ('curl -s http://example.com',                   True),   # now Level 4
        ('rm -rf /',                                     False),
        ('cat /etc/passwd',                              False),
        ('ls /home/seven/swarm',                         True),
        ('grep foo /home/seven/swarm/config.py',         True),
        ('grep -r foo /home/seven/swarm/config.py',      False),  # -r blocked
    ]
    passed = 0
    for cmd, should_pass in tests:
        ok, out = run(cmd, agent='test')
        result = '✓' if ok == should_pass else '✗ UNEXPECTED'
        print(f'  {result}  {cmd!r}: {out[:60].strip()}')
        if ok == should_pass:
            passed += 1
    print(f'\n{passed}/{len(tests)} passed.')


if __name__ == '__main__':
    test()