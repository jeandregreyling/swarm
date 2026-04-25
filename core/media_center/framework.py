"""Media Center framework helpers.

Provides a lightweight persisted state store for the Media Center tile so the
UI can manage projects, queue jobs, and test a local-first generation pipeline
before real audio/video runners are connected.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from core.knowledge import projects as _kc_projects
from core import feeds as _feeds
from core import spine as _spine
from utils.swarm_root import SWARM_ROOT
from utils.db import trace_log as _trace_log
from utils.db._connection import get_connection

_STATE_PATH = Path(SWARM_ROOT) / "sandpits" / "shared" / "media_center_state.json"
_LOCAL_TIMEOUT = 1.5
_MEDIA_STOP_WORDS = {
    "the", "and", "with", "into", "from", "that", "this", "build", "make",
    "video", "music", "audio", "visual", "media", "project", "for", "your",
    "have", "just", "will", "then", "them", "high", "short", "long",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_project_blueprint() -> dict[str, Any]:
    return {
        "tracks": [
            {"id": "trk-score", "name": "Score Bed", "role": "music", "model_hint": "musicgen-small"},
            {"id": "trk-fx", "name": "Texture / FX", "role": "audio-design", "model_hint": "stable-audio-open"},
        ],
        "scenes": [
            {"id": "scn-1", "name": "Intro", "duration_sec": 8, "goal": "Establish the mood and pulse."},
            {"id": "scn-2", "name": "Lift", "duration_sec": 12, "goal": "Build momentum for the main hook."},
        ],
        "deliverables": [
            {"id": "dlv-1", "type": "audio", "format": "wav", "target": "master stem"},
            {"id": "dlv-2", "type": "video", "format": "mp4", "target": "preview reel"},
        ],
    }


def _default_state() -> dict[str, Any]:
    starter = {
        "id": "media-demo",
        "name": "Swarm Launch Teaser",
        "medium": "audio-video",
        "status": "draft",
        "prompt": "Build a cinematic teaser with percussive pulse, luminous pads, and fast-cut system visuals.",
        "style": "future pulse / high-energy",
        "engine_mode": "local-first",
        "duration_sec": 45,
        "updated_at": _now_iso(),
    }
    starter.update(_default_project_blueprint())
    return {
        "created_at": _now_iso(),
        "projects": [starter],
        "jobs": [
            {
                "id": "job-demo",
                "project_id": "media-demo",
                "project_name": "Swarm Launch Teaser",
                "job_type": "compile-preview",
                "mode": "simulate",
                "status": "ready",
                "engine": "local-ffmpeg-placeholder",
                "notes": "Framework stub ready for model wiring.",
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "artifacts": [
                    {"label": "Storyboard", "path": "sandpits/shared/media_center_storyboard.md", "status": "planned"},
                    {"label": "Preview MP4", "path": "exports/media-demo-preview.mp4", "status": "planned"},
                ],
            }
        ],
        "presets": list_presets(),
    }


def _ensure_state_file() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STATE_PATH.exists():
        _STATE_PATH.write_text(json.dumps(_default_state(), indent=2), encoding="utf-8")


def load_state() -> dict[str, Any]:
    _ensure_state_file()
    try:
        raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("state root must be an object")
        raw.setdefault("projects", [])
        raw.setdefault("jobs", [])
        raw.setdefault("presets", list_presets())
        changed = False
        for project in raw["projects"]:
            if _sync_project_integrations(project):
                changed = True
        if changed:
            save_state(raw)
        return raw
    except Exception:
        fallback = _default_state()
        save_state(fallback)
        return fallback


def save_state(state: dict[str, Any]) -> None:
    _ensure_state_file()
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def list_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "pulse-trailer",
            "name": "Pulse Trailer",
            "medium": "audio-video",
            "summary": "Aggressive teaser flow for short promos and launch videos.",
            "music_models": ["musicgen-small", "stable-audio-open"],
            "video_models": ["comfyui", "wan-local", "ffmpeg-comp"],
        },
        {
            "id": "ambient-score",
            "name": "Ambient Score",
            "medium": "music",
            "summary": "Long-form beds, intros, and atmospheric stems.",
            "music_models": ["musicgen-medium", "riffusion", "stable-audio-open"],
            "video_models": [],
        },
        {
            "id": "visualizer-pack",
            "name": "Visualizer Pack",
            "medium": "video",
            "summary": "Loops, waveform overlays, caption bars, and assembly-only outputs.",
            "music_models": [],
            "video_models": ["ffmpeg-comp", "comfyui", "animatediff-local"],
        },
    ]


def summarize_runtime() -> dict[str, Any]:
    return {
        "audio": {
            "ollama": _service_up("http://127.0.0.1:11434/api/tags"),
            "lmstudio": _service_up("http://127.0.0.1:1234/v1/models"),
            "ffmpeg": bool(shutil.which("ffmpeg")),
        },
        "video": {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "python": bool(shutil.which("python3") or shutil.which("python")),
            "comfyui_hint": _service_up("http://127.0.0.1:8188"),
        },
        "storage": {
            "state_path": str(_STATE_PATH),
            "exports_root": str(Path(SWARM_ROOT) / "exports"),
        },
    }


def _service_up(url: str) -> bool:
    try:
        response = requests.get(url, timeout=_LOCAL_TIMEOUT)
        return response.status_code < 500
    except Exception:
        return False


def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    state = load_state()
    project_id = f"media-{uuid4().hex[:8]}"
    project = {
        "id": project_id,
        "name": str(payload.get("name") or "Untitled Media Project").strip()[:120],
        "medium": str(payload.get("medium") or "audio-video").strip()[:40],
        "status": "draft",
        "prompt": str(payload.get("prompt") or "").strip(),
        "style": str(payload.get("style") or "").strip(),
        "engine_mode": str(payload.get("engine_mode") or "local-first").strip()[:40],
        "duration_sec": int(payload.get("duration_sec") or 30),
        "updated_at": _now_iso(),
    }
    project.update(_default_project_blueprint())
    _sync_project_integrations(project)
    state["projects"].insert(0, project)
    save_state(state)
    _spine.log(
        kind=_spine.EventKind.TICKET,
        message=f"Media project created: {project['name']}",
        source="media_center",
        change_id=project_id,
        payload={"project_id": project_id, "studio_project_id": project.get("studio_project_id")},
    )
    return project


def update_project(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    for project in state["projects"]:
        if project.get("id") != project_id:
            continue
        for key in ("name", "prompt", "style", "medium", "engine_mode", "status"):
            if key in payload:
                project[key] = str(payload.get(key) or "").strip() or project.get(key)
        if "duration_sec" in payload:
            try:
                project["duration_sec"] = max(5, int(payload.get("duration_sec")))
            except Exception:
                pass
        project["updated_at"] = _now_iso()
        _sync_project_integrations(project)
        save_state(state)
        return project
    return None


def create_job(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    project = next((p for p in state["projects"] if p.get("id") == project_id), None)
    if not project:
        return None
    job_type = str(payload.get("job_type") or "generate-audio").strip()
    mode = str(payload.get("mode") or "simulate").strip()
    job = {
        "id": f"job-{uuid4().hex[:10]}",
        "project_id": project_id,
        "project_name": project.get("name"),
        "job_type": job_type,
        "mode": mode,
        "status": "queued",
        "engine": _job_engine_hint(job_type),
        "notes": str(payload.get("notes") or "Queued from Media Center UI.").strip(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "artifacts": _default_artifacts(project_id, job_type),
    }
    state["jobs"].insert(0, job)
    project["status"] = "queued"
    project["updated_at"] = _now_iso()
    save_state(state)
    _spine.log(
        kind=_spine.EventKind.TESTLAB,
        message=f"Media job queued: {job_type}",
        source="media_center",
        change_id=project_id,
        payload={"job_id": job["id"], "project_id": project_id, "mode": mode},
    )
    return job


def run_job_simulation(job_id: str) -> dict[str, Any] | None:
    state = load_state()
    job = next((j for j in state["jobs"] if j.get("id") == job_id), None)
    if not job:
        return None
    job["status"] = "completed"
    job["mode"] = "simulated-local"
    job["updated_at"] = _now_iso()
    job["notes"] = "Simulation complete. Replace this stage with local model runners and ffmpeg compilers."
    for artifact in job.get("artifacts", []):
        artifact["status"] = "simulated"
    for project in state["projects"]:
        if project.get("id") == job.get("project_id"):
            project["status"] = "ready"
            project["updated_at"] = _now_iso()
            break
    save_state(state)
    _spine.log(
        kind=_spine.EventKind.CHECKPOINT,
        message=f"Media simulation complete: {job.get('project_name') or job.get('project_id')}",
        source="media_center",
        change_id=job.get("project_id"),
        payload={"job_id": job_id, "artifacts": job.get("artifacts", [])},
    )
    return job


def _job_engine_hint(job_type: str) -> str:
    job_type = job_type.lower()
    if "audio" in job_type or "music" in job_type:
        return "musicgen / stable-audio"
    if "video" in job_type or "visual" in job_type:
        return "comfyui / ffmpeg"
    return "ffmpeg compile graph"


def _default_artifacts(project_id: str, job_type: str) -> list[dict[str, str]]:
    base = Path("exports") / project_id
    job_type = job_type.lower()
    if "audio" in job_type or "music" in job_type:
        return [
            {"label": "Stem Pack", "path": str(base / "stems" / "master.wav"), "status": "planned"},
            {"label": "Cue Sheet", "path": str(base / "cue-sheet.json"), "status": "planned"},
        ]
    if "video" in job_type or "visual" in job_type:
        return [
            {"label": "Preview MP4", "path": str(base / "preview.mp4"), "status": "planned"},
            {"label": "Frame Cache", "path": str(base / "frames"), "status": "planned"},
        ]
    return [
        {"label": "Compile Output", "path": str(base / "final-cut.mp4"), "status": "planned"},
        {"label": "Manifest", "path": str(base / "manifest.json"), "status": "planned"},
    ]


def public_state() -> dict[str, Any]:
    state = load_state()
    payload = copy.deepcopy(state)
    payload["runtime"] = summarize_runtime()
    payload["interests"] = _media_interest_context(payload.get("projects", []))
    payload["feeds"] = _media_feed_context(payload["interests"])
    payload["spine"] = _media_spine_context()
    payload["studio"] = _media_studio_context(payload.get("projects", []))
    payload["counts"] = {
        "projects": len(payload.get("projects", [])),
        "queued_jobs": sum(1 for job in payload.get("jobs", []) if job.get("status") == "queued"),
        "completed_jobs": sum(1 for job in payload.get("jobs", []) if job.get("status") == "completed"),
    }
    return payload


def _sync_project_integrations(project: dict[str, Any]) -> bool:
    changed = False
    if not project.get("studio_project_id"):
        studio_project_id = _kc_projects.create_project(
            project.get("name") or "Media Project",
            description=_studio_project_description(project),
            methodology="mixed",
            owner="seven",
        )
        if studio_project_id:
            project["studio_project_id"] = studio_project_id
            _seed_studio_project(studio_project_id, project)
            changed = True
    elif project.get("studio_project_id"):
        _kc_projects.update_project(
            project["studio_project_id"],
            name=project.get("name") or "Media Project",
            description=_studio_project_description(project),
            owner="seven",
        )
    if _sync_interests(project):
        changed = True
    return changed


def _studio_project_description(project: dict[str, Any]) -> str:
    prompt = str(project.get("prompt") or "").strip()
    style = str(project.get("style") or "").strip()
    medium = str(project.get("medium") or "").strip()
    duration = project.get("duration_sec") or 0
    return (
        f"Media Center sync\n"
        f"Medium: {medium}\n"
        f"Style: {style or 'n/a'}\n"
        f"Duration: {duration}s\n\n"
        f"{prompt}"
    ).strip()


def _seed_studio_project(project_id: str, media_project: dict[str, Any]) -> None:
    try:
        for scene in media_project.get("scenes", [])[:6]:
            _kc_projects.add_step(
                project_id,
                f"Scene: {scene.get('name') or 'Untitled'}",
                description=(scene.get("goal") or "")[:1000],
                owner="seven",
            )
        for deliverable in media_project.get("deliverables", [])[:6]:
            _kc_projects.add_test_case(
                project_id,
                f"Deliverable: {deliverable.get('type') or 'asset'} {deliverable.get('format') or ''}".strip(),
                script_id="media_center_simulation",
                owner="seven",
            )
    except Exception:
        pass


def _extract_topics(project: dict[str, Any]) -> list[str]:
    corpus = " ".join(
        str(project.get(key) or "")
        for key in ("name", "prompt", "style", "medium")
    )
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", corpus.lower())
    topics = []
    for word in words:
        if word in _MEDIA_STOP_WORDS:
            continue
        if word not in topics:
            topics.append(word)
    if "music" not in topics and project.get("medium") in ("music", "audio-video"):
        topics.append("music")
    if "video" not in topics and project.get("medium") in ("video", "audio-video"):
        topics.append("video")
    return topics[:8]


def _sync_interests(project: dict[str, Any], username: str = "ghost") -> bool:
    topics = _extract_topics(project)
    if not topics:
        return False
    changed = False
    conn = get_connection()
    try:
        for topic in topics:
            category = _interest_category(topic)
            before = conn.execute(
                "SELECT id FROM user_interests WHERE username=? AND topic=?",
                (username, topic),
            ).fetchone()
            conn.execute(
                "INSERT INTO user_interests (username, topic, category, source, source_agent, score, active) "
                "VALUES (?, ?, ?, 'media_center', 'media-center', 8.0, 1) "
                "ON CONFLICT(username, topic) DO UPDATE SET "
                "category=excluded.category, "
                "source='media_center', "
                "source_agent='media-center', "
                "score=MAX(score, 8.0), "
                "active=1, "
                "updated_at=datetime('now')",
                (username, topic, category),
            )
            if before is None:
                changed = True
        conn.commit()
    finally:
        conn.close()
    return changed


def _interest_category(topic: str) -> str:
    if topic in {"music", "video", "design", "photography"}:
        return "creative"
    if topic in {"python", "ffmpeg", "ai", "machine", "model", "audio-design"}:
        return "tech"
    return "general"


def _media_interest_context(projects: list[dict[str, Any]], username: str = "ghost") -> dict[str, Any]:
    project_topics = []
    for project in projects[:6]:
        for topic in _extract_topics(project):
            if topic not in project_topics:
                project_topics.append(topic)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT topic, category, score, source, source_agent "
            "FROM user_interests WHERE username=? AND active=1 "
            "ORDER BY score DESC, updated_at DESC LIMIT 20",
            (username,),
        ).fetchall()
    finally:
        conn.close()
    relevant = []
    for row in rows:
        topic = row["topic"] if hasattr(row, "keys") else row[0]
        if project_topics and topic.lower() not in project_topics and topic.lower() not in {"music", "video", "audio", "design"}:
            continue
        relevant.append({
            "topic": topic,
            "category": row["category"] if hasattr(row, "keys") else row[1],
            "score": row["score"] if hasattr(row, "keys") else row[2],
            "source": row["source"] if hasattr(row, "keys") else row[3],
            "source_agent": row["source_agent"] if hasattr(row, "keys") else row[4],
        })
    return {
        "project_topics": project_topics[:10],
        "relevant": relevant[:10],
    }


def _media_feed_context(interest_context: dict[str, Any]) -> dict[str, Any]:
    subscriptions = _feeds.list_subscriptions("seven")
    topics = [str(item.get("topic") or "").lower() for item in interest_context.get("relevant", [])]
    topics.extend([str(t).lower() for t in interest_context.get("project_topics", [])])
    suggestions = []
    if any(t in topics for t in ("music", "audio", "soundtrack", "synth", "video", "design")):
        suggestions.extend([
            {"kind": "youtube", "title": "YouTube creative pipeline feeds", "reason": "Good source for music/video workflow updates."},
            {"kind": "reddit", "title": "Reddit creator communities", "reason": "Useful for visualizer, FFmpeg, and local model tips."},
        ])
    if any(t in topics for t in ("python", "ffmpeg", "ai", "model")):
        suggestions.extend([
            {"kind": "github", "title": "GitHub releases / repos", "reason": "Track local model and tooling updates."},
            {"kind": "rss", "title": "Custom RSS for model releases", "reason": "Bring specific media toolchains into the swarm."},
        ])
    return {
        "subscriptions": subscriptions[:10],
        "suggestions": suggestions[:6],
    }


def _media_spine_context() -> dict[str, Any]:
    items = _trace_log.list_events(
        limit=12,
        kinds=["ticket", "testlab", "checkpoint", "system"],
        min_severity="info",
    )
    media_items = [
        item for item in items
        if str(item.get("source") or "").startswith("media")
        or str(item.get("message") or "").lower().startswith("media ")
    ]
    return {"items": media_items[:8]}


def _media_studio_context(projects: list[dict[str, Any]]) -> dict[str, Any]:
    project_links = []
    for project in projects[:10]:
        project_links.append({
            "id": project.get("id"),
            "name": project.get("name"),
            "studio_project_id": project.get("studio_project_id"),
            "status": project.get("status"),
        })
    return {"linked_projects": project_links}
