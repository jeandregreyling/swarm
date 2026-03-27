"""
internet_serper.py — Gemma's search engine / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Gemma gets Google via Serper.dev — clean authoritative results, no SEO spam.
Replaces Brave Search (which requires a paid subscription).

Seven project key is used first. Falls back to generic key if it fails.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')

import requests
from config import SERPER_API_KEY, SERPER_API_KEY_GENERIC

SERPER_URL = 'https://google.serper.dev/search'


def search(query, num_results=5):
    """
    Search Google via Serper.dev. Returns formatted string ready for
    injection into Gemma's context prompt. Uses Seven key, falls back
    to generic key if the first fails.
    """
    for key in filter(None, [SERPER_API_KEY, SERPER_API_KEY_GENERIC]):
        try:
            resp = requests.post(
                SERPER_URL,
                headers={
                    'X-API-KEY':    key,
                    'Content-Type': 'application/json',
                },
                json={'q': query, 'num': num_results},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            result = _format_results(data, query)
            print(f'[Serper] {len(data.get("organic",[]))} organic results for: {query[:60]}')
            try:
                from database import log_activity
                log_activity('serper', 'search', query[:100])
            except Exception:
                pass
            return result
        except Exception as e:
            print(f'[Serper] Key {key[:12]}... failed: {e}')

    return f'[Serper search unavailable for: {query}]'


def _format_results(data, query):
    lines = [f'Google (Serper) results for: {query}\n']

    # Answer box — direct answer at top of Google results
    ab = data.get('answerBox', {})
    if ab:
        ans = ab.get('answer') or ab.get('snippet') or ab.get('snippetHighlighted', '')
        if ans:
            title = ab.get('title', '')
            lines.append(f'ANSWER BOX{" — " + title if title else ""}: {ans}\n')

    # Knowledge graph — structured entity data
    kg = data.get('knowledgeGraph', {})
    if kg.get('description'):
        lines.append(f'KNOWLEDGE GRAPH — {kg.get("title","")}: {kg["description"]}\n')

    # Organic results — main web results
    for item in data.get('organic', []):
        title   = item.get('title', '')
        snippet = item.get('snippet', '')
        url     = item.get('link', '')
        date    = item.get('date', '')
        date_str = f' [{date}]' if date else ''
        lines.append(f'- {title}{date_str}: {snippet}')
        if url:
            lines.append(f'  Source: {url}')

    # Related searches — useful for Eight/SAP topics
    related = [r.get('query', '') for r in data.get('relatedSearches', [])[:3]]
    if related:
        lines.append(f'\nRelated: {", ".join(related)}')

    return '\n'.join(lines)


if __name__ == '__main__':
    test_query = input('Serper test query: ').strip() or 'SAP HCM payroll processing class 20'
    print('\n' + search(test_query))
