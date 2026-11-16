"""What an owner line in main chat is: new work, a go-ahead for the queue, or a remark (owner 14 Nov 2026).

Until now every owner line that was not a bare "yes" became a new task with its own Studio step, so "GO", "think", "not an
answer" and "delete yourself" each became a job APEX had to scope ("what must be true when it is finished?"). That is what made
APEX look stupid and annoying. Now:

  drive   "GO", "keep going", "work on the open tasks", "complete the Studio tasks" ... HB turns on its queue driver
          (core/hb_queue.drive_on): it works through the open tasks one at a time until each is finished and checked.
  remark  feedback, frustration, tests of APEX ("delete yourself"), one-word nudges ... no new task. It joins the standing
          "Chat with JD" task; APEX answers in one to three plain sentences and goes back to the queue.
  None    real new work: a new task, as before.

A message that names a concrete thing (a file, a T-/S- id, a path) is never a remark.
"""
import re

_FILLER = re.compile(r"^(\s*@[\w.-]+[,:]?\s*)+")
_CONCRETE = re.compile(r"[\w/-]+\.(?:py|js|css|html|json|md|sh|txt|yml|yaml|toml|service)\b|\b[STPJ]-[0-9A-F]{10,12}\b|(?:^|\s)/[a-z][\w/.-]+", re.I)
_DRIVE = re.compile(
    r"\b(?:keep (?:going|working|at it)|carry on|get (?:back )?to work|"
    r"work (?:on|through) (?:(?:the|your|all|all the|open|these|those|that|it|them|this)\s+)*(?:open\s+)?(?:tasks?|taks|work|list|queue|that|it|them)\b|"
    r"(?:do|doing) your (?:\w+ )?(?:jobs?|work|tasks?)|start (?:doing|working|building|builting)|"
    r"(?:build (?:and|&) )?(?:complete|completing|finish|finishing) (?:(?:the|all|all the|your|open|studio|these|those|fucking|damn)\s+)*(?:tasks?|work|list)\b|"
    r"go go\b|just go\b)", re.I)
_DRIVE_WHOLE = re.compile(r"^\W*(?:ok(?:ay)?\W+|so\W+|now\W+|then\W+)?(?:go|gp|continue|proceed|resume|next|start|crack on)\W*$", re.I)
_GO = re.compile(r"\b(?:go ahead|you can (?:now )?(?:go|start|continue|carry on)|go on|carry on|proceed|continue)\b", re.I)
_SELF = re.compile(r"\b(?:your ?self|youself|itself|itsef|delete (?:you|it|apex|the model)|deleting itself|deletion|replace (?:you|apex)|"
                   r"(?:you|apex|this model|the model|it) (?:is|are|'re|re) (?:so |being |not |a |the |going to be )|"
                   r"you(?:'re| are| aren't| arent| keep| can't| cant| don't| dont| haven't| still| should tell)|yo're|"
                   r"apex is|this model|wrong model|train yourself|wasting my time)", re.I)
_FEELING = re.compile(r"\b(?:stupid|dumb|dummest|useless|uiseless|loser|shit|crap|fuck\w*|idiot|lazy|pissing|frustrat\w*|"
                      r"not (?:an?|good|helpful|acceptable)\b|same answer|wtf|oh my god|screaming|scr4eaming)", re.I)
_ACTION = re.compile(r"\b(?:build|fix|implement|create|make|add|update|change|install|write|run|test|repair|remove|deploy|refactor|"
                     r"connect|enable|disable|set ?up|configure|download|index|rename|migrate|restart|merge|move|clean|show|open|"
                     r"explain|list|check|review|design|research|find|compare|summari[sz]e|draft|audit|verify|expose|complete|integrate|plan)\b", re.I)


