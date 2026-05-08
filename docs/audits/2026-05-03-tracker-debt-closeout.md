# 2026-05-03 — Tracker debt closeout (Y.39)

Closing four `project_steps` entries whose source markdown is gone:

| step_id | source (deleted) | reason |
|---|---|---|
| `MD-FEATURE-747133C529E3` | `docs/FEATURES_TODO.md:79` | "make it a first-class system feature, not a hand-installed helper" — no subject; source MD removed in 2026-04 cleanup. |
| `MD-SESSION30-5B10D7D3EA47` | `docs/SESSION_30_PLAN.md:280` | Source MD archived; no migrated description body. |
| `MD-SESSION30-B008577F12D5` | `docs/SESSION_30_PLAN.md:267` | Source MD archived; no migrated description body. |
| `MD-SESSION30-C49C31FDC538` | `docs/SESSION_30_PLAN.md:279` | Source MD archived; no migrated description body. |

Per `STEP-STOP-MARKDOWN-TRACKER-RECREATION-20260430` (closed Y.14), legacy
markdown trackers are gated behind `SWARM_LEGACY_MD_TRACKERS=1` and should not
be recreated. These four orphan rows have no actionable content (no body,
no subject) so we close them as `done` with this audit note as the
record of why.

`MD-BUG-870F0D2F24E6` (mailto: approval-links live UAT bug) is **left open**
on purpose: it's gated on a real round-trip user test, not on missing
context, and re-entering it without that test would be the noise we just
gated against.
