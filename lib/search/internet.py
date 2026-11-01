import re
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))

try:
    from ddgs import DDGS as _DDGS
    _DDGS_OK = True
except ImportError:
    try:
        from duckduckgo_search import DDGS as _DDGS
        _DDGS_OK = True
    except ImportError:
        _DDGS_OK = False
        _DDGS = None

def search_web(query, max_results=3):
    if not _DDGS_OK:
        return "[Search unavailable: ddgs/duckduckgo_search not installed]"
    try:
        with _DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No results found."
        summary = ""
        for r in results:
            summary += f"Source: {r['href']}\n"
            summary += f"{r['title']}: {r['body']}\n\n"
        return summary.strip()
    except Exception as e:
        return f"[Search failed: {str(e)}]"

_FAILED_PREFIXES = ('[Serper search unavailable', '[Tavily search unavailable', '[Search failed',
                    '[Search unavailable', 'No results found')


def search_best(query, max_results=5):
    """Search Serper (Google), then Tavily, then DuckDuckGo; return ``(engine, text)``.

    ``engine`` is ``None`` and ``text`` is empty when every provider fails.
    """
    query = re.sub(r'\s+', ' ', str(query or '')).strip()[:380]
    if not query:
        return None, ''
    providers = []
    try:
        from internet_serper import search as serper
        providers.append(('Serper (Google)', lambda: serper(query, num_results=max_results)))
    except Exception:
        pass
    try:
        from internet_tavily import search as tavily
        providers.append(('Tavily', lambda: tavily(query, max_results=max_results)))
    except Exception:
        pass
    providers.append(('DuckDuckGo', lambda: search_web(query, max_results=max_results)))
    for engine, run in providers:
        try:
            text = str(run() or '').strip()
        except Exception as exc:
            print(f'[search_best] {engine} failed: {exc}')
            continue
        if text and not text.startswith(_FAILED_PREFIXES):
            return engine, text
    return None, ''


_WEB_EXPLICIT_RE = re.compile(
    r'\b(search|look\s?up|google|online|on the (?:web|internet)|web search|find out|check the (?:web|news))\b', re.I)
_WEB_FRESH_RE = re.compile(
    r'\b(latest|recent(?:ly)?|news|today|tonight|this (?:week|month|year)|currently|right now|'
    r'nowadays|update[sd]? (?:on|to|for)|released?|announce[sd]?|launch(?:ed)?|price|prices|cost|'
    r'exchange rate|weather|forecast|score|election|20[2-3]\d|version|rate|law|legislation|'
    r'deadline|due date|ato|fair work|sap note|hotfix|patch day)\b', re.I)
_WEB_QUESTION_RE = re.compile(
    r'^(?:who|what|when|where|which|how|is|are|was|were|does|do|did|can|could|should|will|has|have)\b'
    r'|\?\s*$|\b(difference between|compare|vs\.?|versus|tell me about|explain)\b', re.I)
_WEB_INTERNAL_RE = re.compile(
    r'\b(swarm|fridays?|seven|gemma|qwen|llama|mistral|duck|eight|apex|vortex|sandpits?|tickets?|proposals?|'
    r'studio|staging|kc|knowledge cent(?:er|re)|inbox|my email|qbit\w*|torrent\w*|this repo|our code|'
    r'the code|codebase|files?|folders?|services?|terminal|skills?|yourself|'
    r'memory|memories|agents?|locals?|checkpoints?|commits?|branch(?:es)?|my|think|opinion)\b', re.I)
# Short follow-ups that refer back to the conversation cannot be searched on their own.
_WEB_FOLLOWUP_RE = re.compile(r'\b(they|them|their|those|these|that one|it|its|the first|the last|above|previous)\b', re.I)
_WEB_ACTION_RE = re.compile(
    r'^(?:please\s+)?(?:fix|build|implement|change|modify|patch|write|rewrite|create|delete|add|remove|'
    r'restart|run|open|close|start|stop|send|email|schedule|remind|install|update|edit|save|draft)\b', re.I)


def needs_web_lookup(text):
    """True when a chat message asks about the outside world and benefits from live search."""
    raw = re.sub(r'^(?:@\w+[\s,:]*)+', '', str(text or '')).strip()
    if not raw or len(raw) > 600 or raw.startswith(('/', 'SKILL ')):
        return False
    if _WEB_EXPLICIT_RE.search(raw) and not re.search(r'\b(memory|memories|knowledge|kc|inbox|files?|folders?|code(?:base)?|repo|tickets?|proposals?|logs?)\b', raw, re.I):
        return True
    if _WEB_ACTION_RE.search(raw) or _WEB_INTERNAL_RE.search(raw):
        return False
    if _WEB_FOLLOWUP_RE.search(raw) and len(raw.split()) <= 12:
        return False
    return bool(_WEB_QUESTION_RE.search(raw)) and (bool(_WEB_FRESH_RE.search(raw)) or len(raw.split()) >= 4)


def web_context_block(query, max_results=5, max_chars=3000):
    """Live search results formatted for prompt injection, or ``''`` if unavailable."""
    query = re.sub(r'^(?:@\w+[\s,:]*)+', '', str(query or '')).strip()
    engine, text = search_best(query, max_results=max_results)
    if not engine:
        return ''
    from datetime import date
    return (
        f'LIVE WEB RESULTS ({engine}, fetched {date.today().isoformat()}) for: {query[:200]}\n'
        'Base factual claims on these sources and cite their URLs. If they do not answer the '
        'question, say so plainly instead of guessing.\n\n'
        f'{text[:max_chars]}\n'
        'END LIVE WEB RESULTS'
    )


def verify_online(question, local_answer):
    results = search_web(question)
    return f"Web search results for verification:\n{results}"

def search_topic(topic):
    return search_web(topic)

if __name__ == "__main__":
    print("Testing internet connection via DuckDuckGo...")
    result = search_topic("capital of Japan")
    print(f"Result:\n{result}")
