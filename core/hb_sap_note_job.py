"""SAP notes job (owner 15 Nov 2026): "open that file, look at the 'needs check' tab ... let APEX cook through the notes, they all
need to be included in KC".

When a spreadsheet arrives through the email intake or the inbox folder, HB starts a job by itself:
  1. find the tab whose name says "needs check" (if there is none: every tab),
  2. collect the SAP Note / KBA numbers in it (the column headed Note / KBA when there is one, else every cell that is just a number
     of 6-10 digits, with or without the words "SAP Note" / "KBA"),
  3. fetch each one from SAP with JD's S-user (core/hb_sap_notes.py - the sign-in is a separate process; this code never sees the
     password) and save it in the Knowledge Centre, a few seconds apart, skipping the ones already there,
  4. say in main chat how many were added, which were already there and which SAP would not give.
The spreadsheet is confidential: its rows are read here, on this machine, and never posted. Only note numbers and counts appear in chat.
/notes shows the jobs; /notes run KC<id> starts one by hand for a saved spreadsheet."""
import json
import re
import threading
import time
from contextlib import closing

MAIN_CHAT = 2834
PAUSE_S = 3.0
MAX_NOTES = 400
_RUNNING = threading.Lock()
_NUMBER = re.compile(r'^(?:sap\s*)?(?:note|kba|hinweis)?\s*#?\s*(\d{6,10})$', re.I)
_HEADER = re.compile(r'\b(notes?|kbas?|hinweis)\b', re.I)
# Owner 15 Nov 2026: a link to a note counts, in any column: me.sap.com/notes/N, launchpad #/notes/N, sapnotes/Detail?q=N,
# ?note=N, and KBA links .../knowledge/en/N.
_LINK = re.compile(r'(?:/notes?/|sapnotes/Detail\?q=|[?&]note=|/knowledge/(?:[a-z]{2}/)?)(\d{6,10})\b', re.I)


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS hb_sap_note_jobs(source_id INTEGER PRIMARY KEY, title TEXT, sheet TEXT, numbers TEXT,
        state TEXT NOT NULL DEFAULT 'pending', added TEXT, had TEXT, failed TEXT, note TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL)""")


def sheets(text):
    """[(sheet name, [[cell, ...], ...])] from the text the intake saves ("## Sheet: name (N rows)" blocks, tab-separated rows).
    A CSV file (no sheet heading) is one sheet called 'file'."""
    blocks, name, rows = [], None, []
    for line in str(text).splitlines():
        head = re.match(r'## Sheet: (.*?) \(\d+ rows\)\s*$', line)
        if head:
            if name is not None:
                blocks.append((name, rows))
            name, rows = head.group(1), []
        elif name is not None and line.strip():
            rows.append(line.split('\t'))
    if name is not None:
        blocks.append((name, rows))
    if not blocks:
        body = str(text).split('\n\n', 1)[-1]
        blocks = [('file', [re.split(r'[,;\t]', l) for l in body.splitlines() if l.strip()])]
    return blocks


def pick(blocks, want='needs check'):
    """The tab(s) to read: those whose name contains every word of `want` (case, spaces, dashes and underscores do not matter)."""
    norm = lambda s: re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).split()
    words = [w.rstrip('s') for w in norm(want)]
    hit = [b for b in blocks if all(any(part.rstrip('s') == w for part in norm(b[0])) for w in words)]
    return hit or blocks, bool(hit)


def numbers(rows):
    """SAP Note / KBA numbers in a tab, in the order they appear, each once."""
    found, column = [], None
    for row in rows[:15]:
        cols = [i for i, cell in enumerate(row) if _HEADER.search(str(cell)) and not re.search(r'\d', str(cell))]
        if cols:
            column = cols[0]
            break
    for row in rows:
        cells = [row[column]] if column is not None and column < len(row) else ([] if column is not None else row)
        for n in (n for cell in row for n in _LINK.findall(str(cell))):
            if n not in found:
                found.append(n)
        for cell in cells:
            for piece in re.split(r'[,;/\s]+(?=(?:sap|note|kba|\d))', str(cell).strip(), flags=re.I):
                m = _NUMBER.match(re.sub(r'\.0$', '', piece.strip()))
                if m and m.group(1) not in found:
                    found.append(m.group(1))
    return found[:MAX_NOTES]


def plan(text, want='needs check'):
    """{'sheet': names read, 'matched': was a 'needs check' tab found, 'numbers': [...]} for a saved spreadsheet's text."""
    chosen, matched = pick(sheets(text), want)
    found = []
    for _, rows in chosen:
        found += [n for n in numbers(rows) if n not in found]
    return {'sheet': ', '.join(name for name, _ in chosen), 'matched': matched, 'numbers': found[:MAX_NOTES]}


