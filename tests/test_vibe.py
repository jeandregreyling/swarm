#!/usr/bin/env python3
"""
Vibe Test — targeted checks for everything a user would notice.

Run:  python3 tests/test_vibe.py [--env prod|dev|uat] [--verbose]

Each check is one thing. If it fails, fix that one thing.
This is not a unit test suite — it's a live system health check
from the user's perspective.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ── Config ──────────────────────────────────────────────────

PORTS = {"prod": 5050, "uat": 5052, "dev": 5054}

# ── Result tracking ─────────────────────────────────────────

@dataclass
class Check:
    id: str
    area: str
    description: str
    passed: bool = False
    detail: str = ""
    skipped: bool = False

RESULTS: list[Check] = []
VERBOSE = False


def check(id: str, area: str, description: str):
    """Decorator to register a vibe check."""
    def decorator(fn):
        def wrapper(base_url: str):
            c = Check(id=id, area=area, description=description)
            try:
                result = fn(base_url)
                if result is True:
                    c.passed = True
                elif isinstance(result, str):
                    c.passed = False
                    c.detail = result
                else:
                    c.passed = False
                    c.detail = str(result)
            except Exception as e:
                c.passed = False
                c.detail = f"Exception: {e}"
            RESULTS.append(c)
            mark = "✅" if c.passed else "❌"
            line = f"  {mark} [{c.id}] {c.description}"
            if not c.passed and c.detail:
                line += f" — {c.detail}"
            if VERBOSE or not c.passed:
                print(line)
            elif c.passed:
                print(line)
        return wrapper
    return decorator


def get(base_url: str, path: str, timeout: int = 10) -> tuple[int, str]:
    """GET request, returns (status_code, body)."""
    try:
        req = Request(f"{base_url}{path}")
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace") if e.fp else ""
    except URLError as e:
        return 0, str(e)


def get_json(base_url: str, path: str, timeout: int = 10):
    """GET request, returns parsed JSON or None."""
    code, body = get(base_url, path, timeout)
    if code == 200:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None
    return None


# ═══════════════════════════════════════════════════════════
# CHECKS — grouped by what the user sees
# ═══════════════════════════════════════════════════════════

# ── 1. System Basics ────────────────────────────────────────

@check("SYS-01", "System", "Home page loads (200)")
def sys_home(base_url):
    code, _ = get(base_url, "/")
    return True if code == 200 else f"HTTP {code}"

@check("SYS-02", "System", "Health endpoint responds")
def sys_health(base_url):
    code, body = get(base_url, "/api/health")
    return True if code == 200 else f"HTTP {code}"

@check("SYS-03", "System", "System metrics available")
def sys_metrics(base_url):
    data = get_json(base_url, "/api/metrics")
    return True if data else "No metrics data"

@check("SYS-04", "System", "Monitor stats available")
def sys_monitor(base_url):
    data = get_json(base_url, "/api/monitor/stats")
    return True if data else "No monitor stats"

@check("SYS-05", "System", "System time endpoint works")
def sys_time(base_url):
    data = get_json(base_url, "/api/system/time")
    return True if data else "No time data"


# ── 2. Agent System ─────────────────────────────────────────

@check("AGT-01", "Agents", "Agent roster returns agents")
def agt_roster(base_url):
    data = get_json(base_url, "/api/agents")
    if not data:
        return "No response"
    agents = data if isinstance(data, list) else data.get("agents", [])
    if len(agents) < 10:
        return f"Only {len(agents)} agents (expected 14+)"
    return True

@check("AGT-02", "Agents", "Agent status endpoint works")
def agt_status(base_url):
    data = get_json(base_url, "/api/agents/status")
    return True if data else "No status data"

@check("AGT-03", "Agents", "Circuit breaker state available")
def agt_circuit(base_url):
    data = get_json(base_url, "/api/circuit-breaker")
    return True if data is not None else "No circuit breaker data"

@check("AGT-04", "Agents", "Agent capabilities matrix loads")
def agt_caps(base_url):
    data = get_json(base_url, "/api/agents/capability-matrix")
    return True if data else "No capability matrix"

@check("AGT-05", "Agents", "Idle agents endpoint works")
def agt_idle(base_url):
    data = get_json(base_url, "/api/agents/idle")
    return True if data is not None else "No idle data"

@check("AGT-06", "Agents", "Gemma awareness API returns real data")
def agt_awareness(base_url):
    data = get_json(base_url, "/api/agents/gemma/self")
    if not data:
        return "No response from /api/agents/gemma/self"
    # Should have meaningful fields, not just empty stubs
    if isinstance(data, dict):
        has_name = bool(data.get("name") or data.get("agent"))
        return True if has_name else f"Response missing name field: {list(data.keys())[:5]}"
    return f"Unexpected type: {type(data).__name__}"


# ── 3. Chat ─────────────────────────────────────────────────

@check("CHT-01", "Chat", "Conversations list loads")
def cht_convos(base_url):
    data = get_json(base_url, "/api/conversations")
    return True if data is not None else "No conversations data"

@check("CHT-02", "Chat", "Chat jobs status endpoint works")
def cht_jobs(base_url):
    data = get_json(base_url, "/api/chat/jobs/status")
    return True if data is not None else "No jobs status"

@check("CHT-03", "Chat", "Queue depth endpoint works")
def cht_queue(base_url):
    data = get_json(base_url, "/api/queue/depth")
    return True if data is not None else "No queue data"


# ── 4. Knowledge & Library ──────────────────────────────────

@check("LIB-01", "Library", "Docs listing returns items")
def lib_docs(base_url):
    data = get_json(base_url, "/api/docs")
    if not data:
        return "No docs data"
    items = data if isinstance(data, list) else data.get("docs", data.get("files", []))
    return True if items else "Empty docs list"

@check("LIB-02", "Library", "Knowledge base loads")
def lib_kb(base_url):
    data = get_json(base_url, "/api/kb")
    return True if data is not None else "No KB data"

@check("LIB-03", "Library", "Library categories available")
def lib_cats(base_url):
    data = get_json(base_url, "/api/library/categories")
    return True if data is not None else "No categories"

@check("LIB-04", "Library", "Bugs markdown loads")
def lib_bugs(base_url):
    code, body = get(base_url, "/api/bugs-md")
    if code != 200:
        return f"HTTP {code}"
    return True if len(body) > 50 else "Response too short — likely not reading the file"

@check("LIB-05", "Library", "Testing markdown loads")
def lib_testing(base_url):
    code, body = get(base_url, "/api/testing-md")
    if code != 200:
        return f"HTTP {code}"
    return True if len(body) > 50 else "Response too short"

@check("LIB-06", "Library", "Project markdown loads")
def lib_project(base_url):
    code, body = get(base_url, "/api/project-md")
    if code != 200:
        return f"HTTP {code}"
    return True if len(body) > 100 else "Response too short"


# ── 5. Workspace & Files ────────────────────────────────────

@check("FIL-01", "Files", "Workspace dir listing works")
def fil_dir(base_url):
    data = get_json(base_url, "/api/workspace/dir")
    if not data:
        return "No workspace data"
    return True

@check("FIL-02", "Files", "Workspace search works")
def fil_search(base_url):
    code, body = get(base_url, "/api/workspace/search?q=def&path=.")
    return True if code == 200 else f"HTTP {code}"


# ── 6. Git & Version Control ───────────────────────────────

@check("GIT-01", "Git", "Git status endpoint works")
def git_status(base_url):
    data = get_json(base_url, "/api/git/status")
    return True if data is not None else "No git status"

@check("GIT-02", "Git", "Git environments listing works")
def git_envs(base_url):
    data = get_json(base_url, "/api/git/environments")
    return True if data is not None else "No environments data"

@check("GIT-03", "Git", "Timeline loads")
def git_timeline(base_url):
    data = get_json(base_url, "/api/timeline")
    return True if data is not None else "No timeline data"

@check("GIT-04", "Git", "Time sessions available")
def git_sessions(base_url):
    data = get_json(base_url, "/api/time/sessions")
    return True if data is not None else "No sessions data"


# ── 7. Email ────────────────────────────────────────────────

@check("EML-01", "Email", "Email inbox endpoint responds")
def eml_inbox(base_url):
    code, _ = get(base_url, "/api/email/inbox")
    # 200 = inbox loaded, 401/403 = auth needed but endpoint works, 500 = broken
    return True if code in (200, 401, 403) else f"HTTP {code}"

@check("EML-02", "Email", "Email stats endpoint responds")
def eml_stats(base_url):
    code, _ = get(base_url, "/api/email/stats")
    return True if code in (200, 401, 403) else f"HTTP {code}"


# ── 8. Governance & Proposals ───────────────────────────────

@check("GOV-01", "Governance", "ALM status loads")
def gov_alm(base_url):
    data = get_json(base_url, "/api/alm/status")
    return True if data is not None else "No ALM status"

@check("GOV-02", "Governance", "Tickets endpoint works")
def gov_tickets(base_url):
    data = get_json(base_url, "/api/tickets")
    return True if data is not None else "No tickets data"

@check("GOV-03", "Governance", "Decisions endpoint works")
def gov_decisions(base_url):
    data = get_json(base_url, "/api/decisions")
    return True if data is not None else "No decisions data"


# ── 9. Weather & Clocks ────────────────────────────────────

@check("WEA-01", "Weather", "Weather endpoint returns data")
def wea_data(base_url):
    data = get_json(base_url, "/api/weather")
    if not data:
        return "No weather data"
    # Check it has actual weather, not just an empty response
    if isinstance(data, dict):
        has_content = any(v for v in data.values() if v)
        return True if has_content else "Weather response is empty"
    return True


# ── 10. VPN / Tailscale ────────────────────────────────────

@check("VPN-01", "VPN", "Tailscale status endpoint responds")
def vpn_status(base_url):
    code, _ = get(base_url, "/api/vpn/status")
    # May fail if tailscale not installed, but endpoint should respond
    return True if code in (200, 500) else f"HTTP {code}"

@check("VPN-02", "VPN", "Tailscale data endpoint responds")
def vpn_data(base_url):
    code, _ = get(base_url, "/api/tailscale")
    return True if code in (200, 500) else f"HTTP {code}"


# ── 11. Skills & Patterns ──────────────────────────────────

@check("SKL-01", "Skills", "Skills list loads")
def skl_list(base_url):
    data = get_json(base_url, "/api/skills/available")
    return True if data is not None else "No skills data"

@check("SKL-02", "Skills", "Patterns summary loads")
def skl_patterns(base_url):
    data = get_json(base_url, "/api/patterns/summary")
    return True if data is not None else "No patterns data"


# ── 12. Local AI / Ollama ───────────────────────────────────

@check("OLL-01", "Ollama", "Ollama models endpoint responds")
def oll_models(base_url):
    data = get_json(base_url, "/api/ollama/models")
    return True if data is not None else "No Ollama models data"

@check("OLL-02", "Ollama", "Available models endpoint works")
def oll_available(base_url):
    data = get_json(base_url, "/api/localai/available-models")
    return True if data is not None else "No available models"

@check("OLL-03", "Ollama", "LocalAI status endpoint works")
def oll_status(base_url):
    code, _ = get(base_url, "/api/localai/status")
    return True if code == 200 else f"HTTP {code}"


# ── 13. Audit & Self-Improvement ───────────────────────────

@check("AUD-01", "Audit", "Audit latest endpoint works")
def aud_latest(base_url):
    data = get_json(base_url, "/api/audit/latest")
    return True if data is not None else "No audit data"

@check("AUD-02", "Audit", "Activity feed loads")
def aud_activity(base_url):
    data = get_json(base_url, "/api/activity")
    return True if data is not None else "No activity data"


# ── 14. Sandpits ────────────────────────────────────────────

@check("SND-01", "Sandpits", "Sandpits listing works")
def snd_list(base_url):
    data = get_json(base_url, "/api/sandpits")
    return True if data is not None else "No sandpits data"


# ── 15. Personality & Diary ─────────────────────────────────

@check("PER-01", "Personality", "Gemma personality loads")
def per_gemma(base_url):
    code, body = get(base_url, "/api/agents/gemma/personality")
    if code != 200:
        return f"HTTP {code}"
    return True if len(body) > 10 else "Personality response too short"

@check("PER-02", "Personality", "Gemma diary loads")
def per_diary(base_url):
    code, _ = get(base_url, "/api/agents/gemma/diary")
    # 200 = has entries, 404 = no diary yet (acceptable)
    return True if code in (200, 404) else f"HTTP {code}"


# ═══════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════

ALL_CHECKS = [
    # System
    sys_home, sys_health, sys_metrics, sys_monitor, sys_time,
    # Agents
    agt_roster, agt_status, agt_circuit, agt_caps, agt_idle, agt_awareness,
    # Chat
    cht_convos, cht_jobs, cht_queue,
    # Library
    lib_docs, lib_kb, lib_cats, lib_bugs, lib_testing, lib_project,
    # Files
    fil_dir, fil_search,
    # Git
    git_status, git_envs, git_timeline, git_sessions,
    # Email
    eml_inbox, eml_stats,
    # Governance
    gov_alm, gov_tickets, gov_decisions,
    # Weather
    wea_data,
    # VPN
    vpn_status, vpn_data,
    # Skills
    skl_list, skl_patterns,
    # Ollama
    oll_models, oll_available, oll_status,
    # Audit
    aud_latest, aud_activity,
    # Sandpits
    snd_list,
    # Personality
    per_gemma, per_diary,
]


def main():
    global VERBOSE

    parser = argparse.ArgumentParser(description="Vibe Test — live system health check")
    parser.add_argument("--env", choices=["prod", "dev", "uat"], default="prod")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    VERBOSE = args.verbose
    port = PORTS[args.env]
    base_url = f"http://localhost:{port}"

    print(f"\n🎯 Vibe Test — {args.env.upper()} ({base_url})")
    print(f"{'─' * 60}\n")

    start = time.time()
    for fn in ALL_CHECKS:
        fn(base_url)
    elapsed = time.time() - start

    # ── Summary ──
    passed = sum(1 for c in RESULTS if c.passed)
    failed = sum(1 for c in RESULTS if not c.passed)
    total = len(RESULTS)

    print(f"\n{'─' * 60}")
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}  |  {elapsed:.1f}s")

    if failed:
        print(f"\n  ❌ FAILURES:")
        for c in RESULTS:
            if not c.passed:
                print(f"     [{c.id}] {c.area} — {c.description}")
                if c.detail:
                    print(f"            {c.detail}")

    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
