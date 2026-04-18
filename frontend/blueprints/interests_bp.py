"""Interests engine — derives user interests from conversations + system memory.

Scans recent user messages, cross-references with agent memory tags and sniffer
patterns to surface what the user is actually interested in.  Results power the
home-screen suggestion cards.
"""

import re
from collections import Counter

from flask import Blueprint, jsonify, request

from database import get_connection

interests_bp = Blueprint('interests', __name__)

# ── Stop words (excluded from topic extraction) ─────────────────────────────
_STOP_WORDS = frozenset(
    'a about above after again against all also am an and any are as at be '
    'because been before being below between both but by can could did do does '
    'doing done down during each few for from further get got had has have '
    'having he her here hers herself him himself his how i if in into is it its '
    'itself just know let like make me more most my myself no nor not now of off '
    'on once one only or other our ours ourselves out over own re s same she '
    'should so some still such t than that the their theirs them themselves then '
    'there these they this those through to too under until up us very want was '
    'we were what when where which while who whom why will with would yes you '
    'your yours yourself yourselves about actually already always another back '
    'before being between called came come could did different does each end '
    'even every find first found from give going good got great had has have '
    'here high how however if into its just keep kind last left like line long '
    'look made make many may me might more most much must my name never new next '
    'no not now number of off old on one only or other our out over own part '
    'people place point right said same say see she show side since small so '
    'some something state still such sure take tell than that the them then '
    'there these they thing think this thought three through to together too '
    'turn two under up us use very want was way well went were what when where '
    'which while who will with work world would year you also use using used '
    'hello hey thanks thank please okay sure yeah hey gonna really need help '
    'can able try trying tried looks look looking working check update send '
    'give tell show run test make sure think know'.split()
)


@interests_bp.route('/api/interests')
def get_interests():
    """Derive user interests from recent conversations and system memory."""
    limit = min(int(request.args.get('limit', 10)), 20)

    conn = get_connection()

    # 1. Recent user messages from messages table + queue
    rows = conn.execute(
        "SELECT content FROM messages "
        "WHERE (message_type = 'user' OR message_type = 'chat' OR from_agent = 'user') "
        "ORDER BY created_at DESC LIMIT 300"
    ).fetchall()

    # Also mine queue entries (questions from external sources)
    queue_rows = conn.execute(
        "SELECT question FROM queue "
        "WHERE source_type != 'internal' AND question IS NOT NULL AND question != '' "
        "ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    # Also mine ticket subjects for topic signals (external only)
    ticket_rows = conn.execute(
        "SELECT subject FROM queue "
        "WHERE source_type != 'internal' AND subject IS NOT NULL AND subject != '' "
        "ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    all_user_text = rows + queue_rows + ticket_rows
    total_analyzed = len(all_user_text)

    # 2. Extract word frequencies
    word_counts = Counter()
    bigram_counts = Counter()
    for row in all_user_text:
        content = (row[0] or '').lower()
        words = re.findall(r'[a-z][a-z0-9_-]{2,}', content)
        filtered = [w for w in words if w not in _STOP_WORDS and len(w) > 2]
        word_counts.update(filtered)
        for i in range(len(filtered) - 1):
            bigram_counts[f"{filtered[i]} {filtered[i + 1]}"] += 1

    # 3. Memory tags across all agents
    tag_counts = Counter()
    mem_rows = conn.execute(
        "SELECT tags FROM memory WHERE tags IS NOT NULL AND tags != ''"
    ).fetchall()
    for row in mem_rows:
        tags = [t.strip().lower() for t in (row['tags'] or '').split(',')
                if t.strip()]
        tag_counts.update(tags)

    # 4. Sniffer pattern keywords
    pattern_topics = Counter()
    pat_rows = conn.execute(
        "SELECT description, occurrence_count FROM sniffer_memory "
        "ORDER BY occurrence_count DESC LIMIT 50"
    ).fetchall()
    for row in pat_rows:
        desc_words = re.findall(
            r'[a-z][a-z0-9_-]{2,}', (row['description'] or '').lower()
        )
        for w in desc_words:
            if w not in _STOP_WORDS:
                pattern_topics[w] += row['occurrence_count']

    # 5. Recent research topics
    research_topics = []
    try:
        res_rows = conn.execute(
            "SELECT topic, status FROM research_sessions "
            "ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        for row in res_rows:
            research_topics.append({
                'topic': row['topic'],
                'status': row['status'],
            })
    except Exception:
        pass  # Table may not exist yet

    # 6. Score & merge
    scored = {}
    for word, count in word_counts.items():
        if count < 2:
            continue
        score = count
        sources = ['conversations']
        if word in tag_counts:
            score *= 2
            sources.append('memory')
        if word in pattern_topics:
            score *= 1.5
            sources.append('patterns')
        scored[word] = {
            'topic': word,
            'score': round(score, 1),
            'sources': sources,
        }

    # Strong bigrams (more specific than unigrams)
    for bigram, count in bigram_counts.items():
        if count >= 3:
            scored[bigram] = {
                'topic': bigram,
                'score': round(count * 1.8, 1),
                'sources': ['conversations'],
            }

    # 7. Sort and take top N
    interests = sorted(
        scored.values(), key=lambda x: x['score'], reverse=True
    )[:limit]

    # 8. Generate suggestion prompts
    for item in interests:
        topic = item['topic']
        if 'memory' in item['sources']:
            item['suggestion'] = f"What do the agents know about {topic}?"
        elif 'patterns' in item['sources']:
            item['suggestion'] = f"Show me patterns around {topic}"
        else:
            item['suggestion'] = f"Tell me more about {topic}"

    return jsonify({
        'interests': interests,
        'research_topics': research_topics,
        'total_messages_analyzed': total_analyzed,
        'total_memory_tags': sum(tag_counts.values()),
    })
