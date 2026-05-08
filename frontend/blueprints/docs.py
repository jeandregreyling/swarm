"""docs.py — Docs & Project Files routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

docs_bp = Blueprint('docs', __name__)

# Docs directory setup
import os as _os

_DOCS_DIR = _os.path.join(_os.path.dirname(__file__), '..', '..', 'docs')
_SWARM_ROOT = _os.environ.get('SWARM_ROOT',
              _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))

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
    path = _os.path.join(_SWARM_ROOT, 'docs/PROJECT.md')
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
    path = _os.path.join(_SWARM_ROOT, 'docs/PROJECT.md')
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
    path = _os.path.join(_SWARM_ROOT, 'docs/PROJECT.md')
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
    path = _os.path.join(_SWARM_ROOT, 'docs/PROJECT.md')
    if not _os.path.isfile(path):
        return 'Not found', 404
    return _sf(path, as_attachment=True, download_name='PROJECT.md', mimetype='text/markdown')



@docs_bp.route('/api/testing-md')
def api_testing_md():
    """Return the content of the canonical testing doc for the dashboard.

    The historical UAT_TEST_SCRIPTS.md was archived in 2026-04; prefer the
    live ALM test spec, falling back through known alternatives so this
    endpoint never 404s when *some* testing doc exists on disk.
    """
    candidates = (
        'docs/testing/ALM_TEST_SPECIFICATION.md',
        'docs/testing/E2E_TEST_SUITE.md',
        'docs/testing/COMPREHENSIVE_TEST_PLAN_2026-04-01.md',
        'docs/UAT_TEST_SCRIPTS.md',                 # legacy, may be absent
        'docs/archive/UAT_TEST_SCRIPTS.md',         # archived original
    )
    for rel in candidates:
        path = _os.path.join(_SWARM_ROOT, rel)
        if _os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                return jsonify({'content': fh.read(), 'source': rel})
    return jsonify({'error': 'no testing doc on disk', 'tried': list(candidates)}), 404



@docs_bp.route('/api/bugs-md')
def api_bugs_md():
    """Return the content of BUGS.md for the dashboard."""
    path = _os.path.join(_SWARM_ROOT, 'docs/BUGS.md')
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})



@docs_bp.route('/api/search/global')
def api_search_global():
    """Fast full-text search across docs/ markdown files and KB workspace docs."""
    q = (request.args.get('q') or '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})

    q_lower = q.lower()
    results = []
    _DOC_CAP = 8  # reserve budget for other result types below

    # --- Walk all .md files under docs/ ---
    for dirpath, _dirs, files in _os.walk(_DOCS_DIR):
        # Skip html subdir (binary-ish exports)
        if _os.path.join(_DOCS_DIR, 'html') in dirpath:
            continue
        for fname in sorted(files):
            if not fname.lower().endswith(('.md', '.txt')):
                continue
            fpath = _os.path.join(dirpath, fname)
            try:
                with open(fpath, encoding='utf-8', errors='ignore') as fh:
                    lines = fh.readlines()
            except Exception:
                continue
            rel = _os.path.relpath(fpath, _DOCS_DIR)
            section_title = fname.replace('.md', '').replace('_', ' ').title()
            for i, line in enumerate(lines):
                if q_lower in line.lower():
                    # Grab a snippet: previous line + match + next line
                    start = max(0, i - 1)
                    end = min(len(lines), i + 2)
                    snippet = ''.join(lines[start:end]).strip()[:200]
                    results.append({
                        'type': 'doc',
                        'title': section_title,
                        'filename': rel,
                        'snippet': snippet,
                        'section': _os.path.dirname(rel) or 'root',
                        'line': i + 1,
                    })
                    break  # one hit per file
        if sum(1 for r in results if r['type'] == 'doc') >= _DOC_CAP:
            break
    # Hard cap on docs so other groups get visibility
    _docs = [r for r in results if r['type'] == 'doc'][:_DOC_CAP]
    results = _docs

    # --- Search KB workspace docs (project_docs table) ---
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT doc_name, content FROM project_docs WHERE "
            "LOWER(doc_name) LIKE ? OR LOWER(content) LIKE ? LIMIT 6",
            (f'%{q_lower}%', f'%{q_lower}%')
        ).fetchall()
        conn.close()
        for row in rows:
            content = row['content'] or ''
            idx = content.lower().find(q_lower)
            snippet = content[max(0, idx-60):idx+140].strip() if idx >= 0 else content[:160].strip()
            results.append({
                'type': 'kb',
                'title': row['doc_name'],
                'filename': None,
                'snippet': snippet,
                'section': 'workspace',
                'line': None,
            })
    except Exception:
        pass

    # --- Tickets (open + recent) ---
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT ticket_number, status, question, created_at FROM tickets "
            "WHERE LOWER(question) LIKE ? OR LOWER(ticket_number) LIKE ? "
            "ORDER BY created_at DESC LIMIT 5",
            (f'%{q_lower}%', f'%{q_lower}%')
        ).fetchall()
        conn.close()
        for row in rows:
            question = (row['question'] or '')[:200]
            results.append({
                'type': 'ticket',
                'title': f"#{row['ticket_number']} · {row['status']}",
                'ticket_number': row['ticket_number'],
                'snippet': question,
                'section': 'tickets',
            })
    except Exception:
        pass

    # --- Work proposals (title + description) ---
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT proposal_id, title, status, description FROM work_proposals "
            "WHERE LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(proposal_id) LIKE ? "
            "ORDER BY id DESC LIMIT 5",
            (f'%{q_lower}%', f'%{q_lower}%', f'%{q_lower}%')
        ).fetchall()
        conn.close()
        for row in rows:
            desc = (row['description'] or '')[:180]
            results.append({
                'type': 'proposal',
                'title': f"{row['proposal_id']} · {row['status']}",
                'proposal_id': row['proposal_id'],
                'snippet': (row['title'] or '') + (f' — {desc}' if desc else ''),
                'section': 'proposals',
            })
    except Exception:
        pass

    # --- Conversations (by title or recent preview) ---
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, source, created_at FROM conversations "
            "WHERE LOWER(title) LIKE ? ORDER BY created_at DESC LIMIT 5",
            (f'%{q_lower}%',)
        ).fetchall()
        conn.close()
        for row in rows:
            results.append({
                'type': 'conversation',
                'title': row['title'] or f"Conversation #{row['id']}",
                'conversation_id': row['id'],
                'snippet': f"{row['source'] or 'chat'} · {(row['created_at'] or '')[:16]}",
                'section': 'conversations',
            })
    except Exception:
        pass

    # --- Memory (memories table, if present) ---
    try:
        conn = get_connection()
        # Be schema-tolerant: try common memory table layouts.
        rows = []
        for sql in (
            "SELECT id, content FROM memories WHERE LOWER(content) LIKE ? ORDER BY id DESC LIMIT 5",
            "SELECT id, note AS content FROM memory WHERE LOWER(note) LIKE ? ORDER BY id DESC LIMIT 5",
        ):
            try:
                rows = conn.execute(sql, (f'%{q_lower}%',)).fetchall()
                if rows:
                    break
            except Exception:
                continue
        conn.close()
        for row in rows:
            content = (row['content'] or '')[:200]
            results.append({
                'type': 'memory',
                'title': f"Memory #{row['id']}",
                'memory_id': row['id'],
                'snippet': content,
                'section': 'memory',
            })
    except Exception:
        pass

    # Sort: docs first by title relevance, then kb, then everything else.
    _type_order = {'doc': 0, 'kb': 1, 'ticket': 2, 'proposal': 3,
                   'conversation': 4, 'memory': 5}
    results.sort(key=lambda r: (
        _type_order.get(r.get('type'), 9),
        q_lower not in (r.get('title') or '').lower(),
    ))
    return jsonify({'results': results[:24]})


_GUIDE_SECTIONS = [
    {
        'id': 'welcome',
        'title': 'Welcome to Fridays',
        'icon': '🏠',
        'content': """# Welcome to Fridays

