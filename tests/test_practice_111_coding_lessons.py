"""Practice 111 (owner 16 Nov 2026): APEX's own attempt at the terminal bubble (S-D6D8B49B4F) doubled its regex backslashes, added the
same function twice and broke a code fence across lines. Those three mistakes are now coding lessons every coding turn carries."""
from core.hb_learning import coding_lessons


def test_practice_111_the_three_lessons_reach_apex():
    text = coding_lessons()
    assert 'ONE backslash in the file' in text and 'Add a function once' in text and 'A code fence' in text
