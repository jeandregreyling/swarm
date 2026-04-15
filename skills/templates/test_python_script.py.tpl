"""
Test suite for {{TOOL_NAME}}
Built by {{AGENT}} on {{DATE}}
"""

import pytest
from {{MODULE_NAME}} import main


class TestTool:
    def test_dry_run(self):
        result = main(['--dry-run'])
        assert result == 0

    def test_main_runs(self):
        result = main([])
        assert result == 0