**Fridays** is Seven's Swarm — a personal AI system running locally on a Dell OptiPlex 7090 in Melbourne, Australia. It is owned and operated by Ghost One (Jeandre).

## What is this?

Fridays is a multi-agent AI orchestration platform. It runs a constellation of 18+ AI agents that can:

- **Chat** with you via the Fridays interface, email, or terminal
- **Research** topics using the internet (LLaMA agent)
- **Reason deeply** through complex problems (Qwen agent)
- **Remember** everything in a persistent knowledge library
- **Execute** autonomous tasks via the Vortex pipeline
- **Monitor** system health in real-time

## Getting Started

1. **Chat** — press `Ctrl+J` or click the Chat tile to start a conversation with Gemma (the orchestrator)
2. **Search** — press `Ctrl+Space` to open Spotlight search across all docs and knowledge
3. **Knowledge** — press `Ctrl+B` to open the Knowledge Center
4. **Terminal** — open a terminal tile for direct shell access

## The Three Layers

| Layer | What it does |
|-------|-------------|
| **Ghost Layer** | You — the human operator. Highest trust. |
| **Gemma Layer** | Orchestrator — routes tasks, synthesises responses |
| **Agent Layer** | Specialists — LLaMA (research), Qwen (reasoning), etc. |
"""
    },
    {
        'id': 'agents',
        'title': 'Agents & Roles',
        'icon': '🤖',
        'content': """# Agents & Roles

