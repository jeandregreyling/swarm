"""
fridays/tool_builder.py — Tool build pipeline orchestrator (C.2)
═══════════════════════════════════════════════════════════════════════════════
Stages: scaffold → validate → test → register

Agents invoke this via SKILL build_tool, SKILL tool_validate, etc.
Each stage updates the tool_builds record and integrates with ALM governance.
═══════════════════════════════════════════════════════════════════════════════
"""

import ast
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logger = logging.getLogger('seven.tool_builder')

_TEMPLATE_DIR = Path(__file__).parent.parent / 'skills' / 'templates'

# Tool type → (template file, test template file, language, file extension)
TOOL_CONFIGS = {
    'script': ('python_script.py.tpl', 'test_python_script.py.tpl', 'python', '.py'),
    'skill':  ('python_skill.py.tpl',  'test_python_skill.py.tpl',  'python', '.py'),
    'widget': ('js_widget.js.tpl',     None,                        'javascript', '.js'),
    'cron':   ('cron_job.py.tpl',      'test_cron_job.py.tpl',      'python', '.py'),
    'shell':  ('shell_script.sh.tpl',  None,                        'shell', '.sh'),
}


# ── Scaffold stage ────────────────────────────────────────────────────────

def build_tool(tool_type, name, description, agent, *, conn=None):
    """
    Scaffold a new tool from template and create a build record.
    Returns (build_id, entry_path).
    """
    from utils.db.tools import create_build, update_build

    if tool_type not in TOOL_CONFIGS:
        raise ValueError(f"Unknown tool_type {tool_type!r}. Valid: {list(TOOL_CONFIGS)}")

    tpl_file, test_tpl_file, language, ext = TOOL_CONFIGS[tool_type]
    safe_name = re.sub(r'[^a-z0-9_]', '_', name.lower().strip())
    if not safe_name:
        raise ValueError('Tool name must contain at least one alphanumeric character')

    # Determine output paths
    agent_dir = Path(os.environ.get('SWARM_ROOT', str(Path(__file__).parent.parent)))
    sandpit = agent_dir / 'sandpits' / agent / 'tools'
    sandpit.mkdir(parents=True, exist_ok=True)

    entry_path = sandpit / f'{safe_name}{ext}'
    test_path = ''

    # Read and substitute template
    now = datetime.now().strftime('%Y-%m-%d')
    module_name = safe_name

    tpl = (_TEMPLATE_DIR / tpl_file).read_text(encoding='utf-8')
    content = _substitute(tpl, name=name, safe_name=safe_name,
                          description=description, agent=agent, date=now,
                          module_name=module_name)
    entry_path.write_text(content, encoding='utf-8')

    # Scaffold test file if template exists
    if test_tpl_file and (_TEMPLATE_DIR / test_tpl_file).exists():
        test_file = sandpit / f'test_{safe_name}.py'
        test_tpl = (_TEMPLATE_DIR / test_tpl_file).read_text(encoding='utf-8')
        test_content = _substitute(test_tpl, name=name, safe_name=safe_name,
                                   description=description, agent=agent, date=now,
                                   module_name=module_name)
        test_file.write_text(test_content, encoding='utf-8')
        test_path = str(test_file)

    # Make shell scripts executable
    if ext == '.sh':
        entry_path.chmod(entry_path.stat().st_mode | 0o755)

    # Create build record
    build_id = create_build(
        tool_name=name,
        tool_type=tool_type,
        description=description,
        building_agent=agent,
        language=language,
        conn=conn,
    )
    update_build(
        build_id,
        entry_path=str(entry_path),
        test_path=test_path,
        conn=conn,
    )

    logger.info(f'[ToolBuilder] scaffolded build={build_id} type={tool_type} '
                f'name={name!r} path={entry_path}')
    return build_id, str(entry_path)


# ── Validate stage ────────────────────────────────────────────────────────

def validate_tool(build_id, *, conn=None):
    """
    Syntax-check the tool's entry file.
    Returns (ok: bool, message: str).
    """
    from utils.db.tools import get_build, update_build

    build = get_build(build_id, conn=conn)
    if build is None:
        return False, f'Build #{build_id} not found'

    entry = build['entry_path']
    if not entry or not os.path.isfile(entry):
        return False, f'Entry file not found: {entry}'

    update_build(build_id, status='validating', conn=conn)
    lang = build['language']

    try:
        if lang == 'python':
            ok, msg = _validate_python(entry)
        elif lang == 'javascript':
            ok, msg = _validate_js(entry)
        elif lang == 'shell':
            ok, msg = _validate_shell(entry)
        else:
            ok, msg = True, f'No validator for {lang}, skipping'

        status = 'passed' if ok else 'failed'
        update_build(build_id, test_output=msg, status=status if not ok else build['status'],
                     conn=conn)
        # On validation success, move to building (ready for test)
        if ok:
            update_build(build_id, status='building', conn=conn)
        return ok, msg
    except Exception as e:
        update_build(build_id, status='failed', test_output=str(e), conn=conn)
        return False, str(e)


def _validate_python(path):
    """AST-parse a Python file."""
    with open(path, encoding='utf-8') as f:
        source = f.read()
    try:
        ast.parse(source)
        return True, f'OK — {os.path.basename(path)} has no syntax errors'
    except SyntaxError as e:
        return False, f'SyntaxError at line {e.lineno}: {e.msg}'


