"""Consultant protocol (owner 12 Nov 2026): acknowledge at once, investigate, narrow to four options, follow through.

/consult <question>   HB acknowledges at once (no model) and notes what it will check; the counsel model then investigates.
The answer must have exactly four labelled options - recommended, possible 1, possible 2, dream - each with reasons, risk, effort
and evidence. validate() checks that shape in plain Python (never a model); a wrong shape goes back to the SAME model with the
format string, at most RETRIES times. /choose C-xxxx N records JD's choice; the question, options and choice are saved in the KC.
"""
import json
import threading
import time
import uuid
from contextlib import closing

LABELS = ('recommended', 'possible 1', 'possible 2', 'dream')
KEYS = ('title', 'reasons', 'risk', 'effort', 'evidence')
RETRIES = 2
FORMAT = ('Answer with JSON only: {"options": [four objects]}. Each object has the keys label, title, reasons, risk, effort, evidence '
          '(all non-empty text). The four labels, in this order: "recommended", "possible 1", "possible 2", "dream".')
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['options'],
          'properties': {'options': {'type': 'array', 'minItems': 4, 'maxItems': 4, 'items': {
              'type': 'object', 'additionalProperties': False, 'required': ['label', *KEYS],
              'properties': {'label': {'type': 'string', 'enum': list(LABELS)}, **{k: {'type': 'string', 'maxLength': 500} for k in KEYS}}}}}}
