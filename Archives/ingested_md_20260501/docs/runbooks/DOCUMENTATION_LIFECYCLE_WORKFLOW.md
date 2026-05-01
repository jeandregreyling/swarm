# Documentation Lifecycle Workflow

Effective date: 2026-04-01
Scope: All documentation under `docs/`

This runbook defines how to safely add, edit, retire, and track documentation.

---

## 1) Decide: Create or Update?

Before creating any file:

1. Check [../registry/FILE_REGISTRY.md](../registry/FILE_REGISTRY.md).
2. If a matching canonical doc exists, update it.
3. If no canonical doc exists, create one and register it in the same change.

Decision rule:
- Update existing canonical file when topic overlap is greater than 50%.
- Create new file only for a distinct topic with clear ownership and purpose.

---

## 2) Add a Document

Use this checklist:

1. Place file in the correct domain folder.
2. Add front matter block at top (minimum):

```markdown
# <Title>

Last updated: YYYY-MM-DD
Owner: <team/agent>
Status: ACTIVE
Purpose: <one sentence>
```

3. Add registry entry in [../registry/FILE_REGISTRY.md](../registry/FILE_REGISTRY.md).
4. Add navigation link in [../README.md](../README.md) if user-facing.
5. Log change and audit evidence via `ops/scripts/log_change.sh`.

---

## 3) Edit a Document

1. Confirm file status is `ACTIVE` in the registry.
2. Preserve append-only behavior for canonical ledgers:
   - [../changes/CHANGELOG_OPERATIONS.md](../changes/CHANGELOG_OPERATIONS.md)
   - [../audits/AUDIT_TRAIL.md](../audits/AUDIT_TRAIL.md)
3. Update `Last updated` date if the file has one.
4. Keep links valid and avoid duplicate topic docs.
5. Log change and validation.

---

## 4) Retire, Supersede, or Delete

Preferred order:

1. `ACTIVE -> SUPERSEDED` (with replacement link)
2. `ACTIVE -> ARCHIVE` (historical retention)
3. Physical delete only with explicit approval

Mandatory for retirement:

1. Update status in [../registry/FILE_REGISTRY.md](../registry/FILE_REGISTRY.md).
2. Add replacement pointer where possible.
3. Log rollback path in change entry.

---

## 5) Version Checks and Traceability

Use these commands:

```bash
# history for all docs
git log -- docs/

# history and diff for one doc
git log -p -- docs/<file>.md

# what changed in docs this branch/session
git diff -- docs/
```

Traceability sources:

1. [../changes/CHANGELOG_OPERATIONS.md](../changes/CHANGELOG_OPERATIONS.md)
2. [../audits/AUDIT_TRAIL.md](../audits/AUDIT_TRAIL.md)
3. Git history for exact line changes

---

## 6) Quality Gate (Before Merge)

A docs change is complete only when all are true:

- File is canonical or correctly status-labeled
- Registry is updated for new/retired docs
- Hub navigation in [../README.md](../README.md) still works
- Change and audit entries are appended
- Rollback note is present for non-trivial changes
