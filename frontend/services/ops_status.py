"""Shared read-only runtime status helpers used by operational views."""


def get_local_ai_statuses():
    from frontend.blueprints.localai import (
        _lmstudio_status,
        _ollama_status,
        _picoclaw_status,
    )

    return {
        'ollama': _ollama_status(),
        'lmstudio': _lmstudio_status(),
        'picoclaw': _picoclaw_status(),
    }


def get_expected_farm_nodes(nodes):
    from frontend.blueprints.hive import _with_expected_farm_nodes

    return _with_expected_farm_nodes(nodes)
