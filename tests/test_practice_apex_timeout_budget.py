"""Model-aware APEX decode time budget, DRY repetition guard, and truthful read-timeout reporting.

On 23 Nov 2026 (conv 2848, 07:55), mistral-nemo-12b-abliterated received max_tokens=6336 for a
264 s remaining window because time_budget() still assumed gpt-oss:20b's 30 tok/s and ignored
prompt-eval time (~29 s at 30k tokens). At ~17.6 tok/s with dry_multiplier=0, task 4112 ran past
263 s and surfaced as "APEX is offline" while llama-server was healthy.
"""
from __future__ import annotations

from pathlib import Path

from core import apex_context as ctx
from core import hb_apex_swap as swap
from core.seven_llm import llama_server

ROOT = Path(__file__).resolve().parents[1]


def test_decode_tokens_per_s_uses_playing_model(monkeypatch):
    monkeypatch.setattr(swap, 'playing', lambda: 'mistral-nemo-12b-abliterated')
    assert swap.decode_tokens_per_s() == 13.0
    monkeypatch.setattr(swap, 'playing', lambda: 'swift-qwen3.8-27b')
    assert swap.decode_tokens_per_s() == 10.0
    monkeypatch.setattr(swap, 'playing', lambda: None)
    assert swap.decode_tokens_per_s() == 30.0


def test_time_budget_fits_mistral_nemo_with_prompt_eval_reserve(monkeypatch):
    monkeypatch.delenv('APEX_DECODE_TOKENS_PER_S', raising=False)
    monkeypatch.setattr(swap, 'playing', lambda: 'mistral-nemo-12b-abliterated')
    budget = ctx.time_budget(264)
    assert budget == int((264 - ctx.PROMPT_EVAL_RESERVE_S) * ctx.TIME_SHARE * 13.0)
    # Measured 23 Nov 07:55 speed at 30k ctx: ~29 s prompt eval + ~17.6 tok/s decode
    assert (budget / 17.6) + 29 < 263


def test_llama_server_forwards_dry_repetition_guard():
    plain = llama_server._chat_payload('mistral-nemo-12b-abliterated', [], temperature=0.2, options={})
    assert 'dry_multiplier' not in plain
    assert 'repeat_penalty' not in plain
    guarded = llama_server._chat_payload(
        'mistral-nemo-12b-abliterated', [], temperature=0.2,
        options={'dry_multiplier': 0.5, 'dry_allowed_length': 3, 'repeat_penalty': 1.05},
    )
    assert guarded['dry_multiplier'] == 0.5
    assert guarded['dry_allowed_length'] == 3
    assert guarded['repeat_penalty'] == 1.05


def test_chat_passes_dry_guard_and_labels_read_timeout_accurately():
    src = (ROOT / 'frontend' / 'blueprints' / 'chat.py').read_text(encoding='utf-8')
    assert "options.setdefault('dry_multiplier', 0.5)" in src
    assert "options.setdefault('dry_allowed_length', 3)" in src
    assert 'APEX timed out while generating (server is still running):' in src
