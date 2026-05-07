"""Media Center API blueprint."""

from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from core.media_center.framework import (
    add_media_reference,
    add_timeline_clip,
    create_job,
    create_project,
    create_synth_take,
    link_media_account,
    project_handoff_manifest,
    public_state,
    run_job_real,
    run_job_simulation,
    update_project,
    update_project_routing,
)
from utils.swarm_root import SWARM_ROOT

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


@media_center_bp.route("/api/media-center/projects/<project_id>/clips", methods=["POST"])
def media_center_add_timeline_clip(project_id: str):
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400
    clip = add_timeline_clip(project_id, data)
    if not clip:
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "clip": clip})


@media_center_bp.route("/api/media-center/projects/<project_id>/synth-takes", methods=["POST"])
def media_center_create_synth_take(project_id: str):
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "prompt is required"}), 400
    take = create_synth_take(project_id, data)
    if not take:
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "take": take})


@media_center_bp.route("/api/media-center/projects/<project_id>/references", methods=["POST"])
def media_center_add_reference(project_id: str):
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "title is required"}), 400
    reference = add_media_reference(project_id, data)
    if not reference:
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "reference": reference})


@media_center_bp.route("/api/media-center/accounts/<account_id>/link", methods=["POST"])
def media_center_link_account(account_id: str):
    account = link_media_account(account_id, request.get_json(silent=True) or {})
    if not account:
        return jsonify({"ok": False, "error": "account not found"}), 404
    return jsonify({"ok": True, "account": account})


@media_center_bp.route("/api/media-center/projects/<project_id>/routing", methods=["PATCH"])
def media_center_update_routing(project_id: str):
    routing = update_project_routing(project_id, request.get_json(silent=True) or {})
    if not routing:
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "routing": routing})


@media_center_bp.route("/api/media-center/projects/<project_id>/handoff", methods=["GET"])
def media_center_project_handoff(project_id: str):
    manifest = project_handoff_manifest(project_id)
    if not manifest:
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "manifest": manifest})


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


@media_center_bp.route("/api/media-center/jobs/<job_id>/run", methods=["POST"])
def media_center_run_job(job_id: str):
    job = run_job_real(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job not found"}), 404
    return jsonify({"ok": True, "job": job})


@media_center_bp.route("/api/media-center/artifacts/<path:artifact_path>", methods=["GET"])
def media_center_artifact(artifact_path: str):
    root = (Path(SWARM_ROOT) / "artifacts" / "media_center").resolve()
    target = (Path(SWARM_ROOT) / artifact_path).resolve()
    if root not in target.parents and target != root:
        return jsonify({"ok": False, "error": "artifact outside media center root"}), 404
    if not target.exists() or not target.is_file():
        return jsonify({"ok": False, "error": "artifact not found"}), 404
    return send_file(target)
