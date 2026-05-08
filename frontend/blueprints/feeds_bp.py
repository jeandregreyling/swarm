"""blueprints/feeds_bp.py — Feeds subscription CRUD + poll.

V7C-A10 refinement — server-side truth for the Feeds tab, replacing the
localStorage-only persistence. Custom RSS is real; third-party connectors
(X, HN, LinkedIn, Stack Overflow, Reddit) are recorded as ``pending`` so
the UI can render honest state.
"""
from flask import Blueprint, jsonify, request

from core import feeds as _feeds

feeds_bp = Blueprint('feeds_bp', __name__)


def _owner() -> str:
    # Single-owner deploy for now; hook into session_auth when per-user
    # feeds land (tracked under V8 rather than V7C).
    return 'seven'


@feeds_bp.route('/api/feeds/subscriptions', methods=['GET'])
def list_subs():
    return jsonify({'ok': True, 'items': _feeds.list_subscriptions(_owner())})


@feeds_bp.route('/api/feeds/subscriptions', methods=['POST'])
def add_sub():
    body = request.get_json(silent=True) or {}
    kind = str(body.get('kind') or '').strip().lower()
    url = str(body.get('url') or '').strip()
    title = body.get('title') or None
    status = 'pending' if kind not in ('rss', 'atom') else 'pending'
    try:
        sub_id = _feeds.add_subscription(
            kind, url, title=title, owner=_owner(), status=status,
        )
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    return jsonify({'ok': True, 'sub_id': sub_id})


@feeds_bp.route('/api/feeds/subscriptions/<sub_id>', methods=['PATCH'])
def edit_sub(sub_id: str):
    body = request.get_json(silent=True) or {}
    ok = _feeds.update_subscription(
        sub_id,
        enabled=body.get('enabled'),
        title=body.get('title'),
        owner=_owner(),
    )
    if not ok:
        return jsonify({'ok': False, 'error': 'subscription not found or no fields'}), 404
    return jsonify({'ok': True})


@feeds_bp.route('/api/feeds/subscriptions/<sub_id>', methods=['DELETE'])
def delete_sub(sub_id: str):
    ok = _feeds.remove_subscription(sub_id, owner=_owner())
    if not ok:
        return jsonify({'ok': False, 'error': 'subscription not found'}), 404
    return jsonify({'ok': True})


@feeds_bp.route('/api/feeds/subscriptions/<sub_id>/poll', methods=['POST'])
def poll_sub(sub_id: str):
    rep = _feeds.poll_once(sub_id, owner=_owner())
    if not rep.get('ok'):
        code = 502 if rep.get('kind') in ('rss', 'atom') else 200
        return jsonify(rep), code
    return jsonify(rep)
