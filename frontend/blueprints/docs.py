"""docs.py — Docs & Project Files routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

docs_bp = Blueprint('docs', __name__)

# Docs directory setup
import os as _os

_DOCS_DIR = _os.path.join(_os.path.dirname(__file__), '..', '..', 'docs')

_DOC_DESCRIPTIONS = {
    '00_index.html':        'Master index — all sections, quick-reference tables',
    '01_overview.html':     'What it is, hardware, the three-layer architecture',
    '02_agents.html':       'All agents, personalities, temperatures, roles',
    '03_pipeline.html':     'Email, Terminal, Telegram and Eight pipeline flows',
    '04_database.html':     'All tables, schema, memory design',
    '05_files.html':        'Complete file reference with code highlights',
    '06_access.html':       'Trust levels, Ghost commands, Fridays trust ladder',
    '07_ghost_circle.html': 'Claude API advisory layer, ghost_circle table',
    '08_sessions.html':     'Chronological build log, all sessions',
    '09_roadmap.html':      'What\'s done, what\'s next, backlog phases',
}




@docs_bp.route('/api/docs')
def api_docs():
    docs = []

    # HTML docs (legacy export set)
    html_dir = _os.path.join(_DOCS_DIR, 'html')
    if _os.path.isdir(html_dir):
        for f in sorted(_os.listdir(html_dir)):
            if f.endswith('.html') and f != 'swarm_flow_v3.html':
                path = _os.path.join(html_dir, f)
                mtime = datetime.fromtimestamp(_os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
                docs.append({
                    'filename': f,
                    'title': f,
                    'description': _DOC_DESCRIPTIONS.get(f, ''),
                    'size': _os.path.getsize(path),
                    'kind': 'html',
                    'section': 'html',
                    'modified_at': mtime,
                })

    # Markdown/text docs at docs root + docs/testing for live operational docs
    md_roots = [
        (_DOCS_DIR, 'root'),
        (_os.path.join(_DOCS_DIR, 'testing'), 'testing'),
    ]
    for base, section in md_roots:
        if not _os.path.isdir(base):
            continue
        for f in sorted(_os.listdir(base)):
            if not f.lower().endswith(('.md', '.txt', '.log')):
                continue
            path = _os.path.join(base, f)
            rel = f if section == 'root' else f'{section}/{f}'
            mtime = datetime.fromtimestamp(_os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
            docs.append({
                'filename': rel,
                'title': f,
                'description': '',
                'size': _os.path.getsize(path),
                'kind': 'text',
                'section': section,
                'modified_at': mtime,
            })

    # Newest first for operational visibility
    docs.sort(key=lambda d: d.get('modified_at', ''), reverse=True)
    return jsonify(docs)



@docs_bp.route('/api/docs/text/<path:filename>')
def api_docs_text(filename):
    """Serve markdown/text docs from docs roots for modal viewing."""
    if not filename or '..' in filename or filename.startswith('/'):
        return jsonify({'ok': False, 'error': 'invalid filename'}), 400

    candidates = []
    # Allow both explicit subpaths (e.g. testing/ALM_TEST_SPECIFICATION.md)
    # and basename lookups (e.g. ALM_DRIVER.md).
    candidates.append(_os.path.normpath(_os.path.join(_DOCS_DIR, filename)))
    basename = _os.path.basename(filename)
    candidates.append(_os.path.normpath(_os.path.join(_DOCS_DIR, basename)))
    candidates.append(_os.path.normpath(_os.path.join(_DOCS_DIR, 'testing', basename)))

    allowed_roots = [
        _os.path.normpath(_DOCS_DIR),
        _os.path.normpath(_os.path.join(_DOCS_DIR, 'testing')),
    ]

    picked = None
    for path in candidates:
        if not any(path.startswith(root + _os.sep) or path == root for root in allowed_roots):
            continue
        if _os.path.isfile(path) and path.lower().endswith(('.md', '.txt', '.log', '.json')):
            picked = path
            break

    if not picked:
        return jsonify({'ok': False, 'error': 'not found'}), 404

    with open(picked, encoding='utf-8') as fh:
        content = fh.read()
    return jsonify({'ok': True, 'filename': _os.path.basename(picked), 'content': content})



@docs_bp.route('/docs/html/<filename>')
def serve_doc_html(filename):
    """Serve a raw HTML doc file (used by iframe in the docs accordion)."""
    if not filename.endswith('.html') or '/' in filename or '..' in filename:
        return 'Not found', 404
    path = _os.path.join(_DOCS_DIR, 'html', filename)
    if not _os.path.isfile(path):
        return 'Not found', 404
    with open(path, encoding='utf-8') as fh:
        content = fh.read()
    return content, 200, {'Content-Type': 'text/html; charset=utf-8'}



@docs_bp.route('/docs/download/<filename>')
def download_doc_html(filename):
    """Download an HTML doc file."""
    if not filename.endswith('.html') or '/' in filename or '..' in filename:
        return 'Not found', 404
    path = _os.path.join(_DOCS_DIR, 'html', filename)
    if not _os.path.isfile(path):
        return 'Not found', 404
    from flask import send_file
    return send_file(path, as_attachment=True, download_name=filename,
                     mimetype='text/html')



@docs_bp.route('/api/project-md')
def api_project_md():
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})



@docs_bp.route('/api/project-md', methods=['POST'])
def api_project_md_save():
    """Save edited PROJECT.md content from the dashboard."""
    data    = request.get_json() or {}
    content = data.get('content', '')
    if not content:
        return jsonify({'error': 'empty content'}), 400
    path = '/home/seven/swarm/docs/PROJECT.md'
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    log_activity('terminal', 'project_md_saved', f'{len(content)} chars')
    return jsonify({'ok': True, 'chars': len(content)})



@docs_bp.route('/api/kb/seed-swarm-docs', methods=['POST'])
def api_kb_seed_swarm_docs():
    """
    Seed the KB with key PROJECT.md sections so agents can read about the system.
    Idempotent — updates existing docs, inserts new ones.
    """
    import re
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'PROJECT.md not found'}), 404

    with open(path, encoding='utf-8') as fh:
        text = fh.read()

    # Split into H2 sections
    sections = re.split(r'\n(?=## )', text)
    seeded = 0
    conn = get_connection()
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        heading = lines[0].lstrip('#').strip()
        content = '\n'.join(lines).strip()
        if len(content) < 40:
            continue
        # Determine which agents see this
        if any(k in heading for k in ('SAP', 'Eight')):
            tags = 'eight'
        elif any(k in heading for k in ('Ghost', 'Nine', 'Layer')):
            tags = 'all'
        else:
            tags = 'all'

        doc_name = f'[Swarm] {heading}'
        existing = conn.execute(
            "SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE doc_name=?",
                (content[:4000], tags, doc_name)
            )
        else:
            conn.execute(
                "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                (doc_name, content[:4000], tags)
            )
        seeded += 1

    conn.commit()
    conn.close()
    log_activity('terminal', 'kb_seeded', f'{seeded} sections from PROJECT.md')
    return jsonify({'ok': True, 'sections_seeded': seeded})



@docs_bp.route('/api/project-md/raw')
def api_project_md_raw():
    from flask import send_file as _sf
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return 'Not found', 404
    return _sf(path, as_attachment=True, download_name='PROJECT.md', mimetype='text/markdown')



@docs_bp.route('/api/testing-md')
def api_testing_md():
    """Return the content of UAT_TEST_SCRIPTS.md for the dashboard."""
    path = '/home/seven/swarm/docs/UAT_TEST_SCRIPTS.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})



@docs_bp.route('/api/bugs-md')
def api_bugs_md():
    """Return the content of BUGS.md for the dashboard."""
    path = '/home/seven/swarm/docs/BUGS.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})



@docs_bp.route('/api/testing/run-simulation', methods=['POST'])
def api_run_simulation():
    """Trigger simulate.py and return the output captured from stdout/stderr."""
    import subprocess
    import os
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'run_simulation')
    if gate:
        return gate
    try:
        script_path = '/home/seven/swarm/utils/simulate.py'
        # Run via the current interpreter to ensure paths and env are correct
        result = subprocess.run([sys.executable, script_path], 
                                capture_output=True, text=True, timeout=600)
        return jsonify({
            'ok': result.returncode == 0,
            'output': result.stdout + result.stderr
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



