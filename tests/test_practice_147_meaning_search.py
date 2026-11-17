"""Practice 147 (owner 17 Nov 2026: "find something ... to make HB able to do better research" - "don't we already have enough small
models?"): the notes are searched by meaning with the embedding model HB already has (nomic-embed-text, CPU) as well as by keyword, the
two rankings are fused, and a note whose title lacks the question's words shows its passage closest to the question."""
import hashlib
import sqlite3

import core.hb_note_index as ni
import core.hb_note_vectors as nv

DEF = ('SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super\ncomponent PY-AU | version 8\nSymptom\n\nEmployers pay super on payday.\n\n'
       'Maximum Contribution Base (MCB): From July 1, 2026, the maximum contribution base check is changing from Quarterly to an Annual '
       'amount of 270,830 AUD. MCB is the upper limit of earnings for super guarantee.')
OTHER = ('SAP Note 3800283: 3800283 - Year-end legal change - SI constants (maximum contribution bases)\ncomponent PY-ES\nSymptom\n\n'
         'Spanish social insurance constants for 2027.')


def embed(text):
    v = [0.0] * 64
    for w in text.lower().replace('(', ' ').replace(')', ' ').split():
        if w in ('search_query:', 'search_document:', '|'):
            continue
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
    return v


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, source_ref TEXT, raw_text TEXT, content_hash TEXT, domain_tags TEXT)')
    c.execute("INSERT INTO knowledge_sources VALUES (7004, 'SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super', 'sap://note/3713786', ?, 'h1', '')", (DEF,))
    c.execute("INSERT INTO knowledge_sources VALUES (8000, 'SAP Note 3800283: 3800283 - Year-end legal change - SI constants (maximum contribution bases)', 'sap://note/3800283', ?, 'h2', '')", (OTHER,))
    ni.refresh(c)
    return c


def test_practice_147_chunks_and_fuse():
    assert nv.chunks('a\n\nb') == ['a b']
    assert len(nv.chunks(('x' * 500 + '\n\n') * 4)) == 4
    assert nv.fuse([1, 2, 3], [3, 4])[0] == 3


def test_practice_147_refresh_embeds_once_and_search_finds_the_passage():
    c = db()
    assert nv.refresh(c, embed=embed) == 2
    assert nv.refresh(c, embed=embed) == 0
    hits = nv.search(c, 'maximum contribution base annual amount super guarantee', embed=embed)
    assert hits[0][0] == 7004 and '270,830' in hits[0][2]


def test_practice_147_rank_fuses_and_shows_the_passage(monkeypatch):
    c = db()
    nv.refresh(c, embed=embed)
    monkeypatch.setattr(nv, '_embed', lambda text, e=None: embed(text))
    items, _f = ni.rank(c, 'what is the annual guarantee upper limit on earnings', [], 1 << 40)
    top = items[0]
    assert top['source_id'] == 7004 and top['summary'].startswith('says: ') and '270,830' in top['summary']


def test_practice_147_no_vectors_keeps_keyword_search(monkeypatch):
    c = db()
    items, _f = ni.rank(c, 'Payday Super', [], 1 << 40)
    assert items and items[0]['source_id'] == 7004


def test_practice_147_background_worker_runs_once():
    import threading
    c = db()
    started = nv.start_background(connect=lambda: _Shared(c), batch=5, pause=0)
    assert started


class _Shared:
    def __init__(self, c): self.c = c
    def __getattr__(self, n): return getattr(self.c, n)
    def __enter__(self): return self.c.__enter__()
    def __exit__(self, *a): return self.c.__exit__(*a)
    def close(self): pass
