# Sync Story Spec

Status: active draft  
Date: 2026-05-29  
Scope: Git-backed node sync events surfaced through Studio and Vortex

## Purpose

A sync is not complete when bytes move.
A sync is complete when the operator understands the story of the move.

No sync without story.

This document defines the minimum contract for any Windows/Linux or node-to-node
sync event shown in Fridays.

## Prime Rule

Every sync event must answer:

- what moved,
- why it moved,
- what it changed in the operator's world,
- what state exists now,
- and what can be done next.

If a sync cannot expose this chain, it is born dead.

## Sync Story Contract

Every sync event must render five sections.

### 1. Origin

Required fields:
- `sync_id`
- `source_node`
- `target_node`
- `transport`
- `trigger_actor`
- `trigger_type`
- `started_at`
- `finished_at`

Definitions:
- `source_node`: where the change came from
- `target_node`: where the change landed
- `transport`: `github`, `local-origin`, `fridays-cloud`, `manual-bundle`
- `trigger_actor`: `operator`, `scheduled`, `auto-reconcile`, `startup-recover`
- `trigger_type`: `pull`, `fetch+fast-forward`, `mirror`, `reconcile`

### 2. Intent

Required fields:
- `branch`
- `from_sha`
- `to_sha`
- `commit_count`
- `top_commit_title`
- `intent_summary`

Optional linked context:
- `proposal_id`
- `bug_id`
- `project_id`
- `step_id`
- `conversation_id`

Intent exists to answer:
- why this sync exists at all
- whether it was deliberate, reactive, or automatic

### 3. Transition

Required fields:
- `files_changed_count`
- `insertions`
- `deletions`
- `path_groups`
- `risk_class`

`path_groups` should bucket changed files into:
- `runtime`
- `ui`
- `agent-config`
- `db-schema`
- `docs-studio`
- `node-topology`
- `media`
- `other`

Examples of elevated-risk surfaces:
- `frontend/blueprints/*`
- `frontend/static/js/*`
- `frontend/static/css/*`
- `utils/config.py`
- `utils/db/_schema.py`
- `windows/*`
- `core/hive/*`
- launcher/runtime bootstrap files

### 4. Consequence

Required fields:
- `result`
- `post_sync_repo_state`
- `post_sync_node_state`
- `restart_required`
- `drift_state`
- `state_impact_summary`

`result` values:
- `fast-forward`
- `merged`
- `conflicted`
- `blocked`
- `partial`
- `noop`

`post_sync_repo_state` examples:
- `clean`
- `dirty-local-overrides`
- `conflict-pending`

`post_sync_node_state` examples:
- `aligned`
- `aligned-needs-restart`
- `diverged-local-overrides`
- `blocked-awaiting-operator`

### 5. Intervention

Required actions:
- `open_diff`
- `open_linked_context`
- `restart_affected_runtime`
- `mark_reviewed`
- `defer_on_this_node`
- `rollback`

Optional actions:
- `pin_known_divergence`
- `retry_sync`
- `open_conflict_resolution`

If the operator cannot intervene from the sync surface, the sync story is
incomplete.

## Risk Classification

Every sync must be classified:

- `safe`
- `review_recommended`
- `runtime_impacting`
- `blocked`

Suggested rules:
- docs-only or non-operational assets -> `safe`
- UI/runtime/config changes without conflicts -> `review_recommended`
- bootstrap, DB schema, auth, launcher, runtime, model routing, node topology ->
  `runtime_impacting`
- merge conflicts, unresolved drift, missing prerequisites -> `blocked`

## Studio Rendering Contract

Minimum Studio presentation:

### Sync Event Card

Header:
- source -> target
- branch
- short SHA range
- commit count
- risk class

Body:
- intent summary
- changed surface summary
- current consequence summary

Expandable sections:
- files changed
- linked context
- affected systems
- intervention actions

## Vortex Event Contract

Each sync should also be emitted into Vortex as a time event.

Minimum Vortex payload:

```json
{
  "event_type": "node_sync",
  "sync_id": "SYNC-...",
  "source_node": "potato-1-linux",
  "target_node": "potato-1-win",
  "branch": "main",
  "from_sha": "abc123",
  "to_sha": "def456",
  "intent_summary": "Windows runtime stabilization + ghost log restore",
  "risk_class": "runtime_impacting",
  "result": "fast-forward",
  "restart_required": true,
  "linked_context": {
    "project_id": "P-7B9C4D2F1A"
  }
}
```

Vortex must store the story, not just the fact that a pull happened.

## Data Sources

Recommended sources for Sync Story assembly:

- Git:
  - branch
  - SHAs
  - commit messages
  - file stats
  - diff summaries
- Vortex:
  - prior node state
  - linked proposal/project/step lineage
  - previous divergence context
- Studio:
  - visible event card
  - operator acknowledgement / review state
- Node runtime:
  - whether restart is required
  - whether runtime health changed

## Node Topology Rules

For current architecture:
- `potato-1-linux` and `potato-1-win` are distinct nodes
- GitHub is the active transport
- WSL repo tunnelling is transitional, not target topology

For future architecture:
- the same Sync Story contract must survive transport changes
- only the `transport` field should change between:
  - `github`
  - `local-origin`
  - `fridays-cloud`

The operator model must remain stable.

## Non-Goals

This spec is not:
- a raw git log viewer
- a background daemon status page
- a replacement for Git
- a replacement for Vortex

It is the story layer that makes sync legible.

## Example

```text
Linux -> Windows
main · abc123 -> def456
3 commits · 12 files · runtime_impacting

Intent:
Windows agent reachability + ghost log restoration

Touched:
runtime, agents, chat, Studio docs

Consequence:
Windows node aligned to Linux branch head
restart required
local Ollama still unavailable

Next:
review diff, restart runtime, verify agents tile
```

## Final Rule

A sync event must answer:

What changed in my world because this moved?

If it cannot, it does not satisfy Fridays.
