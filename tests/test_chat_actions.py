"""Tests for core.chat_actions — the Siri-style action detector."""
from __future__ import annotations

import pytest

from core.chat_actions import detect_action


def test_empty_message_returns_none():
    assert detect_action('') is None
    assert detect_action('   ') is None
    assert detect_action(None) is None  # type: ignore[arg-type]


def test_open_window_with_verb():
    intent = detect_action('open vortex please')
    assert intent is not None
    assert intent['id'] == 'open_window'
    assert intent['args']['view'] == 'time-wizard'
    assert intent['args']['template'] == 'view-time-wizard'
    assert intent['confidence'] >= 0.8


def test_open_window_at_message_start():
    intent = detect_action('Vortex')
    assert intent is not None
    assert intent['id'] == 'open_window'
    assert intent['args']['view'] == 'time-wizard'


def test_bare_mention_midsentence_does_not_trigger():
    # "vortex" appearing mid-sentence without an open-verb should NOT match.
    assert detect_action('I was thinking about the vortex approach') is None


def test_search_verb_extracts_query():
    intent = detect_action('search for swarm governance')
    assert intent is not None
    assert intent['id'] == 'spotlight_search'
    assert intent['args']['q'] == 'swarm governance'


def test_search_rejects_trivial_query():
    assert detect_action('find it') is None
    assert detect_action('search for a') is None


def test_vortex_capture_discrete_command():
    intent = detect_action('capture checkpoint')
    assert intent is not None
    assert intent['id'] == 'vortex_capture'
    assert intent['confidence'] >= 0.9


def test_go_home_discrete_command():
    intent = detect_action('take me home')
    assert intent is not None
    assert intent['id'] == 'go_home'


def test_show_shortcuts_discrete_command():
    intent = detect_action('show shortcuts')
    assert intent is not None
    assert intent['id'] == 'show_shortcuts'


def test_discrete_wins_over_window_match():
    # "capture checkpoint" should beat any stray window match.
    intent = detect_action('capture checkpoint now')
    assert intent['id'] == 'vortex_capture'


def test_open_tickets():
    intent = detect_action('show me tickets')
    assert intent is not None
    assert intent['args']['view'] == 'tickets'


def test_open_media_center_from_chat():
    intent = detect_action('open media center')
    assert intent is not None
    assert intent['id'] == 'open_window'
    assert intent['args']['view'] == 'media-center'
    assert intent['args']['template'] == 'view-media-center'


def test_open_music_editor_from_chat():
    intent = detect_action('show music editor')
    assert intent is not None
    assert intent['args']['view'] == 'media-center'


def test_open_media_handoff_manifest_from_chat():
    intent = detect_action('open media handoff')
    assert intent is not None
    assert intent['id'] == 'open_window'
    assert intent['args']['view'] == 'media-center'


def test_open_projects_section_routes_to_studio_projects():
    intent = detect_action('open projects section')
    assert intent is not None
    assert intent['args']['view'] == 'studio'


def test_unrelated_chat_returns_none():
    assert detect_action("hey, how's it going?") is None
    assert detect_action('can you explain how relays work') is None
