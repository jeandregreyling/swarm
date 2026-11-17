"""Search the SAP notes by meaning (Practice 147, owner 17 Nov 2026: "find something ... to make HB able to do better research" -
"don't we already have enough small models?").

Keyword search (core/hb_note_index, FTS5) finds a note by the words in its title, component, Other Terms and Symptom. It ranked SAP
Note 3713786 - the note that defines the MCB - 14th for "maximum contribution base superannuation Australia", because its title is
"Phase 1 Payroll Changes for Payday Super". A test on 516 notes with the embedding model HB already has (nomic-embed-text, CPU) put it
first, and its best passage was the definition itself ("... an Annual amount of 270,830 AUD").

  chunks()   a note's text in ~800-character paragraph groups
  refresh()  embed the chunks of notes that are new or changed (background thread, CPU model, short write transactions)
  search()   the notes whose chunks are closest to a question, each with its best passage
  fuse()     reciprocal rank fusion of the keyword ranking and this one (k=60)
"""
import array
import logging
import re
import threading
import time

LOG = logging.getLogger(__name__)
MODEL = 'nomic-embed-text'          # already installed; the Ollama-store embed entry runs with ngl 0 / --device none
CHUNK = 800
RRF_K = 60
_cache = {'key': None, 'ids': None, 'chunks': None, 'texts': None, 'matrix': None}
_worker = {'thread': None}


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_note_vectors(source_id INTEGER NOT NULL, chunk INTEGER NOT NULL, text TEXT NOT NULL,
        vec BLOB NOT NULL, content_hash TEXT, PRIMARY KEY(source_id, chunk))''')


def chunks(text, size=CHUNK):
    paras = [' '.join(p.split()) for p in re.split(r'\n\s*\n', str(text or '')) if p.strip()]
    out, cur = [], ''
    for p in paras:
        if cur and len(cur) + len(p) > size:
            out.append(cur)
            cur = ''
        cur += (' ' if cur else '') + p
    if cur:
        out.append(cur)
    return [o[:1400] for o in out]


def _embed(text, embed=None):
    if embed is not None:
        return embed(text)
    from core import llm
    for cut in (1400, 900, 500):        # the server refuses an input longer than its window
        try:
            return llm.embeddings(MODEL, text[:cut])
        except Exception as exc:
            last = exc
    raise last


def _unit(v):
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def pending(conn, limit=50):
    ensure(conn)
    return conn.execute('''SELECT s.source_id, s.title, s.raw_text, s.content_hash FROM knowledge_sources s
        LEFT JOIN (SELECT source_id, MAX(content_hash) AS h FROM hb_note_vectors GROUP BY source_id) v ON v.source_id = s.source_id
        WHERE s.source_ref LIKE 'sap://note/%' AND (v.source_id IS NULL OR v.h IS NOT s.content_hash) LIMIT ?''', (limit,)).fetchall()


def refresh(conn, limit=50, embed=None):
    """Embed up to `limit` new or changed notes. Embedding runs outside any transaction; each note is written in one short one."""
    done = 0
    for sid, title, raw, digest in pending(conn, limit):
        rows = []
        for i, ch in enumerate(chunks(raw)):
            vec = _unit(_embed('search_document: ' + str(title or '')[:150] + ' | ' + ch, embed))
            rows.append((sid, i, ch, array.array('f', vec).tobytes(), digest))
        with conn:
            conn.execute('DELETE FROM hb_note_vectors WHERE source_id=?', (sid,))
            conn.executemany('INSERT INTO hb_note_vectors(source_id, chunk, text, vec, content_hash) VALUES (?,?,?,?,?)', rows or
                             [(sid, 0, '', array.array('f', []).tobytes(), digest)])
        done += 1
    return done


def start_background(connect=None, batch=40, pause=2.0):
    """Coordinator tick: start one background thread that embeds pending notes, then stops. Never blocks the tick."""
    t = _worker['thread']
    if t is not None and t.is_alive():
        return False

    def run():
        from contextlib import closing
        if connect is None:
            from utils.db._connection import get_connection as make
        else:
            make = connect
        try:
            while True:
                with closing(make()) as conn:
                    n = refresh(conn, batch)
                if not n:
                    return
                time.sleep(pause)
        except Exception:
            LOG.exception('SAP note embedding stopped')
    _worker['thread'] = threading.Thread(target=run, name='hb-note-vectors', daemon=True)
    _worker['thread'].start()
    return True


def _load(conn):
    ensure(conn)
    key = conn.execute('SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM hb_note_vectors').fetchone()
    if _cache['key'] == tuple(key):
        return _cache
    ids, nums, texts, vecs = [], [], [], []
    for sid, chunk, text, blob in conn.execute('SELECT source_id, chunk, text, vec FROM hb_note_vectors WHERE length(vec) > 0'):
        a = array.array('f')
        a.frombytes(blob)
        ids.append(sid)
        nums.append(chunk)
        texts.append(text)
        vecs.append(a)
    try:
        import numpy as np
        matrix = np.array([list(v) for v in vecs], dtype='float32') if vecs else None
    except ImportError:
        matrix = vecs
    _cache.update(key=tuple(key), ids=ids, chunks=nums, texts=texts, matrix=matrix)
    return _cache


def search(conn, query, limit=30, embed=None):
    """[(source_id, score, best passage)] - the notes closest in meaning to the query, best first."""
    data = _load(conn)
    if not data['ids']:
        return []
    q = _unit(_embed('search_query: ' + str(query or ''), embed))
    try:
        import numpy as np
        scores = (data['matrix'] @ np.array(q, dtype='float32')).tolist()
    except ImportError:
        scores = [sum(a * b for a, b in zip(v, q)) for v in data['matrix']]
    best = {}
    for sid, score, text in zip(data['ids'], scores, data['texts']):
        if score > best.get(sid, (-2.0, ''))[0]:
            best[sid] = (score, text)
    return [(sid, s, t) for sid, (s, t) in sorted(best.items(), key=lambda kv: -kv[1][0])[:limit]]


def fuse(keyword_ids, vector_ids, k=RRF_K):
    """Reciprocal rank fusion: ids from both rankings, by sum of 1/(k + rank)."""
    score = {}
    for ranking in (keyword_ids, vector_ids):
        for rank, sid in enumerate(ranking, 1):
            score[sid] = score.get(sid, 0.0) + 1.0 / (k + rank)
    return sorted(score, key=lambda s: -score[s])
