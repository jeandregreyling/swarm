"""Compact project context packs for local agents and Studio previews."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional


_STOPWORDS = {
    'about', 'after', 'again', 'agent', 'agents', 'also', 'and', 'are',
    'can', 'continue', 'could', 'for', 'from', 'have', 'into', 'local',
    'make', 'need', 'needs', 'next', 'now', 'our', 'please', 'project',
    'should', 'show', 'system', 'task', 'that', 'the', 'their', 'then',
    'this', 'through', 'update', 'what', 'when', 'with', 'work',
}


def normalize_project_context_text(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_project_context_text(value).split()
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _phrase_windows(tokens: List[str], size: int) -> List[str]:
    if len(tokens) < size:
        return []
    return [' '.join(tokens[i:i + size]) for i in range(0, len(tokens) - size + 1)]


def resolve_project_context_id(text: str) -> str:
    text = str(text or '')
    match = re.search(r'\bP-[A-Z0-9]{10}\b', text.upper())
    if match:
        return match.group(0)

    enriched_text = enrich_project_trigger_text(text)
    normalized_text = normalize_project_context_text(enriched_text)
    if not normalized_text:
        return ''
    try:
        from core.knowledge import projects as _projects
        best = ('', 0.0)
        runner_up = 0.0
        for project_row in _projects.list_projects(status='active', limit=80):
            project_id = str(project_row.get('project_id') or '')
            name = str(project_row.get('name') or '')
            normalized_name = normalize_project_context_text(name)
            if normalized_name and normalized_name in normalized_text:
                return project_id
            tokens = [t for t in normalized_name.split() if len(t) >= 5]
            if tokens and all(t in normalized_text for t in tokens[:2]):
                return project_id
            score = score_project_context_match(enriched_text, project_id)
            if score > best[1]:
                runner_up = best[1]
                best = (project_id, score)
            elif score > runner_up:
                runner_up = score
        if best[0] and best[1] >= 6 and best[1] >= runner_up + 1:
            return best[0]
    except Exception:
        return ''
    return ''


def enrich_project_trigger_text(text: str) -> str:
    """Expand text with matching interests, research topics, and task actions."""
    text = str(text or '')
    input_tokens = _tokens(text)
    if not input_tokens:
        return text

    additions: List[str] = []

    def maybe_add(*parts: Any) -> None:
        phrase = ' '.join(str(part or '') for part in parts if str(part or '').strip())
        phrase_tokens = _tokens(phrase)
        if not phrase_tokens:
            return
        overlap = input_tokens & phrase_tokens
        normalized_phrase = normalize_project_context_text(phrase)
        normalized_text = normalize_project_context_text(text)
        distinctive_overlap = any(len(token) >= 6 for token in overlap)
        if len(overlap) >= 2 or distinctive_overlap or normalized_phrase in normalized_text or normalized_text in normalized_phrase:
            additions.append(phrase)

    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            for sql, mapper in (
                (
                    """SELECT topic, category, source_agent
                       FROM user_interests
                       WHERE active=1
                       ORDER BY score DESC, updated_at DESC
                       LIMIT 40""",
                    lambda row: (row['topic'], row['category'], row['source_agent']),
                ),
                (
                    """SELECT topic, summary
                       FROM research_sessions
                       ORDER BY updated_at DESC
                       LIMIT 40""",
                    lambda row: (row['topic'], row['summary']),
                ),
                (
                    """SELECT name, action_data
                       FROM scheduled_tasks
                       WHERE enabled=1
                       ORDER BY id DESC
                       LIMIT 80""",
                    lambda row: (row['name'], row['action_data']),
                ),
            ):
                try:
                    rows = conn.execute(sql).fetchall()
                except Exception:
                    rows = []
                for row in rows:
                    maybe_add(*mapper(row))
        finally:
            conn.close()
    except Exception:
        pass

    if not additions:
        return text
    return text + '\n' + '\n'.join(additions[:12])


def project_context_doc_rows(project_id: str, project_name: str, limit: int = 3) -> List[Dict[str, Any]]:
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT doc_name, content
                FROM project_docs
                WHERE tags LIKE ? OR doc_name LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (f'%{project_id}%', f'%{str(project_name or "")[:80]}%', int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def _project_match_blob(bundle: Dict[str, Any], docs: List[Dict[str, Any]]) -> str:
    project = bundle.get('project') or {}
    parts: List[str] = [
        project.get('project_id'),
        project.get('name'),
        project.get('description'),
        project.get('methodology'),
        project.get('status'),
    ]
    for step in bundle.get('steps') or []:
        parts += [step.get('title'), step.get('description'), step.get('status'), step.get('owner')]
    for case in bundle.get('test_cases') or []:
        parts += [case.get('title'), case.get('script_id'), case.get('status'), case.get('owner')]
    for note in bundle.get('blackboard_notes') or []:
        parts += [note.get('author'), note.get('kind'), note.get('content'), note.get('status')]
    for doc in docs or []:
        parts += [doc.get('doc_name'), str(doc.get('content') or '')[:1200]]
    return '\n'.join(str(part or '') for part in parts)


def score_project_context_match(text: str, project_id: str) -> float:
    """Return a confidence score for routing text to a project context pack."""
    project_id = str(project_id or '').strip()
    enriched_text = enrich_project_trigger_text(text)
    input_tokens = _tokens(enriched_text)
    if not project_id or len(input_tokens) < 2:
        return 0.0
    try:
        from core.knowledge import projects as _projects
        bundle = _projects.get_project(project_id)
    except Exception:
        bundle = None
    if not bundle:
        return 0.0

    project = bundle.get('project') or {}
    project_name = str(project.get('name') or project_id)
    docs = project_context_doc_rows(project_id, project_name, limit=5)
    blob = _project_match_blob(bundle, docs)
    blob_norm = normalize_project_context_text(blob)
    blob_tokens = _tokens(blob)
    if not blob_tokens:
        return 0.0

    overlap = input_tokens & blob_tokens
    score = float(len(overlap) * 1.5)
    project_name_norm = normalize_project_context_text(project_name)
    if project_name_norm and project_name_norm in normalize_project_context_text(enriched_text):
        score += 50.0

    ordered_tokens = [
        token
        for token in normalize_project_context_text(enriched_text).split()
        if len(token) >= 3 and token not in _STOPWORDS
    ]
    for size, weight in ((4, 5.0), (3, 3.5), (2, 2.0)):
        for phrase in _phrase_windows(ordered_tokens, size):
            if phrase in blob_norm:
                score += weight
    return score


def build_project_context_block(
    text: str = '',
    *,
    project_id: Optional[str] = None,
    doc_loader: Optional[Callable[[str, str, int], List[Dict[str, Any]]]] = None,
    doc_limit: int = 3,
    note_limit: int = 5,
) -> str:
    project_id = str(project_id or '').strip() or resolve_project_context_id(text)
    if not project_id:
        return ''
    try:
        from core.knowledge import projects as _projects
        bundle = _projects.get_project(project_id)
    except Exception:
        bundle = None
    if not bundle:
        return ''

    project = bundle.get('project') or {}
    steps = bundle.get('steps') or []
    cases = bundle.get('test_cases') or []
    blackboard = bundle.get('blackboard_notes') or []
    project_name = str(project.get('name') or project_id)
    description = ' '.join(str(project.get('description') or '').split())[:600]
    current_steps = [s for s in steps if str(s.get('status') or '') in {'doing', 'blocked', 'todo'}][:8]
    done_steps = [s for s in steps if str(s.get('status') or '') == 'done'][-5:]
    if not blackboard:
        try:
            blackboard = _projects.list_blackboard_notes(project_id, limit=note_limit)
        except Exception:
            blackboard = []

    loader = doc_loader or project_context_doc_rows
    try:
        docs = loader(project_id, project_name, doc_limit)
    except Exception:
        docs = []

    lines = [
        '\n\n=== Studio project context ===',
        f'Project: {project_name} ({project_id})',
        f"Status: {project.get('status') or 'active'} - Methodology: {project.get('methodology') or 'mixed'}",
    ]
    if description:
        lines += ['', 'Project brief:', description]
    if current_steps:
        lines += ['', 'Current/open steps:']
        for step in current_steps:
            lines.append(f"- [{step.get('status')}] {step.get('title')}")
    if done_steps:
        lines += ['', 'Recently completed steps:']
        for step in done_steps:
            lines.append(f"- {step.get('title')}")
    if cases:
        lines += ['', 'Project tests:']
        for case in cases[-6:]:
            script = str(case.get('script_id') or '').strip()
            suffix = f' - {script[:140]}' if script else ''
            lines.append(f"- [{case.get('status')}] {case.get('title')}{suffix}")
    if blackboard:
        lines += ['', 'Shared project blackboard:']
        for note in blackboard[:note_limit]:
            author = str(note.get('author') or 'agent').strip()
            kind = str(note.get('kind') or 'note').strip()
            content = ' '.join(str(note.get('content') or '').split())[:260]
            if content:
                lines.append(f'- [{kind}] {author}: {content}')
    if docs:
        lines += ['', 'Relevant Knowledge docs:']
        for doc in docs:
            excerpt = ' '.join(str(doc.get('content') or '').split())[:260]
            lines.append(f"- {doc.get('doc_name')}: {excerpt}")
    lines += [
        '',
        'Use this context for continuity, project-specific tests, and next actions. Do not expose private chain-of-thought.',
        '=== End Studio project context ===\n',
    ]
    return '\n'.join(lines)
