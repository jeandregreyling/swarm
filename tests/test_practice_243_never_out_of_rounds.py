"""Practice 243: APEX does not end a turn at 6 rounds or on one over-long reply."""
import inspect

from core import apex_tools


def test_twenty_rounds_and_enough_calls_for_them():
    assert apex_tools.MAX_ROUNDS == 20 and apex_tools.MAX_CALLS == 48


def test_an_over_long_reply_is_retried_not_the_end_of_the_turn():
    src = inspect.getsource(apex_tools._run_apex_tools)
    i = src.index('"APEX output budget exhausted" in str(exc) and output_retry_used < 2')
    assert src.index('OUTPUT_RETRY_NOTICE', i) < src.index('return handoff(str(exc))', i)
    assert 'ONE tool call' in apex_tools.OUTPUT_RETRY_NOTICE
