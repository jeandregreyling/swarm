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
from flask import Blueprint, Response, request

sse_bp = Blueprint('sse', __name__)
logger = logging.getLogger(__name__)

# All active subscriber queues
_subscribers: list[queue.Queue] = []
_sub_lock = threading.Lock()

# Maximum queued events per subscriber before dropping
_MAX_QUEUE = 256


def publish(event_type: str, data: dict):
    """Push an event to all connected SSE subscribers."""
    payload = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
    dead = []
    with _sub_lock:
        for q in _subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
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
            try:
                _subscribers.remove(q)
            except ValueError:
                pass


@sse_bp.route('/api/events', methods=['GET'])
def event_stream():
    """SSE endpoint — clients receive real-time push events."""
    q = queue.Queue(maxsize=_MAX_QUEUE)
    with _sub_lock:
        _subscribers.append(q)
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
