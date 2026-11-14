"""Agent onboarding (owner 14 Nov 2026): every agent gets its own identity, memory, tools and KC link - by profile, never by name.

"They should all have their own memory SQLite and linked to KC with tools; all local models have read/write access; they should know what
they are doing, and we can add their personas as we go along."

onboard(conn, agent_id, kind, profile, about, ...) - each step said in main chat:
  1 register   hb_agents row (kind local/online, model, profile, what it is for, persona later) + a service principal
  2 identity   agent_identity.provision: its own login (credentials.json) and private memory.sqlite
  3 skills     read + Knowledge Centre search for every agent; read/write (fs_write, agent.write) when its profile writes (local agents)
  4 who I am   its first memory: its role, model, tools, rules and what the benchmark showed it is good at - so it knows what it is doing
  5 KC link    a Knowledge Centre document for the agent; kc_tick mirrors its memories into the KC as they grow
onboard_local_models(conn) onboards every benchmarked local model (core/hb_model_bench.py) as a read/write agent.
"""
import json
import re
import time

KINDS = ('local', 'online')
CAPABILITY = __import__('pathlib').Path(__file__).resolve().parent / 'capability_packs' / 'hb.agent.capability.v1.json'


def assess(tests):
    """Owner 14 Nov: registration completes only with a measured pass. tests = {name: {'passed': bool}} from HB's benchmark.
    Returns {'score', 'agency', 'passed', 'why'} using the weights in hb.agent.capability.v1.json (data, so it can change)."""
    rules = json.loads(CAPABILITY.read_text())
    score = round(sum(w for name, w in rules['weights'].items() if (tests or {}).get(name, {}).get('passed')), 2)
    missing = [a for a in rules['agency'] if not (tests or {}).get(a, {}).get('passed')]
    passed = not missing and score >= rules['pass_score']
    why = ('passed' if passed else ('no agency: failed ' + ', '.join(missing) if missing else f"score {score} below {rules['pass_score']}"))
    return {'score': score, 'agency': not missing, 'passed': passed, 'why': why}


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_agents(agent_id TEXT PRIMARY KEY, kind TEXT NOT NULL, model TEXT, model_path TEXT,
        profile TEXT NOT NULL, about TEXT NOT NULL, persona TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', onboarded_at REAL,
        actor TEXT, kc_source_id INTEGER, memory_rows INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active')''')


def slug(label):
    s = re.sub(r'[^a-z0-9]+', '-', str(label).lower()).strip('-')
    s = re.sub(r'-(latest|instruct)$', '', s)
    return (s if s and s[0].isalpha() else 'm-' + s)[:48]


def get(conn, agent_id):
    ensure_schema(conn)
    cur = conn.execute('SELECT * FROM hb_agents WHERE agent_id=?', (agent_id,))
    row = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], row)) if row else None


def writes(conn, agent_id):
    """Does this agent's profile give it write tools? (HB's tool grants ask this instead of checking for the name 'apex'.)
    Only an ACTIVE agent (one that passed HB's capability check) writes."""
    from core.hb_agent_profiles import tools_for
    return bool({'propose_patch', 'propose_write_file'} & set(tools_for(agent_id, conn=conn)))


def _post(conn, text):
    from core.hb_plain import message
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2834,'hummingbird','user',?,'response',0)",
                 (message(text),))


