"""Meltdown detector — self-healing triage for the swarm.

Watches the four failure classes from the 2026-05-10 meltdown:
  1. systemd service restart loops
  2. ollama runner CPU runaway
  3. stale scheduled_tasks (next_run in the past)
  4. DEV/UAT background daemon leakage

Usage::

    from utils.meltdown_detector import check, heal
    report = check()
    if report["severity"] == "critical":
        heal(report)   # attempts safe auto-fixes

All probes are wrapped — a missing binary or permission error returns
False/0 rather than raising.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


def _run(cmd: List[str], timeout: float = 5.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )


def _load_average() -> float:
    try:
        with open("/proc/loadavg", "r") as f:
            return float(f.read().strip().split()[0])
    except Exception:
        return 0.0


def _ollama_runner_pids() -> List[Dict[str, Any]]:
    """Return list of {pid, cpu_percent, model} for ollama runners."""
    out: List[Dict[str, Any]] = []
    try:
        proc = _run(["ps", "aux"], timeout=3.0)
        for line in proc.stdout.splitlines():
            if "ollama" in line and "runner" in line:
                parts = line.split()
                if len(parts) >= 11:
                    try:
                        cpu = float(parts[2])
                    except ValueError:
                        cpu = 0.0
                    out.append({"pid": parts[1], "cpu_percent": cpu, "line": line})
    except Exception:
        pass
    return out


def _systemd_restart_counts() -> List[Dict[str, Any]]:
    """Return services with high restart counts."""
    out: List[Dict[str, Any]] = []
    try:
        proc = _run(
            ["systemctl", "show", "--property=Id,NRestarts", "swarm-discord.service"],
            timeout=5.0,
        )
        restarts = 0
        name = ""
        for line in proc.stdout.splitlines():
            if line.startswith("Id="):
                name = line[3:]
            elif line.startswith("NRestarts="):
                try:
                    restarts = int(line[10:])
                except ValueError:
                    restarts = 0
        if restarts > 5:
            out.append({"service": name, "restarts": restarts})
    except Exception:
        pass
    return out


def _stale_scheduled_tasks(conn=None) -> List[Dict[str, Any]]:
    """Return enabled tasks whose next_run is >24h in the past."""
    out: List[Dict[str, Any]] = []
    own = conn is None
    if own:
        try:
            from utils.db._connection import get_connection

            conn = get_connection()
        except Exception:
            return out
    try:
        cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT name, next_run, action_type FROM scheduled_tasks "
            "WHERE enabled=1 AND next_run <= ?",
            (cutoff,),
        ).fetchall()
        for r in rows:
            out.append(
                {"name": r["name"], "next_run": r["next_run"], "action_type": r["action_type"]}
            )
    except Exception:
        pass
    finally:
        if own:
            try:
                conn.close()
            except Exception:
                pass
    return out


def _dev_uat_background_threads() -> List[Dict[str, Any]]:
    """Check if DEV/UAT terminals have suspicious threads."""
    out: List[Dict[str, Any]] = []
    try:
        proc = _run(["ps", "aux", "-L"], timeout=3.0)
        for line in proc.stdout.splitlines():
            if "swarm-dev" in line or "swarm-uat" in line:
                if any(t in line for t in ("stuck-job-sweep", "agent20-council", "seven-continuous")):
                    out.append({"process": line})
    except Exception:
        pass
    return out


def check(*, load_threshold: float = 15.0, ollama_cpu_threshold: float = 200.0) -> Dict[str, Any]:
    """Run all meltdown probes and return a severity-classified report."""
    report: Dict[str, Any] = {
        "ok": True,
        "severity": "healthy",
        "load_avg": _load_average(),
        "findings": [],
    }
    findings: List[Dict[str, Any]] = []

    # 1. Load average
    load = report["load_avg"]
    if load > load_threshold:
        findings.append(
            {
                "kind": "high_load",
                "severity": "critical" if load > 25 else "warning",
                "detail": f"Load average {load:.1f} exceeds threshold {load_threshold}",
            }
        )

    # 2. Ollama runners
    runners = _ollama_runner_pids()
    for r in runners:
        if r["cpu_percent"] > ollama_cpu_threshold:
            findings.append(
                {
                    "kind": "ollama_runaway",
                    "severity": "critical",
                    "detail": f"Ollama runner PID {r['pid']} at {r['cpu_percent']:.0f}% CPU",
                }
            )

    # 3. systemd restart loops
    restarts = _systemd_restart_counts()
    for s in restarts:
        findings.append(
            {
                "kind": "restart_loop",
                "severity": "critical",
                "detail": f"{s['service']} restarted {s['restarts']} times",
            }
        )

    # 4. Stale scheduled tasks
    stale = _stale_scheduled_tasks()
    for t in stale:
        findings.append(
            {
                "kind": "stale_task",
                "severity": "warning",
                "detail": f"Task '{t['name']}' next_run={t['next_run']} is stale",
            }
        )

    # 5. DEV/UAT background leakage
    leakage = _dev_uat_background_threads()
    for _ in leakage:
        findings.append(
            {
                "kind": "dev_uat_leak",
                "severity": "warning",
                "detail": "DEV/UAT terminal has background daemon threads running",
            }
        )

    report["findings"] = findings
    if any(f["severity"] == "critical" for f in findings):
        report["severity"] = "critical"
        report["ok"] = False
    elif findings:
        report["severity"] = "warning"
        report["ok"] = False

    return report


def heal(report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Attempt safe auto-fixes for findings in *report*. Returns actions taken."""
    if report is None:
        report = check()

    actions: List[str] = []

    for finding in report.get("findings", []):
        kind = finding.get("kind")

        if kind == "ollama_runaway":
            # Stop ollama service — safest broad fix
            try:
                _run(["systemctl", "stop", "ollama"], timeout=10.0)
                actions.append("stopped ollama.service")
            except Exception as exc:
                actions.append(f"failed to stop ollama: {exc}")

        elif kind == "restart_loop":
            # Disable the offending service
            svc = finding.get("detail", "").split()[0]
            if svc:
                try:
                    _run(["systemctl", "stop", svc], timeout=10.0)
                    actions.append(f"stopped {svc}")
                except Exception as exc:
                    actions.append(f"failed to stop {svc}: {exc}")

        elif kind == "stale_task":
            # Disable the zombie task in DB
            name = finding.get("detail", "").split("'")[1] if "'" in finding.get("detail", "") else ""
            if name:
                try:
                    from utils.db._connection import get_connection

                    conn = get_connection()
                    try:
                        conn.execute(
                            "UPDATE scheduled_tasks SET enabled=0 WHERE name=?", (name,)
                        )
                        conn.commit()
                        actions.append(f"disabled stale scheduled task '{name}'")
                    finally:
                        conn.close()
                except Exception as exc:
                    actions.append(f"failed to disable task {name}: {exc}")

        elif kind == "dev_uat_leak":
            actions.append(
                "DEV/UAT background leakage detected — manual restart of swarm-terminal-dev/uat required"
            )

        elif kind == "high_load":
            actions.append(
                f"High load ({report.get('load_avg', '?')}) — review other findings for root cause"
            )

    return {
        "ok": len(actions) == 0 or all("failed" not in a for a in actions),
        "actions": actions,
        "original_severity": report.get("severity", "unknown"),
    }
