"""SAP note index (Practice 131, owner 17 Nov 2026: "I thought part of the homework would have been to properly index the notes").

The Knowledge Centre holds ~6,000 SAP notes, and knowledge_search matched words in their text: "STP Phase 2 Australian payroll" ranked
Italian payroll notes above STP2 ones, and notes whose title does not say STP2 (e.g. 3700339 "RPUSTOQ0 - New option to exclude override
entries") were never found. Every note starts with a header - "component PY-AU-STP | version 2 | released 17.10.2025 | SAP Note |
Correction with medium priority" - and has "Symptom" and "Other Terms" sections. HB reads those into hb_note_index, keeps an FTS5
full-text index (hb_note_fts, ranked by BM25: title, component, other terms, symptom), and a search lists the whole component family
the top notes share (all 14 PY-AU-STP notes). refresh() runs on the coordinator tick and re-reads a note whose text changed.
"""
import re
import time
from collections import Counter

BATCH = 500
FAMILY_NOTES = 20          # notes listed across all families in one search result
_HEAD = re.compile(r'component (\S+) \| version (\d+) \| released (\d{2})\.(\d{2})\.(\d{4}) \| SAP Note \| ([^\n]*)')
_FILL = {'sap', 'note', 'notes', 'what', 'do', 'does', 'our', 'say', 'says', 'about', 'issue', 'issues', 'the', 'and', 'for', 'in',
         'of', 'to', 'a', 'an', 'is', 'are', 'with', 'cite', 'number', 'numbers', 'could', 'not', 'find', 'you', 'your', 'me', 'list',
         'main', 'problems', 'fixes', 'which', 'any', 'there', 'how', 'why', 'when', 'or', 'on', 'by', 'from', 'all'}


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_note_index(note TEXT PRIMARY KEY, source_id INTEGER NOT NULL, title TEXT,
        component TEXT, released TEXT, version INTEGER, priority TEXT, terms TEXT, symptom TEXT, mentions TEXT,
        content_hash TEXT, updated_at REAL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS hb_note_index_component ON hb_note_index(component)')
    conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS hb_note_fts USING fts5(note, title, component, terms, symptom)')


def _section(raw, start, ends):
    i = raw.find('\n' + start)
    if i < 0:
        return ''
    i += len(start) + 1
    found = [k for k in (raw.find('\n' + e, i) for e in ends) if k >= 0]
    return ' '.join(raw[i:min(found) if found else len(raw)].split())


def parse(number, raw):
    """The note's header fields and its Symptom / Other Terms text."""
    raw = str(raw or '')
    m = _HEAD.search(raw[:800])
    mentions = []
    for n in re.findall(r'\b(\d{6,8})\b', raw):
        if n != number and n not in mentions:
            mentions.append(n)
    return {'component': m.group(1) if m else '', 'version': int(m.group(2)) if m else 0,
            'released': f'{m.group(5)}-{m.group(4)}-{m.group(3)}' if m else '', 'priority': m.group(6).strip() if m else '',
            'symptom': _section(raw, 'Symptom', ('Other Terms', 'Reason and Prerequisites', 'Solution'))[:1500],
            'terms': _section(raw, 'Other Terms', ('Reason and Prerequisites', 'Solution'))[:600],
            'mentions': ' '.join(mentions[:30])}


def refresh(conn, batch=BATCH):
    """Index notes that are new or whose text changed. Returns how many were (re)indexed."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_sources'").fetchone():
        return 0
    ensure(conn)
    rows = conn.execute('''SELECT s.source_id, substr(s.source_ref, 12), s.title, s.raw_text, s.content_hash FROM knowledge_sources s
        LEFT JOIN hb_note_index i ON i.note = substr(s.source_ref, 12)
        WHERE s.source_ref LIKE 'sap://note/%' AND (i.note IS NULL OR i.content_hash IS NOT s.content_hash OR i.source_id != s.source_id)
        LIMIT ?''', (batch,)).fetchall()
    now = time.time()
    for sid, number, title, raw, digest in rows:
        f = parse(number, raw)
        conn.execute('''INSERT OR REPLACE INTO hb_note_index(note, source_id, title, component, released, version, priority, terms,
            symptom, mentions, content_hash, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                     (number, sid, title, f['component'], f['released'], f['version'], f['priority'], f['terms'], f['symptom'],
                      f['mentions'], digest, now))
        conn.execute('DELETE FROM hb_note_fts WHERE note = ?', (number,))
        conn.execute('INSERT INTO hb_note_fts(note, title, component, terms, symptom) VALUES (?,?,?,?,?)',
                     (number, title, f['component'].replace('-', ' '), f['terms'], f['symptom']))
    return len(rows)


def fts_query(query):
    """Operator words as an FTS5 prefix query: 'STP Phase 2' -> "stp"* OR "phase"*; 'STP2' also searches "stp"*."""
    words = []
    for t in re.findall(r'[A-Za-z0-9]+', str(query or '')):
        t = t.lower()
        if t in _FILL or (t.isdigit() and len(t) < 3):
            continue
        for w in (t, *(re.fullmatch(r'([a-z]{2,})\d{1,2}', t).groups() if re.fullmatch(r'([a-z]{2,})\d{1,2}', t) else ())):
            if w not in words:
                words.append(w)
    return ' OR '.join(f'"{w}"*' for w in words[:12])


def search(conn, query, limit=12):
    """Ranked notes: [{source_id, note, title, component, symptom, tags}]; [] when the index is not built or nothing matches."""
    q = fts_query(query)
    if not q or not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_note_fts'").fetchone():
        return []
    rows = conn.execute('''SELECT i.source_id, i.note, i.title, i.component, i.symptom, s.domain_tags
        FROM hb_note_fts f JOIN hb_note_index i ON i.note = f.note JOIN knowledge_sources s ON s.source_id = i.source_id
        WHERE hb_note_fts MATCH ? ORDER BY bm25(hb_note_fts, 0.0, 6.0, 4.0, 3.0, 1.0) LIMIT ?''', (q, limit)).fetchall()
    return [dict(zip(('source_id', 'note', 'title', 'component', 'symptom', 'tags'), r)) for r in rows]


def _short(note, title):
    t = str(title or '')
    t = re.sub(r'^SAP Note \d+:\s*(\d+\s*-\s*)?', '', t)
    return f'SAP Note {note}: {t[:60]}'


def families(conn, components):
    """Whole component families shared by at least two of the top notes (most shared first), FAMILY_NOTES notes at most."""
    out, room = [], FAMILY_NOTES
    for comp, hits in Counter(c for c in components if c).most_common(2):
        if hits < 2 or room <= 0:
            continue
        rows = conn.execute('SELECT note, title FROM hb_note_index WHERE component = ? ORDER BY note', (comp,)).fetchall()
        out.append({'component': comp, 'count': len(rows), 'notes': [_short(n, t) for n, t in rows[:room]],
                    'hint': 'SAP files all of these under one component: check each one against the question.'})
        room -= len(rows)
    return out


def rank(conn, query, items, library_id, limit=12):
    """Put the index's ranked notes first in a knowledge_search result, and the families they share. Returns (items, families)."""
    hits = search(conn, query, limit)
    if not hits:
        return items, []
    ids = {h['source_id'] for h in hits}
    have = {i.get('source_id'): i for i in items if i.get('store') == 'knowledge_sources'}
    ranked = [have.get(h['source_id']) or {'document_id': library_id + h['source_id'], 'source_id': h['source_id'], 'title': h['title'],
                                           'excerpt': (h['symptom'] or '')[:650], 'tags': h['tags'],
                                           'source_ref': f"sap://note/{h['note']}", 'store': 'knowledge_sources'} for h in hits]
    rest = [i for i in items if not (i.get('store') == 'knowledge_sources' and i.get('source_id') in ids)]
    return ranked + rest, families(conn, [h['component'] for h in hits[:8]])
