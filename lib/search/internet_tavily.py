"""
internet_tavily.py — Qwen and Eight's search engine / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Tavily AI Search — purpose-built for LLM context injection. Returns clean,
extracted content with source attribution. No HTML noise.

Qwen uses it for independent research in Stage 2.
Eight uses it for SAP-specific queries (Notes, SCN, community forums).

Seven project key is used first. Falls back to generic key if it fails.

Install: pip3 install tavily-python --break-system-packages
═══════════════════════════════════════════════════════════════════════════════
"""

import re
import sys
sys.path.insert(0, '/home/seven/swarm')

from config import TAVILY_API_KEY, TAVILY_API_KEY_GENERIC


def _truncate_query(query, limit=380):
    """Tavily rejects queries > 400 chars with a hard 422.

    We cap defensively at 380 to leave headroom for any wrapper text the
    caller (e.g. ``search_sap``) might prepend, and we cut on a word
    boundary so the truncated query still parses as natural language.
    Returns the original string if it is already short enough.
    """
    q = (query or '').strip()
    if len(q) <= limit:
        return q
    # Prefer cutting at the last whitespace within the limit so we don't
    # slice mid-word; fall back to a hard cut if there's no whitespace
    # (e.g. someone passed a base64 blob — still better than failing).
    head = q[:limit]
    cut = head.rfind(' ')
    if cut >= limit // 2:
        head = head[:cut]
    return head.rstrip(' ,;:-')


def search(query, max_results=5, search_depth='basic'):
    """
    Search via Tavily AI. Returns formatted string ready for context injection.
    search_depth: 'basic' (fast, 1 credit) or 'advanced' (thorough, 2 credits).
    Uses Seven key, falls back to generic key if the first fails.
    """
    # Tavily caps queries at 400 characters; over-long queries (e.g. an
    # entire HTML email body, a stack trace, a transcript) used to fail
    # *both* keys silently and return "[Tavily search unavailable]" with
    # no diagnostic. Truncate up-front so the caller still gets useful
    # results from a long input.
    original_len = len(query or '')
    query = _truncate_query(query)
    if original_len > len(query):
        print(f'[Tavily] Truncated query from {original_len} -> {len(query)} chars '
              f'(Tavily limit is 400).')

    for key in filter(None, [TAVILY_API_KEY, TAVILY_API_KEY_GENERIC]):
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=key)
            response = client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_answer=True,
            )
            result = _format_results(response, query)
            print(f'[Tavily] {len(response.get("results",[]))} results for: {query[:60]}')
            try:
                from database import log_activity
                log_activity('tavily', 'search', query[:100])
            except Exception:
                pass
            return result
        except Exception as e:
            print(f'[Tavily] Key {key[:16]}... failed: {e}')

    return f'[Tavily search unavailable for: {query}]'


def search_sap(query, max_results=5):
    """
    SAP-specific search — Eight uses this. Adds SAP context to the query
    to bias Tavily toward SAP Notes, SCN, SAP Help Portal, and community resources.

    2026-05-02 (S-9D336883B1) — query expansion: when an SAP module is
    mentioned, append a synonym group so Tavily sees richer terms.
    2026-05-03 — distil the input first: callers sometimes hand us a full
    email / transcript / HTML blob, which (a) blows past Tavily's 400-char
    limit and (b) buries the actual question under boilerplate. We strip
    HTML, keep only the most question-like sentence, then expand.
    """
    distilled = _distil_question(query)
    return search(expand_sap_query(distilled), max_results=max_results,
                  search_depth='basic')


# 2026-05-03 — Distil a "question" out of arbitrary noisy input so Tavily
# gets a focused query rather than a wall of HTML.
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


def _distil_question(text, max_chars=300):
    """Pull a search-friendly question out of free-form input.

    Strategy:
      1. Strip HTML tags (email replies, Discord notifications, etc).
      2. Collapse whitespace.
      3. If short enough already, return as-is.
      4. Otherwise prefer the first sentence ending in '?' (humans write
         questions that way); fall back to the first sentence; final
         fallback is the leading slice.
    """
    if not text:
        return ''
    s = _HTML_TAG_RE.sub(' ', text)
    s = _WS_RE.sub(' ', s).strip()
    if len(s) <= max_chars:
        return s
    sentences = _SENTENCE_SPLIT_RE.split(s)
    for sent in sentences:
        sent = sent.strip()
        if sent.endswith('?') and 8 <= len(sent) <= max_chars:
            return sent
    if sentences:
        first = sentences[0].strip()
        if first:
            return first[:max_chars]
    return s[:max_chars]


