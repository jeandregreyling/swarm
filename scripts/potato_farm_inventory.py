"""Potato Farm source-of-truth inventory (S-POTATO-00-INVENTORY).

Builds a live node/capability/blocker matrix and clearly separates live
capacity from stale historical proof. Writes a JSON report under
runtime/reports/ and posts a Studio milestone note + claims the step.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Any

import urllib.request
import urllib.error

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.knowledge.projects import (  # noqa: E402
    add_blackboard_note,
    claim_step,
    update_step_status,
)

LEADER = os.environ.get("SWARM_LEADER_URL", "http://127.0.0.1:5050").rstrip("/")
PROJECT_ID = "P-94531FE267"
STEP_ID = "S-POTATO-00-INVENTORY"
COORD_PROJECT_ID = "P-FAEAF9AF90"
FRESH_S = 180  # node telemetry freshness gate
STALE_S = 3600  # anything older is historical


def _http_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _classify_node(node: dict[str, Any]) -> str:
    age = node.get("age_s")
    if node.get("offline"):
        return "offline"
    if not isinstance(age, (int, float)):
        return "unknown"
    if age <= FRESH_S:
        return "live"
    if age <= STALE_S:
        return "stale-recent"
    return "stale-historical"


def build_inventory() -> dict[str, Any]:
    try:
        nodes_payload = _http_json(f"{LEADER}/api/hive/nodes")
    except (urllib.error.URLError, TimeoutError) as exc:
        nodes_payload = {"error": str(exc), "nodes": []}
    try:
        jobs_payload = _http_json(f"{LEADER}/api/hive/jobs")
    except (urllib.error.URLError, TimeoutError) as exc:
        jobs_payload = {"error": str(exc), "jobs": []}

    nodes = nodes_payload.get("nodes") or []
    jobs = jobs_payload.get("jobs") or []

    by_class: dict[str, list[dict[str, Any]]] = {
        "live": [],
        "stale-recent": [],
        "stale-historical": [],
        "offline": [],
        "unknown": [],
    }
    capabilities: set[str] = set()
    for n in nodes:
        cls = _classify_node(n)
        caps = (n.get("telemetry") or {}).get("capabilities") or []
        capabilities.update(caps)
        by_class[cls].append({
            "node_id": n.get("node_id"),
            "platform": n.get("platform"),
            "age_s": n.get("age_s"),
            "offline": bool(n.get("offline")),
            "expected": bool(n.get("expected")),
            "capabilities": caps,
            "label": n.get("label"),
        })

    pending_by_capability: dict[str, int] = {}
    claimed = 0
    completed = 0
    for j in jobs:
        status = j.get("status")
        if status == "pending":
            cap = j.get("capability_req") or "any"
            pending_by_capability[cap] = pending_by_capability.get(cap, 0) + 1
        elif status == "claimed":
            claimed += 1
        elif status == "completed":
            completed += 1

    live_caps: set[str] = set()
    for n in by_class["live"]:
        live_caps.update(n["capabilities"])
    unmet_demand = {
        cap: count
        for cap, count in pending_by_capability.items()
        if cap not in live_caps and cap != "any"
    }

    blockers: list[dict[str, str]] = []
    if not by_class["live"]:
        blockers.append({
            "id": "no-live-nodes",
            "severity": "critical",
            "summary": "No nodes meet the 180s freshness gate; farm has zero live capacity.",
        })
    if len(by_class["live"]) < 2:
        blockers.append({
            "id": "single-node-cluster",
            "severity": "high",
            "summary": "Acceptance gate requires ≥2 live nodes simultaneously.",
        })
    android_live = any(
        n["platform"] and "android" in n["platform"].lower() for n in by_class["live"]
    )
    if not android_live:
        blockers.append({
            "id": "android-stale",
            "severity": "high",
            "summary": "No Android node is live; Samsung GPU proof is historical only.",
        })
    if unmet_demand:
        blockers.append({
            "id": "unmet-capability-demand",
            "severity": "medium",
            "summary": (
                "Pending jobs require capabilities not present on any live node: "
                + ", ".join(f"{cap}×{n}" for cap, n in sorted(unmet_demand.items()))
            ),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leader_url": LEADER,
        "freshness_s_gate": FRESH_S,
        "node_counts": {k: len(v) for k, v in by_class.items()},
        "nodes_by_class": by_class,
        "live_capabilities": sorted(live_caps),
        "all_known_capabilities": sorted(capabilities),
        "job_summary": {
            "total": len(jobs),
            "pending_by_capability": pending_by_capability,
            "claimed": claimed,
            "completed": completed,
            "unmet_demand_by_capability": unmet_demand,
        },
        "blockers": blockers,
    }


def write_report(inventory: dict[str, Any]) -> pathlib.Path:
    out_dir = REPO_ROOT / "runtime" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"potato_farm_inventory_{ts}.json"
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True))
    return path


def _summary_markdown(inv: dict[str, Any], report_path: pathlib.Path) -> str:
    counts = inv["node_counts"]
    job = inv["job_summary"]
    blockers = inv["blockers"]
    lines = [
        f"[POTATO-00] Inventory snapshot — leader {inv['leader_url']}",
        "",
        f"Generated: {inv['generated_at']}",
        f"Report: {report_path.relative_to(REPO_ROOT)}",
        "",
        "Node classification:",
        *(f"  - {k}: {v}" for k, v in counts.items()),
        "",
        f"Live capabilities: {', '.join(inv['live_capabilities']) or '(none)'}",
        f"Jobs: total={job['total']} claimed={job['claimed']} completed={job['completed']}",
        f"Pending by capability: {json.dumps(job['pending_by_capability'], sort_keys=True)}",
        f"Unmet demand: {json.dumps(job['unmet_demand_by_capability'], sort_keys=True)}",
        "",
        "Blockers:",
    ]
    if not blockers:
        lines.append("  - (none)")
    else:
        for b in blockers:
            lines.append(f"  - [{b['severity']}] {b['id']}: {b['summary']}")
    return "\n".join(lines)


def main() -> int:
    inv = build_inventory()
    report = write_report(inv)
    summary = _summary_markdown(inv, report)

    claim_step(STEP_ID, "codex")
    update_step_status(STEP_ID, "doing", owner="codex")

    note_id = add_blackboard_note(
        PROJECT_ID,
        summary,
        author="codex",
        kind="milestone",
    )
    coord_note = add_blackboard_note(
        COORD_PROJECT_ID,
        f"[PLAN-MODE → Wave-A] Potato Farm inventory captured.\n\n{summary}",
        author="codex",
        kind="milestone",
    )

    print(json.dumps({
        "report_file": str(report),
        "blockers": inv["blockers"],
        "node_counts": inv["node_counts"],
        "studio_note": note_id,
        "coord_note": coord_note,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
