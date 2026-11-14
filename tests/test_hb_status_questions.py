"""Practice 72 (owner 15 Nov): "hey can you please share open tasks and your proposed solutions?" became a task, APEX circled and Fred held
the queue. A question about HB's own work is a status question: HB answers it from its records; real work requests stay tasks."""
from pathlib import Path
import core.hb_owner_intent as i


def test_practice_72_status_questions_are_recognised():
    for line in ('hey can you please share open tasks and your proposed solutions?', 'show me the open tasks', 'list the open tasks and what you propose',
                 'what is left?', '@apex what are you working on', 'please summarise where we are', 'status?', 'which tasks are still open',
                 'is anything waiting for me?', 'what is HB trying to do now?'):
        assert i.classify(line) == 'status', line


def test_practice_72_work_requests_and_remarks_are_unchanged():
    assert i.classify('can you fix the queue so the tasks show?') is None
    assert i.classify('list the open tasks and fix the first one') is None
    assert i.classify('show me core/hb_queue.py') is None
    assert i.classify('HAS ANYONE ACTUALLY HELPED apex?') == 'remark'
    assert i.classify('go') == 'drive' and i.classify('all of them') == 'remark'
    assert i.classify('@apex can you onboard the @github identity') == 'agents'


def test_practice_72_hb_answers_in_chat_and_duplicate_lines_are_gone():
    chat = (Path(__file__).resolve().parents[1] / 'frontend/blueprints/chat.py').read_text()
    assert "if owner_intent == 'status':" in chat and 'hb_owner_intent.status_text(_id_conn, conv_id)' in chat
    src = Path(i.__file__).read_text()
    assert src.count('"HAS ANYONE ACTUALLY HELPED apex?" is a question to answer, not a task') == 1
