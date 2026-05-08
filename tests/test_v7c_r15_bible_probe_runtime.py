"""V7C-R15 refinement — runtime Coding Bible rollout probe.

Closes the deferred (1) from the R15 partial: instead of string-scanning
``utils/config.py``, this test imports the coding-bible probe, which
walks the live ``utils.config`` namespace at process time, and asserts
every expected agent is actually carrying the Bible prefix on its
in-memory ``*_SYSTEM_PROMPT`` constant.

Also exercises the ``/api/coding-bible/probe`` HTTP route so the same
report is visible to Studio / Settings.
"""
from pathlib import Path

import pytest

from core.coding_bible_probe import probe, BIBLE_MARKER, EXPECTED_AGENTS


def test_r15_probe_reports_ok():
    rep = probe()
    assert rep["ok"] is True, rep
    assert rep["marker"] == BIBLE_MARKER
    assert rep["card_present"] is True


def test_r15_probe_covers_every_expected_agent():
    rep = probe()
    assert rep["missing"] == [], f"missing Bible on: {rep['missing']}"
    assert rep["covered"] == rep["total"] == len(EXPECTED_AGENTS)


def test_r15_probe_includes_seven():
    # V7C-A12 companion lock — Seven is a coder and must be in the roster.
    rep = probe()
    assert "SEVEN_SYSTEM_PROMPT" in rep["agents"]
    assert rep["agents"]["SEVEN_SYSTEM_PROMPT"]["status"] == "covered"


def test_r15_librarian_excluded_and_clean():
    rep = probe()
    assert rep["librarian_clean"] is True
    lib = rep["agents"].get("LIBRARIAN_SYSTEM_PROMPT")
    # If the Librarian constant exists in config, it must be excluded (no leak).
    if lib is not None:
        assert lib["status"] == "excluded"


def test_r15_probe_endpoint_returns_same_shape():
    # Spin a minimal Flask app with just the coding_bible blueprint — we only
    # need to prove the route exists and reports the same probe payload.
    from flask import Flask
    from frontend.blueprints.coding_bible import coding_bible_bp
    app = Flask(__name__)
    app.register_blueprint(coding_bible_bp)
    client = app.test_client()
    resp = client.get("/api/coding-bible/probe")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["marker"] == BIBLE_MARKER
    assert set(body["agents"].keys()) >= set(EXPECTED_AGENTS)


def test_r15_prefix_is_prepended_not_appended():
    rep = probe()
    # At least 80% of covered agents have the Bible in the first 400 chars —
    # i.e. it was prepended as a prefix, not buried mid-prompt.
    covered = [n for n, e in rep["agents"].items() if e.get("status") == "covered"]
    prefixed = sum(1 for n in covered if rep["agents"][n]["starts_with_card"])
    assert prefixed >= max(1, int(len(covered) * 0.8)), (
        f"prefix discipline broken: {prefixed}/{len(covered)} have Bible in head"
    )


def test_r15_roster_matches_config_tuple():
    # Guard against drift — probe's EXPECTED_AGENTS is sourced from
    # utils.config._CODING_BIBLE_AGENTS at import time. If either changes,
    # this test surfaces the mismatch rather than letting the probe lie.
    from utils import config as cfg
    assert tuple(EXPECTED_AGENTS) == tuple(cfg._CODING_BIBLE_AGENTS)