Seven's Swarm runs 18 agents across multiple providers. Each has a distinct role.

## Core Agents

| # | Name | Provider | Role |
|---|------|----------|------|
| 1 | **Gemma** | Ollama (local) | Orchestrator — front of house, routes and synthesises |
| 2 | **LLaMA** | Ollama (local) | Internet researcher — web search, current events |
| 3 | **Qwen** | Ollama (local) | Deep reasoning analyst |
| 4 | **Librarian** | Ollama (local) | Silent memory keeper — never responds directly |
| 5 | **Eight** | Local LLM | SAP specialist pipeline agent |
| 9 | **Nine (Groq)** | Groq API | Fast cloud reasoning |
| 10 | **Ten** | Various | General purpose |
| 11 | **Eleven (Grok)** | xAI | Grok-powered agent |
| 12 | **Twelve (Claude)** | Anthropic | Claude API agent |
| 13 | **Thirteen (HF)** | Hugging Face | HF model specialist |

## Ghost Layer Agents (Advisory)
The Ghost Circle provides additional reasoning via the Claude API for high-stakes decisions.

## How Routing Works
Gemma receives your message and decides:
1. Can I answer this directly? → Responds immediately
2. Does this need research? → Routes to LLaMA
3. Does this need deep analysis? → Routes to Qwen
4. Does this need SAP expertise? → Routes to Eight
5. Should I consult the Ghost Circle? → Elevates to advisory layer
"""
    },
    {
        'id': 'chat',
        'title': 'Using Chat',
        'icon': '💬',
        'content': """# Using Chat

The Chat window is your primary interface with the swarm.

## Opening Chat
- **Keyboard**: `Ctrl+J`
- **Home tile**: Click the Chat card
- **Command Palette**: `Ctrl+K` → type "Chat"

## Sending Messages
- Type your message in the input box
- Press `Enter` to send
- Press `Shift+Enter` for a new line

## Selecting an Agent
Use the agent selector dropdown above the input to direct your message to a specific agent, or leave it on **Auto** to let Gemma route it.

## Chat Features
- **Conversation history** — all conversations are persisted and searchable
- **Agent memory** — agents remember previous interactions
- **File attachments** — drag files into the chat
- **Code highlighting** — code blocks are syntax-highlighted

## Home Chat
The home screen also has an inline chat input at the bottom — this connects directly to Gemma without opening a window.

