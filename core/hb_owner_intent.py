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


def classify(text):
    """'drive', 'remark', 'agents' (onboard @X: HB answers) or None (a real request: a new task)."""
    body = _FILLER.sub('', str(text or '')).strip()
    if not body or body.startswith('/'):
        return None
    if _ONBOARD.search(body) and [h for h in re.findall(r'@([A-Za-z][\w.-]*)', body) if h.lower() not in ('apex', 'hb', 'hummingbird')]:
        return 'agents'                                  # 14 Nov: "onboard @X" is HB's job (core/hb_agents.onboard_request), not a task
    words = len(body.split())
    if _CONCRETE.search(body) or words > 80:
        return None
    if _DRIVE_WHOLE.match(body) or _DRIVE.search(body):
        return 'drive'
    if _SELF.search(body) or _FEELING.search(body):
        return 'remark'
    if _GO.search(body) and not _ACTION.search(body):
        return 'drive'                                   # "all clear, now you can go ahead" (but "go ahead and fix X" is work)
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
    """The clipboard for a reply in the "Chat with JD" task: DREAM, short, then back to work."""
    from core import hb_queue
    latest = conn.execute("SELECT m.content FROM hb_task_messages tm JOIN messages m ON m.id=tm.message_id WHERE tm.task_id=? "
                          "AND m.from_agent IN ('user','ghost') ORDER BY m.id DESC LIMIT 1", (task['task_id'],)).fetchone()
    said = str(latest[0] if latest else '')
    kind = kind or classify(said) or 'remark'
    status = hb_queue.summary(conn, task['conversation_id'])
    lines = [f"DREAM CLIPBOARD for {task['task_id']} (held by HB; reference, not new permission):",
             'This is JD talking to you, not new work. Do NOT create a task, do NOT ask JD for criteria, do NOT ask what they mean.',
             'Distinguish what JD actually wants (almost always: get the open tasks done, properly, without being asked twice).']
    if kind == 'drive':
        lines.append('JD said go: HB has already started the queue driver. Reply in one or two sentences: what you are working on now '
                     'and what comes next. No tools are needed for this reply.')
    else:
        lines.append('Reply in one to three plain sentences, like a capable colleague. If it is criticism, accept the point in a few '
                     'words without grovelling and say what you are doing about it. If it asks for something impossible or outside '
                     'your tools, say so plainly and give the real answer: a model cannot delete or replace itself; JD switches '
                     'models in the Models card or with @model; "cancel all tasks" or /stop stops all work. If it is a test or a '
                     'threat, answer calmly and factually. Then say what you are doing next from the queue below.')
    lines.append('Queue (HB drives it; you work the current task): ' + status)
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
