#!/usr/bin/env python3
"""Log a DOES milestone into Studio Projects for continuity."""

from scripts.studio_milestone import log_milestone


def main() -> int:
    story = """
DOES Sovereign Node profile published and runtime handoff tracking hardened.

What was wired:
- Added `docs/architecture/DOES_SOVEREIGN_NODE.md` for external architecture profile.
- Added persisted handoff edges in `does_handoff` table.
- Added handoff trace exposure in DOES history API.
- Added best-effort Studio milestone emission during handoff phases.

Traceability guarantees:
- Every execution now carries generation + audit + handoff evidence.
- Projects thread retains a continuous thought chain per execution_id.
""".strip()

    res = log_milestone(
        packet="PACKET-04",
        title="DOES Sovereign profile + handoff thread continuity",
        status="doing",
        story=story,
    )
    print(res)
    return 0 if res.get("note", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
