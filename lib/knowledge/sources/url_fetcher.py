"""lib/knowledge/sources/url_fetcher.py — Fetch a URL and extract plain text."""
import re
import logging

logger = logging.getLogger('seven.knowledge.url')

_HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; SevenSwarm-Library/1.0)'}


def extract(url, timeout=20):
    """
    Fetch `url` and return the plain-text body (HTML stripped).
    On failure returns a string starting with '[URL fetch failed]'.
    """
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
        resp.raise_for_status()
        ct = resp.headers.get('content-type', '').lower()
        raw = resp.text
        if 'html' in ct:
            return _strip_html(raw)[:200_000]
        return raw[:200_000]
    except Exception as exc:
        logger.warning(f'[URL] fetch failed for {url}: {exc}')
        return f'[URL fetch failed] {exc}'


def _strip_html(html):
    # Drop script / style blocks entirely
    html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', ' ', html, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Collapse horizontal whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    # Normalise vertical whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
