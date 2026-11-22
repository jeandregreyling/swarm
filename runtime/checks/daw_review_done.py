"""Check for S-5F22A498CF (Media Center DAW review): a Studio note on the step's task with a verdict line for each of the 11 review items.
Exit 0 when done. Verdict lines look like '1. <item> - done|needed|drop - <evidence>'."""
import json, re, sqlite3, sys
c = sqlite3.connect('file:/srv/archive/projects/swarm/swarm_memory.db?mode=ro', uri=True, timeout=30)
rows = c.execute("SELECT e.payload FROM hb_task_events e JOIN hb_tasks t ON t.task_id=e.task_id WHERE t.step_id='S-5F22A498CF' "
                 "AND e.kind='studio_note' ORDER BY e.event_id DESC LIMIT 5").fetchall()
text = '\n'.join(str(json.loads(r[0] or '{}').get('note') or json.loads(r[0] or '{}').get('text') or r[0]) for r in rows)
verdicts = re.findall(r'(?m)^\s*\d+[.)].*\b(done|needed|drop)\b', text, re.I)
print(f'{len(verdicts)} verdict lines found (need 11)')
sys.exit(0 if len(verdicts) >= 11 else 1)