def _say(conn, text):
    try:   # owner 15 Nov 2026: in the chat JD last typed in, not the old main chat 2834 where he never saw the notes job
        row = conn.execute("SELECT conversation_id FROM messages WHERE from_agent='user' ORDER BY id DESC LIMIT 1").fetchone()
        chat = int(row[0]) if row else MAIN_CHAT
    except Exception:
        chat = MAIN_CHAT
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                 (chat, text))


def find_new(conn):
    """Spreadsheets the intake saved that have no job yet -> job rows. Returns how many were added."""
    ensure_schema(conn)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_sources'").fetchone():
        return 0
    added = 0
    for sid, title, text in conn.execute("SELECT source_id, title, raw_text FROM knowledge_sources WHERE status='active' AND domain_tags LIKE '%confidential%' "
                                         "AND (title LIKE 'Email attachment:%' OR title LIKE 'Inbox file:%') AND source_id NOT IN (SELECT source_id FROM hb_sap_note_jobs)").fetchall():
        if not re.search(r'\.(xlsx|xlsm|csv|tsv)\b', str(title), re.I):
            continue
        p = plan(text)
        now = time.time()
        conn.execute('INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                     (sid, str(title)[:200], p['sheet'][:200], json.dumps(p['numbers']), 'pending' if p['numbers'] else 'nothing to fetch', now, now))
        from core.hb_plain import message
        _say(conn, message(f"🔎 {str(title)[:120]}: " + (f"{len(p['numbers'])} SAP Note / KBA number(s) found" if p['numbers'] else 'no SAP Note numbers found')
                           + (f" in the tab \"{p['sheet']}\"." if p['matched'] else ' (no tab named "needs check"; every tab was read).'),
                           'HB fetches them from SAP now and saves each in the Knowledge Centre.' if p['numbers'] else 'Nothing to fetch.',
                           details=[f'spreadsheet KC{sid}; /notes shows progress']))
        added += 1
    return added


_BARE = re.compile(r'(?<![\d/#=])(\d{6,10})(?!\d)')
_NAMED = re.compile(r'\b(?:sap\s*)?(?:note|kba|hinweis)\s*#?\s*(\d{6,10})\b', re.I)


def numbers_in(text):
    """SAP note numbers in a chat message, in order: its note links (a pasted list links every row; a title that mentions
    "after SAP Note 3430313" is not a row), else "note 1234567", else a list of at least three bare numbers."""
    text = str(text or '')
    found = list(dict.fromkeys(_LINK.findall(text))) or list(dict.fromkeys(_NAMED.findall(text)))
    if not found:
        bare = list(dict.fromkeys(_BARE.findall(text)))
        found = bare if len(bare) >= 3 else []
    return found


def from_chat(conn, conversation_id, text, now=None):
    """Owner 16 Nov 2026: "ok go on and download all the motes". HB takes the note numbers from this message, else from the latest
    message of JD's in this chat that has some (his pasted list), skips notes already in the Knowledge Centre or already queued, and
    queues the rest in jobs of MAX_NOTES. Returns the plain text HB answers with."""
    from core.hb_plain import message
    ensure_schema(conn)
    now = time.time() if now is None else now
    found, source = numbers_in(text), 'your message'
    if not found:
        for (content,) in conn.execute("SELECT content FROM messages WHERE conversation_id=? AND from_agent='user' ORDER BY id DESC LIMIT 300",
                                       (conversation_id,)):
            found = numbers_in(content)
            if found:
                source = 'the list you pasted earlier in this chat'
                break
    if not found:
        return message('📚 HB found no SAP note numbers to download.',
                       'Paste the list (note links or numbers) into this chat, or save the spreadsheet in the HB inbox folder. A spreadsheet '
                       'with a company protection label cannot be opened here: paste its rows instead.')
    queued = set()
    for (numbers,) in conn.execute("SELECT numbers FROM hb_sap_note_jobs WHERE state IN ('pending','running')"):
        try:
            queued |= set(json.loads(numbers or '[]'))
        except ValueError:
            pass
    have_now = [n for n in found if have(conn, n)]
    todo = [n for n in found if n not in queued and n not in have_now]
    chunks = [todo[i:i + MAX_NOTES] for i in range(0, len(todo), MAX_NOTES)]
    for i, chunk in enumerate(chunks):
        sid = -int(now * 1000) - i                       # a pasted list has no spreadsheet in the Knowledge Centre: a negative id marks it
        conn.execute('INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                     (sid, f"pasted list, part {i + 1} of {len(chunks)} ({len(chunk)} notes), {time.strftime('%d %b %H:%M', time.localtime(now))}",
                      'pasted', json.dumps(chunk), 'pending', now + i * 0.001, now))
    done = f'{len(have_now)} already in the Knowledge Centre' + (f', {len(found) - len(todo) - len(have_now)} already queued' if len(found) - len(todo) - len(have_now) else '')
    if not todo:
        return message(f'📚 Nothing new to download: all {len(found)} SAP notes from {source} are in the Knowledge Centre or already queued.', done + '. /notes shows progress.')
    return message(f'📚 Downloading {len(todo)} SAP notes from {source}.',
                   f'{len(chunks)} job(s) of up to {MAX_NOTES}, one after another, a few seconds apart; HB says here when each is done. {done}.',
                   details=['/notes shows progress', 'SAP notes are HB\'s own job: no archive download, no extra permission needed'])


