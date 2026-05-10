#!/usr/bin/env python3
"""
bulk_path_fixer.py — Automated SWARM_ROOT adoption for hardcoded paths.
═══════════════════════════════════════════════════════════════════════════════
Scans Python, shell, and service files for hardcoded `/home/seven/swarm` paths
and rewrites them to use SWARM_ROOT / __file__ relative resolution.

  python3 scripts/fix_swarm_paths.py --dry-run   # preview
  python3 scripts/fix_swarm_paths.py             # apply

Safety:
  • Backs up every modified file to .bak-<timestamp>
  • Only touches files under git control (unless --force)
  • Never modifies .pyc, __pycache__, or vendored code
  • Idempotent — safe to re-run
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════
HARDCODED = "/home/seven/swarm"
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".vs", "node_modules",
             "agents/seven/llama.cpp", "agents/seven/llama.cpp/**"}
SKIP_PATTERNS = [re.compile(r) for r in (
    r"\.pyc$",
    r"\.bak-",
    r"/\.git/",
    r"/__pycache__/",
    r"test_.*\.py$",          # tests already use tmp_path
    r"test_swarm_root.*\.py$", # our own tests
    r"\.md$",                  # docs — handled separately if needed
    r"\.json$",
)]

# Files known to ALREADY be correct (from previous audit pass)
ALREADY_FIXED = {
    "fridays/task_runner.py",
    "fridays/scheduler.py",
    "lib/system/file_versioning.py",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Detect repo root from this script's location
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def is_git_tracked(path: Path) -> bool:
    try:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--error-unmatch", str(path)],
            capture_output=True, check=True, text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def should_skip(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    for part in rel.parts:
        if part in SKIP_DIRS:
            return True
    for pat in SKIP_PATTERNS:
        if pat.search(str(rel)):
            return True
    if str(rel) in ALREADY_FIXED:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# Transformers
# ═══════════════════════════════════════════════════════════════════════════════

def transform_agent_py(text: str, rel_path: str) -> str | None:
    """
    Rewrite agent *.py files that do sys.path.insert with hardcoded paths.
    Returns new text or None if no change needed.
    """
    if HARDCODED not in text:
        return None

    lines = text.splitlines(keepends=True)
    out_lines = []
    changed = False
    has_import_os = any("import os" in ln and "#" not in ln for ln in lines)
    has_import_sys = any("import sys" in ln and "#" not in ln for ln in lines)

    # Build the standard agent header
    def build_header(depth: int = 2) -> list[str]:
        # depth = number of dirname calls needed to reach repo root from file
        parts = ["os.path.dirname("] * depth + ["os.path.abspath(__file__)"] + [")"] * depth
        root_expr = "os.environ.get('SWARM_ROOT') or " + "".join(parts)
        hdr = []
        if not has_import_os:
            hdr.append("import os\n")
        if not has_import_sys:
            hdr.append("import sys\n")
        hdr.append(f"_SWARM_ROOT = {root_expr}\n")
        return hdr

    # Detect if this is a classic agent file (sys.path inserts near top)
    sys_path_indices = [i for i, ln in enumerate(lines) if "sys.path.insert" in ln]
    if not sys_path_indices:
        return None

    # Simple heuristic: if file has sys.path.insert with hardcoded path,
    # replace all such inserts with dynamic ones.
    inserts_seen = []
    for i, ln in enumerate(lines):
        if "sys.path.insert" in ln and HARDCODED in ln:
            inserts_seen.append((i, ln))

    if not inserts_seen:
        return None

    # Determine depth: e.g. agents/ten/copilot_agent.py → depth 2
    # agents/deepseek_local/deepseek_local_agent.py → depth 2
    depth = len(Path(rel_path).parts)  # agents/ten/file.py → 3 parts → depth 2 (3-1)
    depth = max(2, depth)

    # Remove old sys.path.insert lines
    remove_set = {i for i, _ in inserts_seen}

    # Gather what sub-paths were being inserted
    subpaths = set()
    for _, ln in inserts_seen:
        m = re.search(rf"['\"]\{HARDCODED}(/[^'\"]*)?['\"]", ln)
        if m:
            sub = m.group(1) or ""
            subpaths.add(sub.strip("/"))

    # Build replacement lines
    new_inserts = []
    for sp in sorted(subpaths):
        if sp:
            new_inserts.append(f'sys.path.insert(0, os.path.join(_SWARM_ROOT, "{sp}"))\n')
        else:
            new_inserts.append('sys.path.insert(0, _SWARM_ROOT)\n')

    # Insert header + new sys.path lines right before first old insert
    insert_at = min(remove_set)

    out_lines = lines[:]
    # Remove old inserts in reverse to keep indices stable
    for i in sorted(remove_set, reverse=True):
        del out_lines[i]

    header = build_header(depth)
    # If imports already exist, strip them from header
    final_header = []
    for hln in header:
        if "import os" in hln and has_import_os:
            continue
        if "import sys" in hln and has_import_sys:
            continue
        final_header.append(hln)

    final_header.extend(new_inserts)
    # Add a blank line after inserts if next line isn't blank
    if out_lines and out_lines[insert_at].strip():
        final_header.append("\n")

    out_lines[insert_at:insert_at] = final_header
    return "".join(out_lines)


def transform_generic_py(text: str, rel_path: str) -> str | None:
    """
    Fix non-agent Python files: replace hardcoded paths in strings/args with
    SWARM_ROOT-relative constructions where appropriate.
    """
    if HARDCODED not in text:
        return None

    # Skip files that are just docstrings mentioning the path
    # Heuristic: if every occurrence is in a string literal that's part of a
    # docstring or comment, skip.
    lines = text.splitlines(keepends=True)
    changed_any = False
    out_lines = []

    for ln in lines:
        if HARDCODED not in ln:
            out_lines.append(ln)
            continue

        # Pattern 1: sys.path.insert(0, '/home/seven/swarm')
        # Pattern 2: sys.path.insert(0, '/home/seven/swarm/utils')
        if "sys.path.insert" in ln:
            # Let transform_agent_py handle these; skip here
            out_lines.append(ln)
            continue

        # Pattern 3: string literal inside a function arg, assignment, etc.
        # We only touch lines that look like runtime paths (not docstrings)
        stripped = ln.strip()
        is_docstring = stripped.startswith('"""') or stripped.startswith("'''") or stripped.startswith('#')
        if is_docstring:
            out_lines.append(ln)
            continue

        # Heuristic: lines with .db, .py, .sh, .json references that are executable
        # Replace with os.path.join(SWARM_ROOT, ...)
        # But be conservative — only do this for known runtime path patterns.
        new_ln = ln

        # coding_bible.py style: '/home/seven/swarm/docs/CODING_BIBLE.md'
        new_ln = re.sub(
            rf"['\"]\{HARDCODED}(/[^'\"]+)['\"]",
            lambda m: f'os.path.join(SWARM_ROOT, "{m.group(1).lstrip("/")}")',
            new_ln,
        )

        if new_ln != ln:
            changed_any = True
            # Ensure 'import os' exists if we introduced os.path.join
            # (handled at file level later)
        out_lines.append(new_ln)

    if not changed_any:
        return None
    return "".join(out_lines)


