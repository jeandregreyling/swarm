"""
blueprints/spine_bp.py — Session 29: spine events API.

Three endpoints:
    GET  /api/spine/events         — paged query (kinds, severity, since, limit)
    GET  /api/spine/stream         — SSE, live tail
    POST /api/spine/log            — emit a single event from the frontend
                                     (used for UI-originated notes like Trace
                                     "pin to vortex" clicks)
"""
from __future__ import annotations

import json
import queue
import time
from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request, stream_with_context

from core import spine
from utils.db import trace_log

spine_bp = Blueprint('spine_bp', __name__)


def _as_bool(v, default=False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).lower() in ('1', 'true', 'yes', 'y', 'on')


@spine_bp.route('/api/spine/events', methods=['GET'])
def api_spine_events():
    """Paged list. Query args: kinds (csv), min_severity, thread_id,
    change_id, since (unix s), limit, source (ring|db). Default source=db."""
    args = request.args
    source = (args.get('source') or 'db').lower()
    kinds_csv = args.get('kinds') or ''
    kinds = [k.strip() for k in kinds_csv.split(',') if k.strip()] or None
    min_sev = args.get('min_severity') or None
    thread_id = args.get('thread_id') or None
    change_id = args.get('change_id') or None
    try:
        limit = max(1, min(int(args.get('limit') or 100), 1000))
    except Exception:
        limit = 100
    since_raw = args.get('since')
    since_ts = None
    if since_raw:
        try:
            since_ts = float(since_raw)
        except Exception:
            since_ts = None

    if source == 'ring':
        evs = spine.get_recent(
            limit=limit, kinds=kinds, min_severity=min_sev,
            thread_id=thread_id, change_id=change_id,
        )
        items = [e.to_dict() for e in evs]
    else:
        items = trace_log.list_events(
            limit=limit, kinds=kinds, min_severity=min_sev,
            thread_id=thread_id, change_id=change_id, since_ts=since_ts,
        )

    return jsonify({
        'ok': True,
        'source': 'ring' if source == 'ring' else 'db',
        'count': len(items),
        'items': items,
    })


@spine_bp.route('/api/spine/log', methods=['POST'])
def api_spine_log():
    """Frontend-initiated emit. Useful for UI notes ('pinned to vortex',
    'user dismissed trace'). Does not expose guardian/watchdog kinds to
    prevent spoofing — the backend owns those."""
    data = request.get_json(silent=True) or {}
    kind = (data.get('kind') or 'system').strip()
    if kind in ('guardian', 'watchdog'):
        return jsonify({'ok': False, 'error': 'kind restricted'}), 400
    msg = (data.get('message') or '').strip()
    if not msg:
        return jsonify({'ok': False, 'error': 'message required'}), 400
    sev = data.get('severity') or 'info'
    ev = spine.log(
        kind=kind,
        message=msg,
        severity=sev,
        source=(data.get('source') or 'frontend'),
        agent=data.get('agent'),
        thread_id=data.get('thread_id'),
        change_id=data.get('change_id'),
        payload=(data.get('payload') or {}),
    )
    return jsonify({'ok': True, 'event': ev.to_dict()})


@spine_bp.route('/api/spine/stream', methods=['GET'])
def api_spine_stream():
    """SSE live tail. Clients may filter via ?kinds=csv&min_severity=warn.
    Each event is a JSON TraceEvent dict. A heartbeat ':' ping is sent
    every 20s so proxies don't drop the connection."""
    kinds_csv = request.args.get('kinds') or ''
    kinds = {k.strip() for k in kinds_csv.split(',') if k.strip()}
    min_sev = request.args.get('min_severity') or None

    q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=200)
    spine.subscribe(q)

    def _gen():
        try:
            # Immediate connect-ack so clients (and diagnostics) know the
            # stream is live even before the first real event arrives.
            yield ': ready\n\n'
            # Replay the last 20 matching events so late joiners see context.
            replay = spine.get_recent(limit=20, kinds=kinds or None, min_severity=min_sev)
            for ev in reversed(replay):
                yield f"data: {json.dumps(ev.to_dict())}\n\n"

            last_ping = time.time()
            while True:
                try:
                    ev = q.get(timeout=1.0)
                except queue.Empty:
                    if time.time() - last_ping > 20:
                        yield ': ping\n\n'
                        last_ping = time.time()
                    continue

                if kinds and ev.get('kind') not in kinds:
                    continue
                if min_sev:
                    order = {'debug': 0, 'info': 1, 'warn': 2, 'error': 3, 'critical': 4}
                    if order.get(ev.get('severity'), 1) < order.get(min_sev, 1):
                        continue
                yield f"data: {json.dumps(ev)}\n\n"
        except GeneratorExit:
            pass
        finally:
            spine.unsubscribe(q)

    return Response(
        stream_with_context(_gen()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )
