"""Media Center API blueprint."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
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
from core.media_center.audio_engine import (
    get_media_asset,
    is_media_filename,
    list_media_assets,
    save_media_asset,
)
from core.media_center.dsp_video import (
    mix_two_decks,
    process_audio_dsp,
    render_youtube_visualizer,
)
from core.media_center.storage import MEDIA_STORAGE_ROOT

media_center_bp = Blueprint("media_center", __name__)


def _media_center_lite_payload(reason: str = "fallback") -> dict:
    """Return a fast, minimal Media Center state payload.

    Used when full public_state() is slow or fails (often due locked/slow
    side stores). Keeps the tile usable instead of appearing dead.
    """
    # Keep fallback storage-free: if side stores are locked, this must still
    # return immediately so UI can recover.
    projects = []
    jobs = []
    return {
        "degraded": True,
        "degraded_reason": reason,
        "projects": projects,
        "jobs": jobs,
        "runtime": {},
        "knowledge": {"indexed_count": 0},
        "tracking": {"progress": {"done_steps": 0, "step_count": 0}},
        "counts": {
            "projects": len(projects),
            "queued_jobs": sum(1 for job in jobs if str(job.get("status") or "") == "queued"),
            "completed_jobs": sum(1 for job in jobs if str(job.get("status") or "") == "completed"),
        },
    }


@media_center_bp.route("/api/media-center/state", methods=["GET"])
def media_center_state():
    # Bound expensive state hydration so UI stays responsive when side
    # stores are slow/locked (common on mixed Windows/WSL setups).
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(public_state)
    try:
        payload = future.result(timeout=4.0)
        return jsonify({"ok": True, **payload})
    except FuturesTimeout:
        future.cancel()
        return jsonify({"ok": True, **_media_center_lite_payload("state_timeout")})
    except Exception:
        return jsonify({"ok": True, **_media_center_lite_payload("state_error")})
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


@media_center_bp.route("/api/media-center/state-lite", methods=["GET"])
def media_center_state_lite():
    return jsonify({"ok": True, **_media_center_lite_payload("explicit_lite")})


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
    url = str(data.get("url") or data.get("link") or "").strip()
    if not title and not url:
        return jsonify({"ok": False, "error": "title or URL is required"}), 400
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


@media_center_bp.route("/api/media-center/library", methods=["GET"])
def media_center_library_list():
    items = list_media_assets()
    return jsonify({"ok": True, "assets": items, "count": len(items)})


@media_center_bp.route("/api/media-center/library/<asset_id>", methods=["GET"])
def media_center_library_get(asset_id: str):
    asset = get_media_asset(asset_id)
    if not asset:
        return jsonify({"ok": False, "error": "asset not found"}), 404
    return jsonify({"ok": True, "asset": asset})


@media_center_bp.route("/api/media-center/library/upload", methods=["POST"])
def media_center_library_upload():
    import base64
    if "file" in request.files:
        f = request.files["file"]
        filename = f.filename or "upload.wav"
        data = f.read()
        content_type = f.mimetype or ""
        title = request.form.get("title") or ""
        artist = request.form.get("artist") or ""
    else:
        body = request.get_json(silent=True) or {}
        filename = str(body.get("filename") or "upload.wav")
        raw_b64 = str(body.get("data_base64") or "")
        if not raw_b64:
            return jsonify({"ok": False, "error": "file or data_base64 is required"}), 400
        try:
            data = base64.b64decode(raw_b64)
        except Exception:
            return jsonify({"ok": False, "error": "invalid base64 audio payload"}), 400
        content_type = str(body.get("content_type") or "")
        title = str(body.get("title") or "")
        artist = str(body.get("artist") or "")
    if not data:
        return jsonify({"ok": False, "error": "empty file"}), 400
    if not is_media_filename(filename, content_type):
        return jsonify({"ok": False, "error": f"unsupported media file type: {filename}"}), 400
    asset = save_media_asset(filename, data, source="upload", metadata={"title": title, "artist": artist})
    return jsonify({"ok": True, "asset": asset})


@media_center_bp.route("/api/media-center/library/<asset_id>/dsp", methods=["POST"])
def media_center_library_dsp(asset_id: str):
    opts = request.get_json(silent=True) or {}
    try:
        asset = process_audio_dsp(asset_id, opts)
        return jsonify({"ok": True, "asset": asset})
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@media_center_bp.route("/api/media-center/library/<asset_id>/render-video", methods=["POST"])
def media_center_library_render_video(asset_id: str):
    opts = request.get_json(silent=True) or {}
    try:
        asset = render_youtube_visualizer(asset_id, opts)
        return jsonify({"ok": True, "asset": asset})
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@media_center_bp.route("/api/media-center/decks/mix", methods=["POST"])
def media_center_decks_mix():
    body = request.get_json(silent=True) or {}
    deck_a = str(body.get("deck_a_id") or "").strip()
    deck_b = str(body.get("deck_b_id") or "").strip()
    if not deck_a or not deck_b:
        return jsonify({"ok": False, "error": "deck_a_id and deck_b_id are required"}), 400
    try:
        asset = mix_two_decks(
            deck_a,
            deck_b,
            crossfade_sec=float(body.get("crossfade_sec", 3.0)),
            gain_a_db=float(body.get("gain_a_db", 0.0)),
            gain_b_db=float(body.get("gain_b_db", 0.0)),
            mode=str(body.get("mode") or "crossfade"),
        )
        return jsonify({"ok": True, "asset": asset})
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@media_center_bp.route("/api/media-center/artifacts/<path:artifact_path>", methods=["GET"])
def media_center_artifact(artifact_path: str):
    root = (MEDIA_STORAGE_ROOT / "artifacts" / "media_center").resolve()
    target = (MEDIA_STORAGE_ROOT / artifact_path).resolve()
    if root not in target.parents and target != root:
        return jsonify({"ok": False, "error": "artifact outside media center root"}), 404
    if not target.exists() or not target.is_file():
        return jsonify({"ok": False, "error": "artifact not found"}), 404
    return send_file(target)
