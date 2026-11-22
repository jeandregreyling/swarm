"""Tests for broader unclipped speaker chat bubbles, translucent readable user bubble, and casual-chat task-hold fix."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_casual_chat_never_inherits_completed_or_paused_task_hold():
    src = (ROOT / 'frontend/blueprints/chat.py').read_text(encoding='utf-8')
    assert "if agent_run and bound_task and not _use_lean_chat and bound_task.get('state') not in {'completed', 'cancelled', 'paused'}:" in src


def test_speaker_bubbles_have_broader_unclipped_padding_and_readable_user_glass():
    css = (ROOT / 'frontend/static/css/themes.css').read_text(encoding='utf-8')
    assert 'padding: 12px 16px !important;' in css
    assert 'overflow: visible !important;' in css
    assert 'rgba(14, 38, 66, 0.80)' in css
    assert 'background: transparent !important;' in css