def have(conn, number):
    return conn.execute('SELECT 1 FROM knowledge_sources WHERE source_ref=?', (f'sap://note/{number}',)).fetchone() is not None


def run(conn, source_id, fetch=None, keep=None, pause=PAUSE_S, sleep=time.sleep, commit=None):
    """Fetch every note of one job. Stops at once when SAP refuses the sign-in (so the account is never hammered). Returns the final state."""
    from core import hb_sap_notes
    fetch, keep = fetch or hb_sap_notes.fetch, keep or hb_sap_notes.keep
    row = conn.execute('SELECT title, numbers FROM hb_sap_note_jobs WHERE source_id=?', (source_id,)).fetchone()
    todo = json.loads(row[1])
    added, had, failed, state, note = [], [], [], 'done', ''
    conn.execute("UPDATE hb_sap_note_jobs SET state='running', updated_at=? WHERE source_id=?", (time.time(), source_id))
    if commit:
        commit()                                         # 15 Nov: never hold the database while SAP is being asked (minutes)
    for n, number in enumerate(todo, 1):
        if have(conn, number):
            had.append(number)
            continue
        ok, text = fetch(number)
        if ok:
            keep(conn, number, text)
            added.append(number)
            if commit:
                commit()
        elif 'sign-in' in text.lower() or 'second factor' in text.lower() or 'no sap login' in text.lower():
            state, note = 'stopped', text[:300]
            break
        else:
            failed.append(number)
        conn.execute('UPDATE hb_sap_note_jobs SET added=?, had=?, failed=?, updated_at=? WHERE source_id=?',
                     (json.dumps(added), json.dumps(had), json.dumps(failed), time.time(), source_id))
        if commit:
            commit()
        if n < len(todo):
            sleep(pause)
    conn.execute('UPDATE hb_sap_note_jobs SET state=?, note=?, added=?, had=?, failed=?, updated_at=? WHERE source_id=?',
                 (state, note, json.dumps(added), json.dumps(had), json.dumps(failed), time.time(), source_id))
    from core.hb_plain import message
    left = len(todo) - len(added) - len(had) - len(failed)
    _say(conn, message(f"📚 SAP notes from {str(row[0])[:100]}: {len(added)} added to the Knowledge Centre, {len(had)} already there"
                       + (f", {len(failed)} SAP would not give ({', '.join(failed[:20])})" if failed else '') + '.',
                       (f'Stopped with {left} still to fetch: {note} Fix the login (gold window), then /notes run KC{source_id}.' if state == 'stopped'
                        else 'Every model can read them now: ask APEX about any of them by number, or search the Knowledge Centre for "SAP Note".'),
                       details=[f'job for spreadsheet KC{source_id}; tags sap-note']))
    return state


STALE_S = 600


