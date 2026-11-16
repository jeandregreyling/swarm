"""Practice 101 (owner 16 Nov 2026): APEX's task turns kept ending with "output budget exhausted ... completion_tokens=4320" before any
tool call, while the same model answered chat in seconds. The chat lane asked gpt-oss for low reasoning effort; the task worker did not, so
it reasoned ~40x longer. Task turns now ask for the same low effort (not Fred: his model has no such setting)."""
import json
from contextlib import nullcontext
from pathlib import Path

import scripts.hummingbird_peer_worker as worker
from core import agent_identity, apex_context, apex_routing, llm


def test_practice_101_task_turns_ask_for_low_reasoning(monkeypatch):
    monkeypatch.setattr(apex_routing, 'choose_local_model', lambda _: apex_routing.LocalRoute('test-local', 'general', 16384, 'test'))
    monkeypatch.setattr(agent_identity, 'execution', lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(apex_context, 'prepare_context', lambda messages: messages)
    monkeypatch.setattr(apex_context, 'budget_receipts', lambda _messages, batch: batch)
    monkeypatch.setattr(apex_context, 'generation_budget', lambda _: 1024)

    class RemoteAPI:
        def call(self, path, body):
            return {'ok': True}
    seen = []

    def gateway(*_args, **kwargs):
        seen.append(kwargs['options'])
        return json.dumps({'tool_calls': [], 'answer': 'Nothing to do.'}), 1
    monkeypatch.setattr(llm, 'chat_via_gateway', gateway)
    worker.local_turn(RemoteAPI(), {'id': 9, 'conversation_id': 1, 'body': 'Say what you will do'}, [], ['run_tests'])
    assert seen and seen[0]['reasoning_effort'] == apex_context.APEX_REASONING_EFFORT == 'low'


def test_practice_101_decision_turns_too_and_not_fred():
    src = (Path(__file__).resolve().parents[1] / 'scripts' / 'hummingbird_peer_worker.py').read_text()
    assert "**({} if fred_hands else {'reasoning_effort':APEX_REASONING_EFFORT})" in src
    assert "'require_complete_output':True,'reasoning_effort':APEX_REASONING_EFFORT},response_format=schema)" in src