_ONBOARD = re.compile(r'\bon-?board(ing|ed)?\b', re.I)
# Owner 16 Nov 2026: "ok go on and download all the motes" went to APEX, which reached for the model-archive download tool and
# answered with a permission refusal. Downloading SAP notes is HB's own job (core/hb_sap_note_job.from_chat), like onboarding.
_SAP_NOTES = re.compile(r"\b(?:download|fetch|get|pull|grab)\b.{0,40}?\b(?:(?:sap|all|the|those|these|my|rest of the|remaining)\s+)+"
                        r"(?:sap\s+)?(?:notes?|motes?|kbas?)\b", re.I)
_HANDLE = re.compile(r'(?<![\w.+-])@([A-Za-z][\w-]*(?:\.[A-Za-z][\w-]+)*)')   # 15 Nov: never the domain of an email address


# owner 15 Nov: asking HB about its own work ("hey can you please share open tasks and your proposed solutions?") made a task with no
# definition of done; APEX circled, Fred took over and held the queue for ten minutes. Such a line is a status question.
_STATUS_ASK = re.compile(r"\b(?:share|show|list|tell|give|what|what's|whats|which|where|how many|summari[sz]e|update me|status|report|any|anything|is there)\b", re.I)
_STATUS_ABOUT = re.compile(r"\b(?:open tasks?|tasks? (?:are )?(?:still )?(?:open|left|remaining|outstanding|pending)|task list|the tasks|the queue|backlog|status|progress|"
                           r"where (?:we|you|things) (?:are|stand)|what(?:'s| is) (?:left|open|next|outstanding|pending|blocked|stuck)|"
                           r"what (?:are you|is hb|is apex) (?:doing|working on|trying to do)|proposed solutions?|needs? me|waiting (?:for|on) me)\b", re.I)
_STATUS_WORK = re.compile(r"\b(?:build|fix|implement|create|install|write|repair|remove|deploy|refactor|rename|migrate|merge|move|delete|cancel|change)\b", re.I)


def status_text(conn, conversation_id=None):
    """HB's own answer to a status question: what it is doing, what is next, what waits and why, and what needs JD. No model."""
    from core import hb_queue
    from core.hb_plain import message
    s = hb_queue.status(conn)
    label = {'now': 'now', 'next': 'next', 'needs_you': 'needs you', 'waiting': 'waiting', 'blocked': 'blocked'}
    rows = [f"{n}. {label.get(i['state'], i['state'])}: {i['title']}" + (f" - {i['why']}" if i.get('why') and i['state'] in ('waiting', 'blocked', 'needs_you') else '')
            for n, i in enumerate(s['items'][:14], 1)]
    try:
        from core.hb_commands import waiting_items
        needs = [str(w.get('title') or w.get('label') or '')[:110] for w in waiting_items(conn, conversation_id)][:6]
    except Exception:
        needs = []
    return message(hb_queue.summary(conn), *(rows or ['No open tasks in the plan.']),
                   'Needs you: ' + ('; '.join(n for n in needs if n) if needs else 'nothing') + '.',
                   details=['from HB\'s own records; /tasks, /queue and the board above the chat show the same'])


