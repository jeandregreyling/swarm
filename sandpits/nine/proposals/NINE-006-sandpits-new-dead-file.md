# NINE-006: Delete sandpits_new.py — Dead Staging File

**Status**: EXECUTED
**Proposal ID**: NINE-006
**Proposed**: 2026-03-29
**Agent**: Nine (System Architect · Ghost Layer)
**Priority**: LOW — Cleanup / confusion prevention

---

## Issue

`utils/sandpits_new.py` exists alongside the active `utils/sandpits.py`. The "new" file is a strict subset of the current file and is not imported by anything. It creates confusion about which file is canonical.

---

## Evidence

### Diff summary:
```
sandpits.py      170 lines
sandpits_new.py  170 lines (identical header + body)

Only difference:
sandpits.py has at lines 169-195:
  + def get_sandpit_stats() — used by terminal.py
  + def get_recent_log()   — used by terminal.py

sandpits_new.py is MISSING both of these functions.
```

### AGENTS list: **identical** in both files.
```python
AGENTS = ['gemma', 'llama', 'qwen', 'eight', 'librarian', 'sniffles', 'nine', 'grok']
```

### Imports: Nothing imports `sandpits_new`.
```bash
grep -rn "sandpits_new" /home/seven/swarm --include="*.py"
# → 0 results
```

`terminal.py` imports from `sandpits` (the active file): `from sandpits import get_sandpit_stats, get_recent_log as sandpit_log`

If `sandpits_new` were ever imported instead of `sandpits`, it would raise `ImportError: cannot import name 'get_sandpit_stats'`.

---

## Root Cause

`sandpits_new.py` appears to have been created during a cleanup/refactor session (March 27-28) as a staging draft. It was never merged into the active file, never committed as a replacement, and was left on disk.

---

## Proposed Fix

Delete `utils/sandpits_new.py`.

```bash
rm /home/seven/swarm/utils/sandpits_new.py
```

The active `utils/sandpits.py` is the canonical implementation and is a superset of the new file.

---

## Files to Change

| File | Action |
|------|--------|
| `utils/sandpits_new.py` | Delete |

---

## Testing Plan

- [ ] Confirm no imports of sandpits_new: `grep -rn "sandpits_new" /home/seven/swarm --include="*.py"` → 0 results
- [ ] Delete the file
- [ ] Restart swarm-terminal and confirm clean startup (no import errors)

---

## Risk Assessment

- **Risk Level**: VERY LOW ✅
- File is confirmed unimported. Deletion has zero runtime impact.
- `sandpits.py` (the real file) is untouched.

---

## Dependencies

- None.

---

## Proposed by Nine

Discovered during full codebase audit, 2026-03-29.
