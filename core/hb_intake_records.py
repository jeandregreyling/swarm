"""Intake records in Studio (owner 15 Nov 2026: "make the main chat say it and record in Studio and flow to KC").

Main chat already says what arrived and the Knowledge Centre already holds it; this keeps the third record. sync(conn) gives every
email, every inbox-folder file and every SAP notes job one step in the Studio project "Intake: email, files and SAP notes":
  done      taken in and saved (the step names the Knowledge Centre documents), or a notes job that finished
  blocked   arrived but nothing in it could be read (the step says why), or a notes job that SAP stopped
  doing     a notes job still fetching
A step is updated when its job moves on. Only names, counts and document ids are written - never the content of a confidential file."""
import json
import time
import uuid

PROJECT = 'Intake: email, files and SAP notes'


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_intake_studio(key TEXT PRIMARY KEY, step_id TEXT NOT NULL, state TEXT, updated_at REAL)')


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def project(conn, now=None):
    row = conn.execute('SELECT project_id FROM projects WHERE name=?', (PROJECT,)).fetchone()
    if row:
        return row[0]
    now = time.time() if now is None else now
    pid = 'P-' + uuid.uuid4().hex[:10].upper()
    conn.execute("INSERT INTO projects(project_id, name, description, methodology, status, owner, created_at, updated_at) VALUES (?,?,?,'mixed','active','hummingbird',?,?)",
                 (pid, PROJECT, 'Kept by HB itself: one step per email, inbox-folder file and SAP notes job. Content lives in the Knowledge Centre.', now, now))
    return pid


def _put(conn, pid, key, title, description, status, state, now):
    row = conn.execute('SELECT step_id, state FROM hb_intake_studio WHERE key=?', (key,)).fetchone()
    if row and row[1] == state:
        return None
    if row:
        conn.execute('UPDATE project_steps SET title=?, description=?, status=?, updated_at=? WHERE step_id=?', (title[:200], description[:4000], status, now, row[0]))
        conn.execute('UPDATE hb_intake_studio SET state=?, updated_at=? WHERE key=?', (state, now, key))
        return row[0]
    step = 'S-' + uuid.uuid4().hex[:10].upper()
    order = conn.execute('SELECT COALESCE(MAX(order_idx), -1) + 1 FROM project_steps WHERE project_id=?', (pid,)).fetchone()[0]
    conn.execute("INSERT INTO project_steps(step_id, project_id, title, description, status, owner, order_idx, created_at, updated_at) VALUES (?,?,?,?,?,'hummingbird',?,?,?)",
                 (step, pid, title[:200], description[:4000], status, order, now, now))
    conn.execute('INSERT INTO hb_intake_studio(key, step_id, state, updated_at) VALUES (?,?,?,?)', (key, step, state, now))
    return step


def sync(conn, now=None):
    """Bring Studio up to date with the intake. Returns the number of steps written or changed."""
    tables = _tables(conn)
    if not {'projects', 'project_steps'} <= tables:
        return 0
    now = time.time() if now is None else now
    ensure_schema(conn)
    pid, changed = None, 0
    if 'hb_email_seen' in tables:
        for mid, sender, subject, outcome, kc, at in conn.execute(
                "SELECT message_id, sender, subject, outcome, COALESCE(kc_sources,''), at FROM hb_email_seen WHERE outcome NOT LIKE 'left alone%' ORDER BY at").fetchall():
            pid = pid or project(conn, now)
            is_file = sender == 'inbox folder'
            docs = [d for d in kc.split(',') if d]
            read = bool(docs) and outcome == 'taken in'
            when = time.strftime('%d %b %Y %H:%M', time.localtime(at or now))
            title = (f'File: {subject}' if is_file else f'Email: {subject} ({sender})')
            description = (f"{'Dropped into the inbox folder' if is_file else 'Received from ' + sender} on {when}.\n"
                           + (f"Saved in the Knowledge Centre as confidential: {', '.join('KC' + d for d in docs)}." if read else
                              f"Nothing in it could be read ({outcome if outcome != 'taken in' else 'no readable text or attachment'}). Main chat has the reason for each file.")
                           + '\nDone when: every readable part is in the Knowledge Centre')
            changed += bool(_put(conn, pid, f'intake:{mid}', title, description, 'done' if read else 'blocked', f'{outcome}|{kc}', now))
    if 'hb_sap_note_jobs' in tables:
        count = lambda s: len(json.loads(s)) if s else 0
        for sid, title, sheet, numbers, state, added, had, failed, note in conn.execute(
                'SELECT source_id, title, sheet, numbers, state, added, had, failed, note FROM hb_sap_note_jobs ORDER BY created_at').fetchall():
            pid = pid or project(conn, now)
            status = {'done': 'done', 'nothing to fetch': 'done', 'stopped': 'blocked'}.get(state, 'doing')
            description = (f"Source: {title} (tab: {sheet or '-'}).\n{count(numbers)} SAP Note / KBA number(s): {count(added)} added to the Knowledge Centre, "
                           f"{count(had)} already there, {count(failed)} SAP would not give"
                           + (f" ({', '.join(json.loads(failed)[:30])})" if count(failed) else '') + f'.\nState: {state}' + (f' - {note}' if note else '')
                           + (f"\nNotes added: {', '.join(json.loads(added)[:200])}" if count(added) else '')
                           + '\nDone when: every listed note is in the Knowledge Centre (python -m pytest tests/test_hb_sap_note_job.py covers the job)')
            changed += bool(_put(conn, pid, f'notes:{sid}', f'SAP notes: {title}', description, status, f'{state}|{count(added)}|{count(had)}|{count(failed)}', now))
    return changed