## Tips
- Be specific about what you want — Gemma routes based on intent
- Use `/` commands for special actions (e.g. `/memory`, `/research`)
- Long-running tasks can be monitored in the Monitor tile
"""
    },
    {
        'id': 'knowledge',
        'title': 'Knowledge & Library',
        'icon': '📚',
        'content': """# Knowledge & Library

The Knowledge Center (`Ctrl+B`) is your unified view of everything the system knows.

## Three Tabs

### Files Tab
Browse the project filesystem. Features:
- Directory navigation with breadcrumbs
- File preview (code, markdown, images)
- Grep search within files
- Pattern-based file search

### Docs Tab
Project documentation — all markdown files, HTML exports, and the workspace.

Sub-tabs:
- **Docs** — all project .md files, searchable
- **Workspace** — editable project documents with version history
- **Ghost Brief** — your personal backlog and notes
- **Pinboard** — deferred items and TODOs with checkbox resolution
- **ALM History** — full audit trail of all system changes

### Library Tab
Semantic knowledge base. Add any content (URLs, PDFs, text, emails) and the system creates embeddings for semantic search.

**Adding knowledge:**
1. Click the `+` button in the Library tab
2. Paste a URL, text, or upload a file
3. Select a category (SAP Corner, Programming, Fridays, General)
4. Click Add — the system processes and embeds it

**Searching:**
Type in the search box — results are ranked by semantic similarity, not just keyword match.

### Guide Tab
This user guide — available offline, always up to date.

## Spotlight Search
Press `Ctrl+Space` anywhere to open the global Spotlight search, which searches across all docs, knowledge, and system commands simultaneously.
"""
    },
    {
        'id': 'studio',
        'title': 'Studio & Proposals',
        'icon': '🎛',
        'content': """# Studio & Proposals

Studio (`Ctrl+P`) is the ALM (Application Lifecycle Management) control center.

## What is ALM?
Every significant change to the system goes through a proposal → approval → execution workflow. This creates a full audit trail and prevents accidental changes.

## Tabs

### Proposals
- View pending proposals (changes waiting for approval)
- Approve or reject proposals
- See what changes are queued

### Git
Live git status, diff viewer, and commit history for the swarm repository.

### Tickets
Feature requests, bugs, and tasks. Each ticket has a status, priority, and audit trail.

### ALM History
Full chronological log of every approved and executed change.

## Creating a Proposal
Proposals are created automatically when agents or the system suggest changes. You can also create one manually from the Studio interface.

## Approving Changes
Click the approve button on any pending proposal. The system executes the change and logs it to the audit trail.
"""
    },
    {
        'id': 'files',
        'title': 'Files & Docs',
        'icon': '📁',
        'content': """# Files & Docs

## Files View
The Files view gives you a full filesystem browser for the swarm project.

**Features:**
- Navigate directories with breadcrumb trail
- Preview files inline (markdown renders, code highlights)
- Search files by name pattern (glob)
- Grep within files for content
- Open files in the Terminal

**Keyboard shortcuts in Files:**
- `Enter` on a file — preview
- `Backspace` — go up one directory

## Docs View
The Docs view (`Documents` in command palette) shows all project documentation.

**File types served:**
- `.md` — Markdown docs (rendered)
- `.html` — Legacy HTML exports (iframe)
- `.txt` / `.log` — Plain text

**Key documents:**
- `PROJECT.md` — Master project reference (57KB)
- `ARCHITECTURE.md` — System architecture
- `API_REFERENCE.md` — All API endpoints
- `BUGS.md` — Known bugs and issues
- `CHANGELOG.md` — Version history
- `FEATURES_TODO.md` — Roadmap and wishlist

## Finding Things
Use `Ctrl+Space` (Spotlight) to search across all docs simultaneously — faster than browsing.
"""
    },
    {
        'id': 'shortcuts',
        'title': 'Keyboard Shortcuts',
        'icon': '⌨️',
        'content': """# Keyboard Shortcuts

