import sys
sys.path.insert(0, '/home/jd/swarm')
from contextlib import closing
from utils.db._connection import get_connection
from core import hb_tasks, hb_plan_workflow as wf
sid = sys.argv[1]
with closing(get_connection()) as c:
    title, desc = c.execute('SELECT title, description FROM project_steps WHERE step_id=?', (sid,)).fetchone()
    mid = c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'hummingbird','apex',?,'response',0)",
                    (f"Studio step {sid}: {title} - change set prepared and tested; APEX applies it.",)).lastrowid
    t = hb_tasks.bind(c, 2845, mid, objective=f"Studio step {sid} ({wf.DEFAULT_PROJECT}): {title}\n{desc}", title=title,
                      project_id=wf.DEFAULT_PROJECT, step_id=sid)
    hb_tasks.event(c, t, 'hummingbird', 'change_set_prepared', {'step_id': sid})
    c.commit()
    print(t['task_id'] if isinstance(t, dict) else t)