def visible(conn, source_id):
    try:
        conn.rollback()                                  # look at the database as it is now, not at an old snapshot
    except Exception:
        pass
    return conn.execute('SELECT 1 FROM hb_sap_note_jobs WHERE source_id=?', (source_id,)).fetchone() is not None


def tick(conn):
    """HB's loop: turn newly arrived spreadsheets into jobs and run one pending job in the background."""
    find_new(conn)
    # 15 Nov: a job cut off by a restart (still "running", untouched for 10 minutes) goes back in line; notes already saved are skipped
    conn.execute("UPDATE hb_sap_note_jobs SET state='pending' WHERE state='running' AND updated_at<?", (time.time() - STALE_S,))
    row = conn.execute("SELECT source_id FROM hb_sap_note_jobs WHERE state='pending' ORDER BY created_at LIMIT 1").fetchone()
    if not row or not _RUNNING.acquire(blocking=False):
        return None
    sid = row[0]
    conn.execute("UPDATE hb_sap_note_jobs SET state='running', updated_at=? WHERE source_id=?", (time.time(), sid))

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own:
                for _ in range(60):                      # 15 Nov: the job row is only visible once HB's loop has committed it
                    if visible(own, sid):
                        break
                    time.sleep(1)
                run(own, sid, commit=own.commit)
                own.commit()
        except Exception:
            import logging
            logging.getLogger('hb.sap_notes').exception('SAP notes job %s failed', sid)
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-sap-notes-job', daemon=True).start()
    return sid


def command(conn, args):
    """/notes  ·  /notes run KC<id>  ·  /notes add <numbers, in any layout>"""
    ensure_schema(conn)
    if args and args[0].lower() == 'add':     # owner 15 Nov: a pasted list (a column copied from a sheet, commas, "Note 123..."): no file needed
        found = []
        for piece in re.split(r'[\s,;/|]+', ' '.join(args[1:])):
            m = re.fullmatch(r'#?(\d{6,10})\.?', piece.strip())
            if m and m.group(1) not in found:
                found.append(m.group(1))
        if not found:
            return 'Give the note numbers after /notes add, for example: /notes add 2382421 1999997 2000002'
        now = time.time()
        sid = -int(now * 1000)                # a pasted list has no spreadsheet in the Knowledge Centre: a negative id marks it
        conn.execute('INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                     (sid, f"pasted list of {len(found)} note number(s), {time.strftime('%d %b %H:%M', time.localtime(now))}", 'pasted', json.dumps(found[:MAX_NOTES]),
                      'pending', now, now))
        return (f'{len(found[:MAX_NOTES])} SAP Note number(s) taken; HB starts fetching within a minute and says when they are in the Knowledge Centre. '
                '/notes shows progress.')
    if len(args) == 2 and args[0].lower() == 'run' and re.fullmatch(r'(?i)(kc)?\d+', args[1]):
        sid = int(re.sub(r'\D', '', args[1]))
        row = conn.execute('SELECT title, raw_text FROM knowledge_sources WHERE source_id=?', (sid,)).fetchone()
        if not row:
            return f'KC{sid} is not in the Knowledge Centre.'
        p = plan(row[1])
        now = time.time()
        conn.execute('INSERT OR REPLACE INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                     (sid, str(row[0])[:200], p['sheet'][:200], json.dumps(p['numbers']), 'pending' if p['numbers'] else 'nothing to fetch', now, now))
        return (f"KC{sid}: {len(p['numbers'])} SAP Note number(s) in \"{p['sheet']}\"; HB starts fetching within a minute." if p['numbers']
                else f'KC{sid}: no SAP Note numbers found.')
    rows = conn.execute('SELECT source_id, title, state, numbers, added, had, failed, note FROM hb_sap_note_jobs ORDER BY created_at DESC LIMIT 6').fetchall()
    if not rows:
        return 'No SAP notes job yet. One starts by itself when a spreadsheet arrives by email or in the inbox folder.'
    count = lambda s: len(json.loads(s)) if s else 0
    return 'SAP notes jobs:\n' + '\n'.join(f"- KC{sid} {str(title)[:70]}: {state} - {count(nums)} number(s), {count(a)} added, {count(h)} already there, "
                                           f"{count(f)} failed" + (f' ({note[:120]})' if note else '') for sid, title, state, nums, a, h, f, note in rows)
