"""Practice 249: an interrupted turn of a task that is on never asks JD."""
import inspect

from core import hb_commands


def test_interrupted_turns_of_running_tasks_are_skipped_before_any_replacement_check():
    src = inspect.getsource(hb_commands.waiting_items)
    i = src.index('# Practice 249')
    assert src.index('continue   # Practice 251', i) < src.index('replacement = conn.execute', i)
