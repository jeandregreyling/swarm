"""Owner 13 Nov: HB's own chat messages must be readable at a glance. One plain first line (what happened), an optional plain
second part (what is next / what you can do), and a "Details:" line with ids, checks and commands. Main chat folds the
details away (the action buttons still read the commands from them)."""
import re


def name(title):
    """A step title as a person would say it: no step id prefix, no '(owner)' / '(APEX)' tags."""
    text = ' '.join(str(title or '').split())
    text = re.sub(r'^S-[0-9A-F]{10}\s+', '', text)
    text = re.sub(r'\s*\((?:owner|APEX|apex)\)', '', text)
    return text[:140].rstrip(' .') or 'this task'


def step_name(conn, step_id, fallback=''):
    try:
        row = conn.execute('SELECT title FROM project_steps WHERE step_id=?', (step_id,)).fetchone()
    except Exception:
        row = None
    return name(row[0] if row else fallback or step_id)


def message(lead, *lines, details=()):
    parts = [lead.strip()] + [l.strip() for l in lines if l and l.strip()]
    facts = [d.strip() for d in details if d and str(d).strip()]
    if facts:
        parts.append('Details: ' + ' · '.join(facts))
    return '\n'.join(parts)
