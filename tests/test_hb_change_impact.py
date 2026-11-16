"""Practice 48 (owner 13 Nov): HB classifies every change as cosmetic / behaviour / structural by rules and orders the queue by it."""
import sqlite3
import core.hb_change_impact as i
import core.hb_clipboard as clip


def test_practice_48_rules_classify_by_files_first():
    assert i.classify(['frontend/static/css/chat.css', 'docs/x.md'])[0] == 'cosmetic'
    assert i.classify(['frontend/static/js/home-chat.js'])[:2] == ('behaviour', True)
    assert i.classify(['core/hb_daily_summary.py', 'tests/test_x.py'])[0] == 'behaviour'
    assert i.classify(['core/hb_task_manager.py', 'tests/test_x.py'])[0] == 'structural'
    assert i.classify(['utils/session_auth.py'])[0] == 'structural'
    assert i.classify(['deploy/systemd/apex-server-user.service'])[0] == 'structural'
    assert i.classify(['core/hb_new.py'], 'conn.execute("CREATE TABLE IF NOT EXISTS x(a)")')[0] == 'structural'
    assert i.classify(['tests/test_only.py'], '')[:2] == ('behaviour', False)          # tests alone decide nothing


def test_practice_48_rules_fall_back_to_the_description():
    assert i.classify([], 'Fix the wording and colour of the comment box')[0] == 'cosmetic'
    assert i.classify([], 'Agent identities, logins and scoped memory')[0] == 'structural'
    assert i.classify([], 'Potato Farm sweep') == ('behaviour', False, 'no files and no telling words yet')


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE project_steps(step_id TEXT, title TEXT, description TEXT)')
    c.execute("INSERT INTO project_steps VALUES ('S-AAAAAAAAAA','Comment box','spacing and colour only')")
    return c


def test_practice_48_owner_correction_wins_and_is_kept_as_an_example():
    c = db()
    f = i.for_step(c, 'S-AAAAAAAAAA', paths=[])
    assert (f['impact'], f['importance']) == ('cosmetic', 2)
    assert i.correct(c, 'S-AAAAAAAAAA', 'structural', 'jd') == 'impact: structural (the rules said cosmetic)'
    f = i.for_step(c, 'S-AAAAAAAAAA', paths=[])
    assert (f['impact'], f['importance'], f['impact_why']) == ('structural', 4, 'set by jd')
    assert i.examples(c) == [('S-AAAAAAAAAA', 'cosmetic', 'structural')]
    assert i.correct(c, 'S-AAAAAAAAAA', 'huge', 'jd') == 'Use cosmetic, behaviour or structural.'


def test_practice_48_clipboard_shows_the_class_and_orders_by_it():
    import inspect
    src = inspect.getsource(clip)
    assert "hb_change_impact.for_step(conn, step['step_id'])" in src and "'impact': impact['impact']" in src
    assert "action == 'impact'" in src and 'hb_change_impact.correct(' in src
