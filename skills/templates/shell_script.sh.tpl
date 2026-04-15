#!/usr/bin/env bash
# {{TOOL_NAME}} — {{DESCRIPTION}}
# Built by {{AGENT}} on {{DATE}}
set -euo pipefail

usage() {
    echo "Usage: $(basename "$0") [--dry-run] [--help]"
    echo "  {{DESCRIPTION}}"
}

DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

if $DRY_RUN; then
    echo "[dry-run] {{TOOL_NAME}} would execute here"
    exit 0
fi

# TODO: implement {{TOOL_NAME}} logic here
echo "{{TOOL_NAME}} executed successfully"
