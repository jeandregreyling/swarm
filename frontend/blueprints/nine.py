"""nine.py — Agent Nine routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

nine_bp = Blueprint('nine', __name__)

@nine_bp.route('/api/nine/history')
def api_nine_history():
    conn = get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if 'memory_nine' not in tables:
        conn.close()
        return jsonify([])
        
    rows = conn.execute(
        "SELECT subject, content, created_at FROM memory_nine "
        "WHERE archived=0 AND source IN ('vs_tab','repl_session','dashboard') "
        "ORDER BY created_at ASC LIMIT 40"
    ).fetchall()
    conn.close()
    return jsonify([{'question': r['subject'], 'answer': r['content'], 'ts': str(r['created_at'] or '')[:16]} for r in rows])



@nine_bp.route('/api/nine/actions')
def api_nine_actions():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, subject, content, created_at FROM memory_nine "
        "WHERE archived=0 AND tags LIKE '%action%' "
        "ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([{
        'id': r['id'],
        'title': r['subject'],
        'description': r['content'],
        'ts': str(r['created_at'] or '')[:16]
    } for r in rows])



@nine_bp.route('/api/nine', methods=['POST'])
def api_nine_chat():
    from datetime import datetime as _dt
    data    = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400

    from database import get_agent_memory, save_agent_memory
    try:
        from config import GROQ_API_KEY, NINE_MODEL, NINE_SYSTEM_PROMPT
        from groq import Groq

        if not GROQ_API_KEY:
            return jsonify({'error': 'GROQ_API_KEY not configured — add to /etc/environment'}), 500

        conn       = get_connection()
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]

        nine_history  = conn.execute("SELECT subject, content, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 10").fetchall()
        nine_relevant = get_agent_memory('nine', query=message, limit=5)

        try:
            from sandpits import list_proposals
            proposals = list_proposals()[:5]
        except Exception:
            proposals = []
        open_debates = conn.execute(
            "SELECT topic, rounds FROM debates WHERE status='open' ORDER BY created_at DESC LIMIT 5"
        ).fetchall() if 'debates' in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()] else []
        conn.close()

        ctx  = f"=== Swarm state: {_dt.now().strftime('%Y-%m-%d %H:%M')} ===\n"
        ctx += f"Queue: {queued} queued, {processing} processing\n"
        ctx += f"Open tickets: {open_t}\n"
        ctx += "\n=== Governance (ALM) ===\n"
        ctx += "Mutating actions require approved proposal IDs (approved/executed).\n"
        ctx += "Use proposal-first workflow for shell/skill/exec/write actions.\n"
        ctx += "Draft/refine ideas in sandpits and pressure-test options with Ten, Eleven, and Twelve.\n"
        if proposals:
            ctx += f"Pending proposals: {len(proposals)}\n"
            for p in proposals[:3]:
                ctx += f"  - {str(p.get('title',''))[:80]}\n"
        if open_debates:
            ctx += f"Open debates: {len(open_debates)}\n"
            for d in open_debates:
                ctx += f"  - {d[0][:60]} ({d[1]} rounds)\n"
        if nine_relevant:
            ctx += "\n=== Relevant past context ===\n"
            for m in nine_relevant:
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        if nine_history:
            ctx += "\n=== Recent conversation history ===\n"
            for m in reversed(nine_history):
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"

        full_message = ctx + f"\n=== Ghost asks ===\n{message}"

        client   = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=NINE_MODEL,
            max_tokens=4096,
            messages=[
                {'role': 'system', 'content': NINE_SYSTEM_PROMPT},
                {'role': 'user',   'content': full_message},
            ]
        )
        answer = response.choices[0].message.content
        tokens = response.usage.prompt_tokens + response.usage.completion_tokens

        save_agent_memory(
            agent_name='nine', subject=message[:100], content=answer,
            tags='vs,dashboard', importance=8, source='vs_tab'
        )

        from database import log_activity
        log_activity('terminal', 'nine_consulted', f'tokens={tokens} | {message[:80]}')

        return jsonify({'answer': answer, 'tokens': tokens, 'model': NINE_MODEL})

    except Exception as e:
        print(f'[Terminal] Nine error: {e}')
        return jsonify({'error': str(e)}), 500



@nine_bp.route('/api/nine/stream', methods=['POST'])
def api_nine_stream():
    """Streaming version of Nine chat via SSE — Groq."""
    from datetime import datetime as _dt
    data    = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400

    from database import get_agent_memory, save_agent_memory
    try:
        from config import GROQ_API_KEY, NINE_MODEL, NINE_SYSTEM_PROMPT
        from groq import Groq

        if not GROQ_API_KEY:
            def _err():
                yield 'data: {"error": "GROQ_API_KEY not set"}\n\n'
            return Response(_err(), mimetype='text/event-stream')

        conn          = get_connection()
        queued        = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t        = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        nine_history  = conn.execute("SELECT subject, content, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 8").fetchall()
        nine_relevant = get_agent_memory('nine', query=message, limit=4)
        conn.close()

        ctx  = f"=== Swarm state: {_dt.now().strftime('%Y-%m-%d %H:%M')} ===\n"
        ctx += f"Queue: {queued} queued | Open tickets: {open_t}\n"
        if nine_relevant:
            ctx += "\n=== Relevant past context ===\n"
            for m in nine_relevant:
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        if nine_history:
            ctx += "\n=== Recent conversation history ===\n"
            for m in reversed(nine_history):
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        full_message = ctx + f"\n=== Ghost asks ===\n{message}"

        client = Groq(api_key=GROQ_API_KEY)

        def _generate():
            full_answer = []
            try:
                stream = client.chat.completions.create(
                    model=NINE_MODEL,
                    max_tokens=4096,
                    messages=[
                        {'role': 'system', 'content': NINE_SYSTEM_PROMPT},
                        {'role': 'user',   'content': full_message},
                    ],
                    stream=True,
                )
                for chunk in stream:
                    text = chunk.choices[0].delta.content or ''
                    if text:
                        full_answer.append(text)
                        yield f'data: {json.dumps({"text": text})}\n\n'
                answer = ''.join(full_answer)
                save_agent_memory(
                    agent_name='nine', subject=message[:100], content=answer,
                    tags='vs,dashboard', importance=8, source='vs_tab'
                )
                from database import log_activity
                log_activity('terminal', 'nine_consulted', f'model={NINE_MODEL} | {message[:80]}')
                yield f'data: {json.dumps({"done": True, "model": NINE_MODEL})}\n\n'
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'

        return Response(_generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500



