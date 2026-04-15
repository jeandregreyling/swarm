"""
Test suite for {{TOOL_NAME}} skill
Built by {{AGENT}} on {{DATE}}
"""

import pytest
from {{MODULE_NAME}} import handle


class TestSkill:
    def test_empty_args_returns_usage(self):
        ok, msg = handle('', 'test_agent')
        assert ok is False
        assert 'Usage' in msg

    def test_valid_args_returns_ok(self):
        ok, msg = handle('test input', 'test_agent')
        assert ok is True
        assert '{{TOOL_NAME}}' in msg
