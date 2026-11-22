"""APEX path help (owner 14 Nov 2026): APEX looked for core/DEOS.py three times after DEOS was renamed DOES. A missing file now comes back
with the closest real paths in the repository, so the next call reads the right file instead of repeating the guess."""
import difflib
import os


def did_you_mean(relative, tracked, n=3):
    rel = str(relative or '').strip('/')
    paths = sorted(tracked or ())
    if not rel or not paths:
        return []
    low = {p.lower(): p for p in paths}
    out = [low[m] for m in difflib.get_close_matches(rel.lower(), list(low), n=n, cutoff=0.75)]
    base = os.path.basename(rel).lower()
    for m in difflib.get_close_matches(base, sorted({os.path.basename(p).lower() for p in paths}), n=n, cutoff=0.75):
        out += [p for p in paths if os.path.basename(p).lower() == m and p not in out][:2]
    return out[:n]


def not_found(relative, tracked):
    if str(relative).startswith('tests/test_') and str(relative).endswith('.py'):
        return (f"Workspace source file not found: {relative}. This test file does not exist yet - "
                "create it with propose_write_file instead of calling read_file again.")
    hint = did_you_mean(relative, tracked)
    if hint:
        return (f"Workspace source file not found: {relative}. Did you mean: {', '.join(hint)}? Read that path instead - "
                "do not retry this one.")
    return f"Workspace source file not found: {relative}. Use list_files or grep_repo to resolve the actual import location."