def _validate_js(path):
    """Node --check a JavaScript file."""
    try:
        result = subprocess.run(
            ['node', '--check', path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, f'OK — {os.path.basename(path)} has no JS syntax errors'
        return False, result.stderr[:600]
    except FileNotFoundError:
        return True, 'node not found — validation skipped'
    except Exception as e:
        return False, str(e)


def _validate_shell(path):
    """bash -n syntax check."""
    try:
        result = subprocess.run(
            ['bash', '-n', path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, f'OK — {os.path.basename(path)} has no shell syntax errors'
        return False, result.stderr[:600]
    except Exception as e:
        return False, str(e)


# ── Test stage ────────────────────────────────────────────────────────────

def test_tool(build_id, *, conn=None):
    """
    Run the tool's test suite.
    Returns (ok: bool, output: str).
    """
    from utils.db.tools import get_build, update_build

    build = get_build(build_id, conn=conn)
    if build is None:
        return False, f'Build #{build_id} not found'

    test_path = build['test_path']
    entry_path = build['entry_path']

    update_build(build_id, status='testing', conn=conn)

    if test_path and os.path.isfile(test_path):
        ok, output = _run_pytest(test_path, os.path.dirname(entry_path))
    elif build['language'] == 'python' and entry_path:
        # No test file — try dry-run
        ok, output = _run_dryrun_python(entry_path)
    elif build['language'] == 'shell' and entry_path:
        ok, output = _run_dryrun_shell(entry_path)
    else:
        ok, output = True, 'No test file — skipped'

    status = 'passed' if ok else 'failed'
    update_build(build_id, status=status, test_output=output[:4000], conn=conn)
    logger.info(f'[ToolBuilder] test build={build_id} status={status}')
    return ok, output


def _run_pytest(test_path, working_dir):
    """Run pytest on a test file."""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', test_path, '--tb=short', '-q'],
            capture_output=True, text=True, timeout=30,
            cwd=working_dir,
            env={**os.environ, 'PYTHONPATH': working_dir},
        )
        output = (result.stdout + result.stderr)[:4000]
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, 'Test timed out (30s limit)'
    except Exception as e:
        return False, f'Test runner error: {e}'


def _run_dryrun_python(entry_path):
    """Run a Python tool with --dry-run."""
    try:
        result = subprocess.run(
            [sys.executable, entry_path, '--dry-run'],
            capture_output=True, text=True, timeout=15,
        )
        output = (result.stdout + result.stderr)[:2000]
        return result.returncode == 0, output
    except Exception as e:
        return False, f'Dry-run failed: {e}'


def _run_dryrun_shell(entry_path):
    """Run a shell tool with --dry-run."""
    try:
        result = subprocess.run(
            ['bash', entry_path, '--dry-run'],
            capture_output=True, text=True, timeout=15,
        )
        output = (result.stdout + result.stderr)[:2000]
        return result.returncode == 0, output
    except Exception as e:
        return False, f'Dry-run failed: {e}'


# ── Register stage ────────────────────────────────────────────────────────

def register_tool(build_id, *, conn=None):
    """
    Mark a passing build as registered and publish to knowledge + bus.
    Returns (ok: bool, message: str).
    """
    from utils.db.tools import get_build, update_build

    build = get_build(build_id, conn=conn)
    if build is None:
        return False, f'Build #{build_id} not found'

    if build['status'] not in ('passed', 'building'):
        return False, f'Build #{build_id} status is {build["status"]!r}, must be passed or building'

    update_build(build_id, status='registered', conn=conn)

    # Archive to knowledge
    try:
        from utils.db.knowledge import write_knowledge
        from utils.swarm_bus import publish as bus_publish

        write_knowledge(
            key=f'tool:{build["tool_type"]}:{build["tool_name"]}',
            content=(
                f'{build["description"]}\n'
                f'Type: {build["tool_type"]} | Language: {build["language"]}\n'
                f'Path: {build["entry_path"]}\n'
                f'Builder: {build["building_agent"]} | Status: registered'
            ),
            source_agent=build['building_agent'],
            category='tool',
            importance=6,
            conn=conn,
        )

        bus_publish(
            topic='tool.registered',
            payload={
                'build_id': build_id,
                'tool_name': build['tool_name'],
                'tool_type': build['tool_type'],
                'building_agent': build['building_agent'],
            },
            source_service='tool_builder',
            conn=conn,
        )
    except Exception as e:
        logger.warning(f'[ToolBuilder] knowledge/bus publish failed: {e}')

    logger.info(f'[ToolBuilder] registered build={build_id} name={build["tool_name"]!r}')
    return True, f'Tool "{build["tool_name"]}" registered (build #{build_id})'


# ── Template substitution ─────────────────────────────────────────────────

def _substitute(template, *, name, safe_name, description, agent, date, module_name):
    """Replace {{PLACEHOLDERS}} in a template string."""
    return (template
            .replace('{{TOOL_NAME}}', name)
            .replace('{{SAFE_NAME}}', safe_name)
            .replace('{{DESCRIPTION}}', description)
            .replace('{{AGENT}}', agent)
            .replace('{{DATE}}', date)
            .replace('{{MODULE_NAME}}', module_name))


def list_templates():
    """Return available template types and their descriptions."""
    out = []
    for tool_type, (tpl, test_tpl, lang, ext) in TOOL_CONFIGS.items():
        has_test = test_tpl is not None
        out.append({
            'type': tool_type,
            'language': lang,
            'extension': ext,
            'has_test_template': has_test,
            'template_file': tpl,
        })
    return out
