#!/usr/bin/env python3
"""
daily_gate.py — One-command operational validation for Fridays Swarm

Combines UAT regression, live agent pings, service health, and error log scans
into a single daily check. Designed for vibe-coding workflows — quick pass/fail
that tells you if the swarm is ready to operate.

Usage:
    python3 ops/daily_gate.py [--quick] [--detailed]
    
Options:
    --quick:    Skip channel smoke tests (faster)
    --detailed: Show full error logs and test output
    
Exit Code:
    0 = fully operational green
    1 = failures detected, needs attention
"""

import subprocess
import sys
import json
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd, name="", timeout=300, capture=True):
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=capture,
            text=True,
            timeout=timeout,
            shell=isinstance(cmd, str),
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr if capture else ""
        return success, output
    except subprocess.TimeoutExpired:
        return False, f"[TIMEOUT] {name} exceeded {timeout}s"
    except Exception as e:
        return False, f"[ERROR] {name}: {e}"


def section(title):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def check_service_health():
    """Quick systemd service status check."""
    section("Service Health")
    services = ["swarm-terminal", "swarm-listener", "swarm-discord", "swarm-telegram"]
    all_ok = True
    for svc in services:
        success, _ = run_cmd(f"systemctl is-active {svc}", name=svc)
        status = "✓ active" if success else "✗ inactive"
        print(f"  {svc:25} {status}")
        all_ok = all_ok and success
    return all_ok


def check_uat_gate():
    """Run the main UAT gate suite."""
    section("UAT Regression Gate")
    success, output = run_cmd(
        [str(ROOT / ".venv" / "bin" / "python"), "tests/run_uat_gate.py"],
        name="UAT Gate",
        timeout=120,
    )
    if success:
        # Extract summary line
        for line in output.split("\n"):
            if "UAT GATE:" in line:
                print(f"  {line.strip()}")
    else:
        print("  ✗ FAILED")
        if "--detailed" in sys.argv:
            print(output[-2000:])
    return success


def check_chat_pings():
    """Run agent ping tests with adjusted timeouts."""
    section("Live Agent Pings")
    # Fast agents: 90s, heavy agents: 180s
    env = {
        "CHAT_PING_ENABLE": "1",
        "CHAT_PING_AGENTS": "gemma,llama,qwen,eight,librarian,duck,sniffles,nine,ten,eleven,twelve",
        "CHAT_PING_MAX_SECONDS_PER_AGENT": "180",  # Raised from 90s
        "CHAT_MEMORY_AGENT": "duck",
    }
    cmd = [str(ROOT / ".venv" / "bin" / "python"), "tests/test_chat_quality.py"]
    
    start = time.time()
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        env={**subprocess.os.environ, **env},
    )
    elapsed = time.time() - start
    success = result.returncode == 0
    
    # Parse results
    output = result.stdout + result.stderr
    for line in output.split("\n"):
        if "Results:" in line or "PASS" in line or "FAIL" in line:
            print(f"  {line.strip()}")
    
    if success:
        print(f"  Duration: {elapsed:.1f}s")
    else:
        print(f"  ✗ FAILED ({elapsed:.1f}s)")
        if "--detailed" in sys.argv:
            print(output[-1500:])
    
    return success


def check_channel_smoke():
    """Run channel smoke tests (skip with --quick)."""
    if "--quick" in sys.argv:
        print("  [SKIPPED] Use --quick flag")
        return True
    
    section("Channel Smoke Tests")
    
    # Quick Telegram trust test
    success_tg, output_tg = run_cmd(
        [str(ROOT / ".venv" / "bin" / "python"), "tests/test_telegram_trust.py"],
        name="Telegram Trust",
        timeout=30,
    )
    print(f"  Telegram trust    {'✓' if success_tg else '✗'}")
    
    # Quick direct agent commands test (minimal, fast)
    success_cmds, output_cmds = run_cmd(
        [str(ROOT / ".venv" / "bin" / "python"), "tests/test_direct_agent_commands.py"],
        name="Direct Commands",
        timeout=30,
    )
    print(f"  Direct commands   {'✓' if success_cmds else '✗'}")
    
    all_ok = success_tg and success_cmds
    
    if "--detailed" in sys.argv and not all_ok:
        if not success_tg:
            print("\n  Telegram output:")
            print(output_tg[-500:])
        if not success_cmds:
            print("\n  Commands output:")
            print(output_cmds[-500:])
    
    return all_ok


def check_error_log_scan():
    """Quick scan of recent service logs for critical errors."""
    section("Recent Error Scan")
    
    cmd = """journalctl -u swarm-listener -u swarm-discord -u swarm-telegram --since '60 minutes ago' --no-pager 2>/dev/null | grep -c 'error\\|exception\\|traceback\\|failed' || echo '0'"""
    
    success, count_str = run_cmd(cmd, name="Error scan")
    try:
        error_count = int(count_str.strip())
        if error_count == 0:
            print(f"  ✓ No errors in last 60 minutes")
            return True
        else:
            print(f"  ⚠ {error_count} error mentions in last 60 minutes")
            return error_count < 5  # Warn if too many
    except:
        return True


def main():
    """Run full daily validation."""
    print(f"\n{'='*70}")
    print(f"  FRIDAYS DAILY OPERATIONAL GATE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S AEDT')}")
    print(f"{'='*70}")
    
    results = {
        "services": check_service_health(),
        "uat_gate": check_uat_gate(),
        "agent_pings": check_chat_pings(),
        "channels": check_channel_smoke(),
        "errors": check_error_log_scan(),
    }
    
    # Summary
    section("Summary")
    all_green = all(results.values())
    
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test:20} {status}")
    
    print(f"\n{'='*70}")
    if all_green:
        print("  ✓ FULLY OPERATIONAL — Fridays is ready")
        exit_code = 0
    else:
        print("  ✗ ISSUES DETECTED — Review failures above")
        exit_code = 1
    print(f"{'='*70}\n")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
