"""Tests for core.notifications — Phase 6 shared formatter."""
from core.notifications import (
    format_agent_reply,
    format_alert,
    AlertEnvelope,
    NotificationLevel,
    DEFAULT_MAX_CHARS,
)


def test_format_agent_reply_basic():
    out = format_agent_reply('duck', 'hello world')
    assert out == '**duck**: hello world'


def test_format_agent_reply_normalizes_agent():
    out = format_agent_reply('  DUCK ', 'hi')
    assert out.startswith('**duck**: ')


def test_format_agent_reply_empty_body():
    out = format_agent_reply('ten', '')
    assert '(no content)' in out


def test_format_agent_reply_truncates_long():
    body = 'word ' * 1000
    out = format_agent_reply('ten', body, max_chars=200)
    assert len(out) <= 200
    assert out.endswith('… [truncated]')


def test_format_agent_reply_word_boundary():
    """Truncation picks a space, not mid-word."""
    body = 'alpha beta gamma delta epsilon zeta eta theta iota kappa'
    out = format_agent_reply('x', body, max_chars=40, include_prefix=False)
    assert '… [truncated]' in out
    # Last real char before '…' should be a letter, not half a word
    pre = out.split('…')[0].rstrip()
    assert not pre.endswith(('alph', 'bet', 'gam'))  # not mid-word


def test_format_agent_reply_balances_code_fence():
    """When truncation cuts inside a fenced block, output closes the fence."""
    # Long body opens a fence; truncation must close it.
    body = 'intro\n```python\n' + ('# filler line\n' * 200)
    out = format_agent_reply('ten', body, max_chars=120)
    # Truncated output should have an even number of fences
    assert out.count('```') % 2 == 0
    assert '[truncated]' in out


def test_format_agent_reply_no_prefix():
    out = format_agent_reply('x', 'hello', include_prefix=False)
    assert out == 'hello'


def test_format_alert_basic():
    env = AlertEnvelope(level='warn', subject='queue backlog',
                        body='5 jobs stalled', source='duck')
    out = format_alert(env)
    assert '[!] queue backlog' in out
    assert 'source: duck' in out
    assert '5 jobs stalled' in out


def test_format_alert_unknown_level_defaults_info():
    env = AlertEnvelope(level='bogus', subject='x', body='y')
    out = format_alert(env)
    assert out.startswith('[i]')


def test_format_alert_multiline_subject_first_line_only():
    env = AlertEnvelope(level='info', subject='line1\nline2', body='')
    out = format_alert(env)
    assert '[i] line1' in out
    assert 'line2' not in out


def test_format_alert_truncates():
    body = 'x' * 5000
    env = AlertEnvelope(level='error', subject='big', body=body)
    out = format_alert(env, max_chars=200)
    assert len(out) <= 200
    assert '[truncated]' in out


def test_notification_levels_constant():
    assert NotificationLevel == ('info', 'success', 'warn', 'error', 'critical')


def test_default_cap_is_safe_for_all_transports():
    """1800 < Discord's 2000, far under Telegram's 4096, fits in an email line block."""
    assert DEFAULT_MAX_CHARS <= 2000
