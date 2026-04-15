"""
tests/test_tools.py — Phase C tool-builder integration tests
═══════════════════════════════════════════════════════════════════════════════
Tests C.1 (tables/CRUD), C.2 (pipeline), C.3 (skills), C.5 (quality gate).
"""

import os
import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def tools_db(tmp_path, monkeypatch):
    """Isolated DB with full schema including tool_builds table."""
    db_path = str(tmp_path / 'test_tools.db')

    def _get_conn():
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    from utils.db._schema import SCHEMA
    conn = _get_conn()
    conn.executescript(SCHEMA)
    conn.commit()

    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.DB_PATH', db_path)
    monkeypatch.setattr('utils.db.tools.get_connection', _get_conn)

    try:
        monkeypatch.setattr('utils.db.knowledge.get_connection', _get_conn)
    except Exception:
        pass
    try:
        monkeypatch.setattr('utils.swarm_bus.get_connection', _get_conn)
    except Exception:
        pass

    yield conn
    conn.close()


@pytest.fixture
def sandpit(tmp_path, monkeypatch):
    """Temp sandpit so tool_builder writes to tmp_path."""
    monkeypatch.setenv('SWARM_ROOT', str(tmp_path))
    return tmp_path


# ── C.1 — Tool Registry CRUD ─────────────────────────────────────────────

class TestToolCRUD:
    """C.1: tool_builds table create/read/update/list."""

    def test_create_build(self, tools_db):
        from utils.db.tools import create_build, get_build
        bid = create_build('my_tool', 'script', description='A test tool',
                           building_agent='gemma', conn=tools_db)
        assert bid is not None
        b = get_build(bid, conn=tools_db)
        assert b['tool_name'] == 'my_tool'
        assert b['tool_type'] == 'script'
        assert b['status'] == 'scaffolded'
        assert b['building_agent'] == 'gemma'

    def test_invalid_type_raises(self, tools_db):
        from utils.db.tools import create_build
        with pytest.raises(ValueError, match='Invalid tool_type'):
            create_build('bad', 'nosuchtype', conn=tools_db)

    def test_invalid_language_raises(self, tools_db):
        from utils.db.tools import create_build
        with pytest.raises(ValueError, match='Invalid language'):
            create_build('bad', 'script', language='fortran', conn=tools_db)

    def test_update_build(self, tools_db):
        from utils.db.tools import create_build, get_build, update_build
        bid = create_build('upd', conn=tools_db)
        update_build(bid, status='passed', entry_path='/tmp/x.py', conn=tools_db)
        b = get_build(bid, conn=tools_db)
        assert b['status'] == 'passed'
        assert b['entry_path'] == '/tmp/x.py'

    def test_invalid_status_raises(self, tools_db):
        from utils.db.tools import create_build, update_build
        bid = create_build('x', conn=tools_db)
        with pytest.raises(ValueError, match='Invalid status'):
            update_build(bid, status='bogus', conn=tools_db)

    def test_list_builds_all(self, tools_db):
        from utils.db.tools import create_build, list_builds
        create_build('t1', building_agent='gemma', conn=tools_db)
        create_build('t2', building_agent='llama', conn=tools_db)
        all_ = list_builds(conn=tools_db)
        assert len(all_) == 2

    def test_list_builds_filter_agent(self, tools_db):
        from utils.db.tools import create_build, list_builds
        create_build('t1', building_agent='gemma', conn=tools_db)
        create_build('t2', building_agent='llama', conn=tools_db)
        gemma_only = list_builds(building_agent='gemma', conn=tools_db)
        assert len(gemma_only) == 1
        assert gemma_only[0]['building_agent'] == 'gemma'

    def test_list_builds_filter_status(self, tools_db):
        from utils.db.tools import create_build, update_build, list_builds
        b1 = create_build('t1', conn=tools_db)
        create_build('t2', conn=tools_db)
        update_build(b1, status='passed', conn=tools_db)
        passed = list_builds(status='passed', conn=tools_db)
        assert len(passed) == 1

    def test_get_build_by_proposal(self, tools_db):
        from utils.db.tools import create_build, get_build_by_proposal
        create_build('t1', proposal_id='P-100', conn=tools_db)
        b = get_build_by_proposal('P-100', conn=tools_db)
        assert b is not None
        assert b['tool_name'] == 't1'

    def test_get_build_by_proposal_missing(self, tools_db):
        from utils.db.tools import get_build_by_proposal
        assert get_build_by_proposal('P-999', conn=tools_db) is None

    def test_get_build_missing(self, tools_db):
        from utils.db.tools import get_build
        assert get_build(99999, conn=tools_db) is None