_RUNNING = threading.Lock()


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS hb_consultations(consult_id TEXT PRIMARY KEY, conversation_id INTEGER, asked_by TEXT,
        question TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', options TEXT, attempts INTEGER NOT NULL DEFAULT 0, choice INTEGER,
        kc_source_id INTEGER, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL)""")


def validate(answer):
    """Deterministic shape check. Returns the list of problems ([] = valid). answer: dict or JSON text."""
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except ValueError:
            return ['the answer is not JSON']
    options = answer.get('options') if isinstance(answer, dict) else None
    if not isinstance(options, list):
        return ['no "options" list']
    problems = []
    labels = [str(o.get('label', '')).strip().lower() if isinstance(o, dict) else '' for o in options]
    if labels != list(LABELS):
        problems.append('the four labels must be, in order: ' + ', '.join(LABELS))
    for n, o in enumerate(options, 1):
        missing = [k for k in KEYS if not (isinstance(o, dict) and str(o.get(k) or '').strip())]
        if missing:
            problems.append(f'option {n} is missing: ' + ', '.join(missing))
    return problems


def acknowledge(question):
    """The first answer, posted at once without a model."""
    from core.hb_plain import message
    return message('👋 I am looking at it.', f'Your question: {" ".join(str(question).split())[:300]}',
                   'I will check what HB already has (code, Knowledge Centre, earlier Studio work), then come back with four options: '
                   'one recommended, two possible and one dream, each with reasons, risk, effort and evidence. Slow is fine; I will say when it is ready.')


def ask(model, question, facts=''):
    """Ask the model; a wrong shape goes back to the same model with the format string. Returns (options, attempts) or raises ValueError."""
    messages = [{'role': 'system', 'content': 'You are HB\'s consultant: a careful business partner. Use only the facts given; say so when '
                                              'evidence is thin. ' + FORMAT},
                {'role': 'user', 'content': f'Question from the owner: {question}\n\nWhat HB found:\n{facts or "(nothing found)"}'}]
    problems = []
    for attempt in range(1, RETRIES + 2):
        answer = model(messages)
        problems = validate(answer)
        if not problems:
            data = json.loads(answer) if isinstance(answer, str) else answer
            return data['options'], attempt
        messages = messages[:2] + [{'role': 'assistant', 'content': answer if isinstance(answer, str) else json.dumps(answer)},
                                   {'role': 'user', 'content': 'The harness rejected that answer: ' + '; '.join(problems) + '. ' + FORMAT}]
    raise ValueError('the model did not give four valid options: ' + '; '.join(problems))


def _say(conn, conversation_id, text):
    return conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                        "VALUES (?,'hummingbird','user',?,'response',0)", (conversation_id, text)).lastrowid


def open_consultation(conn, conversation_id, question, actor):
    """/consult: record the question and return the acknowledgement (HB posts it as the command's answer)."""
    question = ' '.join(str(question or '').split())
    if len(question) < 8:
        return 'Ask a full question: /consult <your question>'
    ensure_schema(conn)
    cid = 'C-' + uuid.uuid4().hex[:8].upper()
    now = time.time()
    conn.execute('INSERT INTO hb_consultations(consult_id,conversation_id,asked_by,question,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                 (cid, conversation_id, str(actor)[:80], question[:2000], now, now))
    return acknowledge(question) + f'\nDetails: consultation {cid}'


def call_model(messages):
    from core import llm
    from core.hb_counsel import MODEL
    text, _ = llm.chat_via_gateway(MODEL, messages, temperature=0.2, absolute_timeout_s=1200, idle_timeout_s=400, queue_timeout_s=10, keep_alive=600,
                                   options={'num_ctx': 16384, 'num_predict': 1500, 'timeout': 1200, 'startup_timeout': 300, 'require_complete_output': True},
                                   response_format={'type': 'json_schema', 'json_schema': {'name': 'hb_consultant', 'strict': True, 'schema': SCHEMA}})
    return text


def gather(conn, question):
    """What HB already has on the question: Knowledge Centre passages (best effort)."""
    words = [w for w in ''.join(ch if ch.isalnum() else ' ' for ch in question.lower()).split() if len(w) > 4][:6]
    found = []
    try:
        for w in words:
            for title, text in conn.execute("SELECT s.title, substr(c.content,1,400) FROM knowledge_chunks c JOIN knowledge_sources s "
                                            "ON s.source_id=c.source_id WHERE c.content LIKE ? LIMIT 2", (f'%{w}%',)):
                found.append(f'- KC "{title}": {" ".join(str(text).split())}')
    except Exception:
        pass
    return '\n'.join(found[:8])


def options_text(cid, question, options):
    from core.hb_plain import message
    lines = [f"{n}. {o['label'].capitalize()}: {o['title']} - {o['reasons']} Risk: {o['risk']} Effort: {o['effort']} Evidence: {o['evidence']}"
             for n, o in enumerate(options, 1)]
    return message(f'🧭 Four options for: {question[:200]}', *lines, f'Choose with /choose {cid} N (1-4).', details=[f'consultation {cid}'])


def investigate(conn, cid, model=call_model):
    """Run one consultation: facts -> model -> shape check -> post the four options. Returns the new state."""
    row = conn.execute('SELECT conversation_id, question FROM hb_consultations WHERE consult_id=?', (cid,)).fetchone()
    conversation_id, question = row
    try:
        options, attempts = ask(model, question, gather(conn, question))
    except Exception as exc:
        conn.execute("UPDATE hb_consultations SET state='failed', error=?, updated_at=? WHERE consult_id=?", (str(exc)[:500], time.time(), cid))
        _say(conn, conversation_id, f'⚠ HB could not get four valid options for {cid}: {str(exc)[:300]} Ask again with /consult.')
        return 'failed'
    conn.execute("UPDATE hb_consultations SET state='options', options=?, attempts=?, updated_at=? WHERE consult_id=?",
                 (json.dumps(options), attempts, time.time(), cid))
    _say(conn, conversation_id, options_text(cid, question, options))
    return 'options'


def choose(conn, cid, number, actor):
    """/choose C-xxxx N: record the choice and save question, options and choice in the Knowledge Centre."""
    ensure_schema(conn)
    row = conn.execute('SELECT question, options, state FROM hb_consultations WHERE consult_id=?', (cid,)).fetchone()
    if not row:
        return f'No consultation {cid}.'
    if not row[1]:
        return f'{cid} has no options yet (state: {row[2]}).'
    options = json.loads(row[1])
    if not 1 <= number <= 4:
        return 'Choose 1-4.'
    o = options[number - 1]
    text = (f'Consultation {cid}\nQuestion: {row[0]}\n\n' + '\n'.join(
        f"{n}. {x['label']}: {x['title']}\n   Reasons: {x['reasons']}\n   Risk: {x['risk']}\n   Effort: {x['effort']}\n   Evidence: {x['evidence']}"
        for n, x in enumerate(options, 1)) + f"\n\nChosen by {actor} on {time.strftime('%d %b %Y')}: option {number} ({o['label']}) - {o['title']}\n")
    sid = None
    try:
        from core import hb_kc_records as kc
        if {'knowledge_sources', 'knowledge_chunks'} <= kc._tables(conn):
            sid = kc._new_source(conn, f'Consultation {cid}: {row[0][:80]}', f'hb://consultation/{cid}', text, ['hb-consultation'], 'hb-consultation')
            kc._write_chunks(conn, sid, kc._chunk(text))
    except Exception:
        sid = None
    conn.execute("UPDATE hb_consultations SET state='chosen', choice=?, kc_source_id=?, updated_at=? WHERE consult_id=?", (number, sid, time.time(), cid))
    return (f"{cid}: option {number} ({o['label']}: {o['title']}) is recorded" + (f' and saved in the Knowledge Centre (KC{sid}).' if sid else '.')
            + ' Say "go" with what you want built from it and HB follows through.')


def tick(conn):
    """HB's loop: investigate the oldest pending consultation in the background (one at a time, when the counsel model is free)."""
    ensure_schema(conn)
    row = conn.execute("SELECT consult_id FROM hb_consultations WHERE state='pending' ORDER BY created_at LIMIT 1").fetchone()
    if not row:
        return None
    from core import hb_counsel
    if not hb_counsel.can_run(conn) or not _RUNNING.acquire(blocking=False):
        return None
    cid = row[0]
    conn.execute("UPDATE hb_consultations SET state='investigating', updated_at=? WHERE consult_id=?", (time.time(), cid))

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own, own:
                investigate(own, cid)
        except Exception:
            import logging
            logging.getLogger('hb.consultant').exception('consultation %s failed', cid)
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-consultant', daemon=True).start()
    return cid