## Global

| Shortcut | Action |
|----------|--------|
| `Ctrl+Space` | **Spotlight Search** — search everything |
| `Ctrl+K` | Command Palette — open windows and commands |
| `Ctrl+H` | Go Home |
| `Esc` | Close top modal / window |
| `?` | Show this shortcuts reference |

## Quick Open

| Shortcut | Opens |
|----------|-------|
| `Ctrl+J` | Chat |
| `Ctrl+B` | Knowledge Center |
| `Ctrl+P` | Studio / Proposals |
| `Ctrl+T` | Tickets |
| `Ctrl+G` | Studio → Git tab |
| `Ctrl+E` | Email |

## Chat

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |

## Terminal

| Shortcut | Action |
|----------|--------|
| `Enter` | Execute command |
| `↑` / `↓` | Command history |

## Tips
- Most shortcuts work from anywhere — no need to click first
- `Ctrl+K` then type to fuzzy-search all available windows
- `Ctrl+Space` searches docs, knowledge, and commands simultaneously
"""
    },
    {
        'id': 'settings',
        'title': 'Settings & Themes',
        'icon': '⚙️',
        'content': """# Settings & Themes

## Opening Settings
Click the ⚙️ gear icon in the top-right corner of any page.

## Themes
Fridays supports multiple visual themes:

- **Auto** — follows your system dark/light preference
- **Dark** — always dark
- **Light** — always light
- **Diamond** — premium glass-morphism theme

The theme also shifts automatically based on time of day (the "sundial" system) when set to Auto.

## Sundial System
The sundial in the top-left shows live system metrics:
- **CPU** — processor load
- **RAM** — memory usage
- **V-RAM** — swap usage (48GB SSD swap for running large models)
- **GPU** — GPU VRAM usage

Hover over any ray to see the value and description.

## Window Management
- **Drag** window headers to move
- **Drag** window edges/corners to resize
- **Minimize** — sends window to taskbar at bottom
- **Maximize** — fills the viewport
- **Pin** — keeps window on top

## Per-Window Themes
Each floating window has its own theme toggle — useful if you want the chat window dark but docs light.

