# Swarm Documentation Hub

Last updated: 2026-04-01
Audience: Developers, operators, and agents working in this repository

This is the primary entry point for project documentation.
If you are not sure where to start, start here.

---

## Start Here

1. Read [registry/FILING_SYSTEM.md](registry/FILING_SYSTEM.md) for canonical filing rules.
2. Read [registry/FILE_REGISTRY.md](registry/FILE_REGISTRY.md) to locate live files and avoid duplicates.
3. Use [runbooks/DOCUMENTATION_LIFECYCLE_WORKFLOW.md](runbooks/DOCUMENTATION_LIFECYCLE_WORKFLOW.md) for add/edit/delete/version workflows.

---

## Quick Tasks

### Add a New Document

Use this when no existing canonical file matches your need.

1. Confirm no suitable doc exists in [registry/FILE_REGISTRY.md](registry/FILE_REGISTRY.md).
2. Create the new document in the correct canonical folder.
3. Add the new file to [registry/FILE_REGISTRY.md](registry/FILE_REGISTRY.md) in the same change.
4. Log the change:

```bash
bash ops/scripts/log_change.sh "<actor>" "docs/<path>" "add new doc" "validated links and format" "delete file and remove registry entry"
```

### Edit an Existing Document

1. Edit the canonical file only (avoid editing archives/superseded copies).
2. Keep historical records append-only where required:
   - [changes/CHANGELOG_OPERATIONS.md](changes/CHANGELOG_OPERATIONS.md)
   - [audits/AUDIT_TRAIL.md](audits/AUDIT_TRAIL.md)
3. Log the change using `ops/scripts/log_change.sh`.

### Delete or Retire a Document

Do not hard-delete historical records without a governance reason.

1. Prefer status change in [registry/FILE_REGISTRY.md](registry/FILE_REGISTRY.md): `ACTIVE -> SUPERSEDED` or `ACTIVE -> ARCHIVE`.
2. Add a redirect note to replacement canonical file.
3. Remove only if explicitly approved and safe.
4. Log action and rollback note using `ops/scripts/log_change.sh`.

### Check Versions and Change History

1. Review operational change history in [changes/CHANGELOG_OPERATIONS.md](changes/CHANGELOG_OPERATIONS.md).
2. Review validation evidence in [audits/AUDIT_TRAIL.md](audits/AUDIT_TRAIL.md).
3. For code and docs diffs, use git:

```bash
git log -- docs/
git log -p -- docs/<file>.md
git diff HEAD~1 -- docs/
```

---

## Documentation Map

### Core Project Context

- [PROJECT.md](PROJECT.md): vision, scope, layers, and current project narrative
- [ARCHITECTURE.md](ARCHITECTURE.md): architecture and major system boundaries
- [FILE_STRUCTURE.md](FILE_STRUCTURE.md): high-level directory and module structure

### Workflows and Governance

- [DEVELOPER_WORKFLOW.md](DEVELOPER_WORKFLOW.md): implementation and governance lifecycle
- [runbooks/CHANGE_AND_AUDIT_WORKFLOW.md](runbooks/CHANGE_AND_AUDIT_WORKFLOW.md): required change + audit flow
- [runbooks/DOCUMENTATION_LIFECYCLE_WORKFLOW.md](runbooks/DOCUMENTATION_LIFECYCLE_WORKFLOW.md): practical doc operations

### Canonical Registries

- [registry/FILING_SYSTEM.md](registry/FILING_SYSTEM.md): filing standards and naming rules
- [registry/FILE_REGISTRY.md](registry/FILE_REGISTRY.md): authoritative file index and statuses
- [changes/CHANGELOG_OPERATIONS.md](changes/CHANGELOG_OPERATIONS.md): append-only change ledger
- [audits/AUDIT_TRAIL.md](audits/AUDIT_TRAIL.md): append-only evidence ledger

### Active Engineering Docs

- [BUGS.md](BUGS.md)
- [FEATURES_TODO.md](FEATURES_TODO.md)
- [TASK_TRACKER_LIVE.md](TASK_TRACKER_LIVE.md)
- [AGENT_TWELVE_MANUAL.md](AGENT_TWELVE_MANUAL.md)

---

## Clarity Rules

- Keep one canonical file per topic.
- Mark historical docs as `ARCHIVE` or `SUPERSEDED` in the registry.
- Avoid creating date-stamped docs unless policy requires it.
- Prefer updating existing canonical docs over creating new siblings.
- Every non-trivial change must be traceable in both ledgers.
