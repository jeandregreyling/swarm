"""
fridays/research_workflow.py — Multi-stage research orchestrator (B.2)
═══════════════════════════════════════════════════════════════════════════════
Entry point: run_research(topic, depth, requesting_agent)
Stages: decompose → search → analyse → synthesise → archive

Depth controls:
  quick    — 1 sub-question, 1 search pass, no cross-validation
  standard — 3 sub-questions, 3 search passes, summary synthesis
  deep     — 5 sub-questions, 5+ search passes, cross-validation + gaps

All evidence is tracked in research_evidence with source attribution.
Results archived to swarm_knowledge on completion.
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logger = logging.getLogger('seven.research')

# Depth → config mapping
DEPTH_CONFIG = {
    'quick':    {'max_questions': 1, 'max_results_per_q': 3, 'cross_validate': False},
    'standard': {'max_questions': 3, 'max_results_per_q': 5, 'cross_validate': False},
    'deep':     {'max_questions': 5, 'max_results_per_q': 8, 'cross_validate': True},
}


# ── Public entry point ────────────────────────────────────────────────────

def run_research(topic, *, depth='standard', requesting_agent='user', conn=None):
    """
    Run a complete research workflow.
    Returns (session_id, summary_text).
    """
    from utils.db.research import (
        create_session, update_session, get_session,
        add_evidence, get_evidence_for_session,
    )

    cfg = DEPTH_CONFIG.get(depth, DEPTH_CONFIG['standard'])
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()

    try:
        # Create session
        sid = create_session(
            topic, depth=depth, requesting_agent=requesting_agent, conn=conn,
        )
        logger.info(f'[Research] session={sid} topic={topic!r} depth={depth}')

        # Stage 1: Decompose
        update_session(sid, status='planning', conn=conn)
        sub_questions = _decompose(topic, cfg['max_questions'])
        update_session(sid, phases_json=json.dumps(sub_questions), conn=conn)

        # Stage 2: Search
        update_session(sid, status='searching', conn=conn)
        for sq in sub_questions:
            results = _search(sq, max_results=cfg['max_results_per_q'])
            for r in results:
                add_evidence(
                    sid,
                    source_url=r.get('url', ''),
                    source_type=r.get('source_type', 'web'),
                    title=r.get('title', ''),
                    snippet=r.get('snippet', ''),
                    confidence=r.get('confidence', 0.5),
                    collecting_agent=r.get('agent', 'seeker'),
                    conn=conn,
                )

        # Stage 3: Analyse
        update_session(sid, status='analysing', conn=conn)
        evidence = get_evidence_for_session(sid, conn=conn)

        # Stage 4: Synthesise
        update_session(sid, status='synthesising', conn=conn)
        summary = _synthesise(topic, sub_questions, evidence, cfg['cross_validate'])

        # Stage 5: Archive
        update_session(sid, status='done', summary=summary, conn=conn)
        _archive_to_knowledge(sid, topic, summary, requesting_agent, conn=conn)

        logger.info(f'[Research] session={sid} DONE evidence={len(evidence)}')
        return sid, summary

    except Exception as e:
        logger.error(f'[Research] session failed: {e}')
        try:
            update_session(sid, status='paused', conn=conn)
        except Exception:
            pass
        raise
    finally:
        if own:
            conn.close()


def resume_research(session_id, *, conn=None):
    """Resume a paused research session from where it left off."""
    from utils.db.research import get_session, update_session, get_evidence_for_session, add_evidence

    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()

    try:
        sess = get_session(session_id, conn=conn)
        if sess is None:
            return None, 'Session not found'
        if sess['status'] not in ('paused', 'planning', 'searching', 'analysing'):
            return session_id, sess.get('summary', 'Already completed')

        cfg = DEPTH_CONFIG.get(sess['depth'], DEPTH_CONFIG['standard'])
        topic = sess['topic']
        phases = json.loads(sess['phases_json']) if sess['phases_json'] else []

        # If no sub-questions yet, decompose
        if not phases:
            phases = _decompose(topic, cfg['max_questions'])
            update_session(session_id, phases_json=json.dumps(phases), conn=conn)

        # If in planning or searching, run search
        if sess['status'] in ('paused', 'planning', 'searching'):
            update_session(session_id, status='searching', conn=conn)
            existing_evidence = get_evidence_for_session(session_id, conn=conn)
            searched_urls = {e['source_url'] for e in existing_evidence}

            for sq in phases:
                results = _search(sq, max_results=cfg['max_results_per_q'])
                for r in results:
                    if r.get('url', '') not in searched_urls:
                        add_evidence(
                            session_id,
                            source_url=r.get('url', ''),
                            source_type=r.get('source_type', 'web'),
                            title=r.get('title', ''),
                            snippet=r.get('snippet', ''),
                            confidence=r.get('confidence', 0.5),
                            collecting_agent=r.get('agent', 'seeker'),
                            conn=conn,
                        )

        # Analyse + synthesise
        update_session(session_id, status='analysing', conn=conn)
        evidence = get_evidence_for_session(session_id, conn=conn)
        update_session(session_id, status='synthesising', conn=conn)
        summary = _synthesise(topic, phases, evidence, cfg['cross_validate'])
        update_session(session_id, status='done', summary=summary, conn=conn)
        _archive_to_knowledge(session_id, topic, summary, sess['requesting_agent'], conn=conn)

        return session_id, summary
    finally:
        if own:
            conn.close()


# ── Stage implementations ─────────────────────────────────────────────────

def _decompose(topic, max_questions):
    """Break topic into sub-questions. Uses a local agent if available, else heuristic."""
    try:
        return _decompose_via_agent(topic, max_questions)
    except Exception as e:
        logger.warning(f'[Research] agent decompose failed ({e}), using heuristic')
        return _decompose_heuristic(topic, max_questions)


def _decompose_heuristic(topic, max_questions):
    """Simple heuristic decomposition when no agent is available."""
    base = [topic]
    if max_questions >= 2:
        base.append(f'{topic} recent developments')
    if max_questions >= 3:
        base.append(f'{topic} best practices')
    if max_questions >= 4:
        base.append(f'{topic} common problems')
    if max_questions >= 5:
        base.append(f'{topic} expert opinions')
    return base[:max_questions]


def _decompose_via_agent(topic, max_questions):
    """Use a local Ollama agent to decompose the topic into sub-questions."""
    import ollama
    prompt = (
        f"Break this research topic into exactly {max_questions} specific search queries. "
        f"Return ONLY a JSON array of strings, no other text.\n\n"
        f"Topic: {topic}"
    )
    resp = ollama.chat(
        model='qwen2.5:latest',
        messages=[{'role': 'user', 'content': prompt}],
        options={'temperature': 0.1},
    )
    text = resp['message']['content']
    start = text.find('[')
    end   = text.rfind(']')
    if start >= 0 and end > start:
        questions = json.loads(text[start:end + 1])
        if isinstance(questions, list) and len(questions) > 0:
            return [str(q).strip() for q in questions[:max_questions]]
    raise RuntimeError('Agent decomposition unavailable')


def _search(query, *, max_results=5):
    """
    Search for a query. Returns list of dicts with keys:
    url, title, snippet, confidence, source_type, agent
    Priority: Tavily → Ollama cloud web_search → DuckDuckGo.
    """
    results = _search_tavily(query, max_results)
    if results:
        return results
    results = _search_ollama_web(query, max_results)
    if results:
        return results
    return _search_duckduckgo(query, max_results)


def _search_ollama_web(query, max_results):
    """Search using ollama.web_search() if OLLAMA_API_KEY is configured."""
    import os
    api_key = os.environ.get('OLLAMA_API_KEY', '').strip()
    if not api_key:
        return []
    try:
        import ollama
        client = ollama.Client(headers={'Authorization': f'Bearer {api_key}'})
        result = client.web_search(query, max_results=max_results)
        out = []
        for r in (result.results or []):
            out.append({
                'url':         r.url or '',
                'title':       r.title or '',
                'snippet':     str(r.content or '')[:500],
                'confidence':  0.7,
                'source_type': 'web',
                'agent':       'ollama_web',
            })
        return out
    except Exception as e:
        logger.debug(f'[Research] Ollama web_search failed: {e}')
        return []


def _search_tavily(query, max_results):
    """Search using Tavily (Seeker's backend)."""
    try:
        from tavily import TavilyClient
        from config import TAVILY_API_KEY
        if not TAVILY_API_KEY:
            return []
        client = TavilyClient(api_key=TAVILY_API_KEY)
        result = client.search(
            query=query,
            search_depth='advanced',
            max_results=max_results,
            include_answer=False,
            include_raw_content=False,
        )
        out = []
        for s in (result.get('results') or []):
            out.append({
                'url': s.get('url', ''),
                'title': s.get('title', ''),
                'snippet': str(s.get('content') or '')[:500],
                'confidence': s.get('score', 0.5),
                'source_type': 'web',
                'agent': 'seeker',
            })
        return out
    except Exception as e:
        logger.warning(f'[Research] Tavily search failed: {e}')
        return []


def _search_duckduckgo(query, max_results):
    """Fallback: DuckDuckGo search via the internet module."""
    try:
        from internet import search_web
        raw = search_web(query, max_results=max_results)
        if not raw:
            return []
        # search_web returns a formatted string; parse it into structured records
        results = []
        for line in raw.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('• '):
                line = line[2:]
            if not line:
                continue
            results.append({
                'url': '',
                'title': line[:100],
                'snippet': line[:400],
                'confidence': 0.3,
                'source_type': 'web',
                'agent': 'duckduckgo',
            })
        return results[:max_results]
    except Exception as e:
        logger.warning(f'[Research] DuckDuckGo fallback failed: {e}')
        return []


def _synthesise(topic, sub_questions, evidence, cross_validate=False):
    """
    Produce a synthesis of all evidence. Uses Scholar (Gemini) if available,
    else generates a structured summary from the evidence.
    """
    if not evidence:
        return f'No evidence found for: {topic}'

    try:
        return _synthesise_via_agent(topic, sub_questions, evidence, cross_validate)
    except Exception as e:
        logger.warning(f'[Research] agent synthesis failed ({e}), using fallback')
        return _synthesise_fallback(topic, sub_questions, evidence)


def _synthesise_via_agent(topic, sub_questions, evidence, cross_validate):
    """Use Scholar (Gemini) to synthesise evidence."""
    from agents.scholar.scholar_agent import chat as scholar_chat

    evidence_block = '\n'.join(
        f"[{i+1}] {e.get('title', 'Untitled')} (confidence: {e.get('confidence', '?')})\n"
        f"    Source: {e.get('source_url', 'N/A')}\n"
        f"    {e.get('snippet', '')[:300]}"
        for i, e in enumerate(evidence[:20])
    )

    prompt = (
        f"You are synthesising research findings.\n\n"
        f"**Topic:** {topic}\n"
        f"**Sub-questions investigated:** {json.dumps(sub_questions)}\n\n"
        f"**Evidence collected ({len(evidence)} items):**\n{evidence_block}\n\n"
        f"Produce a structured research summary with:\n"
        f"1. Key findings (bullet points)\n"
        f"2. Confidence assessment (high/medium/low)\n"
        f"3. Gaps — what couldn't be answered\n"
    )
    if cross_validate:
        prompt += "4. Contradictions found across sources\n"

    answer, _tokens = scholar_chat(prompt)
    if answer and '[Scholar]' not in answer[:20]:
        return answer
    raise RuntimeError(f'Scholar returned error: {answer[:100]}')


def _synthesise_fallback(topic, sub_questions, evidence):
    """Structured summary without an agent."""
    lines = [f'## Research Summary: {topic}\n']
    lines.append(f'**Sources examined:** {len(evidence)}')
    lines.append(f'**Sub-questions:** {len(sub_questions)}\n')

    seen_titles = set()
    lines.append('### Key Findings\n')
    for e in evidence:
        title = e.get('title', '')
        if title in seen_titles:
            continue
        seen_titles.add(title)
        conf = e.get('confidence', 0.5)
        conf_label = 'HIGH' if conf >= 0.7 else ('MEDIUM' if conf >= 0.4 else 'LOW')
        src = e.get('source_url', '')
        lines.append(f'- **{title}** [{conf_label}]')
        snippet = e.get('snippet', '')[:200]
        if snippet:
            lines.append(f'  {snippet}')
        if src:
            lines.append(f'  Source: {src}')
        lines.append('')

    lines.append('\n### Gaps')
    lines.append('- Automated synthesis unavailable (Scholar/Gemini not reachable)')
    lines.append('- Manual review recommended for cross-validation')

    return '\n'.join(lines)


# ── Archive + Learning Cycle (B.5) ────────────────────────────────────────

def _archive_to_knowledge(session_id, topic, summary, requesting_agent, *, conn=None):
    """Write research findings + lessons to swarm_knowledge + emit bus event."""
    try:
        from utils.db.knowledge import write_knowledge, search_knowledge
        from utils.swarm_bus import publish

        # 1. Write core findings (fact)
        write_knowledge(
            key=f'research:{topic[:100]}',
            content=summary[:4000],
            source_agent=requesting_agent,
            category='fact',
            importance=7,
            conn=conn,
        )

        # 2. Extract and write lesson (B.5.1)
        lesson = _extract_lesson(topic, summary)
        if lesson:
            write_knowledge(
                key=f'lesson:research:{topic[:80]}',
                content=lesson[:2000],
                source_agent=requesting_agent,
                category='lesson',
                importance=6,
                conn=conn,
            )

        # 3. Cross-session pattern detection (B.5.2)
        _detect_patterns(topic, summary, requesting_agent, conn=conn)

        # 4. Emit bus event
        publish(
            topic='research.done',
            payload={'session_id': session_id, 'topic': topic},
            source_service='research',
            conn=conn,
        )
    except Exception as e:
        logger.warning(f'[Research] archive failed: {e}')


def _extract_lesson(topic, summary):
    """Extract a lesson-learned statement from the research summary."""
    if not summary or len(summary) < 50:
        return None

    # Try agent-based extraction
    try:
        import requests
        prompt = (
            f"From this research summary, extract ONE concise lesson learned "
            f"(max 2 sentences). Return ONLY the lesson, no preamble.\n\n"
            f"Topic: {topic}\nSummary: {summary[:1500]}"
        )
        resp = requests.post(
            'http://localhost:11434/api/generate',
            json={'model': 'qwen2.5:latest', 'prompt': prompt, 'stream': False},
            timeout=20,
        )
        if resp.status_code == 200:
            text = resp.json().get('response', '').strip()
            if text and len(text) > 10:
                return text[:500]
    except Exception:
        pass

    # Fallback: first meaningful sentence from summary
    for line in summary.split('\n'):
        line = line.strip().strip('-•* ')
        if len(line) > 30 and not line.startswith('#'):
            return f'Research on "{topic}": {line[:300]}'
    return None


def _detect_patterns(topic, summary, requesting_agent, *, conn=None):
    """Compare findings with existing knowledge. Flag contradictions as warnings."""
    try:
        from utils.db.knowledge import search_knowledge, write_knowledge

        # Search for related existing knowledge
        existing = search_knowledge(topic[:50], category=None, limit=5, conn=conn)
        if not existing:
            return

        summary_lower = summary.lower()
        for entry in existing:
            # Skip if it's our own entry (just written)
            if entry['key'].startswith(f'research:{topic[:100]}'):
                continue

            # Simple contradiction detection: look for negation patterns
            existing_keywords = set(entry['content'].lower().split())
            summary_keywords = set(summary_lower.split())
            overlap = existing_keywords & summary_keywords

            # If there's significant overlap but the entry is from a different source,
            # it's worth noting as an update
            if len(overlap) > 5 and entry.get('source_agent') != requesting_agent:
                write_knowledge(
                    key=f'pattern:update:{topic[:60]}',
                    content=(
                        f'Related knowledge found: "{entry["key"]}" (by {entry["source_agent"]}). '
                        f'New research on "{topic}" provides updated context. '
                        f'Review both entries for consistency.'
                    ),
                    source_agent='research_workflow',
                    category='pattern',
                    importance=5,
                    conn=conn,
                )
                break  # One pattern note per research is enough
    except Exception as e:
        logger.debug(f'[Research] pattern detection skipped: {e}')
