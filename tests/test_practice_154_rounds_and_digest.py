"""Practice 154 (owner 18 Nov 2026): on the 27B the STP2 turn ran out of its 6 tool rounds and HB's digest listed UK, Irish and tax-scale
notes and "63 more". The 27B now has 9 rounds, and the digest lists on-topic notes only."""
import json

import core.apex_tools as t
from core import hb_apex_swap as s

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'
OUT = json.dumps({'matches': ['SAP Note 3660828: [document_id 1] 3660828 - STP2: Performance improvements for CE | slow',
                              'SAP Note 3625431: [document_id 2] 3625431 - PY-GB: OTRE - One Touch Payroll Reporting Engine | uk'],
                  'families': [{'component': 'PY-AU-STP', 'notes': ['SAP Note 3700339: [document_id 3] RPUSTOQ0 - New option to exclude override entries']}]})
REC = [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'STP2'}, 'output': OUT}]


def test_practice_154_digest_keeps_on_topic_notes():
    d = t.research_digest(REC, Q)
    assert '3660828' in d and '3700339' in d and '3625431' not in d
    assert '3625431' in t.research_digest(REC)


def test_practice_154_rounds_per_model(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'swift-qwen3.8-27b')
    assert s.turn_rounds(6) == 9
    monkeypatch.setattr(s, 'playing', lambda: 'gpt-oss:20b')
    assert s.turn_rounds(6) == 6
