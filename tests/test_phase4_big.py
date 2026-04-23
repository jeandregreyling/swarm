"""Tests for Phase-4 BIG tier (B18 fan, B19 voice, B20 bible, B21 hive)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'frontend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))


@pytest.fixture(scope='module')
def app():
    # Import through the real app factory so blueprints register.
    os.environ.setdefault('SWARM_ENV', 'dev')
    from frontend import terminal as term  # type: ignore
    app = term.create_app()
    app.testing = True
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


# ── B20 — Coding Bible ────────────────────────────────────────────────────────

def test_coding_bible_full(client):
    r = client.get('/api/coding-bible')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Coding Bible' in body
    assert 'Agent Role Matrix' in body


def test_coding_bible_quick(client):
    r = client.get('/api/coding-bible/quick')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'CODING BIBLE' in body
    assert 'swarm_memory.db' in body


def test_coding_bible_json(client):
    r = client.get('/api/coding-bible/json')
    assert r.status_code == 200
    d = r.get_json()
    assert d['ok'] is True
    assert d['version']
    assert len(d['full']) > 1000
    assert len(d['quick']) > 100


def test_coding_bible_injects_into_prompt():
    from utils import coding_bible
    out = coding_bible.inject('BASE PROMPT')
    assert 'CODING BIBLE' in out
    assert 'BASE PROMPT' in out


def test_twenty_system_prompt_is_big_coder():
    """Regression for the duplicate-TWENTY_SYSTEM_PROMPT shadow bug."""
    from utils import config
    assert 'BIG CODER' in config.TWENTY_SYSTEM_PROMPT
    assert 'Nervous System' not in config.TWENTY_SYSTEM_PROMPT
    # Legacy card must still be accessible under its new name.
    assert hasattr(config, 'NERVOUS_SYSTEM_PROMPT')
    assert 'Nervous System' in config.NERVOUS_SYSTEM_PROMPT


# ── B21 — Hive Nodes / recent sources ─────────────────────────────────────────

def test_hive_nodes_page(client):
    r = client.get('/hive-nodes')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'hive-graph-canvas' in body


def test_library_sources_recent_param(client):
    r = client.get('/api/library/sources?recent=5')
    assert r.status_code == 200
    d = r.get_json()
    assert d['ok'] is True
    assert isinstance(d.get('sources', []), list)
    assert len(d['sources']) <= 5
    # updated_at must now be present for recent-ordering.
    if d['sources']:
        assert 'updated_at' in d['sources'][0]


# ── B19 — Voice I/O ───────────────────────────────────────────────────────────

def test_voice_status(client):
    r = client.get('/api/voice/status')
    assert r.status_code == 200
    d = r.get_json()
    assert d['ok'] is True
    assert 'stt' in d and 'tts' in d
    assert 'available' in d['stt']
    assert 'available' in d['tts']


def test_voice_stt_without_whisper(client):
    """With Whisper not installed, the endpoint must 503 gracefully."""
    from frontend.blueprints import voice as voice_mod
    if voice_mod._load_whisper() is not None:
        pytest.skip('Whisper installed — degrade path not applicable')
    r = client.post('/api/voice/stt', data={})
    # Missing audio field with no whisper: should also return 503 before 400.
    assert r.status_code == 503
    d = r.get_json()
    assert d['ok'] is False
    assert d['reason'] == 'whisper-not-installed'


def test_voice_tts_without_piper(client):
    from frontend.blueprints import voice as voice_mod
    if voice_mod._PIPER_BIN:
        pytest.skip('Piper installed — degrade path not applicable')
    r = client.post('/api/voice/tts', json={'text': 'hi'})
    assert r.status_code == 503
    d = r.get_json()
    assert d['reason'] == 'piper-not-installed'


# ── B18 — Fan controller ──────────────────────────────────────────────────────

def test_fan_status(client):
    r = client.get('/api/fan/status')
    assert r.status_code == 200
    d = r.get_json()
    assert d['ok'] is True
    assert 'temps' in d
    assert 'helper_installed' in d
    assert d['targets']['auto'] == [56, 60]
    assert d['targets']['boost'] == [40, 40]


def test_fan_mode_without_helper(client):
    r = client.post('/api/fan/mode', json={'mode': 'boost'})
    # If the helper socket doesn't exist (normal CI), must 503.
    if r.status_code == 200:
        pytest.skip('fanctl helper is running; degrade path skipped')
    assert r.status_code == 503
    d = r.get_json()
    assert d['reason'] == 'helper-not-installed'


def test_fan_mode_invalid(client):
    r = client.post('/api/fan/mode', json={'mode': 'nuclear'})
    assert r.status_code == 400
    d = r.get_json()
    assert d['ok'] is False
