#!/usr/bin/env python3
"""
scripts/generate_landscape_json.py — Auto-generate swarm_docs/SYSTEM_LANDSCAPE.json
═══════════════════════════════════════════════════════════════════════════════════════
Machine-queryable JSON landscape index. Extends the MD system index with:
  - Python modules (path + docstring)
  - Flask blueprints (name + route count + routes list)
  - JS view modules (name + size)
  - DB tables (name + row count)
  - Registered agents (name, model, tier, role, enabled)
  - Skills (name, description, trust_level)
  - Frontend buttons/fields (extracted from HTML templates + JS)
  - Workflows / SAP mappings (from docs if present)

Run:  python3 scripts/generate_landscape_json.py
Also callable via: SKILL update_landscape
"""

import ast
import json
import os
import re
import sqlite3
import sys
import glob
import datetime

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'frontend'))

DB_PATH = os.path.join(SWARM_ROOT, 'swarm_memory.db')
OUT_PATH = os.path.join(SWARM_ROOT, 'swarm_docs', 'SYSTEM_LANDSCAPE.json')


def _docstring(filepath):
    try:
        with open(filepath, 'r', errors='replace') as f:
            tree = ast.parse(f.read(), filename=filepath)
        ds = ast.get_docstring(tree)
        if ds:
            return ds.split('\n')[0].strip()
    except Exception:
        pass
    return ''


def _extract_routes(filepath):
    """Extract route paths + methods from a blueprint file."""
    routes = []
    try:
        with open(filepath, 'r', errors='replace') as f:
            for line in f:
                m = re.search(r"\.route\(['\"]([^'\"]+)['\"]", line)
                if m:
                    path = m.group(1)
                    methods = ['GET']
                    mm = re.search(r"methods\s*=\s*\[([^\]]+)\]", line)
                    if mm:
                        methods = [s.strip().strip("'\"") for s in mm.group(1).split(',')]
                    routes.append({'path': path, 'methods': methods})
    except Exception:
        pass
    return routes


def _extract_buttons_from_html(filepath):
    """Extract button ids/classes from HTML template files."""
    buttons = []
    try:
        with open(filepath, 'r', errors='replace') as f:
            content = f.read()
        for m in re.finditer(r'<button[^>]*id=["\']([^"\']+)["\']', content, re.I):
            buttons.append({'id': m.group(1), 'file': os.path.relpath(filepath, SWARM_ROOT)})
        for m in re.finditer(r'<button[^>]*class=["\']([^"\']+)["\']', content, re.I):
            if 'id=' not in content[max(0, m.start()-80):m.start()]:
                buttons.append({'class': m.group(1), 'file': os.path.relpath(filepath, SWARM_ROOT)})
    except Exception:
        pass
    return buttons


def _extract_buttons_from_js(filepath):
    """Extract button/element creation patterns from JS files."""
    buttons = []
    try:
        with open(filepath, 'r', errors='replace') as f:
            content = f.read()
        for m in re.finditer(r'getElementById\(["\']([^"\']+)["\']\)', content):
            buttons.append({'id': m.group(1), 'file': os.path.relpath(filepath, SWARM_ROOT)})
        for m in re.finditer(r'\.id\s*=\s*["\']([^"\']+)["\']', content):
            buttons.append({'id': m.group(1), 'file': os.path.relpath(filepath, SWARM_ROOT)})
    except Exception:
        pass
    return buttons


def _python_modules():
    modules = []
    for pattern, label in [
        ('utils/**/*.py', 'Utils'),
        ('core/**/*.py', 'Core'),
        ('agents/**/*_agent.py', 'Agent Modules'),
        ('fridays/**/*.py', 'Fridays / Skills'),
        ('lib/**/*.py', 'Lib'),
    ]:
        files = sorted(glob.glob(os.path.join(SWARM_ROOT, pattern), recursive=True))
        files = [f for f in files if '__pycache__' not in f]
        for fp in files:
            rel = os.path.relpath(fp, SWARM_ROOT)
            ds = _docstring(fp) or ''
            modules.append({'path': rel, 'group': label, 'description': ds})
    return modules


def _blueprints():
    bp_dir = os.path.join(SWARM_ROOT, 'frontend', 'blueprints')
    bp_files = sorted(glob.glob(os.path.join(bp_dir, '*.py')))
    bp_files = [f for f in bp_files if '__pycache__' not in f and '__init__' not in f]
    result = []
    for fp in bp_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        routes = _extract_routes(fp)
        ds = _docstring(fp) or ''
        result.append({'name': name, 'description': ds, 'routes': routes, 'route_count': len(routes)})
    return result


def _js_views():
    js_dir = os.path.join(SWARM_ROOT, 'frontend', 'static', 'js', 'views')
    js_files = sorted(glob.glob(os.path.join(js_dir, '*.js')))
    result = []
    for fp in js_files:
        name = os.path.basename(fp)
        size = os.path.getsize(fp)
        result.append({'name': name, 'size_kb': round(size / 1024, 1)})
    return result


def _db_tables():
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
                cnt = -1
            result.append({'name': t, 'rows': cnt})
        conn.close()
        return result
    except Exception:
        return []


def _agents():
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
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name, description FROM skills ORDER BY name").fetchall()
        conn.close()
        result = []
        # Enrich with trust_level from the skills module REGISTRY
        try:
            sys.path.insert(0, SWARM_ROOT)
            from fridays.skills import REGISTRY
        except Exception:
            REGISTRY = {}
        for r in rows:
            d = dict(r)
            entry = REGISTRY.get(d['name'], {})
            d['trust_level'] = entry.get('trust_level', 0)
            result.append(d)
        return result
    except Exception:
        return []


def _ui_elements():
    """Extract buttons/fields from HTML templates and JS view files."""
    elements = []
    # HTML templates
    for pattern in ['frontend/templates/**/*.html', 'frontend/templates/*.html']:
        for fp in glob.glob(os.path.join(SWARM_ROOT, pattern), recursive=True):
            elements.extend(_extract_buttons_from_html(fp))
    # JS views
    for fp in glob.glob(os.path.join(SWARM_ROOT, 'frontend', 'static', 'js', 'views', '*.js')):
        elements.extend(_extract_buttons_from_js(fp))
    # Deduplicate by id
    seen = set()
    unique = []
    for el in elements:
        key = el.get('id', el.get('class', ''))
        if key and key not in seen:
            seen.add(key)
            unique.append(el)
    return unique


def generate():
    """Generate the JSON landscape index. Returns (OUT_PATH, total_entry_count)."""
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    data = {
        'generated_at': now,
        'python_modules': _python_modules(),
        'blueprints': _blueprints(),
        'js_views': _js_views(),
        'db_tables': _db_tables(),
        'agents': _agents(),
        'skills': _skills(),
        'ui_elements': _ui_elements(),
    }

    total = sum(len(v) for v in data.values() if isinstance(v, list))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        json.dump(data, f, indent=2)

    return OUT_PATH, total


if __name__ == '__main__':
    path, n = generate()
    print(f'Generated {path} with {n} entries.')
