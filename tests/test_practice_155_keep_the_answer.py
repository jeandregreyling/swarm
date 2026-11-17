"""Practice 155 (owner 18 Nov 2026, "go"): the 27B wrote two good STP2 answers; the read check sent the first back, the KC check sent the
second back for calling 3671186 'missing' (the question asks what could not be found), and the turn ran out into HB's list. The KC check
now fires only on 'not in HB / must be fetched' claims, and a turn that runs out delivers APEX's last real answer with HB's fixes."""
import core.apex_tools as t

GOOD = ('Here is what our SAP notes say about STP Phase 2 issues:\n- 3643537: GMOA, GTPR, GTPA cumulation wage types were generated wrongly '
        'in PASUM; the note corrects the cumulation.\n- 3660828: the CE report was slow for large sets; code changes make it faster.\n'
        '- 3710504: an authorization error after 3660828; fixed.\nWhat I could not find: the fix details of 3671186 are missing from my reads.')


def test_practice_155_kc_check_ignores_what_could_not_be_found(monkeypatch):
    import utils.db._connection as cm
    import sqlite3
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, source_ref TEXT)')
    db.execute("INSERT INTO knowledge_sources(source_ref) VALUES ('sap://note/3671186')")

    class Keep:
        def __enter__(self): return db
        def __exit__(self, *a): return False
        def close(self): pass
        def execute(self, *a): return db.execute(*a)
    monkeypatch.setattr(cm, 'get_connection', lambda: Keep())
    assert t.kc_notes_claimed_missing(GOOD) == []
    assert t.kc_notes_claimed_missing('SAP Note 3671186 is not in the Knowledge Centre; use /notes add 3671186.') == ['3671186']


def test_practice_155_last_rejected_answer():
    w = [{'role': 'user', 'content': 'q'},
         {'role': 'assistant', 'content': GOOD, 'rejected_answer': True},
         {'role': 'user', 'content': 'BACKEND KC CHECK: your answer was not delivered.'},
         {'role': 'assistant', 'content': 'titles 3643537 3660828 ' + 'x' * 400, 'rejected_answer': True},
         {'role': 'user', 'content': 'BACKEND CONTENT CHECK: your answer was not delivered.'}]
    text, check = t.last_rejected_answer(w)
    assert text == GOOD and check == 'kc check'
    assert t.last_rejected_answer([{'role': 'assistant', 'content': 'short 1234567', 'rejected_answer': True}]) is None
