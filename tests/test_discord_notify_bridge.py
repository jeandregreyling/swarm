"""Tests for discord_notify.notify_alert — shared formatter bridge."""
import sys
import os

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/lib/system')

from unittest.mock import patch

from core.notifications import AlertEnvelope
import discord_notify


def test_notify_alert_noop_when_unconfigured():
    """When Discord creds are missing, notify_alert must silently return."""
    env = AlertEnvelope(level='warn', subject='x', body='y')
    with patch.object(discord_notify, '_is_configured', return_value=False):
        with patch.object(discord_notify, 'post_raw') as mock_post:
            discord_notify.notify_alert(env)
            mock_post.assert_not_called()


def test_notify_alert_rejects_non_envelope():
    """Bad input is logged and dropped — never raised."""
    with patch.object(discord_notify, '_is_configured', return_value=True):
        with patch.object(discord_notify, 'post_raw') as mock_post:
            discord_notify.notify_alert({'level': 'warn', 'subject': 'x', 'body': 'y'})
            mock_post.assert_not_called()


def test_notify_alert_posts_with_level_colour():
    """Error level should map to COLOUR_URGENT."""
    env = AlertEnvelope(level='error', subject='boom', body='stack trace', source='duck')
    with patch.object(discord_notify, '_is_configured', return_value=True):
        with patch.object(discord_notify, 'post_raw') as mock_post:
            discord_notify.notify_alert(env)
            assert mock_post.called
            args, kwargs = mock_post.call_args
            # title, body, colour=COLOUR_URGENT
            assert args[0] == 'boom'
            assert 'stack trace' in args[1]
            assert kwargs.get('colour') == discord_notify.COLOUR_URGENT


def test_notify_alert_unknown_level_falls_back_to_info():
    env = AlertEnvelope(level='success', subject='ok', body='done')
    with patch.object(discord_notify, '_is_configured', return_value=True):
        with patch.object(discord_notify, 'post_raw') as mock_post:
            discord_notify.notify_alert(env)
            assert mock_post.call_args.kwargs.get('colour') == discord_notify.COLOUR_OK
