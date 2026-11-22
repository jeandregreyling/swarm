"""Practice 259: short follow-ups continue the focus task instead of asking JD to define done."""
from core import hb_task_manager as tm


def test_follow_ups_are_recognised():
    for t in ('📱 Telegram: Build it Apex', 'do it', 'Test this you dummy', 'apex, fix it now', 'Go'):
        assert tm.FOLLOW_UP.match(t), t
    for t in ('📱 Telegram: What do you want from me?', 'Write a market research brief on ASX miners with sources and probabilities for each'):
        assert not tm.FOLLOW_UP.match(t) or len(t.split()) > 8, t


def test_merge_moves_the_instruction_to_the_focus_task(monkeypatch):
    calls = []
    monkeypatch.setattr('core.peer_bridge.focus_task', lambda conn: 'T-FOCUS0000000')
    monkeypatch.setattr(tm.hb_tasks, 'get', lambda conn, tid: {'task_id': tid, 'title': 'Chunk-first 3/6'})
    monkeypatch.setattr(tm.hb_tasks, 'event', lambda conn, task, agent, kind, payload: calls.append((task['task_id'], kind, payload['content'])))
    monkeypatch.setattr('core.hb_commands.cancel_task', lambda conn, tid, actor: calls.append(('cancel', tid, actor)))
    class C:
        def execute(self, *a): calls.append(('post', a[1][1]))
    assert tm.merge_follow_up(C(), {'task_id': 'T-FOLLOW000000', 'title': '📱 Telegram: Build it Apex', 'conversation_id': 2845}) == 'T-FOCUS0000000'
    assert calls[0] == ('T-FOCUS0000000', 'instruction', 'JD (follow-up): 📱 Telegram: Build it Apex')
    assert calls[1] == ('cancel', 'T-FOLLOW000000', 'HB: follow-up merged into T-FOCUS0000000')
    assert 'carries on with T-FOCUS0000000' in calls[2][1]


def test_real_requests_still_ask():
    assert tm.merge_follow_up(None, {'task_id': 'T-1', 'title': 'Write a market research brief on ASX miners with sources and probabilities'}) is None
