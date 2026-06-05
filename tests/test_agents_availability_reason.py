"""Targeted tests for agent availability reasons."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import frontend.services as services_pkg
from frontend.services import identity


def test_agent_availability_reason_covers_disabled_local_and_api(monkeypatch):
    monkeypatch.setattr(services_pkg, 'DISABLED_AGENTS', {'duck'}, raising=False)
    monkeypatch.setattr(identity, '_reg_runtime', lambda: {'gemma': 'local', 'qwen': 'api'}, raising=False)
    monkeypatch.setattr(identity, '_reg_models', lambda: {'gemma': 'gemma3:latest'}, raising=False)
    monkeypatch.setattr(identity, '_reg_api_keys', lambda: {'qwen': 'QWEN_API_KEY'}, raising=False)
    monkeypatch.setattr(identity, '_ollama_runtime_running', lambda: False, raising=False)
    monkeypatch.delenv('QWEN_API_KEY', raising=False)

    assert identity._agent_availability_reason('duck') == 'disabled'
    assert identity._agent_availability_reason('gemma') == 'Ollama offline'
    assert identity._agent_availability_reason('qwen') == 'missing QWEN_API_KEY'

    monkeypatch.setattr(identity, '_ollama_runtime_running', lambda: True, raising=False)
    monkeypatch.setenv('QWEN_API_KEY', 'abc123')
    assert identity._agent_availability_reason('gemma') == ''
    assert identity._agent_availability_reason('qwen') == ''


def test_agent_availability_reason_uses_seven_runtime_for_direct_model(monkeypatch):
    monkeypatch.setattr(services_pkg, 'DISABLED_AGENTS', set(), raising=False)
    monkeypatch.setattr(identity, '_reg_runtime', lambda: {'seven': 'local'}, raising=False)
    monkeypatch.setattr(identity, '_reg_models', lambda: {'seven': 'seven-direct:daily'}, raising=False)
    monkeypatch.setattr(identity, '_ollama_runtime_running', lambda: False, raising=False)
    monkeypatch.setattr(identity, '_seven_runtime_running', lambda: True, raising=False)

    assert identity._agent_availability_reason('seven') == ''

    monkeypatch.setattr(identity, '_seven_runtime_running', lambda: False, raising=False)
    assert identity._agent_availability_reason('seven') == 'Seven Runtime offline'