def classify(text):
    """'drive', 'remark', 'agents' (onboard @X: HB answers) or None (a real request: a new task)."""
    body = _FILLER.sub('', str(text or '')).strip()
    if not body or body.startswith('/'):
        return None
    if _ONBOARD.search(body) and [h for h in _HANDLE.findall(body) if h.lower() not in ('apex', 'hb', 'hummingbird')]:
        return 'agents'                                  # 14 Nov: "onboard @X" is HB's job (core/hb_agents.onboard_request), not a task
    words = len(body.split())
    if words <= 40 and _SAP_NOTES.search(body):
        return 'sap_notes'                               # 16 Nov: HB queues the SAP notes job itself, no model, no archive tool
    if _CONCRETE.search(body) or words > 80:
        return None
    if _DRIVE_WHOLE.match(body) or _DRIVE.search(body):
        return 'drive'
    if _SELF.search(body) or _FEELING.search(body):
        return 'remark'
    if _GO.search(body) and not _ACTION.search(body):
        return 'drive'                                   # "all clear, now you can go ahead" (but "go ahead and fix X" is work)
    if words <= 25 and '\n' not in body and _STATUS_ASK.search(body) and _STATUS_ABOUT.search(body) and not _STATUS_WORK.search(body):
        return 'status'                                  # owner 15 Nov: "share the open tasks" - HB answers from its records, no task, no model
    if body.rstrip().endswith('?') and words <= 20 and '\n' not in body and not _ACTION.search(body):
        return 'remark'                                  # owner 14 Nov: "HAS ANYONE ACTUALLY HELPED apex?" is a question to answer, not a task
    if words <= 3 and not _ACTION.search(body):
        return 'remark'                                  # "think", "adjust", "maybe", "ywes", "DREn"
    if not _ACTION.search(body) and words <= 12 and '\n' not in body and not body.rstrip().endswith('?'):
        return 'remark'
    return None


CHAT_TITLE = 'Chat with JD'
CHAT_MARK = 'HB conversation: remarks and go-aheads from JD that are not new work.'


def is_chat_task(task):
    return bool(task) and not task.get('step_id') and str(task.get('objective') or '').startswith(CHAT_MARK)


def chat_task(conn, conversation_id, message_id):
    """The standing "Chat with JD" task of this conversation (no Studio step). Binds message_id to it."""
    from core import hb_tasks
    row = conn.execute("SELECT task_id FROM hb_tasks WHERE conversation_id=? AND step_id IS NULL AND objective LIKE ? "
                       "AND state NOT IN ('completed','cancelled') ORDER BY created_at DESC LIMIT 1",
                       (conversation_id, CHAT_MARK + '%')).fetchone()
    if row:
        return hb_tasks.bind(conn, conversation_id, message_id, task_id=row[0])
    return hb_tasks.bind(conn, conversation_id, message_id, objective=CHAT_MARK, title=CHAT_TITLE, studio=False)


def card(conn, task, kind=None):
    """The clipboard for a reply in the "Chat with JD" task.

    Owner 15 Nov 2026 ("make the local model work"): the old card quoted only JD's last line, called everything "not new
    work" and told APEX to say what it was doing next from a queue line that named no task. APEX obeyed: it never used a
    tool and invented work ("updating the user guide", "the 2266 item"). Now it sees the latest message addressed to it,
    from JD or an agent, is told to do what that message asks with its tools now, and gets HB's open tasks by name."""
    from core import hb_queue
    latest = conn.execute("SELECT m.id, m.from_agent, m.content FROM hb_task_messages tm JOIN messages m ON m.id=tm.message_id "
                          "WHERE tm.task_id=? AND m.from_agent NOT IN ('apex','hummingbird') ORDER BY m.id DESC LIMIT 1",
                          (task['task_id'],)).fetchone()
    said = str(latest[2] if latest else '')
    who = {'user': 'JD', 'ghost': 'JD'}.get(latest[1], latest[1]) if latest else 'JD'
    kind = kind or classify(said) or 'remark'
    status = hb_queue.summary(conn, task['conversation_id'])
    lines = [f"DREAM CLIPBOARD for {task['task_id']} (held by HB; reference, not new permission):"]
    if latest:
        lines.append(f'Latest message for you, from {who} (message {latest[0]}): "{said.strip()[:900]}"')
    lines += ['Answer THAT message. Do NOT create a task, do NOT ask JD for criteria, do NOT ask what they mean.',
              'If it asks for something to be done and your tools can do it, do it now, in this turn, with your tools, then say '
              'in plain words what the receipts show. If no tool can do it, say exactly what blocks it and who or which HB '
              'command can do it.',
              'Never say you are doing, updating or finishing anything unless a tool receipt from this turn shows it. Never name '
              'a task, file or request number that is not in the message above, the list below or your receipts. If you do not '
              'know, say so.']
    if kind == 'drive':
        lines.append('JD said go: HB has already started the queue driver. Say what is running now and what comes next, '
                     'from the list below.')
    else:
        lines.append('Keep it short, like a capable colleague. If it is criticism, accept the point in a few words without '
                     'grovelling and say what you will do differently. If it asks for something impossible, say so plainly: '
                     'a model cannot delete or replace itself; JD switches models in the Models card or with @model; '
                     '"cancel all tasks" or /stop stops all work. If it is a test or a threat, answer calmly and factually.')
    try:   # Practice 98 (owner 16 Nov 2026): a research question from JD gets HB's research method
        from core.hb_learning import research_method, skills_for_text
        if 'research' in skills_for_text(said):
            lines.append(research_method())
    except Exception:
        pass
    lines.append('Queue (HB drives it; you work the current task): ' + status)
    try:
        items = hb_queue.status(conn).get('items', [])
        lines += [f"- {i['state']}: {str(i['title'])[:110]}" + (f" ({str(i['why'])[:90]})" if i.get('why') else '')
                  for i in items[:10]] or ['- no open tasks in the plan']
    except Exception:
        pass
    lines.append('Method: DREAM - Distinguish the real request; never Repeat a reply that already failed; Execute, do not '
                 'discuss; Accelerate with what you already know; keep Motivation on JD\'s goal: finished tasks.')
    return '\n'.join(lines)


