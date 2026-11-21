"""Practice 281 (JD 22 Nov: "the chunking function should be used to make such large practices more manageable to the local APEX"): the
chunker splits lettered sections A./B./C. as whole chunks, never leaves fragments like "plan" or "any actor can take it", gives a prose spec
one chunk per Done-when test file, and the doer ladder stops at APEX (Fred only works when JD calls him, Practice 264)."""
from core import hb_chunks as ch, hb_scorecards as s

PLAN_8 = ("Do: build JD's one-window main chat in this order, one chunk per point, each with its test added first to tests/test_practice_226_one_window.py: "
          "A. one column - Live pane on top showing only workers with an active run, chat log below, "
          "B. the clipboard list under Live, ONE primary button per row by state (Start, Approve, Try again, Pause) plus a '...' menu (core/hb_clipboard.py, views/hb-queue.js), "
          "C. Needs-you is the only pop-up: one-click answers; any actor can take it; it closes itself when answered (views/hb-needs-you.js), "
          "D. each run is ONE chat message updated in place - question; plan; result (core/hb_announce.py)\nDone when: tests/test_practice_226_one_window.py passes")
PHONE = ("Preparation only until reviewed example is ready. Bind each question to its original conversation. Recover only safe queued work.\n"
         "Done when: tests/test_hb_phone_conversation_flow.py tests/test_hb_phone_owner_execution.py pass.")


def test_lettered_sections_are_whole_chunks():
    parts = ch.plan(PLAN_8)
    assert [p[:2] for p in parts] == ['A.', 'B.', 'C.', 'D.']
    assert 'any actor can take it' in parts[2] and 'closes itself' in parts[2] and 'result (core/hb_announce.py)' in parts[3]
    assert all('tests/test_practice_226_one_window.py' in p for p in parts)          # the intro's test file travels with each chunk


def test_fragments_join_the_chunk_before_them():
    parts = ch.plan('Do: read core/x.py; fix the parser; plan; result; run tests/test_x.py')
    assert parts == ['read core/x.py', 'fix the parser; plan; result', 'run tests/test_x.py']


def test_a_prose_spec_gets_one_chunk_per_done_when_test_file():
    parts = ch.test_chunks(PHONE)
    assert len(parts) == 3
    assert parts[0].startswith('make tests/test_hb_phone_conversation_flow.py pass:') and 'read the first failure' in parts[0]
    assert parts[1].startswith('make tests/test_hb_phone_owner_execution.py pass:')
    assert parts[2].startswith('run all of them together')
    one = ch.test_chunks('Fix it.\nDone when: tests/test_a.py passes')
    assert [p.split(':')[0] for p in one] == ['run tests/test_a.py and read the first failure', 'fix the code that failure points at', 'run tests/test_a.py again']
    assert ch.test_chunks('No tests named here.') == []


def test_the_ladder_stops_at_apex():
    assert s.next_rung('apex', 9) == ('apex', '') and s.next_rung('small', 2)[0] == 'apex'
