"""
frontend/blueprints/sse.py — Server-Sent Events stream (R.2)
═══════════════════════════════════════════════════════════════════════════════
GET /api/events — SSE stream pushing chat updates, bus events, agent status.
Clients connect once; server pushes as events occur.
"""

import json
import queue
import threading
import time
import logging
import sqlite3
from flask import Blueprint, Response, request

sse_bp = Blueprint('sse', __name__)
logger = logging.getLogger(__name__)

# All active subscriber queues
_subscribers: list[queue.Queue] = []
_approval_audiences: dict[queue.Queue, str] = {}
_sub_lock = threading.Lock()

# Maximum queued events per subscriber before dropping
_MAX_QUEUE = 256


def publish(event_type: str, data: dict, *, audience: str | None = None):
    """Push an event to all connected SSE subscribers."""
    payload = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
    dead = []
    with _sub_lock:
        for q in _subscribers:
            if audience is not None and _approval_audiences.get(q) != audience:
                continue
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _approval_audiences.pop(q, None)
            try:
                _subscribers.remove(q)
            except ValueError:
                pass


def _sse_stream(q):
    """Generator that yields SSE formatted strings from the subscriber queue."""
    try:
        # Send initial keepalive
        yield ": connected\n\n"
        while True:
            try:
                msg = q.get(timeout=30)
                yield msg
            except queue.Empty:
                # Send keepalive comment to prevent timeout
                yield ": keepalive\n\n"
    except GeneratorExit:
        pass
    finally:
        with _sub_lock:
            _approval_audiences.pop(q, None)
            try:
                _subscribers.remove(q)
            except ValueError:
                pass


@sse_bp.route('/api/events', methods=['GET'])
def event_stream():
    """SSE endpoint — clients receive real-time push events."""
    q = queue.Queue(maxsize=_MAX_QUEUE)
    from core.tool_approval import session_identity
    from services.auth import get_current_user
    try:
        user = get_current_user()
    except sqlite3.DatabaseError:
        logger.exception('Approval SSE authentication unavailable; keeping ordinary SSE tool-free')
        user = None
    token = request.cookies.get('friday_session', '')
    with _sub_lock:
        _subscribers.append(q)
        if user and user['role'] == 'owner' and token:
            _approval_audiences[q] = session_identity(token)
    return Response(
        _sse_stream(q),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


# ── Convenience publishers (called from other modules) ───────────────────────

def publish_chat_update(conversation_id: str, agent: str, status: str, **extra):
    """Push a chat job status change to SSE subscribers."""
    publish('chat', {
        'conversation_id': conversation_id,
        'agent': agent,
        'status': status,
        **extra,
    })


def publish_agent_status(agent: str, status: str, **extra):
    """Push agent status change (online/offline/busy)."""
    publish('agent', {'agent': agent, 'status': status, **extra})


def publish_bus_event(topic: str, payload: dict):
    """Push a bus event to SSE subscribers."""
    publish('bus', {'topic': topic, 'payload': payload})