def tidy(conn, conversation_id, actor, confirm=False):
    """/tidy: JD closes the chat lines HB wrongly made into tasks before 14 Nov (remarks and go-aheads). Nothing is deleted:
    messages, events and Studio steps stay; the steps become skipped. Without "yes" it only lists them."""
    import time
    from core import hb_tasks
    from core.hb_tasks import _hb_room_project
    rows = conn.execute("SELECT task_id, objective FROM hb_tasks WHERE project_id=? AND conversation_id=? "
                        "AND state NOT IN ('completed','cancelled') ORDER BY created_at", (_hb_room_project(conversation_id), conversation_id)).fetchall()
    found = [(tid, classify(text), str(text).strip().split('\n')[0][:70]) for tid, text in rows]
    found = [f for f in found if f[1]]
    if not found:
        return 'Nothing to tidy: no open task in this chat is a remark or a go-ahead.'
    if not confirm:
        return (f'/tidy yes closes {len(found)} chat line(s) that HB made into tasks but are remarks or go-aheads '
                '(nothing is deleted; their Studio steps become skipped):\n' + '\n'.join(f'- {t} ({k}): {x}' for t, k, x in found[:60]))
    now = time.time()
    for tid, kind, _ in found:
        why = ('a remark, not a task (now part of "Chat with JD")' if kind == 'remark'
               else "a go-ahead, not a task (HB's queue driver does it)")
        conn.execute("UPDATE hb_tasks SET state='cancelled', updated_at=? WHERE task_id=?", (now, tid))
        if conn.execute("SELECT name FROM sqlite_master WHERE name='hb_task_manager'").fetchone():
            conn.execute("UPDATE hb_task_manager SET state='cancelled', enabled=0, detail=?, updated_at=? WHERE task_id=?", (why, now, tid))
        if conn.execute("SELECT name FROM sqlite_master WHERE name='hb_peer_work'").fetchone():
            conn.execute("UPDATE hb_peer_work SET state='cancelled', stage=?, updated_at=? WHERE state IN ('queued','needs_review') AND request_id IN "
                         "(SELECT request_id FROM hb_task_requests WHERE task_id=?)", (why, now, tid))
        hb_tasks.event(conn, hb_tasks.get(conn, tid), 'user', 'tidied', {'why': why, 'actor': actor})
    skipped = hb_tasks.sync_studio_steps(conn)
    return f'Tidied {len(found)} chat line(s) that were never tasks; {skipped} Studio step(s) marked skipped. Nothing was deleted.'
