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

import sys
sys.path.insert(0, '/home/seven/swarm')

from config import TAVILY_API_KEY, TAVILY_API_KEY_GENERIC


def search(query, max_results=5, search_depth='basic'):
    """
    Search via Tavily AI. Returns formatted string ready for context injection.
    search_depth: 'basic' (fast, 1 credit) or 'advanced' (thorough, 2 credits).
    Uses Seven key, falls back to generic key if the first fails.
    """
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
    """
    sap_query = query if any(
        kw in query.lower() for kw in ['sap', 'abap', 'hcm', 'payroll schema', 'pcr', 'infotype']
    ) else f'SAP HCM {query}'
    return search(sap_query, max_results=max_results, search_depth='basic')


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
