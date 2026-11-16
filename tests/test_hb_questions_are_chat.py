"""Practice 38 (owner 14 Nov): "HAS ANYONE ACTUALLY HELPED apex?" became a task that asked JD for a definition of done.
A short question with no action in it joins "Chat with JD" and is answered there; a request with an action is still a task."""
from core.hb_owner_intent import classify


def test_practice_38_questions_are_answered_not_tasked():
    assert classify('HAS ANYONE ACTUALLY HELPED apex?') == 'remark'
    assert classify('@claude why is apex failing and why haven\'t you given the results?') == 'remark'


def test_practice_38_requests_with_an_action_stay_tasks():
    assert classify('can you fix the queue so the tasks show?') is None
    assert classify('@apex can you onboard the @github identity') == 'agents'
