"""Practice 100 (owner 16 Nov 2026): HB's GitHub step failed 8 times with "Read timed out (read timeout=179)". The 15 Nov change ("let the
system decide") removed the 4096-token answer cap, so a turn could ask for ~100k tokens; at ~38 tokens/s gpt-oss wrote past the worker's
180 s limit and the whole turn was lost. An answer now gets the window's room, but no more than fits the time the call has."""
from pathlib import Path

from core import apex_context as ctx

ROOT = Path(__file__).resolve().parents[1]


def test_practice_100_time_budget():
    assert ctx.time_budget(180, tokens_per_s=30) == 4320          # 80% of 180 s at 30 tokens/s
    assert ctx.time_budget(900, tokens_per_s=30) == 21600
    assert ctx.time_budget(5, tokens_per_s=30) == ctx.FINAL_ANSWER_RESERVE   # never below the closing-answer reserve
    assert ctx.time_budget(-3) == ctx.FINAL_ANSWER_RESERVE
    assert 180 * 38 > ctx.time_budget(180)                        # fits inside 180 s at the measured speed


def test_practice_100_every_apex_call_uses_it():
    worker = (ROOT / 'scripts' / 'hummingbird_peer_worker.py').read_text()
    assert "'num_predict':min(generation_budget(current),time_budget(900 if assigned else 180))" in worker
    chat = (ROOT / 'frontend' / 'blueprints' / 'chat.py').read_text()
    assert 'output_tokens = min(output_tokens, time_budget(remaining))' in chat
