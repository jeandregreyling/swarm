"""Practice 87 (owner 15 Nov 2026, main chat): "what is wrong with this model it repeats itself" - APEX gave five different messages the
same reply. A word-for-word repeat of an earlier reply to a DIFFERENT message gets one correction; the same question twice may still get
the same answer (core/hb_loop_guard.py)."""
from core.apex_tools import REPEAT_ERROR, ReadOnlyRepository, repeats_earlier, run_apex_tools

SAME = "I'm not requesting any confidential emails. I'm only here to help with the tasks you've assigned."
FIRST = "why are you asking for confidential emails?"
OTHER = "it's not confidential you're just being an absolute pain"


def _history(latest):
    return [{'role': 'system', 'content': 'You are APEX.'}, {'role': 'user', 'content': FIRST},
            {'role': 'assistant', 'content': SAME}, {'role': 'user', 'content': latest}]


def _run(history, replies, tmp_path):
    seen, it = [], iter(replies)

    def model(_name, messages):
        seen.append([dict(m) for m in messages])
        return next(it), 1
    answer, _, _ = run_apex_tools(model, history, lambda: True, lambda _: None, ReadOnlyRepository(tmp_path))
    return answer, seen


def test_practice_87_detects_a_parroted_reply():
    assert repeats_earlier(SAME.replace("'", "\u2019"), _history(OTHER))
    assert not repeats_earlier(SAME, _history(FIRST))              # the same question twice: fine
    assert not repeats_earlier('Done.', _history(OTHER) + [{'role': 'assistant', 'content': 'Done.'}])
    assert not repeats_earlier('Something new about the SAP spreadsheet and where to save it.', _history(OTHER))


def test_practice_87_apex_is_corrected_once_and_answers_the_new_message(tmp_path):
    answer, seen = _run(_history(OTHER), [SAME, 'Sorry - I misread you. Send the spreadsheet and I will read the SAP notes in it.'],
                        tmp_path)
    assert seen[1][-1]['content'] == REPEAT_ERROR
    assert answer.startswith('Sorry - I misread you')


def test_practice_87_the_same_question_may_get_the_same_answer(tmp_path):
    answer, seen = _run(_history(FIRST), [SAME], tmp_path)
    assert len(seen) == 1 and answer == SAME
