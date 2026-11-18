"""Online research that stays (Practice 157, owner 18 Nov 2026: "yes search online and download the relevant notes so it can be indexed,
eventually we will have a good size database ... good to have it offline as well and this will let us check for new versions as well").

After a successful web_search, HB keeps what it found:
  pages   every result on SAP's public sites (help.sap.com, community.sap.com, sap.com) is fetched and its readable text saved in the
          Knowledge Centre (source_ref = the URL, subcategory 'sap-web'); when a page cannot be read, the search snippet is saved instead.
          A page already kept is refreshed only when its text changed.
  notes   SAP note numbers the pages or snippets cite are queued in HB's SAP notes job (core/hb_sap_note_job), which fetches them with
          JD's S-user from the keyring - this module never sees the login.
Runs in a background thread so APEX's turn does not wait. Only the search query left the machine; no note text or KC content is sent.
"""
import hashlib
import json
import logging
import re
import threading
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)
SITES = ('help.sap.com', 'community.sap.com', 'sap.com')
MAX_PAGE = 200_000
UA = 'Mozilla/5.0 (X11; Linux x86_64) Hummingbird-research/1.0'


class _Text(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'header', 'footer', 'noscript', 'svg'}

    def __init__(self):
        super().__init__()
        self.out, self.skip, self.title = [], 0, ''
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        self._in_title = tag == 'title'
        if tag in ('p', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'tr', 'div'):
            self.out.append('\n')

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)


def page_text(html):
    p = _Text()
    p.feed(str(html or ''))
    text = re.sub(r'[ \t]+', ' ', ''.join(p.out))
    text = re.sub(r'\n\s*\n+', '\n\n', text).strip()
    return ' '.join(p.title.split()), text


def allowed(url):
    host = (urlparse(str(url or '')).hostname or '').lower()
    return any(host == s or host.endswith('.' + s) for s in SITES)


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(MAX_PAGE).decode('utf-8', errors='replace')


def extract(urls, timeout=40):
    """{url: readable text} through Tavily's extract service (HB's configured key) - for pages a plain fetch cannot read
    (help.sap.com builds its pages with scripts; SAP Community refuses scripted requests)."""
    if not urls:
        return {}
    from config import TAVILY_API_KEY, TAVILY_API_KEY_GENERIC
    key = TAVILY_API_KEY or TAVILY_API_KEY_GENERIC
    if not key:
        return {}
    req = urllib.request.Request('https://api.tavily.com/extract', json.dumps({'urls': list(urls)}).encode(),
                                 {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return {x.get('url'): str(x.get('raw_content') or '') for x in data.get('results') or [] if x.get('url')}


def snippets(result):
    """{url: snippet} from a search result's text ('- title: snippet\\n  Source: url')."""
    out, text = {}, str((result or {}).get('text') or '')
    for m in re.finditer(r'-\s*(.+?)\n\s*Source:\s*(\S+)', text, re.S):
        out[m.group(2)] = ' '.join(m.group(1).split())
    return out


def keep_page(conn, url, title, text):
    """Save or refresh one page as a KC source; returns (source_id, changed)."""
    from core import hb_kc_records as kc
    digest = hashlib.sha256(text.encode()).hexdigest()
    row = conn.execute('SELECT source_id, content_hash FROM knowledge_sources WHERE source_ref=?', (url,)).fetchone()
    title = (title or url)[:200]
    if row and row[1] == kc._hash(text):
        return row[0], False
    if row:
        conn.execute('UPDATE knowledge_sources SET raw_text=?, content_hash=?, title=? WHERE source_id=?', (text, kc._hash(text), title, row[0]))
        sid = row[0]
    else:
        sid = kc._new_source(conn, title, url, text, ['sap-web', urlparse(url).hostname or 'web'], 'sap-web')
    kc._write_chunks(conn, sid, kc._chunk(text))
    return sid, True


def queue_notes(conn, numbers, label):
    """Queue SAP notes HB does not hold and has not queued; returns the queued numbers."""
    from core import hb_sap_note_job as job
    job.ensure_schema(conn)
    queued = set()
    for (nums,) in conn.execute("SELECT numbers FROM hb_sap_note_jobs WHERE state IN ('pending','running')"):
        try:
            queued |= set(json.loads(nums or '[]'))
        except ValueError:
            pass
    todo = [n for n in dict.fromkeys(numbers) if n not in queued and not job.have(conn, n)]
    if todo:
        now = time.time()
        conn.execute('INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                     (-int(now * 1000), f'web research: {label[:80]}', 'web', json.dumps(todo), 'pending', now, now))
    return todo


def capture(conn, result, fetcher=fetch, extractor=extract):
    """Keep the SAP pages of one web_search result and queue the notes they cite. Returns a short summary dict."""
    from core import hb_sap_note_job as job
    snips = snippets(result)
    urls = [u for u in (result or {}).get('sources') or list(snips) if allowed(u)]
    kept, numbers, pages = [], [], {}
    for url in urls:
        try:
            pages[url] = page_text(fetcher(url))
        except Exception as exc:
            LOG.info('web research: %s not fetched (%s)', url, exc)
            pages[url] = ('', '')
    thin = [u for u in urls if len(pages[u][1]) < 200]
    try:
        extracted = extractor(thin) if thin else {}
    except Exception as exc:
        LOG.info('web research: extract failed (%s)', exc)
        extracted = {}
    for url in urls:
        title, text = pages[url]
        if len(text) < 200 and len(extracted.get(url, '')) >= 200:
            text = extracted[url]
        if len(text) < 200:                         # nothing readable: keep what the search showed
            text = snips.get(url, '')
            title = title or (text.split(':', 1)[0] if text else url)
        if not text:
            continue
        sid, changed = keep_page(conn, url, title, f'{title}\nSource: {url}\n\n{text}')
        kept.append({'url': url, 'source_id': sid, 'changed': changed})
        numbers += job.cited(text)
    numbers += job.cited(str((result or {}).get('text') or ''))
    queued = queue_notes(conn, numbers, str((result or {}).get('query') or 'search')) if numbers else []
    return {'kept': kept, 'queued_notes': queued}


def capture_later(result):
    """Background: keep pages and queue notes without holding up APEX's turn."""
    def work():
        from contextlib import closing
        from utils.db._connection import get_connection
        try:
            with closing(get_connection()) as conn:
                out = capture(conn, result)
                conn.commit()
            LOG.info('web research kept %d page(s), queued %d note(s)', len(out['kept']), len(out['queued_notes']))
        except Exception:
            LOG.exception('web research capture failed')
    t = threading.Thread(target=work, name='hb-web-research', daemon=True)
    t.start()
    return t