## Environment Banner
The colored banner at the top shows which environment is active (dev/staging/prod). Click it for environment details.
"""
    },
]


@docs_bp.route('/api/guide')
def api_guide():
    """Return the structured user guide sections."""
    # Return section metadata (without full content for the index)
    sections = [{'id': s['id'], 'title': s['title'], 'icon': s['icon']} for s in _GUIDE_SECTIONS]
    return jsonify({'sections': sections})


@docs_bp.route('/api/guide/<section_id>')
def api_guide_section(section_id):
    """Return the content for a specific guide section."""
    for s in _GUIDE_SECTIONS:
        if s['id'] == section_id:
            return jsonify({'id': s['id'], 'title': s['title'], 'icon': s['icon'], 'content': s['content']})
    return jsonify({'error': 'not found'}), 404


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
        script_path = _os.path.join(_SWARM_ROOT, 'utils/simulate.py')
        # Run via the current interpreter to ensure paths and env are correct
        result = subprocess.run([sys.executable, script_path], 
                                capture_output=True, text=True, timeout=600)
        return jsonify({
            'ok': result.returncode == 0,
            'output': result.stdout + result.stderr
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500





# ── STEP-DOCS-MANUAL-RELATABLE-UX-20260430 ──────────────────────────────────
# Convert doc/manual UX feedback into a tracked project step instead of a
# chat-only note. Posts land in a dedicated 'P-DOCS-UX' project so they don't
# muddy the main burn-down list, and each note becomes its own step the team
# can pick up in priority order. The endpoint is idempotent on (topic, doc):
# repeated submissions for the same target append to the description rather
# than spawning duplicate steps, so iterative feedback consolidates cleanly.

import time as _time
import uuid as _uuid

_DOCS_UX_PROJECT = 'P-DOCS-UX'


def _docs_ux_ensure_project(conn):
    row = conn.execute(
        "SELECT project_id FROM projects WHERE project_id=?",
        (_DOCS_UX_PROJECT,),
    ).fetchone()
    if row:
        return
    now = _time.time()
    conn.execute(
        "INSERT INTO projects (project_id, name, description, methodology, status, owner, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (_DOCS_UX_PROJECT, 'Docs & Manual UX', 'Doc/manual UX feedback collected from the interactive manual.',
         'mixed', 'active', 'seven', now, now),
    )


@docs_bp.route('/api/docs/feedback', methods=['POST'])
def api_docs_feedback():
    """Record doc/manual UX feedback as a project step.

    Body: {topic: str, note: str, doc?: str, severity?: 'low'|'med'|'high'}
    """
    data = request.get_json(silent=True) or {}
    topic = (data.get('topic') or '').strip()[:120]
    note  = (data.get('note')  or '').strip()
    doc   = (data.get('doc')   or '').strip()[:200]
    severity = (data.get('severity') or 'med').strip().lower()
    if severity not in {'low', 'med', 'high'}:
        severity = 'med'
    if not topic or not note:
        return jsonify({'ok': False, 'error': 'topic and note are required'}), 400

    note = note[:4000]
    title = f'Docs UX · {topic}' if not doc else f'Docs UX · {topic} ({doc})'
    now = _time.time()

    conn = get_connection()
    try:
        _docs_ux_ensure_project(conn)
        # Idempotent merge: same (topic, doc) → append.
        existing = conn.execute(
            "SELECT step_id, description FROM project_steps "
            "WHERE project_id=? AND title=?",
            (_DOCS_UX_PROJECT, title),
        ).fetchone()
        if existing:
            step_id = existing['step_id'] if hasattr(existing, 'keys') else existing[0]
            prev    = (existing['description'] if hasattr(existing, 'keys') else existing[1]) or ''
            stamp   = _time.strftime('%Y-%m-%d %H:%M:%S')
            new_desc = f"{prev}\n\n--- {stamp} [{severity}] ---\n{note}".strip()
            conn.execute(
                "UPDATE project_steps SET description=?, updated_at=? WHERE step_id=?",
                (new_desc[:8000], now, step_id),
            )
            conn.commit()
            return jsonify({'ok': True, 'step_id': step_id, 'merged': True,
                            'project_id': _DOCS_UX_PROJECT})
        step_id = f'STEP-DOCS-UX-{_uuid.uuid4().hex[:10].upper()}'
        desc = f"[{severity}] {note}"
        if doc:
            desc = f"Doc: {doc}\n\n{desc}"
        conn.execute(
            "INSERT INTO project_steps (step_id, project_id, title, description, status, owner, order_idx, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (step_id, _DOCS_UX_PROJECT, title, desc[:8000], 'todo', 'seven', 0, now, now),
        )
        conn.commit()
        return jsonify({'ok': True, 'step_id': step_id, 'merged': False,
                        'project_id': _DOCS_UX_PROJECT})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
    finally:
        conn.close()


@docs_bp.route('/api/docs/feedback', methods=['GET'])
def api_docs_feedback_list():
    """List doc UX feedback steps (todo first, newest first)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT step_id, title, description, status, updated_at FROM project_steps "
            "WHERE project_id=? ORDER BY (status='done'), updated_at DESC LIMIT 100",
            (_DOCS_UX_PROJECT,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                'step_id': r['step_id'] if hasattr(r, 'keys') else r[0],
                'title':   r['title']   if hasattr(r, 'keys') else r[1],
                'description': (r['description'] if hasattr(r, 'keys') else r[2]) or '',
                'status':  r['status']  if hasattr(r, 'keys') else r[3],
                'updated_at': r['updated_at'] if hasattr(r, 'keys') else r[4],
            })
        return jsonify({'ok': True, 'project_id': _DOCS_UX_PROJECT, 'items': out})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
    finally:
        conn.close()
