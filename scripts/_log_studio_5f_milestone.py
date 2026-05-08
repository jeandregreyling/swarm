"""Slice-5f milestone: Studio defaults + proposals branching hint + git-blocks polish."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Three flagged Studio surfaces: (1) every reopen of Studio reset to
  the Projects tab regardless of where the user was; (2) when a
  proposal sat at Done/UAT it was unclear from the card alone what
  branches were still available (Revert? Promote? Reopen?); (3) the
  git-branch / git-commit chips inside the diff overlay rendered as
  two separate \"Branch: <code>… Commit: <code>…\" lines, taking
  width and reading like a stack trace instead of metadata.

What we built:
  - Studio defaults (frontend/static/js/views/studio.js loadStudioData
    + studioSetTab):
      * `loadStudioData` now reads the last-used tab from
        localStorage('studio_last_tab') on first open of a session,
        falling back to 'projects'.
      * `studioSetTab` writes the new tab back to that key on every
        switch, in a try/catch (private-mode safe).
      * Net effect: close Studio on Records, reopen \u2192 you land on
        Records, not Projects.

  - Proposals branching hint (_proposalCard pipelineHtml):
      Right under the 6-step pipeline mini-bar, when status is 'done'
      or 'uat' AND the proposal has a git_branch, a 9.5px hint row
      lists the alternates available from this state:
        \u21a9 Revert          (always)
        \u2192 UAT             (Done only)
        \u2192 PROD            (UAT only)
      Rejected proposals get a dashed-border note saying \"Re-open from
      action menu to revisit\". This makes the branching graph visible
      from the card without opening the diff overlay.

  - GIT chips polish (viewProposalDiff overlay header):
      Replaced the two separate `Branch: <code>…</code>` and
      `Commit: <code>…</code>` snippets with a single rounded pill:
        [git-icon] <branch> \u00b7 <commit[:8]>
      Title-tooltip on the pill shows full branch + full commit. When
      neither is present, the pill collapses to nothing. Mono font and
      muted background — reads as metadata, not as code.

How to verify:
  - Open Studio, switch to Records, close, reopen \u2192 lands on Records.
  - Open a 'done' proposal with a git_branch \u2192 card shows
    \"Alternates: \u21a9 Revert  \u2192 UAT\" line under pipeline bar.
  - Click Review Diff \u2192 header shows compact pill like
    `[icon] dev/PR-XXXX \u00b7 a1b2c3d4` instead of two text labels.
  - studio.js?v=35 returns 200; node parse=ok.

Why this matters:
  Studio is the swarm's mission-control. Persisting tab makes long
  multi-session work flow naturally instead of forcing a reorient on
  every reopen. The branching hint makes the proposal lifecycle
  legible from the index card \u2014 you can see what moves are still
  legal without opening the detail overlay. The git-pill compresses
  what was visually noisy metadata into a single muted chip, freeing
  the header for what actually matters (the env-isolation badge).

This closes PACKET-07 slices 5a\u20135f. PACKET-08 platinum doc-mgmt
1\u20135 + PACKET-07 5a\u20135f all shipped, milestoned, asset-verified."""

log_milestone(
    packet="PACKET-08",
    title="Studio defaults persist + proposals branching hint + git-chip polish",
    story=STORY,
    status="done",
)
print("ok")