# 2026-05-02 (S-9D336883B1) — SAP query expansion table
_SAP_EXPANSIONS = {
    'hcm': '"SAP HCM" payroll personnel administration',
    'payroll': 'payroll schema PCR wagetypes',
    'fi': '"SAP FI" finance general ledger',
    'co': '"SAP CO" controlling cost center',
    'mm': '"SAP MM" materials management procurement',
    'sd': '"SAP SD" sales distribution',
    'pp': '"SAP PP" production planning',
    'qm': '"SAP QM" quality management',
    'pm': '"SAP PM" plant maintenance',
    'wm': '"SAP WM" warehouse management',
    'btp': '"SAP BTP" business technology platform',
    'cap': '"SAP CAP" cloud application programming',
    'rap': '"ABAP RAP" restful application programming',
    'fiori': 'SAP Fiori UI5 launchpad',
    'abap': 'ABAP report function module',
    'hana': '"SAP HANA" CDS view calculation view',
    's/4': '"S/4HANA" embedded analytics',
    's4': '"S/4HANA" embedded analytics',
}


def expand_sap_query(query):
    """Return an expanded SAP-aware query string."""
    q = (query or '').strip()
    if not q:
        return q
    lower = q.lower()
    is_sap = any(
        kw in lower for kw in
        ['sap', 'abap', 'hcm', 'payroll schema', 'pcr', 'infotype', 'fiori',
         'hana', 's/4hana', 's4hana']
    )
    base = q if is_sap else f'SAP HCM {q}'
    extras = []
    for token, expansion in _SAP_EXPANSIONS.items():
        # Match as a whole word; avoid 'pp' matching inside 'apple'
        if f' {token} ' in f' {lower} ' or lower.startswith(f'{token} ') or lower.endswith(f' {token}'):
            extras.append(expansion)
    if extras:
        base = f'{base} ({" OR ".join(extras)})'
    return base


# 2026-05-02 (S-B0460BB6BD) — official SAP source allowlist. Hits from these
# domains are authoritative and should be ranked above community/forum content.
_OFFICIAL_SAP_DOMAINS = (
    'help.sap.com',
    'support.sap.com',
    'launchpad.support.sap.com',
    'community.sap.com',
    'developers.sap.com',
    'learning.sap.com',
    'training.sap.com',
    'api.sap.com',
    'blogs.sap.com',
)


def is_official_sap_source(url):
    """Return True if ``url`` is hosted on a known official SAP domain.

    Used by the SAP watcher and Eight's evidence ranking to mark sources
    as authoritative."""
    if not url:
        return False
    u = url.lower()
    # cheap parse: pull host between "://" and the next "/" or query-string.
    if '://' in u:
        u = u.split('://', 1)[1]
    host = u.split('/', 1)[0].split('?', 1)[0]
    return any(host == d or host.endswith('.' + d) for d in _OFFICIAL_SAP_DOMAINS)


def _format_results(data, query):
    lines = [f'Tavily AI results for: {query}\n']

    # Tavily synthesised answer — AI-extracted summary across all sources
    if data.get('answer'):
        lines.append(f'TAVILY ANSWER: {data["answer"]}\n')

    # Individual results — clean extracted content
    for r in data.get('results', []):
        title   = r.get('title', '')
        content = r.get('content', '')[:400]   # Tavily content is pre-extracted
        url     = r.get('url', '')
        score   = r.get('score', 0)
        score_str = f' [relevance: {score:.2f}]' if score else ''
        lines.append(f'- {title}{score_str}: {content}')
        if url:
            lines.append(f'  Source: {url}')

    return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else 'general'
    if mode == 'sap':
        q = input('SAP search query: ').strip() or 'processing class 20 payroll schema XDIVID'
        print('\n' + search_sap(q))
    else:
        q = input('Tavily search query: ').strip() or 'SAP payroll wage type T512W field OPIND'
        print('\n' + search(q))
