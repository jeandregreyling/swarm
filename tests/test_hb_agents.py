"""Owner 14 Nov: agent onboarding - every agent its own memory SQLite, linked to the KC, with tools; local models read/write; they know what
they are for. By profile, never by name."""
import json

import pytest

from core import hb_agents, agent_identity
from core.hb_agent_profiles import tools_for
from test_peer_turns import flow, reply  # noqa: F401


@pytest.fixture
def world(flow, tmp_path, monkeypatch):
    conn, principals = flow
    monkeypatch.setattr(agent_identity, 'STATE', tmp_path / 'identities')
    conn.executescript('''CREATE TABLE IF NOT EXISTS knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, source_type TEXT, source_ref TEXT,
        raw_text TEXT, domain_tags TEXT, added_by TEXT, category TEXT, subcategory TEXT, content_hash TEXT, chunk_count INT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS knowledge_chunks(source_id INT, chunk_index INT, chunk_text TEXT, embedding BLOB);
        CREATE TABLE IF NOT EXISTS user_skill_permissions(username TEXT, skill_name TEXT, allowed INT, UNIQUE(username, skill_name));''')
    return conn


def test_a_local_model_is_onboarded_read_write_with_memory_kc_and_knows_its_job(world):
    conn = world
    said = []
    a = hb_agents.onboard(conn, 'mixtral-8x7b', kind='local', profile='local_worker', model='mixtral-8x7b-instruct',
                          about='A local model for deep research.', tags=['researcher', 'social', 'generalist'], say=said.append,
                          tests={'programmer': {'passed': False}, 'tools': {'passed': True}, 'researcher': {'passed': True}, 'social': {'passed': True}}, exam_by='hb')
    assert a['kind'] == 'local' and a['kc_source_id']
    assert said[0].startswith('🌱 Onboarding mixtral-8x7b') and said[-2].startswith('✅ mixtral-8x7b is onboarded') and said[-1].startswith('🌱 Welcome pack for mixtral-8x7b')
    assert (agent_identity.STATE / 'mixtral-8x7b' / 'memory.sqlite').is_file()                  # its own memory SQLite
    who = agent_identity.read_memory('mixtral-8x7b', 'Who I am', 5)[0]['content']
    assert 'researcher, social, generalist' in who and 'propose_patch' in who                     # it knows what it is for and can do
    assert hb_agents.writes(conn, 'mixtral-8x7b') and 'propose_patch' in tools_for('mixtral-8x7b', conn=conn)
    skills = {r[0] for r in conn.execute("SELECT skill_name FROM user_skill_permissions WHERE username='mixtral-8x7b'")}
    assert {'fs_readonly', 'knowledge_search', 'fs_write'} <= skills
    scopes = json.loads(conn.execute("SELECT scopes FROM service_tokens WHERE principal_id='mixtral-8x7b' AND revoked_at IS NULL").fetchone()[0])
    assert 'agent.write' in scopes and 'agent.memory' in scopes
    page = conn.execute('SELECT raw_text FROM knowledge_sources WHERE source_id=?', (a['kc_source_id'],)).fetchone()[0]
    assert 'HB agent mixtral-8x7b' in page and 'Who I am' in page                                  # linked to the KC


def test_an_online_advisor_stays_read_only_and_memories_mirror_into_the_kc(world):
    conn = world
    assert hb_agents.onboard(conn, 'deepseek', kind='online', profile='advisor', model='deepseek-chat', about='Online advisor (pending onboarding test).',
                             say=lambda t: None)['status'] == 'provisional'                    # no measured pass yet: provisional
    passing = {k: {'passed': True} for k in ('programmer', 'tools', 'researcher', 'social')}
    hb_agents.onboard(conn, 'deepseek', kind='online', profile='advisor', model='deepseek-chat', about='Online advisor.', say=lambda t: None, tests=passing, exam_by='hb')
    assert not hb_agents.writes(conn, 'deepseek') and 'studio_proposal' in tools_for('deepseek', conn=conn)
    assert 'fs_write' not in {r[0] for r in conn.execute("SELECT skill_name FROM user_skill_permissions WHERE username='deepseek'")}
    agent_identity.save_memory('deepseek', 'A lesson', 'Check the KC before advising.')
    assert hb_agents.kc_tick(conn) == ['deepseek']
    sid = hb_agents.get(conn, 'deepseek')['kc_source_id']
    assert 'Check the KC before advising.' in conn.execute('SELECT raw_text FROM knowledge_sources WHERE source_id=?', (sid,)).fetchone()[0]
    assert hb_agents.kc_tick(conn) == []                                                          # unchanged: not rewritten