def ensure_import_os(text: str) -> str:
    if "import os" in text:
        return text
    lines = text.splitlines(keepends=True)
    # Find the last import block
    last_import = -1
    for i, ln in enumerate(lines):
        if ln.strip().startswith(("import ", "from ")):
            last_import = i
    if last_import >= 0:
        lines.insert(last_import + 1, "import os\n")
    else:
        lines.insert(0, "import os\n")
    return "".join(lines)


def transform_file(path: Path, dry_run: bool, force: bool) -> dict:
    rel = str(path.relative_to(REPO_ROOT))
    result = {"path": rel, "action": "skip", "reason": ""}

    if should_skip(path):
        result["reason"] = "skip pattern"
        return result

    if not force and not is_git_tracked(path):
        result["reason"] = "not git tracked (use --force)"
        return result

    text = path.read_text(encoding="utf-8")
    if HARDCODED not in text:
        result["reason"] = "no hardcoded path"
        return result

    # Choose transformer
    if rel.startswith("agents/") and rel.endswith(".py"):
        new_text = transform_agent_py(text, rel)
    elif rel.endswith(".py"):
        new_text = transform_generic_py(text, rel)
    else:
        new_text = None

    if new_text is None:
        result["reason"] = "no applicable transform"
        return result

    # Ensure os import if we introduced os.path.join
    if "os.path.join(SWARM_ROOT" in new_text and "import os" not in new_text:
        new_text = ensure_import_os(new_text)

    if new_text == text:
        result["reason"] = "no change after transform"
        return result

    result["action"] = "dry-run" if dry_run else "fixed"
    result["reason"] = f"rewrote {text.count(HARDCODED)} occurrences"

    if not dry_run:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak-{ts}")
        shutil.copy2(path, backup)
        path.write_text(new_text, encoding="utf-8")
        result["backup"] = str(backup.relative_to(REPO_ROOT))

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk-fix hardcoded SWARM paths")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--force", action="store_true", help="Include untracked files")
    parser.add_argument("--agent-only", action="store_true", help="Only fix agent files")
    args = parser.parse_args()

    all_py = list(REPO_ROOT.rglob("*.py"))
    all_sh = list(REPO_ROOT.rglob("*.sh"))
    all_svc = list(REPO_ROOT.rglob("*.service"))

    targets = all_py + all_sh + all_svc
    if args.agent_only:
        targets = [p for p in all_py if str(p.relative_to(REPO_ROOT)).startswith("agents/")]

    results = []
    for path in targets:
        r = transform_file(path, args.dry_run, args.force)
        if r["action"] not in ("skip",):
            results.append(r)
        elif args.dry_run and r["reason"] == "no hardcoded path":
            pass  # don't spam
        elif args.dry_run:
            results.append(r)

    fixed = [r for r in results if r["action"] in ("fixed", "dry-run")]
    skipped = [r for r in results if r["action"] == "skip"]

    print(f"\n{'='*60}")
    print(f"Files to fix: {len(fixed)}")
    print(f"Files skipped: {len(skipped)}")
    print(f"{'='*60}\n")

    for r in fixed:
        print(f"  [{r['action'].upper()}] {r['path']}")
        if "backup" in r:
            print(f"           backup → {r['backup']}")

    if args.dry_run and fixed:
        print(f"\nRun without --dry-run to apply {len(fixed)} changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
