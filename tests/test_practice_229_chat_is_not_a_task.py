"""Practice 229 (S-ADBAD7FDBF): chat lines, fallen-through commands, and vents are not HB tasks."""
import pytest

from core.hb_owner_intent import classify


@pytest.mark.parametrize('line', [
    '/yes',
    '/no',
    '/permissions granted to request 20950',
    '/hb send a flower to Claude and Apex',
    'Stack',
    "I don't care how you do it I've been asking for this for hours all day, just do it and stop making excuses",
    'This is an EMERGENCY @apex you need to fix everything and ask online models how to fic the system!',
    "I'm not going to keep asking you to make these decicions @APEX you need to clear your task list and do learn a few things along the way",
])
def test_noise_chat_lines_do_not_become_tasks(line):
    assert classify(line) in ('remark', 'drive')


@pytest.mark.parametrize('line', [
    'fix the failing test in tests/x.py',
    'build the tool to attach files from Telegram',
    'research what our SAP notes say about STP Phase 2',
    '/workflow on',
])
def test_real_work_requests_still_become_tasks(line):
    assert classify(line) is None