def onboard(conn, agent_id, *, kind, profile, about, model='', model_path='', tags=(), actor='owner', say=None, provision=None, tests=None):
    from core import agent_identity
    from core.hb_agent_profiles import tools_for, instructions_for
    say = say or (lambda text: _post(conn, text))
    agent_id = agent_identity.name(agent_id)
    if kind not in KINDS:
        raise ValueError('kind must be local or online')
    ensure_schema(conn)
    now = time.time()
    conn.execute('INSERT INTO hb_agents(agent_id,kind,model,model_path,profile,about,tags,onboarded_at,actor) VALUES(?,?,?,?,?,?,?,?,?) '
                 'ON CONFLICT(agent_id) DO UPDATE SET kind=excluded.kind, model=excluded.model, model_path=excluded.model_path, profile=excluded.profile, '
                 'about=excluded.about, tags=excluded.tags', (agent_id, kind, model, model_path, profile, about, ','.join(tags), now, actor))
    conn.execute("INSERT OR IGNORE INTO service_principals(id,display_name,role,enabled,created_at) VALUES (?,?,'service',1,?)",
                 (agent_id, about.split('.')[0][:80], now))
    result = assess(tests)
    conn.execute('UPDATE hb_agents SET status=? WHERE agent_id=?', ('active' if result['passed'] else 'provisional', agent_id))
    say(f"🌱 Onboarding {agent_id} ({kind}{', ' + model if model else ''}): registered with profile {profile}.")
    say((f"✔ {agent_id} passed HB's capability check (score {result['score']}, agency yes)." if result['passed'] else
         f"⏸ {agent_id} is provisional: {result['why']} (score {result['score']}). It can read and remember, not work, until it passes."))
    (provision or agent_identity.provision)(conn)                      # login + private memory.sqlite (idempotent for everyone)
    say(f"🌱 {agent_id}: its own login and private memory are ready.")
    can_write = writes(conn, agent_id)
    cols = {r[1] for r in conn.execute('PRAGMA table_info(user_skill_permissions)')} if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='user_skill_permissions'").fetchone() else set()
    if {'username', 'skill_name', 'allowed'} <= cols:
        for skill in ('fs_readonly', 'knowledge_search') + (('fs_write',) if can_write else ()):
            conn.execute('INSERT OR IGNORE INTO user_skill_permissions(username,skill_name,allowed) VALUES (?,?,1)', (agent_id, skill))
    if can_write and conn.execute("SELECT 1 FROM sqlite_master WHERE name='service_tokens'").fetchone():
        for tid, scopes in conn.execute('SELECT id, scopes FROM service_tokens WHERE principal_id=? AND revoked_at IS NULL', (agent_id,)).fetchall():
            have = set(json.loads(scopes or '[]'))
            if 'agent.write' not in have:
                conn.execute('UPDATE service_tokens SET scopes=? WHERE id=?', (json.dumps(sorted(have | {'agent.write'})), tid))
    say(f"🌱 {agent_id}: skills - {'read and write (changes still go through HB approval)' if can_write else 'read-only research'} + Knowledge Centre search.")
    tools = tools_for(agent_id, conn=conn)
    who = (f"I am {agent_id}, an HB agent ({kind}{', model ' + model if model else ''}). What I am for: {about} "
           f"My profile is {profile}; my tools: {', '.join(tools)}. "
           + (f"HB's benchmark found me good at: {', '.join(tags)}. " if tags else '') + instructions_for(agent_id, conn=conn))
    try:
        agent_identity.save_memory(agent_id, 'Who I am (HB onboarding)', who[:6000], tags='identity,onboarding', importance=9, source='hb_onboarding')
    except Exception as exc:
        say(f"↺ {agent_id}: first memory not written yet ({type(exc).__name__}); HB retries at the next onboarding run.")
    say(f"🌱 {agent_id}: its first memory says who it is and what it is for.")
    kc_link(conn, agent_id)
    say((f"✅ {agent_id} is onboarded: own memory, KC page, {len(tools)} tools{', read/write' if can_write else ''}. Personas can be added later."
         if result['passed'] else f"⏸ {agent_id} is registered (own memory, KC page) but provisional until it passes HB's capability check."))
    return get(conn, agent_id)


def kc_text(conn, agent_id):
    a = get(conn, agent_id)
    from core import agent_identity
    from core.hb_agent_profiles import tools_for
    rows = []
    try:
        rows = agent_identity.read_memory(agent_id, '', 40)
    except Exception:
        pass
    mem = '\n'.join(f"- {r['subject']}: {str(r['content'])[:400]}" for r in rows)
    return (f"HB agent {agent_id}\nKind: {a['kind']}\nModel: {a['model'] or '-'}\nProfile: {a['profile']}\nWhat it is for: {a['about']}\n"
            f"Benchmark tags: {a['tags'] or '-'}\nPersona: {a['persona'] or '(none yet)'}\nTools: {', '.join(tools_for(agent_id, conn=conn))}\n"
            f"Memory file: {agent_identity.STATE / agent_id / 'memory.sqlite'}\n\nMemories:\n{mem or '(none yet)'}\n"), len(rows)


