"""
swarm_governance — Standalone governance core (A.4.4)
═══════════════════════════════════════════════════════
Re-exports the public governance API so any service (including remote nodes)
can do:

    from swarm_governance import transition_proposal, LEGAL_TRANSITIONS
    from swarm_governance import GovernanceError, IllegalTransitionError
    from swarm_governance import STATUS_PENDING, STATUS_DONE, ...

No Flask dependency.  Pure Python + SQLite.
"""

# ── Status constants (from proposal_status) ──────────────────────────────────
from proposal_status import (              # noqa: F401
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_IN_PROGRESS,
    STATUS_DONE,
    STATUS_UAT,
    STATUS_CLOSED,
    STATUS_REJECTED,
    normalize_proposal_status,
)

# ── Governance engine ────────────────────────────────────────────────────────
from utils.governance import (             # noqa: F401
    LEGAL_TRANSITIONS,
    GovernanceError,
    IllegalTransitionError,
    SingletonViolationError,
    ProposalNotFoundError,
    StaleProposalError,
    transition_proposal,
    get_agent_active_proposal,
    get_transition_history,
    is_transition_legal,
)
