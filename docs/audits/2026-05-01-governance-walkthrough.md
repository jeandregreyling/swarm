# Governance — End-to-End Walkthrough + Gap List

_Audit ticket: MD-FEATURE-32AC6CF6055F_
_Date: 2026-05-01_
_Scope: ALM proposal lifecycle from filing to close, plus the surfaces a human
operator actually touches._

---

## 1. What "governance" means in Swarm

Every code/doc change ships through a **proposal** — a row in `work_proposals`
(SQLite, `swarm_memory.db`). The state machine in `utils/governance.py` is the
**only** legal way to mutate `work_proposals.status`. Direct `UPDATE` against
that column is treated as a bug.

Legal states and transitions (verbatim from `LEGAL_TRANSITIONS`):

```
pending      → approved | rejected | closed*
approved     → in_progress | rejected | closed
in_progress  → done | rejected
done         → uat | in_progress | closed
uat          → closed | in_progress
rejected     → pending     (resubmit)
closed       → (terminal)
```

`closed*` from `pending` is a legacy escape hatch for auto-executed decisions;
no new code should rely on it.

**Singleton rule**: any one agent may hold at most **one** proposal in
`in_progress` at a time (`_SINGLETON_STATUSES = {STATUS_IN_PROGRESS}`). The
state machine raises `SingletonViolationError` rather than silently queueing.

---

## 2. The walkthrough — file → close

### 2.1 File a proposal
- **Entry points**: `utils/proposal_review.py::file_proposal()`,
  Studio "New proposal" form, or any agent that calls
  `change_logger.log_change(...)`.
- **Side effects**: row inserted with `status='pending'`, an audit row in
  `governance_audit`, and a Vortex snapshot.

### 2.2 Approve / reject
- Human or guardian approves via the Proposals window or
  `transition_proposal(pid, 'approved', agent=…)`.
- Reject path goes to `rejected`, can be resubmitted to `pending`.

### 2.3 Pick up work
- Agent claims work by transitioning `approved → in_progress`. The singleton
  rule fires here: a second concurrent claim is rejected with
  `SingletonViolationError`.
- The Spine emits a `governance` event so the Traced view can show the claim.

### 2.4 Implement, then mark done
- Agent commits code, then transitions `in_progress → done`.
- `change_logger.log_change` will auto-fire `transition_proposal(...,'done')`
  on commit when configured to do so, so most agents never call it directly.

### 2.5 Duck QA
- Duck consumes `done` proposals, runs the test slice, and either:
  - PASS → `done → uat`
  - FAIL → `done → in_progress` with a `note` carrying the failure reason.

### 2.6 Ghost ships
- Ghost (or human operator) reviews `uat` proposals, runs operator-side
  smoke checks, and transitions `uat → closed`.
- If the ship is rejected the proposal goes `uat → in_progress` for rework.

### 2.7 Closed = terminal
- `closed` has no outbound transitions. A regression on a closed proposal
  must be filed as a new proposal that references the prior one in `note`.

---

## 3. Surfaces a human touches

| Surface | What it shows | Backed by |
|---|---|---|
| Studio status line `#studio-governance` | one-line ALM status | `theme_engine._governance_state()` |
| `GET /api/alm/status` | JSON snapshot of pending / in-progress / uat counts | `frontend/blueprints/system.py` |
| Proposals window | full table: id / agent / status / age / note | `frontend/blueprints/proposals.py` |
| Traced view | spine timeline filtered to `governance` events | `core/spine.py` |
| `/api/spine/events?kinds=governance` | raw event stream | `core/spine.py` |
| Vortex snapshots | per-commit rollback points tied to proposal id | pre-commit hook |

---

## 4. Gap list

These are concrete gaps surfaced by walking through the flow. Each one is a
candidate for its own MD-FEATURE before we can call governance "complete".

1. **No first-class Governance tab.** `studio-governance` is a single dim
   line; operators have to know to open the Proposals window. A dedicated
   tab with kanban-style columns (pending / approved / in_progress / done /
   uat / closed) would make the queue legible at a glance.

2. **Singleton-violation feedback is silent in the UI.** When an agent is
   rejected by the singleton rule, the proposal row stays in `approved`
   with no visible nudge. We should surface a "blocked: agent X already
   holds proposal Y" banner.

3. **No Duck-QA failure narrative.** Round-tripping `done → in_progress` via
   Duck loses the failing-test reason after the next snapshot. The `note`
   column captures it, but the UI does not surface notes per transition.

4. **Closed-proposal regression flow is informal.** There is no UI button
   to "file a regression of #PID"; operators copy-paste manually. A
   one-click "regress" action that pre-fills the new proposal description
   with `Regression of <pid>: <title>` would prevent silent loss of links.

5. **Vortex ↔ proposal linking is one-way.** The pre-commit hook stamps the
   proposal id into the snapshot, but the Proposals window doesn't show
   "rollback to before this proposal" actions inline.

6. **`alm/status` endpoint has no auth or rate-limiting.** Low risk for a
   local-only deployment, but worth tightening before the desktop build
   exposes the same endpoint over LAN.

7. **No explicit `cancelled` status.** A proposal that becomes obsolete
   (spec change, duplicate, scope cut) is currently squeezed through
   `rejected → pending → rejected` or left in limbo. A real `cancelled`
   terminal status with a required reason would be cleaner.

8. **Audit trail rotation is unbounded.** `governance_audit` grows forever.
   Trim policy + a "see full history" link should land before the table
   passes ~1M rows.

9. **No SLA timers.** Proposals can sit in `pending` indefinitely. A simple
   age-bucket badge ("> 24h", "> 7d") would make stale work visible.

10. **Ghost-ship side-effects (PROD restart, deploy) are not in the state
    machine.** They live in `services/proposal_helpers.py::apply()`. The
    state machine only knows about the status flip; the deploy step can
    fail after the flip and leave the system inconsistent. A two-phase
    `closing → closed` substate (or a deploy-side compensation) would tie
    the deploy outcome back to the governance record.

---

## 5. What is verified working today

- `LEGAL_TRANSITIONS` enforcement — covered by `tests/test_governance_state_machine.py`.
- Singleton rule — covered by `tests/test_governance_singleton.py`.
- Optimistic lock (StaleProposalError) — covered by the same suite.
- `change_logger` auto-transition on commit — covered by
  `tests/test_change_logger_governance.py`.
- Duck QA round-trip — covered by `tests/test_duck_governance_loop.py`.

The state machine itself is solid. The gaps above are all **UX / lifecycle
surfacing** issues, not correctness bugs in the governance core.

---

## 6. Recommended next steps

In order of payoff vs. cost:

1. Surface notes-per-transition in the Proposals window (gap 3) — pure UI.
2. Add age badges to pending rows (gap 9) — pure UI, two CSS classes.
3. Add a one-click "regress" action (gap 4) — UI + a single endpoint.
4. Promote `studio-governance` line into a real Governance tab (gap 1).
5. Add `cancelled` terminal status to the state machine (gap 7) — needs a
   migration but otherwise contained.
6. Tighten `/api/alm/status` for the desktop build (gap 6).

Items 8 and 10 are larger; defer until the desktop build forces the issue.
