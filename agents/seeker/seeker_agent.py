"""
# LINKED TO: utils/config.py — imports SEEKER_SYSTEM_PROMPT (edit prompts there, not here)
agents/seeker/seeker_agent.py — Seeker (Tavily Search)
Developer Agent — real-time intelligence. Powered by Tavily AI Search.
Seeker specialises in live web research — it searches, synthesises, and cites.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.seeker')

AGENT_NAME = 'seeker'


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a research query to Seeker (Tavily). Returns (answer, tokens_used).
    Seeker searches the web and returns a synthesised answer with sources.
    Supports stage_cb(text, eta) for live progress in the Fridays UI.
    """
    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    try:
        from tavily import TavilyClient
    except ImportError:
        return '[Seeker] tavily-python package not installed. Run: pip install tavily-python', 0

    from config import TAVILY_API_KEY, SEEKER_SYSTEM_PROMPT

    if not TAVILY_API_KEY:
        return '[Seeker] TAVILY_API_KEY not configured', 0

    _emit('preparing search query')
    # Extract the latest user message from threaded prompt if present
    raw = str(message or '').strip()
    if '=== New user message ===' in raw:
        parts = raw.split('=== New user message ===', 1)
        search_query = parts[1].strip()[:380]
    else:
        search_query = raw[:380]

    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)

        _emit('searching the web')
        result = client.search(
            query=search_query,
            search_depth='advanced',
            max_results=8,
            include_answer=True,
            include_raw_content=False,
        )

        answer_text = result.get('answer') or ''
        sources = result.get('results') or []

        _emit('synthesizing results')
        lines = []
        if answer_text:
            lines.append(answer_text)
        if sources:
            lines.append('\n**Sources:**')
            for s in sources[:6]:
                title = s.get('title', 'Untitled')
                url = s.get('url', '')
                snippet = str(s.get('content') or '').strip()[:200]
                lines.append(f'- **{title}** — {url}\n  {snippet}')

        answer = '\n'.join(lines).strip() or '[Seeker] No results found.'

        _emit('persisting response memory')
        try:
            from database import save_agent_memory
            save_agent_memory(
                agent_name=AGENT_NAME,
                subject=str(message or '')[:100],
                content=answer[:1600],
                tags='chat,search,shared-thread',
                importance=7,
                source='terminal_chat',
            )
        except Exception:
            pass

        # Tavily doesn't report tokens; estimate from answer length
        tokens = len(answer) // 4
        logger.info(f'[Seeker] results={len(sources)} | {str(message or "")[:60]}')
        return answer, tokens

    except Exception as e:
        msg = str(e)
        logger.error(f'[Seeker] search error: {msg}')
        if '401' in msg or 'invalid api key' in msg.lower():
            return '[Seeker] Tavily API key invalid.', 0
        if '429' in msg or 'rate limit' in msg.lower():
            return f'[Seeker] Tavily rate limit hit. {msg}', 0
        return f'[Seeker] Search error: {msg}', 0
