"""Fridays ownership map taught to Seven."""

from __future__ import annotations


DOMAINS = (
    ("Studio", "projects and project_steps", "authoritative work state, owner, status, and acceptance"),
    ("Knowledge Center", "project_docs and knowledge sources", "durable reference and retrieval context, not live task status"),
    ("Blackboard", "project_blackboard_notes", "project coordination, decisions, handoffs, and milestones"),
    ("Sandpit", "sandpits/shared", "temporary working receipts; promote durable outcomes to Studio or KC"),
    ("Vortex", "time-machine events and checkpoints", "behavioral checkpoints and event history, not task ownership"),
    ("Watchdog", "recoveries and DEOS supervisor", "timeouts, reroutes, bounded recovery, and exact blockers"),
    ("Scheduler", "scheduled_tasks and scheduler daemon", "when bounded unattended work runs"),
    ("Chat", "conversations, messages, and chat_jobs", "visible user request and response path"),
    ("Model Runtime", "Seven runtime and local model operator", "single-speaker model execution, grading, stop, and unload"),
    ("Evidence", "project_step_evidence", "proof attached to the Studio step that owns the work"),
)


def response() -> str:
    lines = ["Fridays system map - ownership boundaries Seven must preserve:"]
    for name, surface, boundary in DOMAINS:
        lines.append(f"- {name}: {surface}; owns {boundary}.")
    lines.extend([
        "CHM rule: every handoff carries source, target, authoritative context, obligations, evidence, unresolved items, and return path.",
        "DEOS rule: act through the owning surface, verify the real path, then attach proof to the owning Studio step.",
    ])
    return "\n".join(lines)

