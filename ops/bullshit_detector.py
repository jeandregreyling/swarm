"""Bullshit detector — Seven's quality scanner.

Scans the active codebase for the patterns banned by docs/the-standard.md
and returns a structured report. Seven calls `summary_for_seven()` every
turn so he can tell the user the truth about the build.

Run from CLI:   python -m ops.bullshit_detector
Run from code:  from ops.bullshit_detector import scan, summary_for_seven

Exit code is non-zero when the build is not up to standard.
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent

# Directories that are explicitly NOT shipped code — patterns inside them
# do not count against the build.
EXEMPT_DIR_PARTS = {
    'tests', 'Archives', 'archive', '.git', '.venv', 'node_modules',
    'sandpits', 'sandpits_stage1', 'sandpits_stage2', 'sandpits_stage3',
    'logs', 'attachments', 'models', '__pycache__', 'swarm_docs',
    'swarm-discord', 'swarm-fridays', '.history', 'themes',
    # Tooling, not shipped server code:
    'scripts', 'ops', 'examples', 'desktop', 'windows', 'fridays',
    'audit',
}

EXEMPT_FILE_SUFFIXES = ('.bak', '.backup', '.old', '.orig')
EXEMPT_FILE_GLOBS = ('*.bak.*', '*.backup.*', 'swarm_memory.db.*', 'swarm.db.*')


# ── Pattern bank ────────────────────────────────────────────────────────
# Each rule: (rule_id, severity, file_glob, regex, human_message)
# Severities: 'critical' (build red), 'warning' (yellow), 'info'.
RULES = [
    # Slop markers in shipped code. Word-boundary, but skip lines that
    # explicitly disclaim them (e.g. 'not a TODO'), the regex itself escaping
    # the rule (a pipe-joined list like `TODO|FIXME` in a UI default), and
    # the standard doc which *describes* these as forbidden.
    ('TODO_MARKER', 'warning', ('*.py', '*.js', '*.html'),
     re.compile(r'(?<![A-Za-z_])(?<!not a )(?<!Not a )(TODO|FIXME|XXX|HACK)(?![|A-Za-z0-9_])'),
     'Slop marker left in shipped code'),

    # Placeholder bodies
    ('PLACEHOLDER_PASS', 'critical', ('*.py',),
     re.compile(r'pass\s*#\s*(placeholder|stub|not implemented|tbd)', re.IGNORECASE),
     'Placeholder pass-statement'),

    # NotImplementedError outside abstract bases (best-effort: any occurrence)
    ('NOT_IMPLEMENTED', 'warning', ('*.py',),
     re.compile(r'raise\s+NotImplementedError'),
     'NotImplementedError in shipped code'),

    # Bare except
    ('BARE_EXCEPT', 'warning', ('*.py',),
     re.compile(r'^\s*except\s*:\s*(#.*)?$', re.MULTILINE),
     'Bare `except:` — must be `except Exception:` or specific'),

    # Console.log / print debug
    ('JS_CONSOLE_LOG', 'info', ('*.js',),
     re.compile(r'^\s*console\.log\(', re.MULTILINE),
     'console.log in shipped JS (wrap in window.__SWARM_DEBUG)'),

    ('PY_PRINT_DEBUG', 'info', ('*.py',),
     re.compile(r'(?<![A-Za-z_])print\(\s*[\'"]\s*(debug|test|here|wtf|hello)\b', re.IGNORECASE),
     'Debug print left in Python'),

    # Hard-coded localhost is informational by default — most hits are local
    # model runtimes (Ollama 11434, LM Studio 1234, ComfyUI 8188) or in-process
    # CLI help strings. The detector still surfaces them so we can audit; it
    # just doesn't fail the build over them.
    ('HARDCODED_LOCALHOST', 'info', ('*.py',),
     re.compile(r'(127\.0\.0\.1|localhost)(?!:(?:11434|1234|1235|8188))', re.IGNORECASE),
     'Local URL reference — use config/env if it crosses a process boundary'),

    # Wishlist regression: capture-only after promotion
    ('CAPTURE_ONLY_REGRESSION', 'critical', ('terminal_base.html',),
     re.compile(r'data-wishlist-status\s*=\s*"capture-only"'),
     'Tile regressed to capture-only'),

    # Wishlist regression: tile description still says "capture only" even
    # though the tile is promoted. Catches the description-text mismatch the
    # data-attr rule missed.
    ('CAPTURE_ONLY_DESC', 'critical', ('terminal_base.html',),
     re.compile(r'(?i)\bcapture[\s-]only\b'),
     'Tile description still says "capture only" — promote or remove'),

    # The Standard forbids vapor language in shipped UI/code.
    ('VAPOR_LANGUAGE', 'warning', ('*.py', '*.js', '*.html'),
     re.compile(r'(?i)coming soon|tbd\b|to be determined|placeholder text'),
     'Vapor language in shipped surface (forbidden by The Standard)'),
]


def _is_exempt_path(path: Path) -> bool:
    parts = set(p.name for p in path.parents) | {path.name}
    if parts & EXEMPT_DIR_PARTS:
        return True
    if path.suffix in EXEMPT_FILE_SUFFIXES:
        return True
    name = path.name
    for glob in EXEMPT_FILE_GLOBS:
        # crude: split on '*' and check substrings in order
        bits = glob.split('*')
        i = 0
        ok = True
        for b in bits:
            if not b:
                continue
            j = name.find(b, i)
            if j < 0:
                ok = False
                break
            i = j + len(b)
        if ok:
            return True
    return False


def _iter_target_files(root: Path) -> Iterable[Path]:
    # Prefer git ls-files (tracked only) for speed and accuracy. Falls back to
    # walking the tree if git is unavailable or this isn't a checkout.
    try:
        import subprocess
        out = subprocess.run(
            ['git', '-C', str(root), 'ls-files'],
            capture_output=True, text=True, timeout=4,
        )
        if out.returncode == 0 and out.stdout.strip():
            for line in out.stdout.splitlines():
                rel = Path(line)
                if _is_exempt_path(rel):
                    continue
                p = root / rel
                if p.is_file():
                    yield p
            return
    except Exception:
        pass
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXEMPT_DIR_PARTS and not d.startswith('.')]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                rel = p.relative_to(root)
            except ValueError:
                continue
            if _is_exempt_path(rel):
                continue
            yield p


def _glob_match(name: str, patterns) -> bool:
    for pat in patterns:
        if pat.startswith('*.'):
            if name.endswith(pat[1:]):
                return True
        elif pat == name:
            return True
    return False


def scan(root: Path | None = None, max_hits_per_rule: int = 200) -> dict:
    """Scan the codebase. Returns a dict suitable for JSON / Seven."""
    root = (root or ROOT).resolve()
    started = time.time()
    hits = []
    files_scanned = 0
    files_with_hits = set()

    # Map rule -> compiled regex + meta
    for fp in _iter_target_files(root):
        try:
            rel = fp.relative_to(root)
        except ValueError:
            continue
        name = fp.name
        try:
            text = fp.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        files_scanned += 1
        for rule_id, severity, globs, regex, msg in RULES:
            if not _glob_match(name, globs):
                continue
            for match in regex.finditer(text):
                # compute line number
                line_no = text.count('\n', 0, match.start()) + 1
                line_text = text.splitlines()[line_no - 1].strip() if line_no - 1 < len(text.splitlines()) else ''
                # Self-exemption: explicit per-line opt-outs. `ok-bullshit`
                # (legacy) and `detector:ignore` (current) both forgive a
                # single line. Use sparingly — the line must legitimately
                # reference the marker (e.g. the rule itself, a UI default,
                # or quality-check code that scans for the same word).
                if 'ok-bullshit' in line_text or 'detector:ignore' in line_text:
                    continue
                hits.append({
                    'rule': rule_id,
                    'severity': severity,
                    'message': msg,
                    'path': str(rel),
                    'line': line_no,
                    'snippet': line_text[:200],
                })
                files_with_hits.add(str(rel))
                # cap per-rule output to avoid runaway reports
                if sum(1 for h in hits if h['rule'] == rule_id) >= max_hits_per_rule:
                    break

    by_severity = {'critical': 0, 'warning': 0, 'info': 0}
    by_rule = {}
    for h in hits:
        by_severity[h['severity']] = by_severity.get(h['severity'], 0) + 1
        by_rule[h['rule']] = by_rule.get(h['rule'], 0) + 1

    # Pillar contract checks (cross-file structural)
    pillar_findings = _check_pillar_contract(root)

    score = _score(by_severity, pillar_findings)
    stamp = _stamp(by_severity, pillar_findings)

    return {
        'ok': True,
        'started_ts': int(started),
        'duration_sec': round(time.time() - started, 3),
        'files_scanned': files_scanned,
        'files_with_hits': len(files_with_hits),
        'hits': hits,
        'by_severity': by_severity,
        'by_rule': by_rule,
        'pillar_contract': pillar_findings,
        'score': score,
        'stamp': stamp,
    }


def _check_pillar_contract(root: Path) -> dict:
    findings = []
    bp_dir = root / 'frontend' / 'blueprints'
    expected = {
        'cyber-security': 'cybersecurity_bp.py',
        'financial':      'financial_bp.py',
        'trading':        'trading_bp.py',
        'business':       'business_bp.py',
    }
    have_summary = {}
    for slug, fname in expected.items():
        path = bp_dir / fname
        if not path.exists():
            findings.append({'slug': slug, 'issue': f'blueprint missing: {fname}'})
            have_summary[slug] = False
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        if 'def summary_for_seven' not in text:
            findings.append({'slug': slug, 'issue': 'summary_for_seven() not defined'})
            have_summary[slug] = False
        else:
            have_summary[slug] = True

    # Tile presence + status (template uses data-wishlist-pillar="<slug>")
    tpl = root / 'frontend' / 'templates' / 'terminal_base.html'
    if tpl.exists():
        html = tpl.read_text(encoding='utf-8', errors='replace')
        for slug in expected:
            tile_re_a = re.compile(rf'data-wishlist-pillar\s*=\s*"{re.escape(slug)}"[^>]*data-wishlist-status\s*=\s*"active-v0"')
            tile_re_b = re.compile(rf'data-wishlist-status\s*=\s*"active-v0"[^>]*data-wishlist-pillar\s*=\s*"{re.escape(slug)}"')
            if not (tile_re_a.search(html) or tile_re_b.search(html)):
                findings.append({'slug': slug, 'issue': 'tile not marked active-v0 in terminal_base.html'})
            live_re = re.compile(rf'class="wishlist-pillar-live"[^>]*data-live-slug\s*=\s*"{re.escape(slug)}"')
            if not live_re.search(html):
                findings.append({'slug': slug, 'issue': 'live panel <div data-live-slug> missing'})

    return {
        'findings': findings,
        'have_summary': have_summary,
        'all_clear': not findings,
    }


def _score(by_severity: dict, pillar: dict) -> int:
    """0–100. 100 = pristine. Critical hits and pillar gaps cost real points;
    warnings tax mildly (capped) so a healthy 7k-file repo with a few legacy
    `# TODO` notes can still earn a green stamp once criticals are zero.

    Session 30.2 amendment: when the build has zero critical, zero warning,
    and zero pillar issues, the score is 100 regardless of info items.
    Info items are observational (localhost defaults in config, test URLs,
    etc.) — they do not indicate a build defect and should not prevent a
    perfect score on an otherwise pristine codebase.
    """
    crit = by_severity.get('critical', 0)
    warn = by_severity.get('warning', 0)
    pillar_findings = len(pillar.get('findings', []))

    # Pristine build = 100. Info alone never degrades a perfect build.
    if crit == 0 and warn == 0 and pillar_findings == 0:
        return 100

    s = 100
    s -= 20 * crit
    s -= 10 * pillar_findings
    # Cap warning/info contribution: 30 warnings = -15, 60 = -22 (diminishing)
    import math
    w = warn
    i = by_severity.get('info', 0)
    s -= int(round(15 * (1 - math.exp(-w / 40.0))))
    s -= int(round(5  * (1 - math.exp(-i / 40.0))))
    return max(0, min(100, s))


def _stamp(by_severity: dict, pillar: dict) -> str:
    crit = by_severity.get('critical', 0)
    warn = by_severity.get('warning', 0)
    if crit == 0 and pillar.get('all_clear') and warn <= 10:
        return 'GREEN'
    if crit == 0 and pillar.get('all_clear'):
        return 'AMBER'
    return 'RED'


def summary_for_seven(cache_path: Path | None = None) -> dict:
    """Return a Seven-friendly compact dict. Caches the last full scan to a
    JSON file under .swarm/ so subsequent reads are instant; refreshes if the
    cache is older than 5 minutes.
    """
    cache = cache_path or (ROOT / '.swarm' / 'bullshit_report.json')
    cache.parent.mkdir(exist_ok=True)
    fresh = False
    data = None
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            if int(time.time()) - int(data.get('started_ts', 0)) < 300:
                fresh = True
        except Exception:
            data = None
    if not fresh:
        data = scan()
        try:
            cache.write_text(json.dumps(data, indent=2))
        except Exception:
            pass
    return {
        'pillar': 'bullshit-detector',
        'ok': True,
        'stamp': data['stamp'],
        'score': data['score'],
        'critical': data['by_severity'].get('critical', 0),
        'warnings': data['by_severity'].get('warning', 0),
        'info': data['by_severity'].get('info', 0),
        'files_scanned': data.get('files_scanned', 0),
        'pillar_findings': len(data.get('pillar_contract', {}).get('findings', [])),
        'top_hits': data['hits'][:5],
    }


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    json_out = '--json' in argv
    data = scan()
    if json_out:
        print(json.dumps(data, indent=2))
    else:
        print(f"Bullshit detector — {data['stamp']}  score={data['score']}/100")
        print(f"  files scanned : {data['files_scanned']}")
        print(f"  critical      : {data['by_severity']['critical']}")
        print(f"  warnings      : {data['by_severity']['warning']}")
        print(f"  info          : {data['by_severity']['info']}")
        print(f"  pillar issues : {len(data['pillar_contract']['findings'])}")
        if data['hits']:
            print("\nTop hits:")
            for h in data['hits'][:15]:
                print(f"  [{h['severity']:8}] {h['path']}:{h['line']}  {h['rule']}  — {h['snippet'][:80]}")
        if data['pillar_contract']['findings']:
            print("\nPillar contract:")
            for f in data['pillar_contract']['findings']:
                print(f"  · {f['slug']}: {f['issue']}")
    return 0 if data['stamp'] == 'GREEN' else (1 if data['stamp'] == 'AMBER' else 2)


if __name__ == '__main__':
    sys.exit(main())
