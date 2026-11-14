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
    have = {r[1] for r in conn.execute('PRAGMA table_info(hb_agents)')}
    for col in ('handles', 'exam'):                      # 14 Nov: @handles JD uses, and who examined the agent (only HB's exam counts)
        if col not in have:
            conn.execute(f"ALTER TABLE hb_agents ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_agent_exams(id INTEGER PRIMARY KEY, exam_id TEXT, agent_id TEXT, test TEXT, tag TEXT,
        sent_at REAL, conversation_id INTEGER, answer TEXT, passed INTEGER, why TEXT, answered_at REAL)''')


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


def onboard(conn, agent_id, *, kind, profile, about, model='', model_path='', tags=(), actor='owner', say=None, provision=None, tests=None,
            exam_by=None, handles=()):
    """exam_by='hb' only when HB itself ran the tests (its model benchmark, or examine() through the agent's inbox). Results an agent
    reports about itself do not count (owner 14 Nov): the agent stays provisional and HB examines it."""
    from core import agent_identity
    from core.hb_agent_profiles import tools_for, instructions_for
    lines, post_once = [], say is None
    say = say or lines.append                            # 14 Nov: one readable onboarding message in main chat, not six
    agent_id = agent_identity.name(agent_id)
    if kind not in KINDS:
        raise ValueError('kind must be local or online')
    ensure_schema(conn)
    before = get(conn, agent_id) or {}                   # read before the upsert (it rewrites tags)
    now = time.time()
    conn.execute('INSERT INTO hb_agents(agent_id,kind,model,model_path,profile,about,tags,onboarded_at,actor) VALUES(?,?,?,?,?,?,?,?,?) '
                 'ON CONFLICT(agent_id) DO UPDATE SET kind=excluded.kind, model=excluded.model, model_path=excluded.model_path, profile=excluded.profile, '
                 'about=excluded.about, tags=excluded.tags', (agent_id, kind, model, model_path, profile, about, ','.join(tags), now, actor))
    conn.execute("INSERT OR IGNORE INTO service_principals(id,display_name,role,enabled,created_at) VALUES (?,?,'service',1,?)",
                 (agent_id, about.split('.')[0][:80], now))
    try:
        kept = json.loads(before.get('exam') or '{}')
    except ValueError:
        kept = {}
    if exam_by is None and kept.get('by') == 'hb':         # re-onboarding (new memory, terms, handles) keeps a valid HB exam
        result, exam_by = {k: kept.get(k) for k in ('score', 'agency', 'passed', 'why')}, 'hb'
        tags = tags or tuple(t for t in (before.get('tags') or '').split(',') if t)
        conn.execute("UPDATE hb_agents SET tags=? WHERE agent_id=?", (','.join(tags), agent_id))
    else:
        result = assess(tests) if exam_by == 'hb' else {'score': 0, 'agency': False, 'passed': False,
                                                         'why': 'HB has not examined it yet (results an agent reports about itself do not count)'}
    conn.execute('UPDATE hb_agents SET status=?, exam=? WHERE agent_id=?', ('active' if result['passed'] else 'provisional',
                 json.dumps({**(kept if exam_by == 'hb' and kept.get('by') == 'hb' else {}), 'by': exam_by or 'none',
                             'at': kept.get('at', now) if kept.get('by') == 'hb' else now, **result}), agent_id))
    if handles:
        set_handles(conn, agent_id, handles)
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
           + (f"HB's benchmark found me good at: {', '.join(tags)}. " if tags else '') + instructions_for(agent_id, conn=conn)
           + ' ' + (_online_terms(agent_id, tools) if kind == 'online' else _local_terms(tools)))
    try:
        agent_identity.save_memory(agent_id, 'Who I am (HB onboarding)', who[:6000], tags='identity,onboarding', importance=9, source='hb_onboarding')
    except Exception as exc:
        say(f"↺ {agent_id}: first memory not written yet ({type(exc).__name__}); HB retries at the next onboarding run.")
    say(f"🌱 {agent_id}: its first memory says who it is and what it is for.")
    kc_link(conn, agent_id)
    say((f"✅ {agent_id} is onboarded: own memory, KC page, {len(tools)} tools{', read/write' if can_write else ''}. Personas can be added later."
         if result['passed'] else f"⏸ {agent_id} is registered (own memory, KC page) but provisional until it passes HB's capability check."))
    say(welcome(conn, agent_id))
    if post_once:
        _post(conn, '\n'.join(lines))
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
                            tags=r.get('tags', []), actor=actor, say=say, tests=r.get('tests'), exam_by='hb')['agent_id'])
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
    rows = conn.execute("SELECT agent_id, kind, model, profile || ' (' || status || ')', tags, memory_rows, handles, exam FROM hb_agents "
                        "ORDER BY status, kind, agent_id").fetchall()
    if not rows:
        return 'No agents onboarded through HB yet. /agents onboard-local onboards every benchmarked local model.'
    return 'HB agents:\n' + '\n'.join(
        f"- {a}{' (@' + ', @'.join(h.split(',')) + ')' if h else ''} ({k}{', ' + m if m else ''}): profile {p}; {t or 'no tags'}; {n} memories; "
        f"{_exam_line(e)}" + (f"; {_budget_line(conn, a)}" if k == 'online' else '') for a, k, m, p, t, n, h, e in rows)


# ------------------------------------------------------------------ handles and HB's own exam (owner 14 Nov 2026)
# "@apex can you onboard the @github identity" went nowhere: no agent had the handle @github, and copilot-instructor had marked itself
# active by running HB's scorers on its own answers. Now: handles are data (set_handles), only an exam HB runs counts, and HB answers
# "onboard @X" itself (onboard_request) instead of making it a task for APEX.
EXAM_TIMEOUT_S = 3600


def _exam_line(raw):
    try:
        e = json.loads(raw or '{}')
    except ValueError:
        e = {}
    if not e:
        return 'exam: not recorded'
    when = time.strftime('%d %b %H:%M', time.localtime(e['at'])) if e.get('at') else ''
    return (f"exam by HB {when}: score {e.get('score')} ({e.get('why')})" if e.get('by') == 'hb'
            else f"exam: {e.get('why') or 'not run by HB'}")


def set_handles(conn, agent_id, handles):
    ensure_schema(conn)
    clean = sorted({str(h).strip().lstrip('@').lower() for h in handles if str(h).strip().lstrip('@')})
    conn.execute('UPDATE hb_agents SET handles=? WHERE agent_id=?', (','.join(clean), agent_id))
    return clean


def resolve(conn, handle):
    """'@github' / 'github' / 'copilot-instructor' -> 'copilot-instructor' (or None). By data, never by a hard-coded name."""
    ensure_schema(conn)
    h = str(handle or '').strip().lstrip('@').lower()
    if not h:
        return None
    for agent_id, handles in conn.execute('SELECT agent_id, handles FROM hb_agents').fetchall():
        if h == agent_id.lower() or h in (handles or '').split(','):
            return agent_id
    return None


def examine(conn, agent_id, conversation_id=2834, actor='owner', say=None):
    """HB examines an online agent itself: each benchmark question goes to the agent's inbox with a tag; exam_tick scores the replies with
    HB's own scorers. Until it passes, the agent is provisional (it can read and remember, not work)."""
    from core import hb_model_bench as mb
    say = say or (lambda text: _post(conn, text))
    a = get(conn, agent_id)
    if not a:
        return f'No agent {agent_id}.'
    open_exam = conn.execute('SELECT exam_id FROM hb_agent_exams WHERE agent_id=? AND answered_at IS NULL LIMIT 1', (agent_id,)).fetchone()
    if open_exam:
        return f'HB is already examining {agent_id} (exam {open_exam[0]}); its answers are scored as they arrive.'
    now = time.time()
    exam_id = 'X-' + format(int(now * 1000) % 16 ** 8, '08X')
    conn.execute('UPDATE hb_agents SET status=? WHERE agent_id=?', ('provisional', agent_id))
    for name, prompt, _score, _max in mb.TESTS:
        tag = f'[HB EXAM {exam_id} {name}]'
        body = (f"{tag}\nHB is examining you for onboarding (asked by {actor}). Answer this one question yourself, in a single reply that starts "
                f"with the tag above exactly. Do not read or run HB's scorer or benchmark code: HB measures you, not the code.\n\n{prompt}")
        conn.execute('INSERT INTO peer_messages(conversation_id,message_id,sender,recipient,body,created_at) VALUES (?,?,?,?,?,?)',
                     (conversation_id, None, 'hummingbird', agent_id, body, now))
        conn.execute('INSERT INTO hb_agent_exams(exam_id,agent_id,test,tag,sent_at,conversation_id) VALUES (?,?,?,?,?,?)',
                     (exam_id, agent_id, name, tag, now, conversation_id))
    text = (f"🧪 HB is examining {agent_id} for onboarding (exam {exam_id}): {len(mb.TESTS)} questions sent to its inbox. HB scores each answer "
            f"itself as it arrives and posts it here; until it passes, {agent_id} is provisional.")
    say(text)
    return text


def _answer(conn, row):
    """The agent's reply to one exam question: in its peer inbox replies or in main chat, after the question was sent."""
    exam_row_id, agent_id, tag, sent_at, conv = row
    for sql in ("SELECT body FROM peer_messages WHERE sender=? AND created_at>=? AND instr(body, ?)>0 ORDER BY id LIMIT 1",
                "SELECT content FROM messages WHERE from_agent=? AND created_at>=datetime(?, 'unixepoch') AND instr(content, ?)>0 ORDER BY id LIMIT 1"):
        hit = conn.execute(sql, (agent_id, sent_at - 1, tag)).fetchone()
        if hit:
            return str(hit[0]).split(tag, 1)[-1].strip()
    return None


def exam_tick(conn, say=None, now=None):
    """Coordinator: score exam answers as they arrive; finish an exam when every question is answered or has timed out."""
    from core import hb_model_bench as mb
    ensure_schema(conn)
    say = say or (lambda text: _post(conn, text))
    now = now or time.time()
    scorers = {name: score for name, _p, score, _m in mb.TESTS}
    for rid, agent_id, test, tag, sent_at, conv in conn.execute(
            'SELECT id, agent_id, test, tag, sent_at, conversation_id FROM hb_agent_exams WHERE answered_at IS NULL').fetchall():
        text = _answer(conn, (rid, agent_id, tag, sent_at, conv))
        if text is None and now - sent_at < EXAM_TIMEOUT_S:
            continue
        ok, why = scorers[test](text) if text is not None else (False, 'no answer within an hour')
        conn.execute('UPDATE hb_agent_exams SET answer=?, passed=?, why=?, answered_at=? WHERE id=?', ((text or '')[:4000], int(bool(ok)), why, now, rid))
        say(f"🧪 {agent_id}: {'✔' if ok else '✘'} {test}: {why}")
    for exam_id, agent_id in conn.execute('SELECT DISTINCT exam_id, agent_id FROM hb_agent_exams e WHERE NOT EXISTS (SELECT 1 FROM hb_agent_exams x '
                                          'WHERE x.exam_id=e.exam_id AND x.answered_at IS NULL)').fetchall():
        a = get(conn, agent_id)
        try:
            done = json.loads(a.get('exam') or '{}').get('exam_id') == exam_id
        except ValueError:
            done = False
        if done:
            continue
        tests = {t: {'passed': bool(p)} for t, p in conn.execute('SELECT test, passed FROM hb_agent_exams WHERE exam_id=?', (exam_id,)).fetchall()}
        result = assess(tests)
        conn.execute('UPDATE hb_agents SET status=?, exam=?, tags=? WHERE agent_id=?', ('active' if result['passed'] else 'provisional',
                     json.dumps({'by': 'hb', 'exam_id': exam_id, 'at': now, **result}), ','.join(mb.tags(tests)), agent_id))
        say((f"✅ {agent_id} passed HB's exam {exam_id} (score {result['score']}): onboarding complete, it can work now." if result['passed'] else
             f"⏸ {agent_id} did not pass HB's exam {exam_id}: {result['why']} (score {result['score']}). It stays provisional; "
             f"/agents examine {agent_id} tries again."))
        try:
            kc_link(conn, agent_id)
        except Exception:
            pass


def onboard_request(conn, conversation_id, text, actor):
    """JD: "@apex can you onboard the @github identity" - HB answers this itself (onboarding is HB's job, not a task for APEX)."""
    ensure_schema(conn)
    names = [h for h in re.findall(r'@([A-Za-z][\w.-]*)', str(text or '')) if h.lower() not in ('apex', 'hb', 'hummingbird')]
    if not names:
        return None
    out = []
    for h in dict.fromkeys(names):
        agent_id = resolve(conn, h)
        if not agent_id:
            out.append(f"HB does not know @{h} yet. To register a new online agent: /agents onboard <id> <profile> <what it is for>, then "
                       f"/agents handles <id> {h}. HB then examines it through its inbox. Keys and logins only through JD's secure terminal.")
            continue
        a = get(conn, agent_id)
        try:
            exam = json.loads(a.get('exam') or '{}')
        except ValueError:
            exam = {}
        if a['status'] == 'active' and exam.get('by') == 'hb':
            out.append(f"@{h} is {agent_id}: already onboarded - own memory, KC page {a.get('kc_source_id')}, profile {a['profile']}, "
                       f"{_exam_line(a.get('exam'))}. Nothing left to do.")
        else:
            out.append(f"@{h} is {agent_id}: registered (own memory, KC page {a.get('kc_source_id')}) but HB has not examined it itself. "
                       + examine(conn, agent_id, conversation_id, actor, say=lambda _t: None))
    return '\n'.join(out)


def _online_terms(agent_id, tools):
    """Owner 14 Nov: every online agent is onboarded knowing its access, its limits and what tokens cost JD (same rules as the Gemini build)."""
    from core import hb_budget
    return ("My access in HB: I can read (code, Knowledge Centre, task and Studio records), keep my own memory, and write Studio proposals "
            f"(tools: {', '.join(tools)}). I cannot change HB, run commands or tests, or approve anything: code changes go as Studio proposals "
            "that HB checks and APEX applies. I never see or handle keys, logins or card details. " + hb_budget.text_for(agent_id))


def _budget_line(conn, agent_id):
    try:
        from core import hb_budget
        return hb_budget.line(conn, agent_id)
    except Exception:
        return 'tokens: unknown'


def _local_terms(tools):
    return ("My access in HB: I read and research, keep my own memory, and change code only through HB (proposals that HB checks; JD approves). "
            f"Tools: {', '.join(tools)}. I run on JD's machine, so I cost nothing per token - but GPU and memory are shared, so I keep turns short.")


# ------------------------------------------------------------------ welcome pack (owner 14 Nov 2026), the same for local and online agents
WELCOME = __import__('pathlib').Path(__file__).resolve().parent / 'capability_packs' / 'hb.agent.welcome.v1.json'


def welcome(conn, agent_id, send=True):
    """Who we are (from the pack) + what you are (from the agent's record). Saved as the agent's memory, sent to its inbox, and the agent
    confirms with a tagged reply (welcome_tick). Returns the line HB posts in main chat."""
    from core import agent_identity
    from core.hb_agent_profiles import tools_for
    pack = json.loads(WELCOME.read_text())
    a = get(conn, agent_id)
    tag = f'[HB WELCOME {agent_id}]'
    tools = tools_for(agent_id, conn=conn)
    you = (f"You are {agent_id}" + (f" (@{', @'.join(a['handles'].split(','))})" if a.get('handles') else '') + f", a {a['kind']} agent with the "
           f"{a['profile']} profile. What you are for: {a['about']} Tags from HB's own tests: {a.get('tags') or 'none yet'}. Status: {a['status']} "
           f"({_exam_line(a.get('exam'))}). " + (_online_terms(agent_id, tools) if a['kind'] == 'online' else _local_terms(tools)) +
           f" Your memory: {agent_identity.STATE / agent_id / 'memory.sqlite'}; your KC page: {a.get('kc_source_id')}.")
    text = (f"{tag}\nWelcome to HB, {agent_id}. We are glad you are here.\n\nWho we are:\n- " + '\n- '.join(pack['who_we_are'])
            + f"\n\nWhat you are:\n{you}\n\n" + pack['ack'].format(tag=tag))
    try:
        agent_identity.save_memory(agent_id, 'Welcome pack (HB onboarding)', text[:6000], tags='identity,onboarding,welcome', importance=9,
                                   source='hb_welcome')
    except Exception:
        pass
    if send and a['kind'] == 'online' and conn.execute("SELECT 1 FROM sqlite_master WHERE name='peer_messages'").fetchone():
        conn.execute('INSERT INTO peer_messages(conversation_id,message_id,sender,recipient,body,created_at) VALUES (2834,NULL,?,?,?,?)',
                     ('hummingbird', agent_id, text, time.time()))
    conn.execute('CREATE TABLE IF NOT EXISTS hb_agent_welcome(agent_id TEXT PRIMARY KEY, sent_at REAL, acked_at REAL, ack TEXT)')
    conn.execute('INSERT INTO hb_agent_welcome(agent_id, sent_at) VALUES (?,?) ON CONFLICT(agent_id) DO UPDATE SET sent_at=excluded.sent_at, '
                 'acked_at=NULL, ack=NULL', (agent_id, time.time()))
    return (f"🌱 Welcome pack for {agent_id}: who we are and what it is, in its memory" + (' and its inbox' if a['kind'] == 'online' else '')
            + (f"; HB waits for its reply tagged {tag}." if a['kind'] == 'online' else '.'))


def welcome_tick(conn, say=None):
    """Closes the loop: an online agent's tagged reply to its welcome pack is the proof it got it."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_agent_welcome'").fetchone():
        return
    say = say or (lambda text: _post(conn, text))
    for agent_id, sent_at in conn.execute('SELECT agent_id, sent_at FROM hb_agent_welcome WHERE acked_at IS NULL').fetchall():
        a = get(conn, agent_id)
        if not a or a['kind'] != 'online':
            continue
        text = _answer(conn, (None, agent_id, f'[HB WELCOME {agent_id}]', sent_at, 2834))
        if text:
            conn.execute('UPDATE hb_agent_welcome SET acked_at=?, ack=? WHERE agent_id=?', (time.time(), text[:1000], agent_id))
            say(f"🌺 {agent_id} confirmed its welcome pack: \"{text.strip()[:200]}\" - welcome aboard.")


# ------------------------------------------------------------------ handles in main chat (owner 14 Nov 2026: "@git" must reach the git agent)
def _routed_elsewhere():
    from core.hb_online import PROVIDERS                 # online agents that already have their own route (Codex, Gemini)
    from core.hb_agent_profiles import _pack
    return set(PROVIDERS.values()) - set(_pack().get('inbox_agents', []))   # agents reading their own inbox (data)


def inbox_route(conn, conversation_id, message_id, text, sender='user'):
    """JD's @handle for an onboarded online agent goes to that agent's inbox. Returns the agent ids it went to."""
    ensure_schema(conn)
    out = []
    for h in re.findall(r'@([A-Za-z][\w.-]*)', str(text or '')):
        agent_id = resolve(conn, h)
        a = get(conn, agent_id) if agent_id else None
        if not a or a['kind'] != 'online' or a['status'] == 'retired' or agent_id in out or agent_id in _routed_elsewhere():
            continue
        conn.execute('INSERT INTO peer_messages(conversation_id,message_id,sender,recipient,body,created_at) VALUES (?,?,?,?,?,?)',
                     (conversation_id, message_id, sender, agent_id, str(text), time.time()))
        out.append(agent_id)
    return out


def mention_items(conn):
    """Rows for the @ list: every handle of an onboarded online agent that has no other route."""
    ensure_schema(conn)
    out = []
    for agent_id, handles, status in conn.execute("SELECT agent_id, handles, status FROM hb_agents WHERE kind='online' AND status<>'retired' "
                                                  "ORDER BY agent_id").fetchall():
        if agent_id in _routed_elsewhere():
            continue
        for h in [x for x in (handles or '').split(',') if x]:
            out.append({'key': h, 'label': f'{agent_id} (@{h})', 'tier': 'online', 'note': f'onboarded agent · {status} · its inbox'})
    return out
