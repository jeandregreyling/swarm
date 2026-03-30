#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "usage: $0 <actor> <scope> <change> <validation> <rollback>"
  exit 2
fi

actor="$1"
scope="$2"
change="$3"
validation="$4"
rollback="$5"
uts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
audit_id="AUDIT-$(date -u +"%Y%m%d-%H%M%S")"

change_file="/home/seven/swarm/docs/changes/CHANGELOG_OPERATIONS.md"
audit_file="/home/seven/swarm/docs/audits/AUDIT_TRAIL.md"

cat >> "$change_file" <<EOF
- Time (UTC): $uts
- Actor: $actor
- Scope: $scope
- Change: $change
- Validation: $validation
- Rollback: $rollback

EOF

cat >> "$audit_file" <<EOF
- Audit ID: $audit_id
- Time (UTC): $uts
- Actor: $actor
- Objective: $change
- Evidence: $validation
- Result: PASS
- Follow-up: $rollback

EOF

echo "logged: $change_file"
echo "logged: $audit_file"
