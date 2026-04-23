"""
test_email_bounce_guard.py — Session 28 Backlog #1
Pure-function tests for the bounce / auto-reply detector in listener.py.

Verifies that mailer-daemon bounces, out-of-office auto-replies, and our own
[SWARM-INTERNAL-TEST] probes never reach the ticket-creation path.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ('', 'utils', 'core/pipeline', 'lib/email', 'lib/system', 'agents/ghost'):
    _p = os.path.join(_ROOT, _sub) if _sub else _ROOT
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.pipeline.listener import is_bounce_or_auto_reply  # noqa: E402


def test_mailer_daemon_from_prefix_is_bounce():
    ok, reason = is_bounce_or_auto_reply(
        'Mail Delivery Subsystem <mailer-daemon@googlemail.com>',
        'Delivery Status Notification (Failure)',
        'Address not found. Your message wasn\'t delivered to bogus@example.com.',
    )
    assert ok is True
    assert 'mailer-daemon' in reason


def test_postmaster_from_prefix_is_bounce():
    ok, reason = is_bounce_or_auto_reply(
        'postmaster@outlook.com', 'Undeliverable: test', 'The recipient was not found.'
    )
    assert ok is True
    assert 'postmaster' in reason


def test_out_of_office_is_auto_reply():
    ok, reason = is_bounce_or_auto_reply(
        'Alice <alice@example.com>',
        'Automatic reply: Out of the office',
        'I am out of the office until Monday.',
    )
    assert ok is True
    assert 'subject:' in reason


def test_swarm_internal_test_subject_short_circuits():
    # Even if the bounce comes from an unknown address, our own tagged
    # probe's return subject should always be filed silently.
    ok, reason = is_bounce_or_auto_reply(
        'weird-relay@someprovider.net',
        'Re: [SWARM-INTERNAL-TEST] probe',
        '',
    )
    assert ok is True
    assert 'swarm-internal-test' in reason


def test_body_marker_catches_unusual_sender():
    ok, reason = is_bounce_or_auto_reply(
        'noreply-delivery@mail.example.com',  # caught by noreply prefix
        'Something',
        'Your message wasn\'t delivered to someone@nowhere.com.',
    )
    assert ok is True


def test_plain_user_email_is_not_bounce():
    ok, reason = is_bounce_or_auto_reply(
        'Alice <alice@example.com>',
        'Quick question about the project',
        'Hi team — can you tell me how the queue priority works?',
    )
    assert ok is False
    assert reason == ''


def test_trusted_sender_with_word_failure_in_body_not_flagged():
    # "failure" alone in body should NOT trigger; only specific bounce phrases.
    ok, _ = is_bounce_or_auto_reply(
        'colleague@example.com',
        'Status update',
        'We had a test failure yesterday, pushing fix now.',
    )
    assert ok is False


def test_empty_inputs_safe():
    ok, reason = is_bounce_or_auto_reply('', '', '')
    assert ok is False
    assert reason == ''
