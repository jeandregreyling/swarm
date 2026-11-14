"""Answering a question with a question (owner 14 Nov 2026): "never answer a question with a question unless it has a different outcome than
expected - that is worth measuring and learning."

  asked_back(...)  when an agent's reply to JD's own request is mainly a question, HB records it ('asked_back')
  resolve(...)     JD's next line decides whether the question was needed:
                   a go-ahead, a short yes/no or a remark  -> UNNEEDED: it added nothing; the agent gets a lesson (act on the plain meaning,
                                                              state the assumption)
                   real new information (anything else)    -> NEEDED: the answer changed what happens
  counts per agent appear in /merits (core/hb_merits.py), so HB learns which models ask good questions and which only stall.
"""
import json
import re
import time

_Q_START = re.compile(r'^(what|which|who|when|where|why|how|do|does|did|should|shall|would|could|can|is|are|will|may)\b', re.I)
_ASK_BACK = re.compile(r'^(please\s+)?(define|confirm|clarify|specify|tell me|let me know|provide|give me|share)\b', re.I)   # a request back to JD
_SHORT_YES = re.compile(r"^\s*(yes|yep|yeah|ok(ay)?|sure|no|nope|go|go ahead|do it|just do it|please do|continue|carry on|proceed|fine|whatever)\b[\s!.,]*\w{0,12}[\s!.]*$", re.I)


def is_question(text):
    """Mainly a question: it ends with one, or most of its sentences are questions."""
    t = re.sub(r'\[Backend[^\]]*\]', '', str(text or '')).strip()
    if not t:
        return False
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]
    questions = [s for s in sentences if s.endswith('?') or (_Q_START.match(s) and len(s) < 160 and not s.endswith('.')) or _ASK_BACK.match(s)]
    return t.endswith('?') or (len(questions) * 2 > len(sentences))


def asked_back(conn, task, agent, text, request_id):
    """Called when an agent's reply is recorded. Records it when it answered JD's own request with a question."""
    if not task or not request_id or not is_question(text):
        return None
    sender = conn.execute('SELECT sender FROM peer_messages WHERE id=?', (request_id,)).fetchone()
    if not sender or sender[0] not in ('user', 'ghost', 'owner'):
        return None
    from core import hb_tasks
    return hb_tasks.event(conn, task, 'hummingbird', 'asked_back', {'agent': agent, 'question': str(text)[:400], 'request_id': request_id, 'outcome': None})


def resolve(conn, conversation_id, owner_text, intent=None):
    """JD's next line in the chat decides the newest open 'asked_back'. Returns 'needed', 'unneeded' or None."""
    row = conn.execute("""SELECT e.event_id, e.task_id, e.payload FROM hb_task_events e JOIN hb_tasks t ON t.task_id=e.task_id
        WHERE e.kind='asked_back' AND t.conversation_id=? AND json_extract(e.payload,'$.outcome') IS NULL ORDER BY e.event_id DESC LIMIT 1""",
                       (conversation_id,)).fetchone()
    if not row:
        return None
    p = json.loads(row[2])
    unneeded = intent in ('drive', 'remark') or bool(_SHORT_YES.match(str(owner_text or '')))
    outcome = 'unneeded' if unneeded else 'needed'
    p.update(outcome=outcome, owner_said=str(owner_text or '')[:200], decided_at=time.time())
    conn.execute('UPDATE hb_task_events SET payload=? WHERE event_id=?', (json.dumps(p), row[0]))
    try:
        from core import hb_merits
        role = 'APEX' if p['agent'] == 'apex' else p['agent']
        hb_merits._add(conn, 'asked_' + outcome, role, '', task_id=row[1], ref=f"ask:{row[0]}", note=p['question'][:300])
        if unneeded:
            hb_merits._add(conn, 'lesson', role, '', task_id=row[1], ref=f"ask-lesson:{row[0]}",
                           note=f"What went wrong: answered JD's request with a question that changed nothing (JD said: {p['owner_said'][:80]}) | "
                                "The better way: act on the plain meaning of the request and say the assumption you made; ask only when the answer "
                                "would change what happens.")
    except Exception:
        pass
    return outcome
