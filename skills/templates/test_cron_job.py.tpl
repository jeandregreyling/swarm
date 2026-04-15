"""
Test suite for {{TOOL_NAME}} cron job
Built by {{AGENT}} on {{DATE}}
"""

import pytest
from {{MODULE_NAME}} import run, main


class TestCronJob:
    def test_dry_run(self):
        result = run(dry_run=True)
        assert result == 0

    def test_main_runs(self):
        result = main(['--dry-run'])
        assert result == 0

    def test_normal_run(self):
        result = run()
        assert result == 0
