"""SAP Notes in HB (owner 15 Nov 2026: "can HB use that to look up notes?").

/note <number>  HB fetches the note from SAP for Me with JD's own S-user and keeps a copy in the Knowledge Centre, so every model can
                read it later with the normal knowledge tools - without any model ever touching the login.
The sign-in lives in scripts/hb_sap_note.py, a separate process under the system Python: the S-user and password go from the system
keyring straight to SAP's sign-in pages. This module never sees them; it only receives the note text."""
import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'hb_sap_note.py'
PYTHON = '/usr/bin/python3'


def fetch(number, run=subprocess.run):
    """(ok, text): the note as plain text, or SAP's / the sign-in's reason in plain words."""
    number = str(number).strip()
    if not re.fullmatch(r'\d{4,10}', number):
        return False, 'Give a note number, for example /note 2382421.'
    try:
        done = run([PYTHON, str(SCRIPT), number], capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False, 'SAP did not answer in 3 minutes.'
    if done.returncode != 0 or not done.stdout.strip():
        return False, (done.stderr or 'SAP returned nothing for that number.').strip().splitlines()[-1][:400]
    return True, done.stdout.strip()


def keep(conn, number, text):
    """Save (or refresh) the note as a Knowledge Centre source. Returns its source id, or None when the KC tables are not there."""
    from core import hb_kc_records as kc
    if not {'knowledge_sources', 'knowledge_chunks'} <= kc._tables(conn):
        return None
    ref = f'sap://note/{number}'
    title = text.splitlines()[0][:200]
    row = conn.execute('SELECT source_id FROM knowledge_sources WHERE source_ref=?', (ref,)).fetchone() if _has_ref(conn) else None
    if row:
        conn.execute('UPDATE knowledge_sources SET raw_text=?, content_hash=?, title=? WHERE source_id=?', (text, kc._hash(text), title, row[0]))
        conn.execute('DELETE FROM knowledge_chunks WHERE source_id=?', (row[0],))
        sid = row[0]
    else:
        sid = kc._new_source(conn, title, ref, text, ['sap-note', f'sap-note-{number}'], 'sap-note')
    kc._write_chunks(conn, sid, kc._chunk(text))
    return sid


def _has_ref(conn):
    return 'source_ref' in {r[1] for r in conn.execute('PRAGMA table_info(knowledge_sources)')}


def command(conn, number, run=subprocess.run, keep=keep):
    ok, text = fetch(number, run)
    if not ok:
        return f'SAP Note {number}: {text}' if re.fullmatch(r'\d{4,10}', str(number).strip()) else text
    try:
        sid = keep(conn, str(number).strip(), text)
    except Exception:
        sid = None
    shown = text if len(text) <= 1800 else text[:1800].rsplit('\n', 1)[0] + '\n[...]'
    return shown + (f'\nDetails: the whole note is in the Knowledge Centre (KC{sid}); every model can read it there.' if sid
                    else '\nDetails: the note could not be saved in the Knowledge Centre.')