def test_slugs_are_valid_identities():
    assert hb_agents.slug('llama3.2:latest') == 'llama3-2' and hb_agents.slug('qwen2.5-32b-instruct') == 'qwen2-5-32b'
    agent_identity.name(hb_agents.slug('mixtral-8x7b-instruct'))


def test_no_measured_pass_no_work_and_nothing_is_permanent(world):
    """Owner 14 Nov: registration completes only with a measured pass for agency and capability; nothing is permanent."""
    conn = world
    said = []
    fails_agency = {'programmer': {'passed': True}, 'tools': {'passed': False}, 'researcher': {'passed': True}, 'social': {'passed': True}}
    hb_agents.onboard(conn, 'gpt-oss-20b', kind='local', profile='local_worker', model='gpt-oss:20b', about='A local model.', say=said.append,
                      tests=fails_agency, exam_by='hb')
    a = hb_agents.get(conn, 'gpt-oss-20b')
    assert a['status'] == 'provisional' and any('provisional: no agency: failed tools' in s for s in said)
    assert not hb_agents.writes(conn, 'gpt-oss-20b') and 'propose_patch' not in tools_for('gpt-oss-20b', conn=conn)
    assert (agent_identity.STATE / 'gpt-oss-20b' / 'memory.sqlite').is_file()                     # still registered: memory, KC page
    assert hb_agents.assess({'programmer': {'passed': True}, 'tools': {'passed': True}, 'researcher': {'passed': True}}) == \
        {'score': 0.85, 'agency': True, 'passed': True, 'why': 'passed'}
    conn.execute("CREATE TABLE IF NOT EXISTS hb_model_bench(model TEXT PRIMARY KEY, at REAL, record TEXT)")
    conn.execute("INSERT INTO hb_model_bench VALUES('qwen2.5:7b-instruct', 0, ?)", (json.dumps({'tests': {k: {'passed': True} for k in
                                                                                                         ('programmer', 'tools', 'researcher', 'social')}}),))
    assert 'passed' in hb_agents.swap_model(conn, 'gpt-oss-20b', 'qwen2.5:7b-instruct', 'jd')          # interchangeable
    assert hb_agents.get(conn, 'gpt-oss-20b')['status'] == 'active' and hb_agents.writes(conn, 'gpt-oss-20b')
    assert 'provisional until HB benchmarks it' in hb_agents.swap_model(conn, 'gpt-oss-20b', 'brand-new-model', 'jd')
    assert hb_agents.retire(conn, 'gpt-oss-20b', 'jd').startswith('gpt-oss-20b retired')
    assert tools_for('gpt-oss-20b', conn=conn) == []                                                # retired: no tools


# ------------------------------------------------------------------ 14 Nov: handles and HB's own exam
def test_self_reported_results_do_not_activate_an_agent(world):
    conn = world
    passing = {t: {'passed': True} for t in ('programmer', 'tools', 'researcher', 'social')}
    a = hb_agents.onboard(conn, 'copilot-instructor', kind='online', profile='advisor', about='VS Code instructor.', say=lambda t: None,
                          tests=passing, handles=['@github', 'Copilot'])
    assert a['status'] == 'provisional' and json.loads(a['exam'])['by'] == 'none'
    assert hb_agents.resolve(conn, '@GitHub') == hb_agents.resolve(conn, 'copilot') == 'copilot-instructor'
    assert hb_agents.resolve(conn, '@nobody') is None


