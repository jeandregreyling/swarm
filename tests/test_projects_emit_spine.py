"""Regression test for _emit_spine argument mismatch (S-EMIT-SPINE-FIX).

Previously _emit_spine passed `summary` and `detail` to spine.log,
which expects `message` and `payload`. Because _emit_spine swallows
all exceptions, the TypeError was silent and zero project mutations
reached Vortex — causing the "no updates /卡顿" symptom.
"""
from __future__ import annotations

import pytest


def test_emit_spine_forwards_message_and_payload(monkeypatch):
    """_emit_spine must call spine.log with message= and payload=."""
    calls = []

    def fake_log(*, kind, message, severity, source, payload, **kw):
        calls.append({
            'kind': kind,
            'message': message,
            'severity': severity,
            'source': source,
            'payload': payload,
        })

    monkeypatch.setattr('core.spine.log', fake_log)

    from core.knowledge.projects import _emit_spine
    _emit_spine(
        "Project created: Demo",
        {'project_id': 'P-123', 'methodology': 'agile'},
        severity='info',
    )

    assert len(calls) == 1
    call = calls[0]
    assert call['message'] == 'Project created: Demo'
    assert call['payload'] == {'project_id': 'P-123', 'methodology': 'agile'}
    assert call['severity'] == 'info'
    assert call['source'] == 'projects'


def test_emit_spine_does_not_raise_on_spine_failure(monkeypatch):
    """Best-effort: spine.log failure must not bubble up."""
    def explosive_log(**kw):
        raise RuntimeError("spine is down")

    monkeypatch.setattr('core.spine.log', explosive_log)

    from core.knowledge.projects import _emit_spine
    # Must not raise.
    _emit_spine("Step added: X", {"step_id": "S-999"})


def test_emit_spine_severity_mapping(monkeypatch):
    """severity string is forwarded literally; spine.log coerces it."""
    calls = []

    def fake_log(*, kind, message, severity, source, payload, **kw):
        calls.append(severity)

    monkeypatch.setattr('core.spine.log', fake_log)

    from core.knowledge.projects import _emit_spine
    _emit_spine("X", {}, severity='warn')
    assert calls[-1] == 'warn'

    _emit_spine("Y", {}, severity='critical')
    assert calls[-1] == 'critical'
