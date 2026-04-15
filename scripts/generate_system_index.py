#!/usr/bin/env python3
"""
scripts/generate_system_index.py — Auto-generate swarm_docs/SYSTEM_INDEX.md
═══════════════════════════════════════════════════════════════════════════════
Scans the repo and produces a machine+human readable index of:
  - Python modules (docstrings)
  - JS view modules
  - Flask blueprints (route counts)
  - DB tables
  - Registered agents
  - Skills

Run:  python3 scripts/generate_system_index.py
Also callable as a skill: SKILL system_index
"""

import ast
import os
import sqlite3
import sys
import glob
import datetime

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'frontend'))

DB_PATH = os.path.join(SWARM_ROOT, 'swarm_memory.db')
OUT_PATH = os.path.join(SWARM_ROOT, 'swarm_docs', 'SYSTEM_INDEX.md')


def _docstring(filepath):
    """Extract module-level docstring from a Python file."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            tree = ast.parse(f.read(), filename=filepath)
        ds = ast.get_docstring(tree)
        if ds:
            return ds.split('\n')[0].strip()
    except Exception:
        pass
    return ''


def _count_routes(filepath):
    """Count @bp.route decorators in a blueprint file."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            return sum(1 for line in f if '.route(' in line)
    except Exception:
        return 0


def _db_tables():
    """List all tables in swarm_memory.db with row counts."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        result = []
        for t in tables:
            try:
                cnt = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except Exception:
                cnt = '?'
            result.append((t, cnt))
        conn.close()
        return result
    except Exception:
        return []


def _agents():
    """List all agents from the DB."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, model, role, tier, enabled FROM agents ORDER BY number ASC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _skills():
    """List skills from the DB."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name, description FROM skills ORDER BY name").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def generate():
    lines = []
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append(f'# SYSTEM INDEX\n')
    lines.append(f'*Auto-generated: {now}*\n')

    # ── Python modules ────────────────────────────────────────────────────
    lines.append('\n## Python Modules\n')
    for pattern, label in [
        ('utils/**/*.py', 'Utils'),
        ('core/**/*.py', 'Core'),
        ('agents/**/*_agent.py', 'Agent Modules'),
        ('fridays/**/*.py', 'Fridays / Skills'),
        ('lib/**/*.py', 'Lib'),
    ]:
        files = sorted(glob.glob(os.path.join(SWARM_ROOT, pattern), recursive=True))
        files = [f for f in files if '__pycache__' not in f]
        if not files:
            continue
        lines.append(f'\n### {label}\n')
        lines.append('| File | Description |')
        lines.append('|------|-------------|')
        for fp in files:
            rel = os.path.relpath(fp, SWARM_ROOT)
            ds = _docstring(fp) or '—'
            lines.append(f'| `{rel}` | {ds} |')

    # ── Flask Blueprints ──────────────────────────────────────────────────
    lines.append('\n## Flask Blueprints\n')
    bp_dir = os.path.join(SWARM_ROOT, 'frontend', 'blueprints')
    bp_files = sorted(glob.glob(os.path.join(bp_dir, '*.py')))
    bp_files = [f for f in bp_files if '__pycache__' not in f and '__init__' not in f]
    lines.append('| Blueprint | Routes | Description |')
    lines.append('|-----------|--------|-------------|')
    for fp in bp_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        routes = _count_routes(fp)
        ds = _docstring(fp) or '—'
        lines.append(f'| `{name}` | {routes} | {ds} |')

    # ── JS View Modules ──────────────────────────────────────────────────
    lines.append('\n## JS View Modules\n')
    js_dir = os.path.join(SWARM_ROOT, 'frontend', 'static', 'js', 'views')
    js_files = sorted(glob.glob(os.path.join(js_dir, '*.js')))
    lines.append('| Module | Size |')
    lines.append('|--------|------|')
    for fp in js_files:
        name = os.path.basename(fp)
        size = os.path.getsize(fp)
        lines.append(f'| `{name}` | {size / 1024:.1f} KB |')

    # ── DB Tables ────────────────────────────────────────────────────────
    lines.append('\n## Database Tables\n')
    tables = _db_tables()
    if tables:
        lines.append('| Table | Rows |')
        lines.append('|-------|------|')
        for t, cnt in tables:
            lines.append(f'| `{t}` | {cnt} |')
    else:
        lines.append('*No database found.*\n')

    # ── Agents ───────────────────────────────────────────────────────────
    lines.append('\n## Agents\n')
    agents = _agents()
    if agents:
        lines.append('| Name | Model | Tier | Role | Enabled |')
        lines.append('|------|-------|------|------|---------|')
        for a in agents:
            en = '✅' if a.get('enabled', 1) else '❌'
            lines.append(f'| `{a["name"]}` | {a.get("model","")} | {a.get("tier","")} | {a.get("role","")} | {en} |')
    else:
        lines.append('*No agents registered.*\n')

    # ── Skills ───────────────────────────────────────────────────────────
    lines.append('\n## Skills\n')
    skills = _skills()
    if skills:
        lines.append('| Skill | Description |')
        lines.append('|-------|-------------|')
        for s in skills:
            lines.append(f'| `{s["name"]}` | {s.get("description", "")} |')
    else:
        lines.append('*No skills registered.*\n')

    content = '\n'.join(lines) + '\n'

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        f.write(content)
    return OUT_PATH, len(lines)


if __name__ == '__main__':
    path, n = generate()
    print(f'Generated {path} ({n} lines)')
