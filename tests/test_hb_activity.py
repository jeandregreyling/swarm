"""Owner 14 Nov: live activity in words a person reads, one chain per task."""
from core.hb_activity import plain


def test_actions_read_like_plain_statuses():
    assert plain('tool_result', {'tool': 'read_file', 'arguments': {'path': 'core/hb_rename.py'}}) == 'Reading hb_rename.py'
    assert plain('tool_result', {'tool': 'knowledge_search', 'arguments': {'query': 'DOES'}}) == 'Looking up “DOES” in the KC'
    assert plain('mutation', {'output': 'Approved patch completed: agents/seven/seven_agent.py; SHA-256 abc'}) == '✔ Changed seven_agent.py'
    assert plain('test_result', {'alm_run_status': 'pass', 'verdict': 'PASS: 3 passed in 0.2s'}).startswith('✔ Checks pass: 3 passed')
    assert plain('tool_failure', {'tool': 'propose_patch', 'error': 'ALREADY APPLIED: ...'}) == '↺ That change was already in - moving on'
    assert plain('progress', {'stage': 'Attached agent picked up the explicitly addressed request'}) == 'Started'
    assert plain('progress', {'stage': 'read_file: succeeded'}) is None


def test_background_jobs_show_in_activity_and_post_to_main_chat(tmp_path):
    """Owner 14 Nov: the homework team and counsel show in main chat like any agent - and never hold a write lock while they think
    (bug 14 Nov: 131 "database is locked" in 20 min made the page show Maintenance)."""
    import sqlite3
    from core import hb_background as bg, hb_activity
    conn = sqlite3.connect(':memory:')

    conn.executescript('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT);'
                       'CREATE TABLE hb_peer_work(request_id INT, state TEXT, stage TEXT); CREATE TABLE peer_messages(id INT, recipient TEXT);')
    task = {'task_id': 'T-1', 'title': 'Potato Farm sweep', 'conversation_id': 2834}
    db = tmp_path / 'hb.db'                       # a real database FILE, like HB's
    job = sqlite3.connect(db)
    job.executescript('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT);')
    bg.start('homework', task, 'homework-cpu:7b', 'writing the spec card', job)
    assert not job.in_transaction                 # the job's connection holds no write lock while the model thinks
    other = sqlite3.connect(db, timeout=0.1)
    other.execute('BEGIN IMMEDIATE'); other.rollback()   # someone else can write right away
    bg.step('homework', 'found 3 files')
    chain = hb_activity.chains(conn)[0]
    assert chain['task'] == 'Potato Farm sweep' and chain['members'][0]['role'] == 'Homework' and chain['members'][0]['where'] == 'RAM / CPU'
    assert chain['members'][0]['now'] == 'found 3 files'
    bg.finish('homework', job, task, '📝 Homework card: READY')
    assert hb_activity.chains(conn) == []
    said = [r[0] for r in sqlite3.connect(db).execute('SELECT content FROM messages ORDER BY id')]
    assert said[0].startswith('🌱 Homework (homework-cpu:7b) started') and said[1].startswith('📝 Homework card: READY')
