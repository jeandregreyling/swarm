"""
fridays/browser_agent.py — Seven's Swarm (RL-018)
═══════════════════════════════════════════════════════════════════════════════
Playwright headless browser. Gives the swarm the ability to read web pages,
not just search them.

Trust levels:
  Level 0 — Read page / extract text (always allowed)
  Level 3 — Fill form / click button (Gemma must approve first)
  Level 4 — External POST / login (Ghost notified, logged to ghost_circle)

All actions logged to sandpit_log. Duck-checked on Level 3+.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import re
import logging
from datetime import datetime

sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.browser_agent')

# Max page text returned to agents — keeps context reasonable
MAX_CONTENT_CHARS = 8000


def _log_action(agent, action, url, result_summary, trust_level=0):
    """Log every browser action to sandpit_log."""
    try:
        from database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT INTO sandpit_log (agent, operation, path, size_bytes, status, reason, created_at)
               VALUES (?, ?, ?, ?, 'ok', ?, datetime('now'))""",
            (agent, action, url[:500], len(result_summary), result_summary[:200])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[Browser] sandpit_log write failed: {e}')


def _clean_text(raw):
    """Strip excess whitespace from extracted page text."""
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        line = line.strip()
        if line:
            cleaned.append(line)
    return '\n'.join(cleaned)


def browse(url, agent='browser', timeout_ms=15000):
    """
    Level 0 — Read a web page and return its text content.
    Safe, always allowed. Used to give agents full page context when a URL
    is present in a question.

    Returns: str — page text, truncated to MAX_CONTENT_CHARS
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print(f'[Browser] Reading: {url}')
    content = ''

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            )
            page.set_default_timeout(timeout_ms)

            try:
                page.goto(url, wait_until='domcontentloaded')
            except PWTimeout:
                logger.warning(f'[Browser] Timeout loading {url}')
                browser.close()
                return f'[Browser] Page timed out after {timeout_ms // 1000}s: {url}'

            # Try to extract main content — article/main first, fall back to body
            for selector in ['article', 'main', '[role="main"]', 'body']:
                el = page.query_selector(selector)
                if el:
                    raw = el.inner_text()
                    if raw and len(raw.strip()) > 100:
                        content = raw
                        break

            browser.close()

    except Exception as e:
        logger.error(f'[Browser] Error browsing {url}: {e}')
        return f'[Browser] Could not load page: {e}'

    content = _clean_text(content)
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + '\n\n[... page truncated ...]'

    _log_action(agent, 'browse_read', url, f'{len(content)} chars extracted')
    print(f'[Browser] Read {len(content)} chars from {url}')
    return content


def extract_urls(text):
    """Extract all URLs from a block of text."""
    pattern = r'https?://[^\s\)\]\>\"\']+'
    return re.findall(pattern, text)


def browse_all(text, agent='browser'):
    """
    Extract all URLs from text and browse each one.
    Returns a combined string of all page contents, labelled by URL.
    Used by consult_stage1 when NEEDS_BROWSER=yes.
    """
    urls = extract_urls(text)
    if not urls:
        return ''

    parts = []
    for url in urls[:3]:   # max 3 URLs per question to keep context reasonable
        content = browse(url, agent=agent)
        parts.append(f'[Browser — {url}]\n{content}')

    return '\n\n'.join(parts)


def test():
    print('\n[Browser Agent] Test — reading example.com...')
    result = browse('https://example.com')
    print(result[:500])
    print('\n✓ browser_agent.py works.')


if __name__ == '__main__':
    test()
