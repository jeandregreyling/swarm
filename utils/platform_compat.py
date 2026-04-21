"""
utils/platform_compat.py — Cross-platform guard helpers.

Import this wherever Linux-specific tools (systemctl, sudo, tailscale) are used
to get clean Windows-safe fallbacks without crashing.
"""
import sys
import os

IS_WINDOWS = sys.platform == 'win32' or os.environ.get('SWARM_PLATFORM') == 'windows'


def run_safe(cmd, **kwargs):
    """
    subprocess.run() wrapper that returns a dummy result on Windows
    for commands that don't exist there (systemctl, sudo, tailscale, etc.).
    """
    import subprocess
    linux_only = ('systemctl', 'sudo', 'tailscale', 'journalctl', 'service')
    if IS_WINDOWS and cmd and cmd[0] in linux_only:
        class _R:
            stdout     = 'windows'
            stderr     = ''
            returncode = 1
        return _R()
    return subprocess.run(cmd, **kwargs)
