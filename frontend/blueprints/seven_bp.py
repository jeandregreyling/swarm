"""blueprints.seven_bp — HTTP surface for Seven (perception + brain).

Endpoints:

  Perception:
    GET  /api/seven/observe?focus=<id|kind:id>
    GET  /api/seven/related/<kind>/<id>?depth=1|2
    GET  /api/seven/suggest
    GET  /api/seven/stats

  Memory:
    GET  /api/seven/episodes?limit=&kind=&record_id=&source=
    GET  /api/seven/beliefs?subject=&predicate=&min_confidence=
    GET  /api/seven/concepts?tag=&q=
    GET  /api/seven/concepts/<slug>
    GET  /api/seven/attention?limit=
    GET  /api/seven/memory

  Reasoning:
    GET  /api/seven/explain?focus=<id>
    GET  /api/seven/decide?intent=...&focus=<id>

  Liveness:
    GET  /api/seven/heartbeat

  Maintenance (POST):
    POST /api/seven/concepts/reload
    POST /api/seven/consolidate

Seven is propose-only. None of these endpoints mutate records, edges,
steps, or any swarm state. The two POST routes only refresh Seven's
internal indices (concepts and derived beliefs).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.seven import (
    observe, related, stats, suggestions,
    memory as _mem,
    concepts as _concepts,
    explain, decide, consolidate,
    heartbeat as _heartbeat,
)

seven_bp = Blueprint("seven_bp", __name__)


# ── perception ──────────────────────────────────────────────────────────────

@seven_bp.route("/api/seven/observe", methods=["GET"])
def api_observe():
    focus = request.args.get("focus") or None
    try:
        limit_recent = int(request.args.get("limit_recent", "10"))
        limit_open = int(request.args.get("limit_open", "12"))
    except ValueError:
        limit_recent, limit_open = 10, 12
    snap = observe(focus=focus, limit_recent=limit_recent, limit_open=limit_open)
    return jsonify({"ok": True, **snap})


@seven_bp.route("/api/seven/related/<kind>/<rid>", methods=["GET"])
def api_related(kind: str, rid: str):
    try:
        depth = int(request.args.get("depth", "1"))
    except ValueError:
        depth = 1
    depth = max(1, min(2, depth))
    return jsonify({"ok": True, **related(kind, rid, depth=depth)})


@seven_bp.route("/api/seven/suggest", methods=["GET"])
def api_suggest():
    snap = observe(limit_recent=10, limit_open=12)
    return jsonify({"ok": True, **suggestions(snap)})


@seven_bp.route("/api/seven/stats", methods=["GET"])
def api_stats():
    return jsonify({"ok": True, **stats()})


# ── memory ──────────────────────────────────────────────────────────────────

@seven_bp.route("/api/seven/episodes", methods=["GET"])
def api_episodes():
    try:
        limit = int(request.args.get("limit", "25"))
    except ValueError:
        limit = 25
    out = _mem.recall_episodes(
        kind=request.args.get("kind") or None,
        record_id=request.args.get("record_id") or None,
        source=request.args.get("source") or None,
        limit=max(1, min(200, limit)),
    )
    return jsonify({"ok": True, "items": out, "count": len(out)})


@seven_bp.route("/api/seven/beliefs", methods=["GET"])
def api_beliefs():
    try:
        min_conf = float(request.args.get("min_confidence", "0"))
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        min_conf, limit = 0.0, 50
    out = _mem.beliefs_about(
        subject=request.args.get("subject") or None,
        predicate=request.args.get("predicate") or None,
        min_confidence=min_conf,
        limit=max(1, min(200, limit)),
    )
    return jsonify({"ok": True, "items": out, "count": len(out)})


@seven_bp.route("/api/seven/concepts", methods=["GET"])
def api_concepts():
    q = request.args.get("q") or None
    tag = request.args.get("tag") or None
    if q:
        out = _mem.search_concepts(q, limit=50)
    else:
        out = _mem.list_concepts(tag=tag, limit=200)
    return jsonify({"ok": True, "items": out, "count": len(out)})


@seven_bp.route("/api/seven/concepts/<slug>", methods=["GET"])
def api_concept_one(slug: str):
    c = _mem.get_concept(slug)
    if not c:
        return jsonify({"ok": False, "error": "not_found", "slug": slug}), 404
    return jsonify({"ok": True, "concept": c})


@seven_bp.route("/api/seven/attention", methods=["GET"])
def api_attention():
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        limit = 20
    return jsonify({"ok": True, "items": _mem.hot_records(limit=max(1, min(100, limit)))})


@seven_bp.route("/api/seven/memory", methods=["GET"])
def api_memory():
    return jsonify({"ok": True, **_mem.memory_stats()})


# ── reasoning ───────────────────────────────────────────────────────────────

@seven_bp.route("/api/seven/explain", methods=["GET"])
def api_explain():
    focus = request.args.get("focus") or None
    try:
        limit_eps = int(request.args.get("limit_episodes", "8"))
    except ValueError:
        limit_eps = 8
    return jsonify({"ok": True, **explain(focus=focus, limit_episodes=limit_eps)})


@seven_bp.route("/api/seven/decide", methods=["GET"])
def api_decide():
    intent = request.args.get("intent") or "status"
    focus = request.args.get("focus") or None
    return jsonify({"ok": True, **decide(intent, focus=focus)})


# ── liveness ────────────────────────────────────────────────────────────────

@seven_bp.route("/api/seven/heartbeat", methods=["GET"])
def api_heartbeat():
    return jsonify({"ok": True, **_heartbeat()})


# ── maintenance ─────────────────────────────────────────────────────────────

@seven_bp.route("/api/seven/concepts/reload", methods=["POST"])
def api_concepts_reload():
    out = _concepts.reload_all()
    return jsonify({"ok": True, "loaded": len(out), "items": out})


@seven_bp.route("/api/seven/consolidate", methods=["POST"])
def api_consolidate():
    return jsonify({"ok": True, **consolidate()})