def kc_link(conn, agent_id):
    """The agent's Knowledge Centre page (its profile and its memories), rewritten when its memory grows."""
    from core import hb_kc_records as kc
    if not {'knowledge_sources', 'knowledge_chunks'} <= kc._tables(conn):
        return None
    text, n = kc_text(conn, agent_id)
    a = get(conn, agent_id)
    sid = a.get('kc_source_id')
    if not sid or not conn.execute('SELECT 1 FROM knowledge_sources WHERE source_id=?', (sid,)).fetchone():
        sid = kc._new_source(conn, f'HB agent {agent_id}', f'hb://agent/{agent_id}', text, ['hb-agent', agent_id], 'hb-agent')
    else:
        conn.execute('UPDATE knowledge_sources SET raw_text=?, content_hash=? WHERE source_id=?', (text, kc._hash(text), sid))
    kc._write_chunks(conn, sid, kc._chunk(text))
    conn.execute('UPDATE hb_agents SET kc_source_id=?, memory_rows=? WHERE agent_id=?', (sid, n, agent_id))
    return sid


def kc_tick(conn):
    """Mirror each onboarded agent's memories into its KC page when they changed."""
    from core import agent_identity
    ensure_schema(conn)
    updated = []
    for agent_id, rows in conn.execute("SELECT agent_id, memory_rows FROM hb_agents WHERE status='active'").fetchall():
        try:
            n = len(agent_identity.read_memory(agent_id, '', 40))
        except Exception:
            continue
        if n != rows:
            kc_link(conn, agent_id)
            updated.append(agent_id)
    return updated


def onboard_local_models(conn, actor='owner', say=None):
    """Every benchmarked local model becomes a read/write HB agent (profile local_worker), knowing what the benchmark found."""
    from core import hb_model_bench as mb
    mb.ensure_schema(conn)
    done = []
    for (raw,) in conn.execute('SELECT record FROM hb_model_bench ORDER BY model').fetchall():
        r = json.loads(raw)
        if r.get('error'):
            continue
        path = next((m['path'] for m in mb.models() if m['label'] == r['model']), '')
        tags = [t for t in r.get('tags', []) if t != 'useless']
        about = (f"A local model on this machine ({r['size_gb']} GB, {'fits' if r['gpu_fit'] else 'too big for'} the GPU, about {r.get('tok_s', '?')} "
                 f"words a second on the CPU). Use it for {', '.join(tags) if tags else 'nothing yet - it failed every benchmark test, so it learns before it works'}.")
        names = sorted(r.get('aliases') or [r['model']], key=lambda n: (n.startswith(('apex-', 'seven-', 'llama-direct', 'gemma-direct', 'homework-', 'fred-')),
                                                                        'latest' in n, -len(n)))
        done.append(onboard(conn, slug(names[0]), kind='local', profile='local_worker', about=about, model=r['model'], model_path=path,
                            tags=r.get('tags', []), actor=actor, say=say, tests=r.get('tests'))['agent_id'])
    return done


def retire(conn, agent_id, actor):
    """Nothing is permanent: an agent can be retired (its memory and KC page stay) and onboarded again later."""
    ensure_schema(conn)
    n = conn.execute("UPDATE hb_agents SET status='retired' WHERE agent_id=?", (agent_id,)).rowcount
    if n:
        conn.execute('UPDATE service_principals SET enabled=0 WHERE id=?', (agent_id,))
    return f'{agent_id} retired (memory and KC page kept; onboard it again any time).' if n else f'No agent {agent_id}.'


def swap_model(conn, agent_id, model_label, actor):
    """Interchangeable: give an agent another model. It is provisional again until the new model's benchmark passes."""
    from core import hb_model_bench as mb
    a = get(conn, agent_id)
    if not a:
        return f'No agent {agent_id}.'
    mb.ensure_schema(conn)
    row = conn.execute('SELECT record FROM hb_model_bench WHERE model=?', (model_label,)).fetchone()
    tests = json.loads(row[0]).get('tests') if row else None
    result = assess(tests)
    conn.execute('UPDATE hb_agents SET model=?, status=? WHERE agent_id=?', (model_label, 'active' if result['passed'] else 'provisional', agent_id))
    return (f"{agent_id} now runs on {model_label}: " + ('passed HB\'s capability check.' if result['passed'] else
            (f"provisional - {result['why']}." if row else 'provisional until HB benchmarks it (/bench ' + model_label + ').')))


def status_text(conn):
    ensure_schema(conn)
    rows = conn.execute("SELECT agent_id, kind, model, profile || ' (' || status || ')', tags, memory_rows FROM hb_agents ORDER BY status, kind, agent_id").fetchall()
    if not rows:
        return 'No agents onboarded through HB yet. /agents onboard-local onboards every benchmarked local model.'
    return 'HB agents:\n' + '\n'.join(f"- {a} ({k}{', ' + m if m else ''}): profile {p}; {t or 'no tags'}; {n} memories" for a, k, m, p, t, n in rows)
