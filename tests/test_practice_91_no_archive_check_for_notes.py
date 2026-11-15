"""Practice 91 (owner 16 Nov 2026): while APEX worked on the SAP notes step it told JD "I'm unable to call archive_status because it
isn't an available tool in this session". HB's inventory check had demanded the model-archive tool: the request mentioned downloading,
and HB's continuation said "Continue" after an old archive_status reply in the chat. Neither is a question about the model archive."""
import json

from core.apex_tools import ReadOnlyRepository, run_apex_tools

OLD = {'role': 'assistant', 'content': '[tool:archive_status] succeeded (receipt abc) {"view": "files"} {"items": []}'}


def _run(messages, tmp_path):
    seen, calls = [], []

    def model(_name, msgs):
        seen.append(msgs[-1]['content'])
        return json.dumps({'tool_calls': [], 'answer': 'The SAP notes job is queued; 1,200 notes are in the Knowledge Centre.'}), 1
    answer, _, _ = run_apex_tools(model, messages, lambda: True, lambda _: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=lambda name, args: calls.append(name) or {})
    return answer, seen, calls


def test_practice_91_downloading_sap_notes_is_not_an_archive_inventory(tmp_path):
    answer, seen, calls = _run([{'role': 'user', 'content': 'ok go on and download all the SAP note files'}], tmp_path)
    assert len(seen) == 1 and calls == [] and 'Backend inventory check' not in answer


def test_practice_91_hbs_own_continuation_is_not_an_archive_question(tmp_path):
    cont = json.dumps({'task_type': 'hb_managed_continuation', 'instruction': 'Continue the unfinished owner-authorized task.'})
    answer, seen, calls = _run([{'role': 'user', 'content': 'hello'}, OLD, {'role': 'user', 'content': cont}], tmp_path)
    assert len(seen) == 1 and 'Backend inventory check' not in answer


def test_practice_91_jd_asking_about_downloaded_files_still_gets_the_check(tmp_path):
    answer, seen, calls = _run([{'role': 'user', 'content': 'Identify the files downloaded and indexed.'}], tmp_path)
    assert seen[-1].startswith('BACKEND INVENTORY CHECK') or 'Backend inventory check' in answer
