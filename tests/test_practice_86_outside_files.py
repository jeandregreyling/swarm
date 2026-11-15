"""Practice 86 (owner 15 Nov 2026): JD asked APEX to read /home/jd/Downloads/SAPKE608F9 - G4.xlsx and "what folder do you have access
to so I can put the file in the directory you have access to?". APEX's true answer (it cannot reach that folder) was replaced with
"No current tool receipt establishes that permission blocker". Now APEX's answer stands and HB names its inbox folder."""
import json

from core import apex_tools
from core.apex_tools import ReadOnlyRepository, outside_files, run_apex_tools


def _run(user, replies, tmp_path):
    (tmp_path / 'example.py').write_text('value = 1\n')
    seen, it = [], iter(replies)

    def model(_name, messages):
        seen.append(messages)
        return next(it), 1
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': user}], lambda: True, lambda _: None,
                                  ReadOnlyRepository(tmp_path), proposal_handler=lambda *a: {})
    return answer, seen


def test_practice_86_outside_files_are_recognised():
    root = str(ReadOnlyRepository().root)
    assert outside_files('read it from the downloads directory directly /home/jd/Downloads SAPKE608F9 - G4.xlsx')
    assert outside_files('what folder do you have access to so I can put the file in the directory you have access to?')
    assert outside_files('can you read ~/Desktop/notes.txt')
    assert not outside_files(f'read {root}/core/apex_tools.py')
    assert not outside_files('Edit example.py to set value = 3.')


def test_practice_86_a_true_answer_about_downloads_stands_and_names_the_inbox(tmp_path):
    user = 'can you read it from the downloads directory directly /home/jd/Downloads SAPKE608F9 - G4.xlsx'
    answer, seen = _run(user, ["I cannot read files in /home/jd/Downloads; my tools only reach the project."], tmp_path)
    assert len(seen) == 1                                    # no capability retry
    assert 'I cannot read files in /home/jd/Downloads' in answer
    assert apex_tools.inbox_folder() in answer
    assert 'No current tool receipt' not in answer


def test_practice_86_a_false_refusal_in_the_repository_ends_in_plain_words(tmp_path):
    answer, seen = _run('Edit example.py to set value = 3.',
                        ["I don't have permission to write files.", "I don't have permission to write files."], tmp_path)
    assert seen[1][-1]['content'].startswith('BACKEND CAPABILITY CHECK')
    assert 'receipt' not in answer and 'not allowed' in answer