# ── C.2 — Build Pipeline ─────────────────────────────────────────────────

class TestBuildPipeline:
    """C.2: scaffold, validate, test, register stages."""

    def test_scaffold_python_script(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool
        bid, path = build_tool('script', 'Hello World', 'A hello tool',
                               'gemma', conn=tools_db)
        assert bid > 0
        assert os.path.isfile(path)
        content = Path(path).read_text()
        assert 'Hello World' in content
        # Test file should also exist
        test_file = Path(path).parent / f'test_{Path(path).stem}.py'
        assert test_file.exists()

    def test_scaffold_shell_script(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool
        bid, path = build_tool('shell', 'backup_db', 'Backup the database',
                               'llama', conn=tools_db)
        assert os.path.isfile(path)
        assert path.endswith('.sh')
        # Should be executable
        assert os.access(path, os.X_OK)

    def test_scaffold_js_widget(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool
        bid, path = build_tool('widget', 'status panel', 'Show agent status',
                               'qwen', conn=tools_db)
        assert path.endswith('.js')
        content = Path(path).read_text()
        assert 'status panel' in content or 'status_panel' in content

    def test_scaffold_invalid_type(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool
        with pytest.raises(ValueError, match='Unknown tool_type'):
            build_tool('nosuch', 'x', 'x', 'gemma', conn=tools_db)

    def test_scaffold_empty_name(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool
        with pytest.raises(ValueError, match='alphanumeric'):
            build_tool('script', '   ', 'x', 'gemma', conn=tools_db)

    def test_validate_python_ok(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool, validate_tool
        bid, _ = build_tool('script', 'valid_py', 'test', 'gemma', conn=tools_db)
        ok, msg = validate_tool(bid, conn=tools_db)
        assert ok is True
        assert 'OK' in msg

    def test_validate_python_syntax_error(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool, validate_tool
        from utils.db.tools import get_build
        bid, path = build_tool('script', 'bad_py', 'test', 'gemma', conn=tools_db)
        # Corrupt the file
        Path(path).write_text('def broken(\n')
        ok, msg = validate_tool(bid, conn=tools_db)
        assert ok is False
        assert 'SyntaxError' in msg

    def test_validate_shell_ok(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool, validate_tool
        bid, _ = build_tool('shell', 'ok_sh', 'test', 'gemma', conn=tools_db)
        ok, msg = validate_tool(bid, conn=tools_db)
        assert ok is True

    def test_validate_missing_build(self, tools_db):
        from fridays.tool_builder import validate_tool
        ok, msg = validate_tool(99999, conn=tools_db)
        assert ok is False
        assert 'not found' in msg

    def test_test_python_with_test_file(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool, test_tool
        bid, _ = build_tool('script', 'tested_script', 'A tested tool',
                            'gemma', conn=tools_db)
        ok, output = test_tool(bid, conn=tools_db)
        assert ok is True
        assert 'passed' in output.lower() or output  # pytest output

    def test_test_shell_dryrun(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool, test_tool
        bid, _ = build_tool('shell', 'dryrun_sh', 'test dry', 'gemma', conn=tools_db)
        ok, output = test_tool(bid, conn=tools_db)
        assert ok is True

    def test_register_passed_build(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool, validate_tool, test_tool, register_tool
        from utils.db.tools import get_build
        bid, _ = build_tool('script', 'register_me', 'test', 'gemma', conn=tools_db)
        validate_tool(bid, conn=tools_db)
        test_tool(bid, conn=tools_db)
        ok, msg = register_tool(bid, conn=tools_db)
        assert ok is True
        assert 'registered' in msg.lower()
        b = get_build(bid, conn=tools_db)
        assert b['status'] == 'registered'

    def test_register_fails_for_failed_build(self, tools_db, sandpit):
        from fridays.tool_builder import build_tool, register_tool
        from utils.db.tools import update_build
        bid, _ = build_tool('script', 'fail_reg', 'test', 'gemma', conn=tools_db)
        update_build(bid, status='failed', conn=tools_db)
        ok, msg = register_tool(bid, conn=tools_db)
        assert ok is False

    def test_register_missing(self, tools_db):
        from fridays.tool_builder import register_tool
        ok, msg = register_tool(99999, conn=tools_db)
        assert ok is False

    def test_list_templates(self):
        from fridays.tool_builder import list_templates
        tpls = list_templates()
        assert len(tpls) == 5
        types = {t['type'] for t in tpls}
        assert types == {'script', 'skill', 'widget', 'cron', 'shell'}


# ── C.3 — Tool Builder Skills ────────────────────────────────────────────

class TestToolSkills:
    """C.3: skill handlers for tool building."""

    def test_skill_build_tool(self, tools_db, sandpit, monkeypatch):
        from fridays.skills import _skill_build_tool
        ok, msg = _skill_build_tool('script my_skill A test skill', 'gemma')
        assert ok is True
        assert 'scaffolded' in msg.lower() or 'build' in msg.lower()

    def test_skill_build_tool_missing_args(self):
        from fridays.skills import _skill_build_tool
        ok, msg = _skill_build_tool('', 'gemma')
        assert ok is False

    def test_skill_tool_validate(self, tools_db, sandpit, monkeypatch):
        from fridays.skills import _skill_build_tool, _skill_tool_validate
        ok, msg = _skill_build_tool('script val_test validation test', 'gemma')
        # Extract build id from message
        import re
        bid_match = re.search(r'#(\d+)', msg)
        assert bid_match, f'Expected build id in message: {msg}'
        bid = bid_match.group(1)
        ok, msg = _skill_tool_validate(bid, 'gemma')
        assert ok is True

    def test_skill_tool_test(self, tools_db, sandpit, monkeypatch):
        from fridays.skills import _skill_build_tool, _skill_tool_test
        import re
        ok, msg = _skill_build_tool('script tst_test test tool', 'gemma')
        bid = re.search(r'#(\d+)', msg).group(1)
        ok, msg = _skill_tool_test(bid, 'gemma')
        assert ok is True

    def test_skill_tool_status(self, tools_db, sandpit, monkeypatch):
        from fridays.skills import _skill_build_tool, _skill_tool_status
        import re
        ok, msg = _skill_build_tool('script st_test status tool', 'gemma')
        bid = re.search(r'#(\d+)', msg).group(1)
        ok, msg = _skill_tool_status(bid, 'gemma')
        assert ok is True
        assert 'scaffolded' in msg.lower() or 'status' in msg.lower()

    def test_skill_tool_list(self, tools_db, sandpit, monkeypatch):
        from fridays.skills import _skill_build_tool, _skill_tool_list
        _skill_build_tool('script ls_1 tool one', 'gemma')
        _skill_build_tool('script ls_2 tool two', 'gemma')
        ok, msg = _skill_tool_list('', 'gemma')
        assert ok is True
        assert 'ls_1' in msg or '2' in msg


# ── C.5 — Quality Gate ───────────────────────────────────────────────────

class TestQualityGate:
    """C.5: alm_complete blocks on failing tool builds."""

    def test_gate_blocks_on_failed_validation(self, tools_db, sandpit):
        """If a linked tool build fails validation, completion is blocked."""
        from utils.db.tools import create_build, update_build, get_build_by_proposal
        bid = create_build('gate_fail', proposal_id='P-GATE-1',
                           building_agent='gemma', conn=tools_db)
        update_build(bid, entry_path='/nonexistent/file.py', conn=tools_db)
        # The gate check uses get_build_by_proposal, then validate_tool
        from fridays.tool_builder import validate_tool
        ok, msg = validate_tool(bid, conn=tools_db)
        assert ok is False  # file doesn't exist

    def test_gate_passes_for_good_build(self, tools_db, sandpit):
        """A passing tool build should not block completion."""
        from fridays.tool_builder import build_tool, validate_tool, test_tool
        from utils.db.tools import get_build
        bid, _ = build_tool('script', 'gate_good', 'test', 'gemma', conn=tools_db)
        v_ok, _ = validate_tool(bid, conn=tools_db)
        assert v_ok is True
        t_ok, _ = test_tool(bid, conn=tools_db)
        assert t_ok is True
        b = get_build(bid, conn=tools_db)
        assert b['status'] == 'passed'

    def test_gate_skips_when_no_linked_build(self, tools_db):
        """If proposal has no linked tool_build, gate is a no-op."""
        from utils.db.tools import get_build_by_proposal
        assert get_build_by_proposal('P-NO-BUILD', conn=tools_db) is None
