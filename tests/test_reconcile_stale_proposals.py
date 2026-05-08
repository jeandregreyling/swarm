"""Batch V regression tests — STALE_PROPOSALS reconciliation + dedup guard.

Covers:
  MD-STALE-PROPOSALS-RECONCILE-20260430  reconcile_stale_proposals
  (and the orchestrator dedup patch that prevents it growing again).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ops import reconcile_stale_proposals as rsp


# ── parse / dedupe / render ──────────────────────────────────────────────


SAMPLE = """# Stale Proposals

- [13:13] STUDIO-PROPOSALS-0001 (studio): Improve ALM/Studio Proposals UI
- [13:13] STUDIO-PROPOSALS-0002 (studio): Improve ALM/Studio Proposals UI
- [13:18] STUDIO-PROPOSALS-0001 (studio): Improve ALM/Studio Proposals UI
- [13:18] STUDIO-PROPOSALS-0002 (studio): Improve ALM/Studio Proposals UI
- [13:23] STUDIO-PROPOSALS-0001 (studio): Improve ALM/Studio Proposals UI
- [14:00] OTHER-XYZ-0099 (eight): Some other proposal that takes up space
"""


class TestParse:
    def test_parses_well_formed_lines(self):
        out = rsp.parse_lines(SAMPLE)
        assert len(out) == 6
        assert out[0]['proposal_id'] == 'STUDIO-PROPOSALS-0001'
        assert out[0]['ts'] == '13:13'
        assert out[0]['agent'] == 'studio'

    def test_skips_header_and_blank_lines(self):
        text = "# Stale Proposals\n\n  \n- [10:00] X-1 (a): t\n"
        assert len(rsp.parse_lines(text)) == 1

    def test_skips_garbage_lines(self):
        text = "# Stale Proposals\nthis is not a list item\nrandom prose\n"
        assert rsp.parse_lines(text) == []


class TestDedupe:
    def test_collapses_to_one_per_id(self):
        out = rsp.dedupe(rsp.parse_lines(SAMPLE))
        ids = [e['proposal_id'] for e in out]
        assert ids == ['STUDIO-PROPOSALS-0001', 'STUDIO-PROPOSALS-0002', 'OTHER-XYZ-0099']

    def test_keeps_first_seen_timestamp(self):
        out = rsp.dedupe(rsp.parse_lines(SAMPLE))
        first = next(e for e in out if e['proposal_id'] == 'STUDIO-PROPOSALS-0001')
        assert first['ts'] == '13:13'

    def test_prefers_longer_title(self):
        entries = [
            {'ts': '01:00', 'proposal_id': 'X-1', 'agent': 'a', 'title': 'short'},
            {'ts': '02:00', 'proposal_id': 'X-1', 'agent': 'a', 'title': 'a much longer title'},
        ]
        out = rsp.dedupe(entries)
        assert len(out) == 1
        assert out[0]['title'] == 'a much longer title'


class TestRender:
    def test_round_trip(self):
        deduped = rsp.dedupe(rsp.parse_lines(SAMPLE))
        text = rsp.render(deduped)
        assert text.startswith('# Stale Proposals')
        assert text.count('STUDIO-PROPOSALS-0001') == 1
        # Renders one line per id (plus header + blank + trailing).
        body = [l for l in text.splitlines() if l.startswith('- ')]
        assert len(body) == 3


# ── reconcile_file ───────────────────────────────────────────────────────


class TestReconcileFile:
    def test_dry_run_does_not_modify(self, tmp_path):
        p = tmp_path / 'STALE_PROPOSALS.md'
        p.write_text(SAMPLE)
        before = p.read_text()
        summary = rsp.reconcile_file(p, dry_run=True)
        assert summary['changed'] is True
        assert p.read_text() == before, 'dry run must not write'

    def test_non_dry_collapses_file(self, tmp_path):
        p = tmp_path / 'STALE_PROPOSALS.md'
        p.write_text(SAMPLE)
        summary = rsp.reconcile_file(p)
        body = [l for l in p.read_text().splitlines() if l.startswith('- ')]
        assert len(body) == 3
        assert summary['kept'] == 3

    def test_reconcile_is_idempotent(self, tmp_path):
        p = tmp_path / 'STALE_PROPOSALS.md'
        p.write_text(SAMPLE)
        rsp.reconcile_file(p)
        first = p.read_text()
        rsp.reconcile_file(p)
        assert p.read_text() == first

    def test_known_ids_filter_drops_others(self, tmp_path):
        p = tmp_path / 'STALE_PROPOSALS.md'
        p.write_text(SAMPLE)
        summary = rsp.reconcile_file(p, known_ids={'STUDIO-PROPOSALS-0001'})
        assert summary['kept'] == 1
        assert 'STUDIO-PROPOSALS-0002' in summary['dropped_unknown']
        assert 'OTHER-XYZ-0099' in summary['dropped_unknown']

    def test_missing_file_is_handled(self, tmp_path):
        p = tmp_path / 'doesnt-exist.md'
        summary = rsp.reconcile_file(p)
        assert summary['parsed_entries'] == 0
        assert summary['kept'] == 0


# ── Orchestrator dedup guard ─────────────────────────────────────────────


def _stale_proposal(pid='X-1', agent='studio', title='t'):
    """Build a proposal that will be considered stale."""
    return {
        'proposal_id': pid,
        'agent': agent,
        'title': title,
        'created_at': '2020-01-01T00:00:00+00:00',  # ancient → guaranteed stale
    }


class TestOrchestratorDedup:
    def test_no_duplicate_lines_appended(self, tmp_path, monkeypatch):
        # Redirect SANDPIT_ROOT so the orchestrator writes inside tmp_path.
        sandpit = tmp_path
        (sandpit / 'shared').mkdir()
        from fridays import orchestrator as orch
        monkeypatch.setattr(orch, 'SANDPIT_ROOT', sandpit)
        # STEP-STOP-MARKDOWN-TRACKER-RECREATION-20260430 — the legacy MD path is
        # now opt-in. These dedup guards still run when an operator turns it on.
        monkeypatch.setattr(orch, 'LEGACY_MD_TRACKERS', True)

        proposals = [_stale_proposal('STUDIO-PROPOSALS-0001')]
        orch._check_stale_proposals(proposals)
        orch._check_stale_proposals(proposals)
        orch._check_stale_proposals(proposals)

        body = (sandpit / 'shared' / 'STALE_PROPOSALS.md').read_text()
        assert body.count('STUDIO-PROPOSALS-0001') == 1, body

    def test_new_id_still_appended(self, tmp_path, monkeypatch):
        sandpit = tmp_path
        (sandpit / 'shared').mkdir()
        from fridays import orchestrator as orch
        monkeypatch.setattr(orch, 'SANDPIT_ROOT', sandpit)
        monkeypatch.setattr(orch, 'LEGACY_MD_TRACKERS', True)

        orch._check_stale_proposals([_stale_proposal('A-1')])
        orch._check_stale_proposals([_stale_proposal('A-1'), _stale_proposal('B-2')])
        body = (sandpit / 'shared' / 'STALE_PROPOSALS.md').read_text()
        assert 'A-1' in body and 'B-2' in body
        # A-1 should still appear exactly once even after the second pass.
        assert body.count('A-1') == 1
