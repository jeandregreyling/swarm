"""Media Center API blueprint."""

from flask import Blueprint, jsonify, request

from core.media_center.framework import (
    create_job,
    create_project,
    public_state,
    run_job_simulation,
    update_project,
)

media_center_bp = Blueprint("media_center", __name__)


@media_center_bp.route("/api/media-center/state", methods=["GET"])
def media_center_state():
    return jsonify({"ok": True, **public_state()})


@media_center_bp.route("/api/media-center/projects", methods=["POST"])
def media_center_create_project():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    prompt = str(data.get("prompt") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400
    if not prompt:
        return jsonify({"ok": False, "error": "prompt is required"}), 400
    project = create_project(data)
    return jsonify({"ok": True, "project": project})


@media_center_bp.route("/api/media-center/projects/<project_id>", methods=["PATCH"])
def media_center_patch_project(project_id: str):
    project = update_project(project_id, request.get_json(silent=True) or {})
    if not project:
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "project": project})


@media_center_bp.route("/api/media-center/projects/<project_id>/jobs", methods=["POST"])
def media_center_create_job(project_id: str):
    job = create_job(project_id, request.get_json(silent=True) or {})
    if not job:
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "job": job})


@media_center_bp.route("/api/media-center/jobs/<job_id>/simulate", methods=["POST"])
def media_center_simulate_job(job_id: str):
    job = run_job_simulation(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job not found"}), 404
    return jsonify({"ok": True, "job": job})

