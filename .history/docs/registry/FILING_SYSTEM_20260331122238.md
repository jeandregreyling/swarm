# Filing System Standard (Swarm)

Effective date: 2026-03-30
Owner: Ghost layer governance

## Purpose
This document defines the canonical filing model for code, audits, and operations records.
It exists to stop drift, duplicate trackers, and undocumented fixes.

## Canonical Locations
- Architecture and structure rules: docs/registry/
- Change records (human-readable): docs/changes/
- Audit evidence (append-only): docs/audits/
- Operational procedures: docs/runbooks/
- Automation helpers: ops/scripts/

## Single Sources of Truth
- Current structure map: docs/registry/FILE_REGISTRY.md
- Change log ledger: docs/changes/CHANGELOG_OPERATIONS.md
- Audit trail ledger: docs/audits/AUDIT_TRAIL.md
- Workflow rules: docs/runbooks/CHANGE_AND_AUDIT_WORKFLOW.md

## Required Logging Contract
Every non-trivial code change must append one entry to:
1) docs/changes/CHANGELOG_OPERATIONS.md
2) docs/audits/AUDIT_TRAIL.md

Each entry must include:
- UTC timestamp
- actor
- scope (module/path)
- change summary
- validation evidence (command/test/api)
- risk or rollback note

## Naming Rules
- New audit docs: AUDIT-YYYYMMDD-\<slug\>.md
- New runbooks: \<TOPIC\>_WORKFLOW.md
- New structure records: UPPER_SNAKE_CASE.md

## Compatibility Rule
Existing files remain valid until migrated. Do not delete or move legacy docs without adding a redirect note in docs/registry/FILE_REGISTRY.md.
