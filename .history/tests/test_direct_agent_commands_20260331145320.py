#!/usr/bin/env python3
"""
Tests for direct-agent command parsing and ticket_create skill.

Run:
  python3 tests/test_direct_agent_commands.py
"""

import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')


class TestDirectAgentParsing(unittest.TestCase):
    def test_telegram_parse_agent_keyword(self):
        from fridays.telegram_bot import _parse_direct_agent_command
        self.assertEqual(
            _parse_direct_agent_command('AGENT llama explain queue drift'),
            ('llama', 'explain queue drift')
        )

    def test_telegram_parse_at_syntax(self):
        from fridays.telegram_bot import _parse_direct_agent_command
        self.assertEqual(
            _parse_direct_agent_command('@qwen what are the risks?'),
            ('qwen', 'what are the risks?')
        )

    def test_discord_parse_agent_keyword(self):
        from fridays.discord_bot import _parse_direct_agent_command
        self.assertEqual(
            _parse_direct_agent_command('AGENT gemma synthesize this request'),
            ('gemma', 'synthesize this request')
        )

    def test_invalid_command_returns_none(self):
        from fridays.discord_bot import _parse_direct_agent_command
        self.assertIsNone(_parse_direct_agent_command('hello team'))


class TestTicketCreateSkill(unittest.TestCase):
    @patch('queue_manager.intake_internal', return_value=(321, 'INTERNAL-TEST-0321'))
    def test_ticket_create_with_separator(self, _mock_intake):
        from fridays.skills import call
        ok, out = call('ticket_create', args='Queue audit || Validate queue edge-case handling', agent='llama')
        self.assertTrue(ok)
        self.assertIn('queue_id=321', out)
        self.assertIn('proposal_id=INTERNAL-TEST-0321', out)

    @patch('queue_manager.intake_internal', return_value=(322, 'INTERNAL-TEST-0322'))
    def test_ticket_create_without_separator(self, _mock_intake):
        from fridays.skills import call
        ok, out = call('ticket_create', args='Validate watchdog timeout behavior in sandbox.', agent='gemma')
        self.assertTrue(ok)
        self.assertIn('queue_id=322', out)


if __name__ == '__main__':
    unittest.main()
