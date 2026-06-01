# Fridays Operator Heuristics

Status: active  
Date: 2026-05-29  
Scope: Fridays, Vortex, Studio, Git, node topology, operator-facing runtime behavior

## Purpose

This document encodes the operator heuristics that keep Fridays from drifting
back into dead-admin-panel behavior.

Fridays is not a reporting harness with a chat veneer.
Fridays is a living local-first control plane.

The system is only complete when the operator can feel:
- what the machine is doing,
- why it is doing it,
- what changed,
- what happens next,
- and how to intervene.

## Prime Directive

No state without story.

Status without narrative is dead.
Telemetry without provenance is dead.
Automation without intervention is dead.

Every meaningful state change must carry its causal chain into the visible
operator surface.

## Core Heuristics

### 1. Visible Causality

Every meaningful event must expose:
- Origin: who or what initiated it
- Intent: why it was initiated
- Transition: what changed
- Consequence: what state exists now and what happens next
- Intervention: how the operator can steer, block, or override it

If a feature cannot expose that chain inside Fridays, it is incomplete.

### 2. No Invisible State

If the operator cannot see why the machine is behaving a certain way from
inside Fridays, the feature is not production-ready.

Hidden state may exist internally.
Hidden state may not be the only source of truth the operator can access.

### 3. Operator Cognition Is Telemetry

Operator questions, friction, hesitation, and intuition are not noise.
They are system input.

Treat the following as structured signal:
- "this feels dead"
- "this feels wrong"
- "this is too detached"
- "I don't trust what it is doing"

These are Systemic Friction Events.
They must be traceable in Vortex or Studio rather than discarded as chat fluff.

### 4. Empirical Composition Over Consensus Predictability

Do not default to the cleanest industry-standard abstraction if it kills the
operator-control-plane feel.

Prefer:
- live click validation over speculative tidiness,
- runtime truth over documentation comfort,
- compositional clarity over generic framework orthodoxy.

Clean but dead loses to slightly rough but alive.

### 5. Local Truth First

Each node is real in its own right.
Windows and Linux are separate operational truths even on the same metal.

Local behavior is not a testing inconvenience.
Local behavior is the substrate.

### 6. Failure Is Data

A failure is not just a defect to suppress.
It is a signal about system boundaries, hidden couplings, or lying contracts.

Do not only ask:
- how do we stop this error?

Also ask:
- what contract was false?
- what state was invisible?
- what surface lied to the operator?

### 7. Story Before Automation

Do not add automation that performs meaningful work silently.

Automated operations must be born alive:
- visible in Studio,
- attributable in Vortex,
- explainable in chat or tile state,
- interruptible by the operator.

## Architecture Gates

Every meaningful design decision must pass these gates:

### Git = Truth

- Code is canonical in Git.
- Branches, SHAs, diffs, merges, and working-tree truth belong to Git.
- Vortex does not become a second repo owner.

### Vortex = Time

- Vortex owns provenance, intent history, drift records, rollback context,
  checkpoint lineage, and operational memory.
- Vortex is useless if it stores data without causal story.

### Studio = Visibility

- Studio is the operator control surface.
- State must be rendered with narrative, not buried in APIs or logs.
- If the operator cannot see and steer it, the surface is incomplete.

### Nodes = Separate

- `potato-1-linux` and `potato-1-win` are distinct nodes.
- Shared hardware does not collapse runtime truth.
- Sync must respect node-specific state rather than flatten it.

## DOES / DEOS Relationship

Fridays already contains both principles.

### DOES

DOES is the structural side:
- gateway discipline,
- state as truth,
- persisted handoffs,
- deterministic orchestration boundaries.

Reference:
- [DOES_SOVEREIGN_NODE.md](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/docs/architecture/DOES_SOVEREIGN_NODE.md)

### DEOS

DEOS is the operational side:
- Decide
- Execute
- Operate
- Sustain

It is the control-plane loop that keeps work alive, bounded, and evidenced.

References:
- [watchdog_deos.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/watchdog_deos.py)
- [deos_teaching.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/deos_teaching.py)

The operator heuristics in this document are the human-facing layer that binds
DOES and DEOS into one surface.

## Required Evaluation Modes

When evaluating a design path, produce three views:

### Standard

The safe, industry-default path.

### Compositional

The path that best aligns with Fridays as a local-first living control plane.

### Pivot

The path that deliberately tests system boundaries and exposes hidden
assumptions.

Do not flatten these into one "best practice" answer without showing the
tradeoff.

## Systemic Friction Event Format

When the operator experiences misalignment, record it in structured form:

- Surface
- Trigger
- Felt problem
- Hidden state suspected
- Causality gap
- Proposed relink

Example:

```text
Surface: Studio / Chat
Trigger: audit trail detached from active conversation
Felt problem: dead admin panel
Hidden state suspected: action provenance exists only in backend logs
Causality gap: operator sees result without story
Proposed relink: surface event origin/intent/transition in chat + Studio
```

## Anti-Drift Rules

The system is drifting toward dead-admin-panel territory if:
- tiles show status but not cause,
- sync happens silently,
- runtime failures are softened into vague UI language,
- operator questions are treated as distraction instead of telemetry,
- Vortex stores facts without intention,
- Studio becomes a report viewer instead of a control surface.

## Final Rule

Fridays must always answer:

What changed in my world because this happened?

Not merely:

What changed in the database, branch, or log?
