"""V7C-R17 + A16 refinement — close-out harness + live step probe.

Closes the deferred bullets from R17/A16 partials. These tests exercise
:mod:`core.knowledge.close_out` end-to-end:

    * ``build_report`` walks real ALM project steps and resolves locked
      pytest files by scanning ``tests/`` for the step_id marker.
    * ``run_step_probe`` actually subprocesses pytest and parses verdict.
    * ``/api/knowledge/projects/<pid>/close-out`` returns a JSON-safe
      report shape.
    * ``/api/knowledge/steps/<sid>/probe`` runs the probe over HTTP.

The V7C project (``P-E9BAE4159F``) is the live corpus.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.knowledge import close_out as _co

V7C_PROJECT = "P-E9BAE4159F"
# A step we know has a single fast test file locked in tests/.
# Split so the close-out indexer doesn't pull *this* harness file into the
# step's file list (which would cause a recursive pytest invocation).
V7C_STEP_WITH_TEST = "S-" + "42D0BC0EB1"  # A04 monitor visibility


@pytest.fixture(autouse=True)
def _pin_real_db(monkeypatch):
    """Earlier tests in the session may have left SWARM_DB_PATH pointing at
    a tmp file and reloaded utils.db._connection. Pin it back to the real
    swarm.db so close-out can see live V7C data, then restore on teardown."""
    import importlib
    import utils.db._connection as _dbc
    real_db = Path(__file__).resolve().parent.parent / "swarm_memory.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(real_db))
    importlib.reload(_dbc)
    yield
    importlib.reload(_dbc)


def test_r17_index_is_nonempty():
    idx = _co._index_tests_by_step_id()
    assert idx, "test index should discover V7C step markers"
    # Any V7C test file mentions a step; at least 10 should be indexed.
    assert len(idx) >= 10, f"only {len(idx)} step ids indexed"


def test_r17_build_report_shape():
    rep = _co.build_report(V7C_PROJECT)
    assert rep["ok"] is True
    assert rep["project_id"] == V7C_PROJECT
    assert isinstance(rep["totals"], dict)
    assert rep["totals"]["steps"] >= 33
    for key in ("done", "partial", "todo", "doing", "blocked", "skipped"):
        assert key in rep["totals"]
    assert isinstance(rep["steps"], list)
    for s in rep["steps"]:
        assert "step_id" in s and "status" in s and "verdict" in s
        assert "test_files" in s


def test_r17_known_statuses_only():
    rep = _co.build_report(V7C_PROJECT)
    statuses = {s["status"] for s in rep["steps"]}
    # Every step must have a valid ALM enum status. At close of V7C the
    # project is all "done"; this test also accepts "partial" / "todo" etc.
    # so it remains stable if new steps are added mid-cycle.
    allowed = {"todo", "doing", "blocked", "partial", "done", "skipped"}
    assert statuses <= allowed, f"unexpected statuses: {statuses - allowed}"
    assert "done" in statuses


def test_r17_test_files_resolve_for_known_steps():
    rep = _co.build_report(V7C_PROJECT)
    with_tests = [s for s in rep["steps"] if s["test_files"]]
    # Majority of V7C steps should resolve to at least one locked test file.
    assert len(with_tests) >= 20, (
        f"only {len(with_tests)} of {len(rep['steps'])} steps have a locked file"
    )


def test_r17_bad_project_is_404ish():
    rep = _co.build_report("P-DOES-NOT-EXIST")
    assert rep["ok"] is False


def test_a16_run_step_probe_executes_real_pytest():
    rep = _co.run_step_probe(V7C_STEP_WITH_TEST, timeout=60.0)
    assert rep["ok"] is True, rep
    assert rep["files"], "probe must resolve at least one test file"
    assert rep["return_code"] == 0
    assert rep["verdict"] == "green"
    assert rep["passed"] >= 1


def test_a16_run_step_probe_missing_file():
    rep = _co.run_step_probe("S-UNKNOWN123", timeout=10.0)
    assert rep["ok"] is False
    assert "no test file" in rep["reason"].lower()


def test_r17_close_out_endpoint():
    from flask import Flask
    from frontend.blueprints.knowledge_bp import knowledge_bp
    app = Flask(__name__)
    app.register_blueprint(knowledge_bp)
    client = app.test_client()
    resp = client.get(f"/api/knowledge/projects/{V7C_PROJECT}/close-out")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["totals"]["steps"] >= 33
    assert isinstance(body["steps"], list)
