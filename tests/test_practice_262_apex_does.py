"""Practice 262: offers and questions without an action receipt are not delivered; done-with-receipt answers are."""
from core.apex_tools import doer_ok, DOER_NOTICE

OK = [{'tool': 'propose_patch', 'status': 'succeeded', 'id': 'abc123'}]   # 265: cited receipts must be real


def test_offers_without_action_are_sent_back():
    for a in ("I can start the build steps now.", "Let me know what you'd like to tackle next.", "Please provide the file contents.",
              "I don't have permission to run builds or tests directly.", "I'm ready to dive into the code.", "I'm here to help."):
        assert not doer_ok(a, [{'tool': 'read_file', 'status': 'succeeded'}]), a


def test_done_reports_and_plain_answers_pass():
    assert doer_ok("Done: added step_chunks to core/hb_live.py (receipt abc123). Is it working?", OK)
    assert doer_ok("There are 20 open HB tasks.", [])
    assert doer_ok("I can confirm it: tests pass (receipt x).", [{'tool': 'run_tests', 'status': 'succeeded'}])


def test_the_notice_calls_for_relevant_work_and_honest_blockers():
    assert "actual request" in DOER_NOTICE
    assert "unrelated activity" in DOER_NOTICE
    assert "ask JD for the specific help needed" in DOER_NOTICE
    assert "Is it working?" not in DOER_NOTICE


def test_listing_tasks_is_not_a_work_action():
    assert not doer_ok('I can start work now.', [{'tool': 'hb_tasks', 'arguments': {'action': 'list'}, 'status': 'succeeded'}])
    assert doer_ok('I can start work now.', [{'tool': 'hb_tasks', 'arguments': {'action': 'continue'}, 'status': 'succeeded'}])
