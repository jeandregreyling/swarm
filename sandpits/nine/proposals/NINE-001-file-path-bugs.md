# NINE-001: Fix Broken File Path References in terminal.py

**Status**: PROPOSED
**Proposal ID**: NINE-001
**Proposed**: 2026-03-29
**Agent**: Nine (System Architect · Ghost Layer)
**Priority**: CRITICAL

---

## Issue

Four API endpoints in `frontend/terminal.py` build file paths relative to `__file__` (the terminal.py location in `frontend/`), but the files they reference were moved to `docs/` and `utils/` during the March 28 reorganisation. All four endpoints currently return 404 or fail silently.

---

## Affected Endpoints

### 1. `/api/project-md` (GET + POST) — terminal.py:920, 934, 948, 1000
```python
path = _os.path.join(_os.path.dirname(__file__), 'PROJECT.md')
# Resolves to: /home/seven/swarm/frontend/PROJECT.md  ❌ DOES NOT EXIST
# Actual file:  /home/seven/swarm/docs/PROJECT.md
```
**Impact**: Dashboard "PROJECT.md" view always returns 404. Ghost cannot read or edit PROJECT.md from the dashboard.

### 2. `/api/testing-md` (GET) — terminal.py:1009
```python
path = _os.path.join(_os.path.dirname(__file__), 'UAT_TEST_SCRIPTS.md')
# Resolves to: /home/seven/swarm/frontend/UAT_TEST_SCRIPTS.md  ❌ DOES NOT EXIST
# Actual file:  /home/seven/swarm/docs/UAT_TEST_SCRIPTS.md
```
**Impact**: Testing scripts view in dashboard always returns 404.

### 3. `/api/bugs-md` (GET) — terminal.py:1019
```python
path = _os.path.join(_os.path.dirname(__file__), 'BUGS.md')
# Resolves to: /home/seven/swarm/frontend/BUGS.md  ❌ DOES NOT EXIST
# Actual file:  /home/seven/swarm/docs/BUGS.md
```
**Impact**: Bugs view in dashboard always returns 404.

### 4. `/api/testing/run-simulation` (POST) — terminal.py:1032
```python
script_path = os.path.join(os.path.dirname(__file__), 'simulate.py')
# Resolves to: /home/seven/swarm/frontend/simulate.py  ❌ DOES NOT EXIST
# Actual file:  /home/seven/swarm/utils/simulate.py
```
**Impact**: Simulation runner always fails with FileNotFoundError or subprocess error.

---

## Root Cause

The March 28 reorganisation moved files from root/flat structure into subdirectories:
- `PROJECT.md` → `docs/PROJECT.md`
- `UAT_TEST_SCRIPTS.md` → `docs/UAT_TEST_SCRIPTS.md`
- `BUGS.md` → `docs/BUGS.md`
- `simulate.py` → `utils/simulate.py`

The `terminal.py` routes were not updated to reflect the new paths. The `_DOCS_DIR` variable already correctly resolves to `../docs` (used for HTML docs), but the individual file paths were not updated to use it or the equivalent pattern.

---

## Proposed Fix

Define a `_SWARM_ROOT` constant near the top of `terminal.py` and use it consistently:

```python
# Near top of terminal.py, after _DOCS_DIR definition:
_SWARM_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))

# Then fix each path:
# /api/project-md → _os.path.join(_DOCS_DIR, 'PROJECT.md')
# /api/testing-md → _os.path.join(_DOCS_DIR, 'UAT_TEST_SCRIPTS.md')
# /api/bugs-md    → _os.path.join(_DOCS_DIR, 'BUGS.md')
# /api/testing/run-simulation → _os.path.join(_SWARM_ROOT, 'utils', 'simulate.py')
```

Note: `_DOCS_DIR` is already defined at terminal.py:797 as `../docs` — reuse it.

---

## Files to Change

| File | Lines | Change |
|------|-------|--------|
| `frontend/terminal.py` | 920, 934, 948, 1000, 1009, 1019, 1032 | Fix 4 path references to use correct locations |

Total change: ~7 line edits. No new files. No schema changes. No service restarts needed (Flask reloads on change if debug mode, or service restart).

---

## Testing Plan

- [ ] `curl http://127.0.0.1:5050/api/project-md` → returns JSON with `content` key, not 404
- [ ] `curl http://127.0.0.1:5050/api/testing-md` → returns JSON with `content` key, not 404
- [ ] `curl http://127.0.0.1:5050/api/bugs-md` → returns JSON with `content` key, not 404
- [ ] POST to `/api/testing/run-simulation` → runs utils/simulate.py without FileNotFoundError
- [ ] Open dashboard, verify PROJECT.md view, bugs view, testing view all render content

---

## Risk Assessment

- **Risk Level**: LOW ✅
- **Impact**: Read-only path fixes. No data mutation. No schema changes.
- **Rollback**: Revert 7 line edits.

---

## Dependencies

- None. Standalone fix.

---

## Proposed by Nine

Discovered during full codebase audit, 2026-03-29.
All four paths verified broken by tracing `__file__` → `frontend/terminal.py` → resolution to non-existent files.
