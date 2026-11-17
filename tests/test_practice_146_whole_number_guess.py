"""Practice 146 (owner 17 Nov 2026, "keep going ... till it's right"): APEX's first research round still read document 12345 - the
Practice 145 guard matched it inside the prompt's example step id "S-0123456789". The guard now matches whole numbers."""
import json

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'


def test_practice_146_a_number_inside_another_is_still_a_guess(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    reads = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_read', 'arguments': {'document_id': 12345}}], 'answer': ''})] + \
            [json.dumps({'tool_calls': [], 'answer': 'done'})] * 6

    def studio(name, args):
        if name == 'knowledge_read':
            reads.append(args['document_id'])
            return {'status': 'found', 'title': 'x', 'content': 'y'}
        return {'status': 'found', 'matches': ['SAP Note 3713786: [document_id 1099511634780] 3713786 - Phase 1 | z']}
    run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'Example step S-0123456789. ' + Q}], lambda: True,
                   lambda _r: None, ReadOnlyRepository(tmp_path), studio_handler=studio)
    assert 12345 not in reads
