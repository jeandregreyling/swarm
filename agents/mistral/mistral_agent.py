"""
agents/mistral/mistral_agent.py — Mistral
Local Ollama generalist analyst. Powered by mistral:latest.
Replaces Qwen as the always-on analytical debate partner.
Qwen (qwen2.5:latest) is archived to the virtual RAM layer (on-demand only).

Inference is handled by core/pipeline/orchestrator.py ask_agent('mistral', prompt).
This module provides identity, standalone batch tasks, and memory utilities.
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')

from logging_bridge import log_action
from database import get_connection, save_agent_memory, get_agent_memory

AGENT_NAME = 'mistral'
MODEL      = 'mistral:latest'
SANDPIT    = 'sandpits/mistral/'


def get_recent_memory(query='', limit=5):
    """Return Mistral's recent agent memory rows."""
    return get_agent_memory(AGENT_NAME, query=query, limit=limit) or []


def save_memory(subject, content, tags='', importance=5):
    """Persist a memory entry for Mistral."""
    save_agent_memory(AGENT_NAME, subject, content, tags=tags, importance=importance)
    log_action(AGENT_NAME, 'memory_write', f'saved: {subject[:60]}', 'info')


def ask(prompt):
    """
    Run a one-shot prompt through Mistral via the orchestrator.
    Returns the response text or raises on failure.
    """
    from core.pipeline.orchestrator import ask_agent
    log_action(AGENT_NAME, 'ask', prompt[:80], 'info')
    return ask_agent(AGENT_NAME, prompt)
