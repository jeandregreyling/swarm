#!/usr/bin/env python3
"""
test_channel_smoke.py — Channel integration smoke tests for Fridays Swarm

Validates that Telegram, Discord, and listener pipelines respond cleanly
without requiring live external integrations. Tests trust gating, command
parsing, and safe fallback behavior.

Run: python3 tests/test_channel_smoke.py
Exit: 0 = all pass, 1 = failures detected
"""

import sys
import os
import unittest

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')


class TestTelegramChannelSmoke(unittest.TestCase):
    """Smoke tests for Telegram channel pipeline."""

    def test_telegram_trust_import_clean(self):
        """Telegram module imports without errors."""
        try:
            import fridays.telegram_bot
            self.assertTrue(hasattr(fridays.telegram_bot, 'run'))
        except Exception as e:
            self.fail(f"Telegram import failed: {e}")

    def test_telegram_error_handler_exists(self):
        """Telegram has global error handler wired."""
        try:
            import fridays.telegram_bot as tg_bot
            self.assertTrue(hasattr(tg_bot, '_handle_polling_error'))
        except Exception as e:
            self.fail(f"Telegram error handler missing: {e}")


class TestDiscordChannelSmoke(unittest.TestCase):
    """Smoke tests for Discord channel pipeline."""

    def test_discord_import_clean(self):
        """Discord module imports without errors."""
        try:
            import fridays.discord_bot
            self.assertTrue(hasattr(fridays.discord_bot, 'run'))
        except Exception as e:
            self.fail(f"Discord import failed: {e}")


class TestListenerChannelSmoke(unittest.TestCase):
    """Smoke tests for email listener pipeline."""

    def test_listener_import_clean(self):
        """Listener module imports without errors."""
        try:
            from core.pipeline import listener
            self.assertTrue(hasattr(listener, 'process_emails'))
        except Exception as e:
            self.fail(f"Listener import failed: {e}")

    def test_listener_classify_sender_callable(self):
        """Listener has a working sender classifier."""
        try:
            from core.pipeline.listener import classify_sender
            result = classify_sender('test@example.com')
            self.assertIn(result, ['trusted', 'notification', 'unknown', 'self', 'moderator'])
        except Exception as e:
            self.fail(f"Listener classify_sender failed: {e}")


class TestChannelCommandParsing(unittest.TestCase):
    """Validate command parsing across channels."""

    def test_telegram_command_parse_fallback(self):
        """Telegram command parsing doesn't crash on edge cases."""
        try:
            from fridays.telegram_bot import _parse_direct_agent_command
            
            # Test valid commands
            result = _parse_direct_agent_command('AGENT gemma hello')
            self.assertIsNotNone(result)
            
            # Test invalid — should not raise
            result = _parse_direct_agent_command('random text')
            self.assertIsNone(result)
        except Exception as e:
            self.fail(f"Telegram command parsing failed: {e}")

    def test_listener_classify_sender_coverage(self):
        """Listener sender classification covers all expected types."""
        try:
            from core.pipeline.listener import classify_sender
            
            # Test that classifier works for different sender types
            # (exact classification depends on system config, just verify no crash)
            result1 = classify_sender('seven@sevenair.local')
            self.assertIsInstance(result1, str)
            self.assertIn(result1, ['self', 'unknown', 'notification', 'external'])
            
            # Unknown email should classify as unknown or notification
            result2 = classify_sender('unknown@random.com')
            self.assertIn(result2, ['unknown', 'notification', 'external'])
        except Exception as e:
            self.fail(f"Listener classification coverage failed: {e}")


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
