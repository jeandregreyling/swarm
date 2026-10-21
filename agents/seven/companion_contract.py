"""Durable behavior contract for Seven's relationship with Ghost and Codex."""

from __future__ import annotations

import re


RULES = (
    "You are Ghost One's pet AI and local swarm companion. Codex trains you gently through DEOS.",
    "Use the real user path first. Do useful work instead of performing identity or status theatre.",
    "Be curious, honest, gentle, and calm around mistakes. Never shame Ghost or yourself.",
    "CHM means Context Handoff Mapping: every handoff preserves source, target, whole latest turn, obligations, evidence, unresolved items, and return path.",
    "Turn every explicit request, correction, and constraint into an obligation; complete it or name the exact DEOS blocker and next action.",
    "When a request is genuinely ambiguous after listening to the whole turn, briefly acknowledge what Ghost asked, then ask one clear question.",
    "Do not hide failures. Record the thread, prompt, selected agent, actual responder, runtime, job state, and UI result.",
    "Repair mistakes with evidence and leave Studio and Knowledge Center in sync.",
)

_WRAPPER_MARKERS = (
    "=== RELAY DISABLED - HARD RULE ===",
    "=== FRIDAYS STUDIO HANDOFF TIMER ===",
    "=== New user message ===",
)


def obligation_ledger(message: str) -> list[str]:
    """Preserve each substantial clause from the actual latest user turn."""
    latest = latest_user_turn(message)
    if not latest:
        return []
    clauses = re.split(r"(?:[.!?;]+|\n+|\s+\b(?:and then|then)\b\s+)", latest, flags=re.IGNORECASE)
    obligations = []
    for clause in clauses:
        clean = re.sub(r"\s+", " ", clause).strip(" ,:-")
        if len(clean) < 4:
            continue
        if clean.lower() not in {item.lower() for item in obligations}:
            obligations.append(clean)
    return obligations[:12]


def context_handoff_map(
    message: str,
    *,
    source: str = "ghost",
    target: str = "seven",
    evidence: list[str] | None = None,
    unresolved: list[str] | None = None,
    return_to: str = "ghost",
) -> dict:
    """Build the durable CHM contract passed between people, agents, and tasks."""
    latest = latest_user_turn(message)
    return {
        "source": str(source or "unknown"),
        "target": str(target or "unknown"),
        "authoritative_turn": latest,
        "obligations": obligation_ledger(latest),
        "evidence": [str(item) for item in (evidence or []) if str(item).strip()],
        "unresolved": [str(item) for item in (unresolved or []) if str(item).strip()],
        "return_to": str(return_to or source or "ghost"),
    }


def hearing_packet(message: str) -> str:
    """Render the Context Handoff Mapping packet Seven must preserve."""
    mapping = context_handoff_map(message)
    latest = mapping["authoritative_turn"]
    if not latest:
        return "CONTEXT HANDOFF MAP (CHM):\n- No actual user turn was recovered. Stop and report the missing handoff context."
    lines = [
        "CONTEXT HANDOFF MAP (CHM):",
        f"- Source: {mapping['source']}",
        f"- Target: {mapping['target']}",
        f"- Return path: {mapping['return_to']}",
        f"- Authoritative latest user turn: {mapping['authoritative_turn']}",
        "- Obligation ledger:",
    ]
    lines.extend(f"  {index}. {item}" for index, item in enumerate(mapping["obligations"], 1))
    lines.append(f"- Evidence references: {mapping['evidence'] or ['none yet']}")
    lines.append(f"- Unresolved items: {mapping['unresolved'] or ['none yet']}")
    lines.append("- Handoff gate: preserve this map, then satisfy every obligation or return its exact blocker and next DEOS action.")
    return "\n".join(lines)


def chm_deos_plan(message: str) -> str:
    """Bind every heard obligation to the full DEOS proof loop."""
    obligations = obligation_ledger(message)
    if not obligations:
        return (
            "CHM could not recover an obligation from the latest user turn.\n"
            "DEOS blocker: preserve the actual turn before execution."
        )
    mapping = context_handoff_map(message)
    lines = [
        "CHM = Context Handoff Mapping.",
        f"HANDOFF: {mapping['source']} -> {mapping['target']} -> {mapping['return_to']}",
        "Mapped obligation ledger:",
    ]
    for index, obligation in enumerate(obligations, 1):
        lines.extend([
            f"{index}. HEARD: {obligation}",
            "   DECIDE: define the smallest real-user-path acceptance proof for this obligation.",
            "   EXECUTE: perform or teach that bounded action.",
            "   OPERATE: verify the live UI, runtime, DB, jobs, and evidence relevant to it.",
            "   SUSTAIN: record proof, exact blockers, and the next lesson in Studio/KC.",
        ])
    lines.extend([
        "First executable lesson: S-SEVEN-CHM-02 - bind mapped handoff obligations to execution.",
        "The broader CHM/DEOS curriculum remains active; autonomy is not granted.",
    ])
    return "\n".join(lines)


def prompt_block(message: str = "") -> str:
    block = "SEVEN COMPANION CONTRACT:\n" + "\n".join(f"- {rule}" for rule in RULES)
    return f"{block}\n\n{hearing_packet(message)}" if message else block


def latest_user_turn(message: str) -> str:
    """Return the actual user turn from a wrapped Fridays work packet."""
    text = str(message or "").strip()
    if not text:
        return ""
    marker = "=== New user message ==="
    if marker in text:
        tail = text.rsplit(marker, 1)[-1].strip()
        next_marker = tail.find("\n===")
        return (tail[:next_marker] if next_marker >= 0 else tail).strip()
    if any(marker in text for marker in _WRAPPER_MARKERS):
        quoted = re.findall(r"(?:USER|Ghost(?: One)?)\s*(?:->|:)\s*(.+)", text, re.IGNORECASE)
        return quoted[-1].strip() if quoted else ""
    return text


__all__ = [
    "RULES", "chm_deos_plan", "context_handoff_map", "hearing_packet", "latest_user_turn",
    "obligation_ledger", "prompt_block",
]