def test_hb_examines_through_the_inbox_scores_answers_and_activates(world, monkeypatch):
    from core import hb_model_bench as mb
    conn = world
    monkeypatch.setattr(mb, 'TESTS', [(n, f'question {n}', (lambda text, n=n: (f'right {n}' in text, 'checked')), 50)
                                      for n in ('programmer', 'tools', 'researcher', 'social')])
    hb_agents.onboard(conn, 'copilot-instructor', kind='online', profile='advisor', about='VS Code instructor.', say=lambda t: None,
                      handles=['github'])
    said = []
    reply = hb_agents.onboard_request(conn, 2834, '@apex can you onboard the @github identity', 'jd via chat')
    assert 'copilot-instructor' in reply and 'has not examined it' in reply and 'questions sent to its inbox' in reply
    asked = conn.execute("SELECT body FROM peer_messages WHERE recipient='copilot-instructor' AND body LIKE '[HB EXAM %'").fetchall()
    assert len(asked) == 4
    tags = [b[0].split('\n')[0] for b in asked]
    for tag in tags[:3]:                                # three answers arrive; one never does
        name = tag.split()[-1].rstrip(']')
        conn.execute('INSERT INTO peer_messages(conversation_id,message_id,sender,recipient,body,created_at) VALUES (2834,NULL,?,?,?,?)',
                     ('copilot-instructor', 'apex', f'{tag} right {name}', __import__('time').time()))
    hb_agents.exam_tick(conn, say=said.append)
    assert len([s for s in said if s.startswith('🧪')]) == 3 and hb_agents.get(conn, 'copilot-instructor')['status'] == 'provisional'
    hb_agents.exam_tick(conn, say=said.append, now=__import__('time').time() + hb_agents.EXAM_TIMEOUT_S + 5)   # the 4th times out
    a = hb_agents.get(conn, 'copilot-instructor')
    e = json.loads(a['exam'])
    assert e['by'] == 'hb' and e['score'] == 0.85 and a['status'] == 'active' and any(s.startswith('✅ copilot-instructor passed') for s in said)
    again = hb_agents.onboard_request(conn, 2834, 'onboard @github please', 'jd via chat')
    assert 'already onboarded' in again and 'exam by HB' in again


def test_onboard_requests_are_hb_work_not_tasks():
    from core.hb_owner_intent import classify
    assert classify("@apex can you onboard the @github identity and if you can't let me know why not") == 'agents'
    assert classify('@apex onboarding the database migration needs a plan') != 'agents'
    assert hb_agents.onboard_request is not None


def test_welcome_pack_is_the_same_for_local_and_online_and_the_online_reply_closes_the_loop(world):
    conn = world
    said = []
    hb_agents.onboard(conn, 'qwen-local', kind='local', profile='local_worker', about='A local model.', say=said.append,
                      tests={t: {'passed': True} for t in ('programmer', 'tools', 'researcher', 'social')}, exam_by='hb')
    assert any(s.startswith('🌱 Welcome pack for qwen-local') for s in said)
    mem = agent_identity.read_memory('qwen-local', 'Welcome pack', 5)
    assert mem and 'Who we are' in mem[0]['content'] and 'cost nothing per token' in mem[0]['content']
    hb_agents.onboard(conn, 'gemini-advisor', kind='online', profile='advisor', about='Online advisor.', say=lambda t: None, handles=['gemini'])
    sent = conn.execute("SELECT body FROM peer_messages WHERE recipient='gemini-advisor' AND body LIKE '[HB WELCOME gemini-advisor]%'").fetchone()
    assert sent and 'paid for by JD' in sent[0] and 'Who we are' in sent[0]
    conn.execute("INSERT INTO peer_messages(conversation_id,message_id,sender,recipient,body,created_at) VALUES (2834,NULL,'gemini-advisor','apex',?,?)",
                 ('[HB WELCOME gemini-advisor] I am the online advisor; I will not change HB.', __import__('time').time()))
    out = []
    hb_agents.welcome_tick(conn, say=out.append)
    assert out and out[0].startswith('🌺 gemini-advisor confirmed its welcome pack')


def test_re_onboarding_keeps_a_valid_hb_exam_and_its_tags(world):
    conn = world
    passing = {t: {'passed': True} for t in ('programmer', 'tools', 'researcher', 'social')}
    hb_agents.onboard(conn, 'qwen-local', kind='local', profile='local_worker', about='A local model.', say=lambda t: None, tests=passing,
                      exam_by='hb', tags=['programmer', 'researcher'])
    a = hb_agents.onboard(conn, 'qwen-local', kind='local', profile='local_worker', about='A local model, new memory.', say=lambda t: None)
    assert a['status'] == 'active' and json.loads(a['exam'])['by'] == 'hb' and a['tags'] == 'programmer,researcher'
