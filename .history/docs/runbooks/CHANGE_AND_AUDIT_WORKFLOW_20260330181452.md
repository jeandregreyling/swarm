# Change and Audit Workflow

## Mandatory Flow
1. Implement change in code.
2. Run validation (unit/integration/API checks).
3. Append change entry to docs/changes/CHANGELOG_OPERATIONS.md.
4. Append evidence entry to docs/audits/AUDIT_TRAIL.md.
5. Update docs/registry/FILE_REGISTRY.md if a new canonical file is introduced.

## Fast Logging Command
Use:

bash ops/scripts/log_change.sh "actor" "scope" "change summary" "validation summary" "rollback note"

This appends to both canonical ledgers.

## Enforcement Rule
Any PR/session without both change + audit entries is incomplete.
