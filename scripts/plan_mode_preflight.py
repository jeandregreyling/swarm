#!/usr/bin/env python3
"""Plan-mode preflight checks for June 2026 execution.

Checks:
- Swap capacity and current pressure (target: >=32 GiB total swap)
- NTFS LLM drive mount/writability (/mnt/llm)
- Local backup freshness check (PACKET-10A verify recent)
- API reachability (health/system/git status)
- Optional chunking smoke test via /api/docs/recursive-chunk

Writes JSON report to runtime/reports and prints a compact summary.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Tuple

SWAP_MIN_BYTES = 32 * 1024 * 1024 * 1024
SWARM_ROOT = Path(os.environ.get("SWARM_ROOT", Path(__file__).resolve().parents[1]))
REPORT_DIR = SWARM_ROOT / "runtime" / "reports"


def _read_meminfo_swap() -> Dict[str, int]:
    total_kb = 0
    free_kb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("SwapTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("SwapFree:"):
                    free_kb = int(line.split()[1])
    except Exception:
        pass
    used_kb = max(0, total_kb - free_kb)
    return {
        "swap_total_bytes": total_kb * 1024,
        "swap_free_bytes": free_kb * 1024,
        "swap_used_bytes": used_kb * 1024,
    }


def _swapon_show_total() -> Dict[str, object]:
    # util-linux variations differ across hosts; try conservative invocations.
    candidates = [
        ["swapon", "--show", "--bytes", "--noheadings"],
        ["swapon", "--show", "--noheadings"],
    ]
    errors = []
    for cmd in candidates:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
        except Exception as exc:
            errors.append(str(exc))
            continue
        if r.returncode != 0:
            errors.append((r.stderr or "").strip()[:200])
            continue

        entries = []
        total = 0
        for raw in (r.stdout or "").splitlines():
            parts = raw.split()
            if len(parts) < 3:
                continue
            name = parts[0]
            # Common layouts:
            # NAME SIZE USED PRIO
            # NAME TYPE SIZE USED PRIO
            if len(parts) >= 5 and parts[1].isalpha():
                size_s, used_s = parts[2], parts[3]
            else:
                size_s, used_s = parts[1], parts[2]
            try:
                size_i = int(float(size_s))
                used_i = int(float(used_s))
            except Exception:
                continue
            total += size_i
            entries.append({"name": name, "size": size_i, "used": used_i})

        return {
            "ok": True,
            "returncode": 0,
            "stderr": "",
            "entries": entries,
            "total_bytes": total,
        }

    return {
        "ok": False,
        "returncode": 1,
        "stderr": " | ".join([e for e in errors if e])[:240],
        "entries": [],
        "total_bytes": 0,
    }


def _check_ntfs(path: str) -> Dict[str, object]:
    p = Path(path)
    mounted = False
    try:
        m = subprocess.run(["mountpoint", "-q", str(p)], check=False, timeout=5)
        mounted = m.returncode == 0
    except Exception:
        mounted = False

    writable = p.exists() and os.access(p, os.W_OK)
    fs_type = "unknown"
    try:
        s = subprocess.run(["stat", "-f", "-c", "%T", str(p)], capture_output=True, text=True, timeout=5, check=False)
        if s.returncode == 0:
            fs_type = (s.stdout or "").strip() or "unknown"
    except Exception:
        pass

    return {
        "path": str(p),
        "exists": p.exists(),
        "mounted": mounted,
        "writable": bool(writable),
        "fs_type": fs_type,
        "ok": bool(p.exists() and mounted and writable),
    }


def _api_get(url: str, timeout: int = 8) -> Tuple[bool, int, Dict[str, object]]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body[:400]}
            return True, resp.getcode(), parsed
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")[:400]
        return False, exc.code, {"error": payload}
    except Exception as exc:
        return False, 0, {"error": str(exc)}


def _api_post_json(url: str, data: Dict[str, object], timeout: int = 10) -> Tuple[bool, int, Dict[str, object]]:
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body[:400]}
            return True, resp.getcode(), parsed
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")[:400]
        return False, exc.code, {"error": payload}
    except Exception as exc:
        return False, 0, {"error": str(exc)}


def _backup_recent_check() -> Dict[str, object]:
    cmd = [
        str(SWARM_ROOT / ".venv" / "bin" / "python"),
        str(SWARM_ROOT / "scripts" / "backup_verify.py"),
        "recent",
    ]
    try:
        env = os.environ.copy()
        env["SWARM_ROOT"] = str(SWARM_ROOT)
        r = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30, env=env)
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout": (r.stdout or "").strip(),
            "stderr": (r.stderr or "").strip(),
        }
    except Exception as exc:
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": str(exc)}


def run_preflight(api_base: str, run_chunking_smoke: bool) -> Dict[str, object]:
    meminfo = _read_meminfo_swap()
    swapon = _swapon_show_total()
    ntfs_candidates = ["/mnt/llm", "/mnt/f"]
    ntfs_checks = [_check_ntfs(p) for p in ntfs_candidates]
    ntfs_ok = any(item.get("ok") for item in ntfs_checks)
    backup_recent = _backup_recent_check()

    health_ok, health_code, health_body = _api_get(f"{api_base}/api/health")
    system_ok, system_code, system_body = _api_get(f"{api_base}/api/system")
    git_ok, git_code, git_body = _api_get(f"{api_base}/api/git/status?check_remote=1")
    git_remote_ok = True
    if isinstance(git_body, dict):
        remote_check = git_body.get("remote_check") or {}
        if isinstance(remote_check, dict) and remote_check.get("checked"):
            git_remote_ok = bool(remote_check.get("ok"))

    chunking = {"enabled": run_chunking_smoke, "ok": None, "status": 0, "body": {}}
    if run_chunking_smoke:
        chunk_ok, chunk_code, chunk_body = _api_post_json(
            f"{api_base}/api/docs/recursive-chunk",
            {"query": "quintum", "path": "core/chunk", "limit": 2},
            timeout=15,
        )
        chunking = {
            "enabled": True,
            "ok": bool(chunk_ok and chunk_body.get("ok") is True),
            "status": chunk_code,
            "body": chunk_body,
        }

    swap_total = max(int(swapon.get("total_bytes") or 0), int(meminfo.get("swap_total_bytes") or 0))
    swap_meets_target = swap_total >= SWAP_MIN_BYTES

    gates = {
        "swap_target": swap_meets_target,
        "ntfs_llm_drive": ntfs_ok,
        "backup_recent": bool(backup_recent.get("ok")),
        "api_health": bool(health_ok and health_code == 200),
        "api_system": bool(system_ok and system_code == 200),
        "api_git_status": bool(git_ok and git_code == 200),
        "git_remote_auth": bool(git_ok and git_code == 200 and git_remote_ok),
        "chunking_smoke": (chunking.get("ok") is True) if run_chunking_smoke else None,
    }

    return {
        "timestamp": int(time.time()),
        "api_base": api_base,
        "gates": gates,
        "swap": {
            "min_bytes": SWAP_MIN_BYTES,
            "swapon": swapon,
            "meminfo": meminfo,
            "effective_total_bytes": swap_total,
            "target_met": swap_meets_target,
        },
        "ntfs": {
            "ok": ntfs_ok,
            "candidates": ntfs_checks,
        },
        "backup_recent": backup_recent,
        "api": {
            "health": {"ok": health_ok, "status": health_code, "body": health_body},
            "system": {"ok": system_ok, "status": system_code, "body": system_body},
            "git_status": {"ok": git_ok, "status": git_code, "body": git_body},
        },
        "chunking_smoke": chunking,
    }


def _write_report(report: Dict[str, object]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["timestamp"]))
    out = REPORT_DIR / f"plan_mode_preflight_{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default="http://127.0.0.1:5050")
    ap.add_argument("--chunking-smoke", action="store_true", help="Run /api/docs/recursive-chunk smoke check")
    args = ap.parse_args()

    report = run_preflight(args.api_base.rstrip("/"), args.chunking_smoke)
    out_file = _write_report(report)

    gates = report["gates"]
    failed = [name for name, ok in gates.items() if ok is False]
    print(json.dumps({
        "ok": len(failed) == 0,
        "failed_gates": failed,
        "report_file": str(out_file),
        "gates": gates,
    }, indent=2))
    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
