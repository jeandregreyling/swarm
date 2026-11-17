"""Source links in answers (Practice 137, owner 17 Nov 2026: "in the results the references should be links to the actual notes if I want
to look at them myself as well" - "shouldn't it reference KC and the actual online sources it used instead?").

An answer is built from the Knowledge Centre, so its references point there first, then to where that copy came from:
  link_notes()      every SAP note number the KC holds links HB's copy (/kc/note/N); its first mention also links the note's online
                    origin, SAP for Me (me.sap.com/notes/N - where HB fetched it with JD's S-user). Numbers inside links, URLs, code and
                    longer numbers (document ids, receipts) are left alone.
  sources_footer()  "Sources used": every KC document APEX read this turn (knowledge_read), linked to HB's copy (/kc/source/ID) and to
                    its online origin when it has one (SAP note, web page); emails and PDFs have only HB's copy.
  source_html()     the read-only page for one KC source.
"""
import json
import re
from html import escape

SAP_URL = 'https://me.sap.com/notes/{n}'
NOTE_URL = '/kc/note/{n}'
SOURCE_URL = '/kc/source/{id}'
_SKIP = re.compile(r'\[[^\]]*\]\([^)]*\)|https?://\S+|`[^`]*`')
_NUM = re.compile(r'(?<![\w/#.-])(\d{6,8})(?![\w/])')


def origin_url(source_ref):
    """The online page a KC source came from, or None (emails, PDFs, HB's own records)."""
    ref = str(source_ref or '')
    m = re.fullmatch(r'sap://note/(\d+)', ref)
    if m:
        return SAP_URL.format(n=m.group(1))
    return ref if re.match(r'https?://', ref) else None


def _connect(conn):
    from contextlib import closing, nullcontext
    from utils.db._connection import get_connection
    return nullcontext(conn) if conn is not None else closing(get_connection())


def kc_notes(numbers, conn=None):
    """The numbers in `numbers` that the Knowledge Centre holds as SAP notes."""
    numbers = sorted(set(numbers))
    if not numbers:
        return set()
    try:
        with _connect(conn) as c:
            refs = [f'sap://note/{n}' for n in numbers]
            rows = c.execute(f"SELECT source_ref FROM knowledge_sources WHERE source_ref IN ({','.join('?' * len(refs))})", refs).fetchall()
        return {r[0].rsplit('/', 1)[-1] for r in rows}
    except Exception:
        return set()


def link_notes(text, known=None, conn=None):
    text = str(text or '')
    found = set(_NUM.findall(text))
    if not found:
        return text
    known = kc_notes(found, conn) if known is None else set(known)
    if not known:
        return text
    seen = set()

    def sub(m):
        n = m.group(1)
        if n not in known:
            return n
        first = n not in seen
        seen.add(n)
        return f'[{n}]({NOTE_URL.format(n=n)})' + (f' ([SAP for Me]({SAP_URL.format(n=n)}))' if first else '')
    out, last = [], 0
    for m in _SKIP.finditer(text):
        out.append(_NUM.sub(sub, text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_NUM.sub(sub, text[last:]))
    return ''.join(out)


def _read_ids(receipts):
    from core.apex_knowledge import LIBRARY_ID
    ids = []
    for r in receipts or []:
        if r.get('tool') != 'knowledge_read' or r.get('status') != 'succeeded':
            continue
        try:
            doc = int((r.get('arguments') or {}).get('document_id'))
        except (TypeError, ValueError):
            continue
        if doc > LIBRARY_ID and doc - LIBRARY_ID not in ids:
            ids.append(doc - LIBRARY_ID)
    return ids


def sources_footer(receipts, conn=None):
    """Markdown list of the KC documents read this turn, with HB's copy and the online origin; '' when none were read."""
    ids = _read_ids(receipts)
    if not ids:
        return ''
    try:
        with _connect(conn) as c:
            rows = {r[0]: r[1:] for r in c.execute(
                f"SELECT source_id, title, source_ref FROM knowledge_sources WHERE source_id IN ({','.join('?' * len(ids))})", ids).fetchall()}
    except Exception:
        return ''
    lines = []
    for sid in ids:
        if sid not in rows:
            continue
        title, ref = rows[sid]
        title = re.sub(r'^(SAP Note \d+):\s*\d+\s*-\s*', r'\1: ', str(title or f'Source {sid}')).replace('[', '(').replace(']', ')')
        online = origin_url(ref)
        lines.append(f'- [{title}]({SOURCE_URL.format(id=sid)})' + (f' · [online]({online})' if online else ' · Knowledge Centre only'))
    return ('\n\n**Sources used** (read in HB\'s Knowledge Centre this turn):\n' + '\n'.join(lines)) if lines else ''


def source_html(source_id, title, source_ref, raw):
    """HB's copy of one KC source as a plain page, with a link to its online origin when it has one."""
    online = origin_url(source_ref)
    where = (f'<a href="{escape(online)}" target="_blank" rel="noopener">Open the online original</a>' if online
             else escape('No online original: ' + (str(source_ref or '').split('://', 1)[0] or 'local') + ' source'))
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(str(title or "Knowledge Centre source"))[:120]}</title><style>'
            ':root{--bg:#fbfbf9;--text:#1d1d1b;--dim:#6b6b66;--accent:#0b7a5a;--line:#e4e4df}'
            '@media (prefers-color-scheme:dark){:root{--bg:#141414;--text:#e8e8e4;--dim:#9a9a94;--accent:#4fd1a5;--line:#2a2a28}}'
            'body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}'
            'main{max-width:860px;margin:0 auto;padding:24px 16px 48px}a{color:var(--accent)}'
            '.top{color:var(--dim);font-size:13px;border-bottom:1px solid var(--line);padding-bottom:10px}'
            'h1{font-size:20px;line-height:1.35;margin:16px 0}pre{white-space:pre-wrap;word-wrap:break-word;font:inherit;margin:0}'
            '</style></head><body><main>'
            f'<div class="top">HB Knowledge Centre copy · source #{int(source_id)} · {where}</div>'
            f'<h1>{escape(str(title or "Untitled source"))}</h1><pre>{escape(str(raw or ""))}</pre></main></body></html>')
