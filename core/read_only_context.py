"""Bounded, read-only context retrieval for restricted local agent profiles."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger('core.read_only_context')

REPO_ROOT = Path(__file__).resolve().parents[1]
VORTEX_ROOT = Path(os.environ.get('SWARM_VORTEX_LEDGER_ROOT', '/mnt/archive/vortex'))
_SEARCH_SCOPES = ('agents', 'core', 'fridays', 'frontend', 'lib', 'utils', 'config.py')
_SEARCH_GLOBS = (
    '*.py', '*.js', '*.ts', '*.tsx', '*.jsx', '*.json', '*.yaml', '*.yml',
    '*.toml', '*.sql', '*.md', '*.sh',
)
_EXCLUDED_GLOBS = (
    '!**/.env*',
    '!**/*secret*',
    '!**/*credential*',
    '!**/*token*',
    '!**/.git/**',
    '!**/.venv*/**',
    '!**/__pycache__/**',
    '!**/node_modules/**',
    '!**/sandpits/**',
    '!**/logs/**',
    '!**/attachments/**',
    '!**/models/**',
    '!**/*.db*',
)
_STOP_WORDS = frozenset({
    'about', 'after', 'also', 'because', 'from', 'have', 'into', 'just',
    'more', 'should', 'that', 'their', 'there', 'these', 'this', 'those',
    'what', 'when', 'where', 'which', 'with', 'would', 'your',
})
_SECRET_ASSIGNMENT_RE = re.compile(
    r'(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)'
    r'["\']?(\s*[:=]\s*)(["\']?)[^\s,"\'}]+'
)
_BEARER_RE = re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+')
_KNOWN_TOKEN_RE = re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,})\b')


def _terms(query: Any, limit: int = 5) -> list[str]:
    found = []
    for value in re.findall(r'[A-Za-z0-9_]{3,40}', str(query or '').lower()):
        if value in _STOP_WORDS or value in found:
            continue
        found.append(value)
        if len(found) >= limit:
            break
    return found


def _sanitize_excerpt(value: Any, limit: int = 400) -> str:
    text = str(value or '')
    text = _BEARER_RE.sub('Bearer [REDACTED]', text)
    text = _SECRET_ASSIGNMENT_RE.sub(r'\1\2[REDACTED]', text)
    text = _KNOWN_TOKEN_RE.sub('[REDACTED]', text)
    return text[:limit]


def _repository_matches(query: str) -> tuple[list[dict[str, str]], str | None]:
    terms = _terms(query)
    if not terms:
        return [], None
    rg = shutil.which('rg')
    if not rg:
        logger.error('Read-only repository retrieval requires ripgrep (rg)')
        return [], None

    pattern = '|'.join(re.escape(term) for term in terms)
    command = [
        rg, '--ignore-case', '--no-heading', '--line-number', '--color=never',
        '--max-columns=220', '--max-columns-preview', '--max-count=1',
        '--max-filesize=256K', '-e', pattern,
    ]
    for glob in _SEARCH_GLOBS:
        command.extend(('-g', glob))
    for glob in _EXCLUDED_GLOBS:
        command.extend(('-g', glob))
    scopes = [scope for scope in _SEARCH_SCOPES if (REPO_ROOT / scope).exists()]
    command.extend(('--', *scopes))
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=4,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning('Read-only repository retrieval timed out')
        return [], None
    except OSError:
        logger.exception('Read-only repository retrieval could not run ripgrep')
        return [], None
    if result.returncode not in (0, 1):
        logger.error('Read-only repository retrieval failed: %s', _sanitize_excerpt(result.stderr, 300))
        return [], None

    matches: list[dict[str, str]] = []
    seen_paths: list[str] = []
    for raw_line in result.stdout.splitlines():
        try:
            rel_path, line_number, excerpt = raw_line.split(':', 2)
        except ValueError:
            continue
        rel_path = rel_path.replace('\\', '/')
        if rel_path.startswith('/') or any(part in {'..', '.env', '.git'} for part in Path(rel_path).parts):
            continue
        matches.append({
            'path': rel_path,
            'line': line_number,
            'excerpt': _sanitize_excerpt(excerpt, 240),
        })
        if rel_path not in seen_paths:
            seen_paths.append(rel_path)
        if len(matches) >= 8:
            break
    history_path = seen_paths[0] if seen_paths else None
    return matches, history_path


def _git_history(path: str | None) -> list[str]:
    if not path or not shutil.which('git'):
        return []
    try:
        history = subprocess.run(
            ['git', 'log', '--all', '--max-count=2', '--format=%h%x09%cs%x09%s', '--', path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning('Read-only Git history retrieval timed out for %s', path)
        return []
    except OSError:
        logger.exception('Read-only Git history retrieval failed for %s', path)
        return []
    if history.returncode:
        logger.warning('Read-only Git history query failed for %s: %s', path, _sanitize_excerpt(history.stderr, 200))
        return []

    lines = [
        f'commit { _sanitize_excerpt(line, 240) }'
        for line in history.stdout.splitlines()
        if line.strip()
    ]
    if not lines:
        return []

    commit = history.stdout.splitlines()[0].split('\t', 1)[0].strip()
    try:
        diff = subprocess.run(
            [
                'git', 'show', '--format=', '--no-ext-diff', '--no-renames',
                '--unified=1', commit, '--', path,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning('Read-only Git diff retrieval timed out for %s', path)
        return lines
    except OSError:
        logger.exception('Read-only Git diff retrieval failed for %s', path)
        return lines
    if diff.returncode:
        logger.warning('Read-only Git diff query failed for %s: %s', path, _sanitize_excerpt(diff.stderr, 200))
        return lines

    safe_diff = [
        _sanitize_excerpt(line, 220)
        for line in diff.stdout.splitlines()
        if line.startswith(('diff --git ', 'index ', '--- ', '+++ ', '@@', '+', '-'))
    ]
    if safe_diff:
        lines.append('latest relevant diff:\n' + '\n'.join(safe_diff[:18]))
    return lines


def _vortex_events(query: str, limit: int = 5) -> list[dict[str, str]]:
    terms = _terms(query)
    index_dir = VORTEX_ROOT / 'indexes'
    if not index_dir.is_dir():
        logger.warning('Vortex index directory is unavailable: %s', index_dir)
        return []
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=90)
    scored: list[tuple[int, str, dict[str, str]]] = []
    for path in sorted(index_dir.glob('*.jsonl'), reverse=True):
        try:
            partition_date = datetime.strptime(path.stem, '%Y-%m-%d').date()
        except ValueError:
            continue
        if partition_date < cutoff or partition_date > today:
            continue
        if path.is_symlink():
            continue
        try:
            with path.open('rb') as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                offset = max(0, size - 16 * 1024)
                stream.seek(offset)
                raw_data = stream.read()
            if offset:
                raw_data = raw_data.split(b'\n', 1)[-1]
            for raw_line in raw_data.decode('utf-8', errors='replace').splitlines():
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    logger.warning('Ignoring malformed Vortex index row in %s', path.name)
                    continue
                if not isinstance(event, dict):
                    logger.warning('Ignoring non-object Vortex index row in %s', path.name)
                    continue
                event_terms = event.get('terms') if isinstance(event.get('terms'), list) else []
                searchable = ' '.join(
                    str(value)[:100]
                    for value in (
                        event.get('source_agent'),
                        event.get('target_agent'),
                        event.get('action_type'),
                        event.get('execution_status'),
                        event.get('kind'),
                        event.get('source'),
                        *event_terms[:50],
                    )
                ).lower()
                score = sum(1 for term in terms if term in searchable) if terms else 1
                if score:
                    scored.append((score, str(event.get('timestamp') or ''), {
                        'timestamp': str(event.get('timestamp') or ''),
                        'source_agent': str(event.get('source_agent') or ''),
                        'target_agent': str(event.get('target_agent') or ''),
                        'action_type': str(event.get('action_type') or ''),
                        'status': str(event.get('execution_status') or ''),
                        'context_hash': str(event.get('payload_context_hash') or ''),
                    }))
        except OSError:
            logger.exception('Could not read Vortex ledger partition %s', path)
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:limit]]


def _vortex_checkpoints(query: str, limit: int = 4) -> list[dict[str, str]]:
    terms = _terms(query)
    try:
        from utils.db._connection import get_connection

        conn = get_connection()
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='time_checkpoints'"
            ).fetchone()
            if not exists:
                return []
            where = ''
            params: list[Any] = []
            if terms:
                where = ' WHERE ' + ' OR '.join(
                    '(LOWER(checkpoint_name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(agent) LIKE ?)'
                    for _ in terms
                )
                for term in terms:
                    pattern = f'%{term}%'
                    params.extend((pattern, pattern, pattern))
            rows = conn.execute(
                'SELECT checkpoint_name, timestamp, description, agent '
                'FROM time_checkpoints' + where + ' ORDER BY timestamp DESC LIMIT ?',
                (*params, limit),
            ).fetchall()
            return [
                {
                    'name': _sanitize_excerpt(row['checkpoint_name'], 120),
                    'timestamp': _sanitize_excerpt(row['timestamp'], 40),
                    'agent': _sanitize_excerpt(row['agent'], 80),
                    'description': _sanitize_excerpt(row['description'], 240),
                }
                for row in rows
            ]
        finally:
            conn.close()
    except Exception:
        logger.exception('Read-only Vortex checkpoint retrieval failed')
        return []


def build_local_agent_context(agent_name: str, query: str, *, max_chars: int = 5000) -> str:
    """Retrieve bounded repository, Git, Vortex, and checkpoint context without writes."""
    matches, history_path = _repository_matches(query)
    history = _git_history(history_path)
    events = _vortex_events(query)
    checkpoints = _vortex_checkpoints(query)
    sections = []
    if matches:
        sections.append(
            'Repository source matches:\n' + '\n'.join(
                f"- {item['path']}:{item['line']}: {item['excerpt']}" for item in matches
            )
        )
    if history:
        sections.append('Relevant commit history and diff:\n' + '\n'.join(history))
    if events:
        sections.append(
            'Vortex execution history (metadata and hashes only):\n' + '\n'.join(
                '- {timestamp} {source_agent} -> {target_agent} {action_type} '
                'status={status} hash={context_hash}'.format(**item)
                for item in events
            )
        )
    if checkpoints:
        sections.append(
            'Vortex checkpoints:\n' + '\n'.join(
                '- {timestamp} {name} by {agent}: {description}'.format(**item)
                for item in checkpoints
            )
        )

    try:
        from core.vortex_ledger import hash_context, record_action

        record_action(
            'context_retrieval',
            source_agent=agent_name,
            target_agent='local_read_only_corpus',
            status='completed' if sections else 'no_results',
            context_parts=(query,),
            details={
                'repository_matches': len(matches),
                'git_history_records': len(history),
                'vortex_events': len(events),
                'checkpoints': len(checkpoints),
                'query_hash': hash_context(query),
            },
            source='local_context.retrieval',
        )
    except Exception:
        logger.exception('Could not record local read-only context retrieval')

    if not sections:
        return '(no matching local repository, Vortex, or checkpoint context)'
    return '\n\n'.join(sections)[:max_chars]
