#!/usr/bin/env python3
"""
test_notification_reliability.py — Cross-channel notification reliability checks

Validates the unknown-sender notification paths for email, Telegram, and Discord.
These tests focus on whether the system records success/failure correctly and
does not silently report delivery when send_reply returns False.
"""

import asyncio
import sys
import types
import unittest

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/lib/email')
sys.path.insert(0, '/home/seven/swarm/lib/system')


class TestEmailNotificationReliability(unittest.TestCase):
    def test_unknown_email_logs_notify_failed_when_send_reply_false(self):
        import core.pipeline.listener as listener

        captured = []
        original_get_lists = listener.get_all_email_lists
        original_send_checked = listener._send_reply_checked
        original_log_activity = listener.log_activity
        original_discord_notify = sys.modules.get('discord_notify')

        fake_discord_notify = types.ModuleType('discord_notify')
        fake_discord_notify.notify_unknown_sender = lambda *a, **kw: captured.append(('discord_notify', a, kw))
        sys.modules['discord_notify'] = fake_discord_notify

        try:
            listener.get_all_email_lists = lambda: ([], ['mod1@example.com', 'mod2@example.com'], [])
            listener._send_reply_checked = lambda **kwargs: False
            listener.log_activity = lambda service, event, detail: captured.append((service, event, detail))

            listener.ask_moderator_about('unknown@example.com', 'Subject', 'Preview body')

            failed = [row for row in captured if row[:2] == ('listener', 'notify_failed')]
            self.assertEqual(len(failed), 2)
            self.assertTrue(any(row[0] == 'discord_notify' for row in captured))
        finally:
            listener.get_all_email_lists = original_get_lists
            listener._send_reply_checked = original_send_checked
            listener.log_activity = original_log_activity
            if original_discord_notify is not None:
                sys.modules['discord_notify'] = original_discord_notify
            else:
                sys.modules.pop('discord_notify', None)


class TestTelegramNotificationReliability(unittest.TestCase):
    def test_unknown_telegram_logs_notify_failed_when_send_reply_false(self):
        import fridays.telegram_bot as telegram_bot
        import email_handler

        captured = []
        original_get_mods = telegram_bot._get_moderators
        original_send_reply = email_handler.send_reply
        original_log_activity = telegram_bot.log_activity

        try:
            telegram_bot._get_moderators = lambda: ['mod@example.com']
            email_handler.send_reply = lambda **kwargs: False
            telegram_bot.log_activity = lambda service, event, detail: captured.append((service, event, detail))

            asyncio.run(telegram_bot._notify_ghost(None, 123456, 'ghost-user', 'preview text'))

            self.assertIn(
                ('telegram', 'notify_failed', 'chat_id=123456 → mod@example.com | send_reply=False'),
                captured,
            )
        finally:
            telegram_bot._get_moderators = original_get_mods
            email_handler.send_reply = original_send_reply
            telegram_bot.log_activity = original_log_activity


class TestDiscordNotificationReliability(unittest.TestCase):
    def test_unknown_discord_logs_notify_failed_when_send_reply_false(self):
        import fridays.discord_bot as discord_bot
        import email_handler

        captured = []
        original_get_mods = discord_bot._get_moderators
        original_send_reply = email_handler.send_reply
        original_log_activity = discord_bot.log_activity

        try:
            discord_bot._get_moderators = lambda: ['mod@example.com']
            email_handler.send_reply = lambda **kwargs: False
            discord_bot.log_activity = lambda service, event, detail: captured.append((service, event, detail))

            asyncio.run(discord_bot._notify_ghost(654321, 'ghost-user', 'preview text'))

            self.assertIn(
                ('discord', 'notify_failed', 'user_id=654321 → mod@example.com | send_reply=False'),
                captured,
            )
        finally:
            discord_bot._get_moderators = original_get_mods
            email_handler.send_reply = original_send_reply
            discord_bot.log_activity = original_log_activity


if __name__ == '__main__':
    unittest.main(verbosity=2)