"""Media Center framework helpers.

Provides a lightweight persisted state store for the Media Center tile so the
UI can manage projects, queue jobs, and test a local-first generation pipeline
before real audio/video runners are connected.
"""

from __future__ import annotations

import copy
import json
import math
import re
import shutil
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from uuid import uuid4

import requests

from core.knowledge import projects as _kc_projects
from core.knowledge import test_runs as _kc_runs
from core import feeds as _feeds
from core import spine as _spine
from utils.db import knowledge as _knowledge
from utils.db import nodes as _nodes
from utils.db import registry as _registry
from utils.swarm_root import SWARM_ROOT
from utils.db import trace_log as _trace_log
from utils.db._connection import get_connection

_STATE_PATH = Path(SWARM_ROOT) / "sandpits" / "shared" / "media_center_state.json"
_ARTIFACT_ROOT = Path(SWARM_ROOT) / "artifacts" / "media_center"
_LOCAL_TIMEOUT = 1.5
_MEDIA_STOP_WORDS = {
    "the", "and", "with", "into", "from", "that", "this", "build", "make",
    "video", "music", "audio", "visual", "media", "project", "for", "your",
    "have", "just", "will", "then", "them", "high", "short", "long",
}

_TRACKING_PROJECT_NAME = "Media Center + Studio Integration"
_TRACKING_PROJECT_DESCRIPTION = (
    "Internal Fridays project for Media Center becoming a Studio-linked DAW-first "
    "music/video editor with research docks, Knowledge Center memory, reviewable layout, "
    "chat actions, project tracking, test cases, advisor roles, linked accounts, feeds, "
    "models, and swarm federation."
)

_TRACKING_STEPS = [
    (
        "DAW-first workspace review",
        "Keep the composer/editor surface as the dominant default view and push research, review, runtime, and routing into supporting docks.",
    ),
    (
        "Transport and command bar review",
        "Make sure New Project, Research, Queue Audio, Queue Video, Render/Compile, Route, Save Handoff, and Open Project Plan stay reachable without hunting.",
    ),
    (
        "Research dock usefulness review",
        "Check that references, accounts, feeds, knowledge docs, routing, and advisor roles are all one click away without overpowering the editor.",
    ),
    (
        "Bottom review dock review",
        "Keep queue, Studio review plan, runtime scan, and handoff visibility beneath the editor so the workflow reads compose -> research -> queue -> route -> review -> handoff.",
    ),
    (
        "Composition and scene workflow",
        "Verify that clips, scene markers, synth takes, and references can all be staged from the editor surface.",
    ),
    (
        "Knowledge Center composition seeding",
        "Seed Fridays composition and render handoff guidance so the right dock and Knowledge Center teach music/video workflow instead of just storing artifacts.",
    ),
    (
        "Advisor workflow review",
        "Expose agents 10, 17, and 19 as assistive advisors for composition structure, production workflow, and critique/review loops.",
    ),
    (
        "Studio project linkage",
        "Keep every media project linked to Studio Projects so review steps, test cases, and verification runs stay attached to the editor workspace.",
    ),
    (
        "Knowledge provenance and feeds",
        "Link media accounts and feeds, then index imported/generated assets with provenance and interest signals.",
    ),
    (
        "Routing and federation readiness",
        "Advertise which local models, remote swarms, and connected agents can contribute to the media pipeline without taking over the composer.",
    ),
    (
        "Chat and local-agent flow checks",
        "Keep media chat intents, local-agent dispatch, and sequential media workflows readable and stable during editor-driven use.",
    ),
]

_TRACKING_CASES = [
    ("Media Center opens as a DAW-first editor with a dominant composer surface", "pytest:media-center-daw-layout"),
    ("Transport bar exposes New Project, Research, Queue Audio, Queue Video, Render/Compile, Route, Save Handoff, and Open Project Plan", "pytest:media-center-transport"),
    ("Research Center renders references, accounts, feeds, knowledge docs, routing, and advisor roles as dock tabs", "pytest:media-center-research-dock"),
    ("Bottom review dock keeps queue, Studio review plan, runtime, and handoff visible beneath the editor", "pytest:media-center-review-dock"),
    ("Media Center review plan is visible inside Studio Projects tracking", "pytest:media-center-studio-review"),
    ("Media Center state exposes Projects, Chat, model, swarm, feeds, interests, spine, advisors, and Knowledge project docs", "pytest:media-center-state"),
    ("Media project creates and updates linked Studio project tracking", "pytest:media-center-project-sync"),
    ("Media Center panes remain resizable and persist user sizing", "pytest:media-center-resize"),
    ("Chat action intents can open Media Center and Studio Projects", "pytest:chat-actions-media-projects"),
    ("Media project timeline lanes, clips, and synth takes can be edited through the API", "pytest:media-center-editor"),
    ("Linked feeds/accounts preserve source provenance for Knowledge indexing", "pytest:media-center-knowledge-provenance"),
    ("Advisor roles 10, 17, and 19 are exposed for composition, production, and critique guidance", "pytest:media-center-advisors"),
    ("Remote swarms and enabled models are visible to the media pipeline", "pytest:media-center-federation"),
]

_FRIDAYS_KNOWLEDGE_DOCS = [
    (
        "FRIDAYS_MUSIC_WORKFLOW.md",
        "media,knowledge,fridays,music",
        """# Fridays music workflow

Fridays creates music in Media Center through a project-first flow.

1. Open Media Center and create or select a project.
2. Set the prompt, style, duration, and medium. Use `Music only` or `Audio + video` when the track is part of a larger teaser.
3. Build the structure in `Active Project Graph`:
- scenes define the arc
- audio lanes define stems and synth takes
- deliverables define the final WAV or preview target
4. Review `Model / Swarm Routing` to decide whether music should stay local or be handed to a specific agent or linked swarm.
5. Queue the work from the graph instead of freehand chatting the runner:
- `Queue audio` for stems, beds, or synth passes
- `Queue compile` when the project is ready to render a joined output
6. Use `Signals & Inputs` to attach references, feeds, and linked accounts so provenance is preserved in Knowledge Center.
7. Review the linked Studio Project for open tasks, test cases, and tracking before promotion.

Mental model:
brief -> graph -> queue -> route -> review -> export
""",
    ),
    (
        "FRIDAYS_VIDEO_WORKFLOW.md",
        "media,knowledge,fridays,video",
        """# Fridays video workflow

Fridays builds video projects in the same workspace as music so timing, references, and provenance stay connected.

1. Create a Media Center project and choose `Video only` or `Audio + video`.
2. Add scenes for the story beats you want to cover.
3. Use the timeline lanes for clips, overlays, captions, and generated visuals.
4. Add media references in `Signals & Inputs` so source links and notes get indexed into Knowledge Center.
5. Review `Model / Swarm Routing`:
- choose a video agent if one should own the generation
- choose a linked swarm if the work should move off-node
- keep `local-first` when ffmpeg/local tools should stay in charge
6. Queue `video` or `compile` jobs from Media Center so the run is tracked in Studio Projects and Test Lab.
7. Check Studio Projects for the linked review plan and test cases before treating the output as done.

Use Media Center for creation and arrangement, Studio Projects for planning and verification, and Knowledge Center for the reusable how-to/reference layer.
""",
    ),
    (
        "FRIDAYS_COMPOSITION_HEURISTICS.md",
        "media,knowledge,fridays,music,composition",
        """# Fridays composition heuristics

Use this when shaping music inside Media Center.

1. Start with sections before sound design.
- intro: what is the mood and what should the first 4 to 8 seconds promise
- lift: where does the energy rise or the harmony widen
- hook: what is the memorable moment
- release: how do you let the track breathe or resolve
2. Give each lane one clear job.
- music stems carry harmony, pulse, bass, or texture
- synth takes are experiments or alternates
- reference markers tell the team why a move exists
- video/cut markers protect timing against visual edits
3. Write prompts that mention:
- tempo / pacing
- instrumentation or texture
- emotional arc
- transition or arrangement intent
4. Keep references attached to the project so provenance stays visible in Knowledge Center.
5. Route only when needed. Stay local-first when the work is still exploratory.
6. Review in Studio Projects before treating a render as final.
""",
    ),
    (
        "FRIDAYS_RENDER_HANDOFF.md",
        "media,knowledge,fridays,video,render,handoff",
        """# Fridays render and handoff guidance

Media Center should hand work off cleanly.

1. Compose first, then queue.
2. Make sure scenes, lanes, clips, synth takes, and references describe the project clearly.
3. Save routing before delegating.
4. Use the handoff manifest when another agent or swarm node needs the project state.
5. Keep Studio Project steps and test cases attached so review is not lost during delegation.
6. Index important references and outputs into Knowledge Center with provenance notes.
""",
    ),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_project_blueprint() -> dict[str, Any]:
    return {
        "timeline": {
            "tempo_bpm": 120,
            "time_signature": "4/4",
            "lanes": [
                {"id": "lane-scenes", "name": "Scenes / Sections", "kind": "marker", "role": "scene"},
                {"id": "lane-music", "name": "Music Stems", "kind": "audio", "role": "stem"},
                {"id": "lane-synth", "name": "Synth Takes", "kind": "audio", "role": "generated"},
                {"id": "lane-references", "name": "Reference Markers", "kind": "marker", "role": "reference"},
                {"id": "lane-video", "name": "Video / Cut Markers", "kind": "video", "role": "cut"},
                {"id": "lane-captions", "name": "Captions", "kind": "caption", "role": "text"},
            ],
            "clips": [
                {
                    "id": "clip-intro-scene",
                    "lane_id": "lane-scenes",
                    "name": "Intro section",
                    "kind": "marker",
                    "start_sec": 0,
                    "duration_sec": 8,
                    "source": "planned",
                    "prompt": "Set the emotional and visual premise.",
                    "status": "planned",
                },
                {
                    "id": "clip-intro-bed",
                    "lane_id": "lane-music",
                    "name": "Intro score bed",
                    "kind": "audio",
                    "start_sec": 0,
                    "duration_sec": 8,
                    "source": "planned",
                    "prompt": "Percussive pulse with luminous pads.",
                    "status": "planned",
                },
                {
                    "id": "clip-intro-visual",
                    "lane_id": "lane-video",
                    "name": "Intro visual pass",
                    "kind": "video",
                    "start_sec": 0,
                    "duration_sec": 8,
                    "source": "planned",
                    "prompt": "Fast-cut system visuals with bright UI motion.",
                    "status": "planned",
                },
            ],
        },
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
        "synth_registry": list_synths(),
        "media_accounts": list_media_accounts(),
    }


def _ensure_state_file() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STATE_PATH.exists():
        _STATE_PATH.write_text(json.dumps(_default_state(), indent=2), encoding="utf-8")


def load_state() -> dict[str, Any]:
    _ensure_state_file()
    _seed_media_center_knowledge_docs()
    try:
        raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("state root must be an object")
        raw.setdefault("projects", [])
        raw.setdefault("jobs", [])
        raw.setdefault("presets", list_presets())
        raw.setdefault("synth_registry", list_synths())
        raw.setdefault("media_accounts", list_media_accounts())
        changed = False
        for project in raw["projects"]:
            if _ensure_project_editor_defaults(project):
                changed = True
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


def _seed_media_center_knowledge_docs() -> None:
    """Keep Fridays music/video how-to docs visible in Knowledge Center."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_name TEXT NOT NULL,
                content TEXT DEFAULT '',
                tags TEXT DEFAULT 'all',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        for doc_name, tags, content in _FRIDAYS_KNOWLEDGE_DOCS:
            row = conn.execute(
                "SELECT id FROM project_docs WHERE doc_name=?",
                (doc_name,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                    (content, tags, row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                    (doc_name, content, tags),
                )
        conn.commit()
    finally:
        conn.close()


def _ensure_project_editor_defaults(project: dict[str, Any]) -> bool:
    changed = False
    blueprint = _default_project_blueprint()
    for key in ("tracks", "scenes", "deliverables"):
        if not isinstance(project.get(key), list):
            project[key] = copy.deepcopy(blueprint[key])
            changed = True
    timeline = project.get("timeline")
    if not isinstance(timeline, dict):
        project["timeline"] = copy.deepcopy(blueprint["timeline"])
        return True
    if not isinstance(timeline.get("lanes"), list) or not timeline.get("lanes"):
        timeline["lanes"] = copy.deepcopy(blueprint["timeline"]["lanes"])
        changed = True
    if not isinstance(timeline.get("clips"), list):
        timeline["clips"] = copy.deepcopy(blueprint["timeline"]["clips"])
        changed = True
    timeline.setdefault("tempo_bpm", blueprint["timeline"]["tempo_bpm"])
    timeline.setdefault("time_signature", blueprint["timeline"]["time_signature"])
    existing_ids = {str(item.get("id") or "") for item in timeline.get("lanes", [])}
    for lane in blueprint["timeline"]["lanes"]:
        lane_id = str(lane.get("id") or "")
        if lane_id and lane_id not in existing_ids:
            timeline["lanes"].append(copy.deepcopy(lane))
            changed = True
    if not isinstance(project.get("synth_runs"), list):
        project["synth_runs"] = []
        changed = True
        if not isinstance(project.get("media_refs"), list):
            project["media_refs"] = []
            changed = True
    if not isinstance(project.get("artifacts"), list):
        project["artifacts"] = []
        changed = True
    if not isinstance(project.get("routing"), dict):
        project["routing"] = {
            "music_agent": "",
            "video_agent": "",
            "swarm_node_id": "",
            "handoff_mode": "local-first",
        }
        changed = True
    return changed


def list_media_accounts() -> list[dict[str, Any]]:
    return [
        {
            "id": "youtube",
            "name": "YouTube",
            "kind": "video",
            "status": "available",
            "feed_kind": "youtube",
            "provenance": ["channel", "playlist", "video_url"],
        },
        {
            "id": "youtube-music",
            "name": "YouTube Music",
            "kind": "music",
            "status": "available",
            "feed_kind": "youtube",
            "provenance": ["artist", "album", "track_url"],
        },
        {
            "id": "spotify",
            "name": "Spotify",
            "kind": "music",
            "status": "pending_auth",
            "feed_kind": "rss",
            "provenance": ["artist", "playlist", "track_url"],
        },
        {
            "id": "apple-music",
            "name": "Apple Music",
            "kind": "music",
            "status": "pending_auth",
            "feed_kind": "rss",
            "provenance": ["artist", "playlist", "track_url"],
        },
        {
            "id": "soundcloud",
            "name": "SoundCloud",
            "kind": "music",
            "status": "available",
            "feed_kind": "rss",
            "provenance": ["creator", "track_url"],
        },
        {
            "id": "bandcamp",
            "name": "Bandcamp",
            "kind": "music",
            "status": "available",
            "feed_kind": "rss",
            "provenance": ["artist", "release", "track_url"],
        },
        {
            "id": "custom-feed",
            "name": "Custom RSS / Feed",
            "kind": "feed",
            "status": "available",
            "feed_kind": "rss",
            "provenance": ["feed_url", "item_url"],
        },
        {
            "id": "local-folder",
            "name": "Local Folder",
            "kind": "local",
            "status": "local",
            "feed_kind": "filesystem",
            "provenance": ["path", "mtime", "checksum"],
        },
    ]


def list_synths() -> list[dict[str, Any]]:
    return [
        {
            "id": "local-tone",
            "name": "Local Tone Synth",
            "kind": "audio",
            "lane_kind": "audio",
            "runner_key": "local_synth_audio_runner",
            "status": "available",
            "capabilities": ["tone", "placeholder", "wav"],
            "model_hint": "python-wave",
        },
        {
            "id": "ffmpeg-visualizer",
            "name": "FFmpeg Visualizer",
            "kind": "video",
            "lane_kind": "video",
            "runner_key": "local_ffmpeg_video_runner",
            "status": "available" if shutil.which("ffmpeg") else "needs_ffmpeg",
            "capabilities": ["testsrc", "sine", "mp4"],
            "model_hint": "ffmpeg",
        },
        {
            "id": "lmstudio-prompt",
            "name": "LM Studio Prompt Synth",
            "kind": "prompt",
            "lane_kind": "audio",
            "runner_key": "lmstudio_prompt_synth",
            "status": "available" if _service_up("http://127.0.0.1:1234/v1/models") else "offline",
            "capabilities": ["prompt", "lyrics", "arrangement"],
            "model_hint": "lmstudio",
        },
        {
            "id": "remote-swarm-render",
            "name": "Remote Swarm Render",
            "kind": "federated",
            "lane_kind": "video",
            "runner_key": "remote_swarm_render",
            "status": "ready_when_linked",
            "capabilities": ["delegate", "render", "model"],
            "model_hint": "node-registry",
        },
    ]


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


def add_timeline_clip(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    for project in state["projects"]:
        if project.get("id") != project_id:
            continue
        _ensure_project_editor_defaults(project)
        timeline = project.setdefault("timeline", {})
        lanes = timeline.setdefault("lanes", [])
        clips = timeline.setdefault("clips", [])
        lane_id = str(payload.get("lane_id") or "").strip()
        if not lane_id or not any(lane.get("id") == lane_id for lane in lanes):
            lane_id = lanes[0]["id"] if lanes else "lane-music"
        lane = next((item for item in lanes if item.get("id") == lane_id), {})
        try:
            start_sec = max(0.0, float(payload.get("start_sec") or 0))
        except Exception:
            start_sec = 0.0
        try:
            duration_sec = max(0.25, float(payload.get("duration_sec") or 4))
        except Exception:
            duration_sec = 4.0
        clip = {
            "id": f"clip-{uuid4().hex[:10]}",
            "lane_id": lane_id,
            "name": str(payload.get("name") or "Untitled clip").strip()[:120],
            "kind": str(payload.get("kind") or lane.get("kind") or "audio").strip()[:40],
            "start_sec": round(start_sec, 3),
            "duration_sec": round(duration_sec, 3),
            "source": str(payload.get("source") or "manual").strip()[:80],
            "prompt": str(payload.get("prompt") or "").strip()[:1000],
            "status": str(payload.get("status") or "planned").strip()[:40],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        clips.append(clip)
        clips.sort(key=lambda item: (float(item.get("start_sec") or 0), str(item.get("lane_id") or "")))
        project["status"] = "editing"
        project["updated_at"] = _now_iso()
        _sync_project_integrations(project)
        save_state(state)
        _spine.log(
            kind=_spine.EventKind.CHECKPOINT,
            message=f"Media timeline clip added: {clip['name']}",
            source="media_center",
            change_id=project_id,
            payload={"project_id": project_id, "clip_id": clip["id"], "lane_id": lane_id},
        )
        return clip
    return None


def create_synth_take(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    synths = state.get("synth_registry") or list_synths()
    synth_id = str(payload.get("synth_id") or "local-tone").strip()
    synth = next((item for item in synths if item.get("id") == synth_id), None) or synths[0]
    for project in state["projects"]:
        if project.get("id") != project_id:
            continue
        _ensure_project_editor_defaults(project)
        timeline = project.setdefault("timeline", {})
        lanes = timeline.setdefault("lanes", [])
        target_kind = synth.get("lane_kind") or synth.get("kind") or "audio"
        lane_id = str(payload.get("lane_id") or "").strip()
        if not lane_id:
            lane = next((item for item in lanes if item.get("kind") == target_kind and item.get("role") == "generated"), None)
            lane = lane or next((item for item in lanes if item.get("kind") == target_kind), None)
            lane_id = (lane or lanes[0]).get("id") if lanes else "lane-synth"
        prompt = str(payload.get("prompt") or project.get("prompt") or "").strip()
        take_id = f"take-{uuid4().hex[:10]}"
        try:
            start_sec = max(0.0, float(payload.get("start_sec") or 0))
        except Exception:
            start_sec = 0.0
        try:
            duration_sec = max(0.25, float(payload.get("duration_sec") or min(8, project.get("duration_sec") or 8)))
        except Exception:
            duration_sec = 8.0
        take = {
            "id": take_id,
            "synth_id": synth.get("id"),
            "synth_name": synth.get("name"),
            "runner_key": synth.get("runner_key"),
            "prompt": prompt[:1000],
            "status": "planned" if synth.get("status") not in {"available", "ready_when_linked"} else "generated",
            "lane_id": lane_id,
            "start_sec": round(start_sec, 3),
            "duration_sec": round(duration_sec, 3),
            "created_at": _now_iso(),
            "artifact_path": "",
        }
        project.setdefault("synth_runs", []).insert(0, take)
        clip = _clip_from_take(take, synth)
        timeline.setdefault("clips", []).append(clip)
        timeline["clips"].sort(key=lambda item: (float(item.get("start_sec") or 0), str(item.get("lane_id") or "")))
        project["status"] = "editing"
        project["updated_at"] = _now_iso()
        job = {
            "id": f"job-{uuid4().hex[:10]}",
            "project_id": project_id,
            "project_name": project.get("name"),
            "job_type": f"synth:{synth.get('id')}",
            "mode": "manifest",
            "status": take["status"],
            "engine": str(synth.get("runner_key") or synth.get("name") or "synth"),
            "notes": prompt[:500] or f"Queued {synth.get('name')} take.",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "artifacts": [{"label": "Timeline take", "path": clip["id"], "status": take["status"]}],
        }
        state.setdefault("jobs", []).insert(0, job)
        _sync_project_integrations(project)
        save_state(state)
        _spine.log(
            kind=_spine.EventKind.TESTLAB,
            message=f"Media synth take created: {synth.get('name')}",
            source="media_center",
            change_id=project_id,
            payload={"project_id": project_id, "take_id": take_id, "synth_id": synth.get("id"), "clip_id": clip["id"]},
        )
        result = dict(take)
        result["clip"] = clip
        result["job"] = job
        return result
    return None


def add_media_reference(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    accounts = state.get("media_accounts") or list_media_accounts()
    detected = _detect_media_reference(payload)
    account_id = str(
        payload.get("account_id")
        or payload.get("provider")
        or detected.get("account_id")
        or "custom-feed"
    ).strip()
    account = next((item for item in accounts if item.get("id") == account_id), None)
    if not account:
        account = next((item for item in accounts if item.get("id") == "custom-feed"), accounts[0])
        account_id = str(account.get("id") or "custom-feed")
    for project in state["projects"]:
        if project.get("id") != project_id:
            continue
        _ensure_project_editor_defaults(project)
        title = str(payload.get("title") or detected.get("title") or "Untitled media reference").strip()[:160]
        url = str(payload.get("url") or payload.get("link") or "").strip()[:1000]
        media_type = str(payload.get("media_type") or detected.get("media_type") or account.get("kind") or "media").strip()[:40]
        notes = str(payload.get("notes") or payload.get("summary") or "").strip()[:2000]
        tags = _normalize_tags(payload.get("tags"), project)
        for tag in detected.get("tags") or []:
            if tag not in tags:
                tags.append(tag)
        reference = {
            "id": f"ref-{uuid4().hex[:10]}",
            "title": title,
            "account_id": account_id,
            "account_name": account.get("name") or account_id,
            "media_type": media_type,
            "url": url,
            "embed_url": detected.get("embed_url") or "",
            "preview_kind": detected.get("preview_kind") or "link",
            "source_id": detected.get("source_id") or "",
            "canonical_url": detected.get("canonical_url") or url,
            "notes": notes,
            "tags": tags[:10],
            "status": "indexed",
            "provenance": {
                "source": "media_center",
                "provider": account_id,
                "feed_kind": account.get("feed_kind"),
                "linked_account_status": account.get("status"),
                "detected_provider": detected.get("account_id") or "",
            },
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        project.setdefault("media_refs", []).insert(0, reference)
        project["updated_at"] = _now_iso()
        _write_media_reference_knowledge(project, reference)
        _write_studio_reference_evidence(project, reference)
        _sync_project_integrations(project)
        save_state(state)
        _spine.log(
            kind=_spine.EventKind.CHECKPOINT,
            message=f"Media reference indexed: {reference['title']}",
            source="media_center",
            change_id=project_id,
            payload={"project_id": project_id, "reference_id": reference["id"], "provider": account_id},
        )
        return reference
    return None


def _detect_media_reference(payload: dict[str, Any]) -> dict[str, Any]:
    url = str(payload.get("url") or payload.get("link") or "").strip()
    if not url:
        return {}
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")
    title = str(payload.get("title") or "").strip()

    if host in {"youtu.be", "youtube.com", "m.youtube.com", "music.youtube.com"}:
        video_id = path.split("/", 1)[0] if host == "youtu.be" else ""
        if not video_id:
            if path.startswith("watch"):
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif path.startswith(("shorts/", "embed/")):
                video_id = path.split("/", 1)[1].split("/", 1)[0]
        if video_id:
            return {
                "account_id": "youtube",
                "media_type": "video",
                "preview_kind": "embed",
                "source_id": video_id,
                "embed_url": f"https://www.youtube.com/embed/{video_id}",
                "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
                "title": title or "YouTube reference",
                "tags": ["youtube", "video"],
            }

    if host == "music.apple.com":
        embed_path = parsed.path
        return {
            "account_id": "apple-music",
            "media_type": "music",
            "preview_kind": "embed",
            "source_id": path.rsplit("/", 1)[-1],
            "embed_url": f"https://embed.music.apple.com{embed_path}",
            "canonical_url": url,
            "title": title or "Apple Music reference",
            "tags": ["apple-music", "music"],
        }

    if host == "open.spotify.com":
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            kind, source_id = parts[0], parts[1]
            return {
                "account_id": "spotify",
                "media_type": "music",
                "preview_kind": "embed",
                "source_id": source_id,
                "embed_url": f"https://open.spotify.com/embed/{kind}/{source_id}",
                "canonical_url": url,
                "title": title or "Spotify reference",
                "tags": ["spotify", kind],
            }

    if host.endswith("soundcloud.com"):
        return {
            "account_id": "soundcloud",
            "media_type": "music",
            "preview_kind": "embed",
            "source_id": path,
            "embed_url": "https://w.soundcloud.com/player/?url=" + quote_plus(url),
            "canonical_url": url,
            "title": title or "SoundCloud reference",
            "tags": ["soundcloud", "music"],
        }

    return {
        "account_id": "custom-feed",
        "media_type": "media",
        "preview_kind": "link",
        "canonical_url": url,
        "title": title or parsed.netloc or "Media reference",
        "tags": ["media-link"],
    }


def link_media_account(account_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    payload = payload or {}
    state = load_state()
    accounts = state.setdefault("media_accounts", list_media_accounts())
    account = next((item for item in accounts if item.get("id") == account_id), None)
    if not account:
        return None
    feed_kind = str(account.get("feed_kind") or "rss")
    url = str(payload.get("url") or payload.get("handle") or f"account://{account_id}").strip()
    title = str(payload.get("title") or account.get("name") or account_id).strip()
    if feed_kind == "filesystem":
        account["status"] = "local"
        account["linked_at"] = _now_iso()
        account["source"] = url
        sub_id = ""
    else:
        try:
            sub_id = _feeds.add_subscription(
                feed_kind,
                url,
                title=title,
                owner="seven",
                status="pending" if feed_kind not in {"rss", "atom"} else "pending",
            )
        except Exception:
            sub_id = ""
        account["status"] = "linked" if sub_id else "pending_auth"
        account["subscription_id"] = sub_id
        account["source"] = url
        account["linked_at"] = _now_iso()
    state["updated_at"] = _now_iso()
    save_state(state)
    _spine.log(
        kind=_spine.EventKind.CHECKPOINT,
        message=f"Media account linked: {account.get('name')}",
        source="media_center",
        change_id=account_id,
        payload={"account_id": account_id, "subscription_id": sub_id, "feed_kind": feed_kind},
    )
    return dict(account)


def update_project_routing(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    model_names = {item.get("agent") for item in _media_model_context().get("agents", [])}
    node_ids = {item.get("node_id") for item in _media_swarm_context().get("nodes", [])}
    for project in state["projects"]:
        if project.get("id") != project_id:
            continue
        _ensure_project_editor_defaults(project)
        routing = project.setdefault("routing", {})
        for key in ("music_agent", "video_agent"):
            if key in payload:
                value = str(payload.get(key) or "").strip()
                routing[key] = value if not value or value in model_names else routing.get(key, "")
        if "swarm_node_id" in payload:
            value = str(payload.get("swarm_node_id") or "").strip()
            routing["swarm_node_id"] = value if not value or value in node_ids else routing.get("swarm_node_id", "")
        if "handoff_mode" in payload:
            mode = str(payload.get("handoff_mode") or "local-first").strip()
            if mode in {"local-first", "swarm-assisted", "model-directed"}:
                routing["handoff_mode"] = mode
        routing["updated_at"] = _now_iso()
        project["updated_at"] = _now_iso()
        _sync_project_integrations(project)
        save_state(state)
        _spine.log(
            kind=_spine.EventKind.CHECKPOINT,
            message=f"Media routing updated: {project.get('name')}",
            source="media_center",
            change_id=project_id,
            payload={"project_id": project_id, "routing": routing},
        )
        return routing
    return None


def project_handoff_manifest(project_id: str) -> dict[str, Any] | None:
    state = load_state()
    payload = public_state()
    project = next((item for item in payload.get("projects", []) if item.get("id") == project_id), None)
    if not project:
        return None
    timeline = project.get("timeline") or {}
    routing = project.get("routing") or {}
    refs = project.get("media_refs") or []
    synth_runs = project.get("synth_runs") or []
    manifest = {
        "schema": "fridays.media_center.handoff.v1",
        "generated_at": _now_iso(),
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "medium": project.get("medium"),
            "status": project.get("status"),
            "style": project.get("style"),
            "duration_sec": project.get("duration_sec"),
            "prompt": project.get("prompt"),
            "studio_project_id": project.get("studio_project_id"),
        },
        "routing": {
            "handoff_mode": routing.get("handoff_mode") or "local-first",
            "music_agent": routing.get("music_agent") or "",
            "video_agent": routing.get("video_agent") or "",
            "swarm_node_id": routing.get("swarm_node_id") or "",
        },
        "timeline": {
            "tempo_bpm": timeline.get("tempo_bpm"),
            "time_signature": timeline.get("time_signature"),
            "lanes": timeline.get("lanes") or [],
            "clips": timeline.get("clips") or [],
        },
        "inputs": {
            "references": [
                {
                    "id": ref.get("id"),
                    "title": ref.get("title"),
                    "account_id": ref.get("account_id"),
                    "media_type": ref.get("media_type"),
                    "url": ref.get("url"),
                    "tags": ref.get("tags") or [],
                    "knowledge_status": ref.get("knowledge_status") or ref.get("status"),
                }
                for ref in refs[:20]
            ],
            "interests": payload.get("interests", {}).get("project_topics", []),
            "feeds": [
                {
                    "sub_id": feed.get("sub_id"),
                    "kind": feed.get("kind"),
                    "title": feed.get("title"),
                    "url": feed.get("url"),
                    "status": feed.get("status"),
                }
                for feed in payload.get("feeds", {}).get("subscriptions", [])[:20]
            ],
        },
        "generation": {
            "synth_registry": payload.get("synths", {}).get("registry", []),
            "recent_takes": synth_runs[:12],
            "jobs": [
                job for job in state.get("jobs", [])
                if job.get("project_id") == project_id
            ][:12],
        },
        "federation": {
            "models": payload.get("models", {}).get("agents", []),
            "linked_swarms": payload.get("linked_swarms", {}).get("nodes", []),
        },
        "instructions": [
            "Preserve provenance for imported references and generated clips.",
            "Use the routing block to choose local model, remote swarm, or model-directed handoff.",
            "Write generated outputs back as timeline clips, synth takes, jobs, and Knowledge-indexed references.",
        ],
    }
    return manifest


def _clip_from_take(take: dict[str, Any], synth: dict[str, Any]) -> dict[str, Any]:
    kind = str(synth.get("lane_kind") or synth.get("kind") or "audio")
    return {
        "id": f"clip-{take['id']}",
        "lane_id": take.get("lane_id") or "lane-synth",
        "name": f"{synth.get('name') or 'Synth'} take",
        "kind": "audio" if kind == "prompt" else kind,
        "start_sec": take.get("start_sec") or 0,
        "duration_sec": take.get("duration_sec") or 4,
        "source": f"synth:{synth.get('id')}",
        "prompt": take.get("prompt") or "",
        "status": take.get("status") or "planned",
        "take_id": take.get("id"),
        "created_at": take.get("created_at") or _now_iso(),
        "updated_at": take.get("created_at") or _now_iso(),
    }


def _normalize_tags(raw_tags: Any, project: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    if isinstance(raw_tags, str):
        pieces = re.split(r"[,#\s]+", raw_tags)
    elif isinstance(raw_tags, list):
        pieces = [str(item) for item in raw_tags]
    else:
        pieces = []
    pieces.extend(_extract_topics(project)[:4])
    for piece in pieces:
        tag = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(piece).strip().lower()).strip("-")
        if len(tag) >= 2 and tag not in tags:
            tags.append(tag[:40])
    for fallback in ("media", str(project.get("medium") or "creative").lower()):
        if fallback and fallback not in tags:
            tags.append(fallback[:40])
    return tags[:10]


def _write_media_reference_knowledge(project: dict[str, Any], reference: dict[str, Any]) -> None:
    try:
        content = (
            f"Media reference indexed for project: {project.get('name')}\n"
            f"Reference: {reference.get('title')}\n"
            f"Provider: {reference.get('account_name')} ({reference.get('account_id')})\n"
            f"Type: {reference.get('media_type')}\n"
            f"URL: {reference.get('url') or 'n/a'}\n"
            f"Embed: {reference.get('embed_url') or 'n/a'}\n"
            f"Preview: {reference.get('preview_kind') or 'link'}\n"
            f"Tags: {', '.join(reference.get('tags') or [])}\n\n"
            f"{reference.get('notes') or ''}"
        ).strip()
        key = f"media-ref-{project.get('id')}-{reference.get('id')}"
        _knowledge.write_knowledge(
            key,
            content,
            "media-center",
            source_proposal_id=str(project.get("studio_project_id") or project.get("id") or ""),
            category="fact",
            importance=7,
        )
    except Exception:
        reference["knowledge_status"] = "write_failed"
    else:
        reference["knowledge_status"] = "indexed"


def create_job(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    project = next((p for p in state["projects"] if p.get("id") == project_id), None)
    if not project:
        return None
    job_type = str(payload.get("job_type") or "generate-audio").strip()
    mode = str(payload.get("mode") or "real-local").strip()
    input_reference_id = str(payload.get("reference_id") or payload.get("input_reference_id") or "").strip()
    input_reference = next(
        (ref for ref in project.get("media_refs", []) if ref.get("id") == input_reference_id),
        None,
    )
    job = {
        "id": f"job-{uuid4().hex[:10]}",
        "project_id": project_id,
        "project_name": project.get("name"),
        "job_type": job_type,
        "mode": mode,
        "status": "queued",
        "engine": _job_engine_hint(job_type),
        "notes": str(payload.get("notes") or "Queued from Media Center UI.").strip(),
        "input_reference_id": input_reference_id,
        "input_reference_title": (input_reference or {}).get("title", ""),
        "input_reference_url": (input_reference or {}).get("canonical_url") or (input_reference or {}).get("url", ""),
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


def run_job_real(job_id: str) -> dict[str, Any] | None:
    """Run the first real local Media Center action.

    This intentionally starts small: it renders a playable WAV preview and a
    manifest with only the Python standard library. Rich engines can replace
    this adapter later, but the user-facing loop is already real: queue -> run
    -> artifact -> playback URL -> Studio evidence.
    """
    state = load_state()
    job = next((j for j in state["jobs"] if j.get("id") == job_id), None)
    if not job:
        return None
    project = next((p for p in state["projects"] if p.get("id") == job.get("project_id")), None)
    if not project:
        return None

    artifact_dir = _ARTIFACT_ROOT / str(project.get("id")) / str(job_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    wav_path = artifact_dir / "preview.wav"
    manifest_path = artifact_dir / "manifest.json"
    _render_tone_preview(wav_path, project, job)
    input_reference = next(
        (ref for ref in project.get("media_refs", []) if ref.get("id") == job.get("input_reference_id")),
        None,
    )
    manifest = {
        "schema": "fridays.media_center.artifact.v1",
        "generated_at": _now_iso(),
        "project_id": project.get("id"),
        "studio_project_id": project.get("studio_project_id"),
        "job_id": job_id,
        "job_type": job.get("job_type"),
        "engine": "python-wave-local-preview",
        "source": "real-local-runner",
        "prompt": project.get("prompt") or "",
        "notes": job.get("notes") or "",
        "input_reference": input_reference or {},
        "artifacts": ["preview.wav", "manifest.json"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    artifacts = [
        _artifact_payload("Audio Preview", wav_path, "audio/wav"),
        _artifact_payload("Run Manifest", manifest_path, "application/json"),
    ]
    job["status"] = "completed"
    job["mode"] = "real-local"
    job["engine"] = "python-wave-local-preview"
    job["updated_at"] = _now_iso()
    job["notes"] = "Real local preview rendered. This is a playable artifact, not a simulated completion."
    job["artifacts"] = artifacts
    project["status"] = "ready"
    project["updated_at"] = _now_iso()
    project.setdefault("artifacts", []).insert(0, {
        "id": f"artifact-{uuid4().hex[:10]}",
        "job_id": job_id,
        "label": "Audio Preview",
        "path": str(wav_path.relative_to(SWARM_ROOT)),
        "url": artifacts[0]["url"],
        "mime_type": "audio/wav",
        "status": "ready",
        "created_at": _now_iso(),
    })
    _write_media_artifact_knowledge(project, job, artifacts[0])
    _write_studio_artifact_evidence(project, job, artifacts)
    save_state(state)
    _spine.log(
        kind=_spine.EventKind.CHECKPOINT,
        message=f"Media real local run complete: {job.get('project_name') or job.get('project_id')}",
        source="media_center",
        change_id=job.get("project_id"),
        payload={"job_id": job_id, "artifacts": artifacts},
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


def _render_tone_preview(path: Path, project: dict[str, Any], job: dict[str, Any]) -> None:
    sample_rate = 44100
    duration = min(12.0, max(2.0, float(project.get("duration_sec") or 6) / 12.0))
    prompt = (
        f"{project.get('name') or ''} {project.get('prompt') or ''} "
        f"{job.get('job_type') or ''} {job.get('input_reference_title') or ''} "
        f"{job.get('input_reference_url') or ''}"
    )
    seed = sum(ord(ch) for ch in prompt)
    base_freq = 196 + (seed % 220)
    mod_freq = base_freq * (1.25 if "video" in str(job.get("job_type") or "") else 1.5)
    total = int(sample_rate * duration)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for idx in range(total):
            t = idx / sample_rate
            envelope = min(1.0, idx / (sample_rate * 0.08), (total - idx) / (sample_rate * 0.16))
            pulse = 0.62 * math.sin(2 * math.pi * base_freq * t)
            shimmer = 0.28 * math.sin(2 * math.pi * mod_freq * t)
            beat = 0.10 * math.sin(2 * math.pi * 2.0 * t)
            sample = int(max(-1.0, min(1.0, (pulse + shimmer + beat) * envelope * 0.38)) * 32767)
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(bytes(frames))


def _artifact_payload(label: str, path: Path, mime_type: str) -> dict[str, str]:
    rel = path.relative_to(SWARM_ROOT)
    return {
        "label": label,
        "path": str(rel),
        "url": f"/api/media-center/artifacts/{rel.as_posix()}",
        "mime_type": mime_type,
        "status": "ready",
    }


def _write_media_artifact_knowledge(project: dict[str, Any], job: dict[str, Any], artifact: dict[str, str]) -> None:
    try:
        content = (
            f"Media artifact produced for project: {project.get('name')}\n"
            f"Project ID: {project.get('id')}\n"
            f"Studio project: {project.get('studio_project_id') or 'n/a'}\n"
            f"Job: {job.get('id')} ({job.get('job_type')})\n"
            f"Artifact: {artifact.get('label')} — {artifact.get('path')}\n"
            f"Playback URL: {artifact.get('url')}\n\n"
            f"Prompt: {project.get('prompt') or ''}\n"
            f"Notes: {job.get('notes') or ''}"
        ).strip()
        key = f"media-artifact-{project.get('id')}-{job.get('id')}"
        _knowledge.write_knowledge(
            key,
            content,
            "media-center",
            source_proposal_id=str(project.get("studio_project_id") or project.get("id") or ""),
            category="artifact",
            importance=8,
        )
    except Exception:
        pass


def _write_studio_reference_evidence(project: dict[str, Any], reference: dict[str, Any]) -> None:
    studio_project_id = str(project.get("studio_project_id") or "").strip()
    if not studio_project_id:
        return
    try:
        studio = _kc_projects.get_project(studio_project_id) or {}
        steps = studio.get("steps") or []
        step_id = ""
        for step in steps:
            title = str(step.get("title") or "")
            if title in {"Knowledge provenance and feeds", "Studio project linkage"}:
                step_id = str(step.get("step_id") or "")
                break
        if not step_id and steps:
            step_id = str(steps[0].get("step_id") or "")
        if not step_id:
            return
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO project_step_evidence "
                "(project_id, step_id, source_type, source_ref, summary, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    studio_project_id,
                    step_id,
                    "media_center_reference",
                    str(reference.get("id") or ""),
                    "Media reference indexed: "
                    + str(reference.get("title") or reference.get("url") or reference.get("canonical_url") or ""),
                    "ok",
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _write_studio_artifact_evidence(
    project: dict[str, Any],
    job: dict[str, Any],
    artifacts: list[dict[str, str]],
) -> None:
    studio_project_id = str(project.get("studio_project_id") or "").strip()
    if not studio_project_id:
        return
    try:
        studio = _kc_projects.get_project(studio_project_id) or {}
        steps = studio.get("steps") or []
        step_id = ""
        for step in steps:
            title = str(step.get("title") or "")
            if title.startswith("Deliverable:") or title == "Studio project linkage":
                step_id = str(step.get("step_id") or "")
                break
        if not step_id and steps:
            step_id = str(steps[0].get("step_id") or "")
        if not step_id:
            return
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO project_step_evidence "
                "(project_id, step_id, source_type, source_ref, summary, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    studio_project_id,
                    step_id,
                    "media_center_artifact",
                    str(job.get("id") or ""),
                    "Real Media Center artifact produced: "
                    + ", ".join(str(a.get("path") or a.get("label") or "") for a in artifacts),
                    "ok",
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


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
    tracking_project_id = _ensure_tracking_project(state)
    payload = copy.deepcopy(state)
    payload["runtime"] = summarize_runtime()
    payload["interests"] = _media_interest_context(payload.get("projects", []))
    payload["feeds"] = _media_feed_context(payload["interests"])
    payload["spine"] = _media_spine_context()
    payload["studio"] = _media_studio_context(payload.get("projects", []), tracking_project_id)
    payload["tracking"] = _media_tracking_context(tracking_project_id)
    payload["chat"] = _media_chat_context(payload.get("projects", []))
    payload["models"] = _media_model_context()
    payload["linked_swarms"] = _media_swarm_context()
    payload["synths"] = _media_synth_context(payload)
    payload["accounts"] = _media_accounts_context(payload)
    payload["knowledge"] = _media_knowledge_context(payload)
    payload["routing"] = _media_routing_context(payload)
    payload["advisors"] = _media_advisor_context(payload)
    payload["counts"] = {
        "projects": len(payload.get("projects", [])),
        "queued_jobs": sum(1 for job in payload.get("jobs", []) if job.get("status") == "queued"),
        "completed_jobs": sum(1 for job in payload.get("jobs", []) if job.get("status") == "completed"),
    }
    return payload


def _media_accounts_context(payload: dict[str, Any]) -> dict[str, Any]:
    registry = payload.get("media_accounts") or list_media_accounts()
    linked = [item for item in registry if item.get("status") in {"linked", "available", "local"}]
    auth_needed = [item for item in registry if item.get("status") == "pending_auth"]
    refs_by_provider: dict[str, int] = {}
    for project in payload.get("projects") or []:
        for ref in project.get("media_refs") or []:
            provider = str(ref.get("account_id") or "custom-feed")
            refs_by_provider[provider] = refs_by_provider.get(provider, 0) + 1
    return {
        "registry": registry,
        "linked": linked,
        "auth_needed": auth_needed,
        "references_by_provider": refs_by_provider,
    }


def _media_routing_context(payload: dict[str, Any]) -> dict[str, Any]:
    routes = []
    for project in payload.get("projects") or []:
        routing = project.get("routing") or {}
        if any(routing.get(key) for key in ("music_agent", "video_agent", "swarm_node_id")):
            routes.append({
                "project_id": project.get("id"),
                "project_name": project.get("name"),
                "music_agent": routing.get("music_agent") or "",
                "video_agent": routing.get("video_agent") or "",
                "swarm_node_id": routing.get("swarm_node_id") or "",
                "handoff_mode": routing.get("handoff_mode") or "local-first",
            })
    return {
        "active_routes": routes[:12],
        "default_mode": "local-first",
    }


def _media_knowledge_context(payload: dict[str, Any]) -> dict[str, Any]:
    references = []
    for project in payload.get("projects") or []:
        for ref in (project.get("media_refs") or [])[:8]:
            item = dict(ref)
            item["project_id"] = project.get("id")
            item["project_name"] = project.get("name")
            references.append(item)
    recent_entries = []
    try:
        recent_entries = _knowledge.search_knowledge("media-ref-", category="fact", limit=8)
    except Exception:
        recent_entries = []
    docs: list[dict[str, Any]] = []
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT doc_name, tags FROM project_docs "
            "WHERE doc_name LIKE 'FRIDAYS_%' "
            "ORDER BY doc_name ASC"
        ).fetchall()
        docs = [{"doc_name": row["doc_name"], "tags": row["tags"], "source": "project_docs"} for row in rows]
    except Exception:
        docs = []
    finally:
        conn.close()
    return {
        "references": references[:16],
        "indexed_count": sum(1 for item in references if item.get("knowledge_status") == "indexed"),
        "project_docs": docs,
        "recent_entries": [
            {
                "key": item.get("key"),
                "category": item.get("category"),
                "source_agent": item.get("source_agent"),
                "importance": item.get("importance"),
            }
            for item in recent_entries
        ],
    }


def _media_synth_context(payload: dict[str, Any]) -> dict[str, Any]:
    registry = payload.get("synth_registry") or list_synths()
    projects = payload.get("projects") or []
    recent_takes = []
    for project in projects[:6]:
        for take in (project.get("synth_runs") or [])[:4]:
            item = dict(take)
            item["project_id"] = project.get("id")
            item["project_name"] = project.get("name")
            recent_takes.append(item)
    return {
        "registry": registry,
        "available": [item for item in registry if item.get("status") in {"available", "ready_when_linked"}],
        "recent_takes": recent_takes[:12],
    }


def _ensure_tracking_project(state: dict[str, Any]) -> str:
    project_id = str(state.get("tracking_project_id") or "").strip()
    existing = _kc_projects.get_project(project_id) if project_id else None
    if not existing:
        for project in _kc_projects.list_projects(limit=250):
            if str(project.get("name") or "") == _TRACKING_PROJECT_NAME:
                project_id = str(project.get("project_id") or "")
                existing = _kc_projects.get_project(project_id)
                break
    if not existing:
        project_id = _kc_projects.create_project(
            _TRACKING_PROJECT_NAME,
            description=_TRACKING_PROJECT_DESCRIPTION,
            methodology="mixed",
            owner="seven",
        ) or ""
    if project_id:
        _kc_projects.update_project(
            project_id,
            name=_TRACKING_PROJECT_NAME,
            description=_TRACKING_PROJECT_DESCRIPTION,
            methodology="mixed",
            owner="seven",
            status="active",
        )
        _seed_studio_project(project_id, {
            "name": _TRACKING_PROJECT_NAME,
            "medium": "audio-video",
            "style": "internal roadmap",
            "duration_sec": 0,
            "prompt": _TRACKING_PROJECT_DESCRIPTION,
            "scenes": [],
            "deliverables": [],
        })
    if project_id and state.get("tracking_project_id") != project_id:
        state["tracking_project_id"] = project_id
        state["updated_at"] = _now_iso()
        save_state(state)
    return project_id


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
        _seed_studio_project(project["studio_project_id"], project)
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
        existing = _kc_projects.get_project(project_id) or {}
        existing_steps = {
            str(step.get("title") or "")
            for step in existing.get("steps", [])
        }
        existing_cases = {
            str(case.get("title") or "")
            for case in existing.get("test_cases", [])
        }
        for idx, (title, description) in enumerate(_TRACKING_STEPS):
            if title in existing_steps:
                continue
            _kc_projects.add_step(
                project_id,
                title,
                description=description,
                owner="seven",
                order_idx=idx,
            )
        for scene in media_project.get("scenes", [])[:6]:
            title = f"Scene: {scene.get('name') or 'Untitled'}"
            if title in existing_steps:
                continue
            _kc_projects.add_step(
                project_id,
                title,
                description=(scene.get("goal") or "")[:1000],
                owner="seven",
            )
        for deliverable in media_project.get("deliverables", [])[:6]:
            title = f"Deliverable: {deliverable.get('type') or 'asset'} {deliverable.get('format') or ''}".strip()
            if title in existing_cases:
                continue
            _kc_projects.add_test_case(
                project_id,
                title,
                script_id="media_center_simulation",
                owner="seven",
            )
        for title, script_id in _TRACKING_CASES:
            if title in existing_cases:
                continue
            _kc_projects.add_test_case(
                project_id,
                title,
                script_id=script_id,
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


def _media_studio_context(projects: list[dict[str, Any]], tracking_project_id: str = "") -> dict[str, Any]:
    project_links = []
    for project in projects[:10]:
        project_links.append({
            "id": project.get("id"),
            "name": project.get("name"),
            "studio_project_id": project.get("studio_project_id"),
            "status": project.get("status"),
        })
    return {
        "tracking_project_id": tracking_project_id,
        "tracking_project_name": _TRACKING_PROJECT_NAME if tracking_project_id else "",
        "linked_projects": project_links,
    }


def _media_chat_context(projects: list[dict[str, Any]]) -> dict[str, Any]:
    active = projects[0] if projects else {}
    project_name = active.get("name") or "Media Center"
    return {
        "actions": [
            {
                "phrase": "open media center",
                "intent": "open_window",
                "view": "media-center",
                "template": "view-media-center",
            },
            {
                "phrase": "open projects section",
                "intent": "open_window",
                "view": "studio",
                "template": "view-studio",
            },
            {
                "phrase": "show music editor",
                "intent": "open_window",
                "view": "media-center",
                "template": "view-media-center",
            },
        ],
        "context_hint": (
            f"Media Center active project: {project_name}. "
            "Use Media Center as the composer/editor, Research Center for references and Knowledge, and Studio Projects for tracking/tests."
        ),
    }


def _media_tracking_context(project_id: str) -> dict[str, Any]:
    if not project_id:
        return {"project_id": "", "steps": [], "test_cases": [], "recent_runs": [], "progress": {}}
    tree = _kc_projects.get_project(project_id) or {}
    project = tree.get("project") or {}
    steps = tree.get("steps") or []
    cases = tree.get("test_cases") or []
    runs = _kc_runs.list_runs(project_id=project_id, limit=8)
    done = sum(1 for step in steps if step.get("status") == "done")
    partial = sum(1 for step in steps if step.get("status") == "partial")
    blocked = sum(1 for step in steps if step.get("status") == "blocked")
    passed = sum(1 for run in runs if run.get("status") == _kc_runs.STATUS_PASS)
    failed = sum(1 for run in runs if run.get("status") in {_kc_runs.STATUS_FAIL, _kc_runs.STATUS_ERROR})
    return {
        "project_id": project_id,
        "name": project.get("name") or _TRACKING_PROJECT_NAME,
        "status": project.get("status") or "active",
        "steps": [
            {
                "step_id": step.get("step_id"),
                "title": step.get("title"),
                "status": step.get("status"),
                "owner": step.get("owner"),
            }
            for step in steps
        ],
        "test_cases": [
            {
                "case_id": case.get("case_id"),
                "title": case.get("title"),
                "script_id": case.get("script_id"),
                "status": case.get("status"),
            }
            for case in cases
        ],
        "recent_runs": [
            {
                "run_id": run.get("run_id"),
                "script_id": run.get("script_id"),
                "status": run.get("status"),
                "duration_ms": run.get("duration_ms"),
                "case_id": run.get("case_id"),
                "step_id": run.get("step_id"),
            }
            for run in runs
        ],
        "progress": {
            "step_count": len(steps),
            "done_steps": done,
            "partial_steps": partial,
            "blocked_steps": blocked,
            "case_count": len(cases),
            "recent_passes": passed,
            "recent_failures": failed,
        },
    }


def _media_model_context() -> dict[str, Any]:
    try:
        models = _registry.get_agent_models()
        roster = _registry.get_agent_roster()
    except Exception:
        models = {}
        roster = []
    media_candidates = []
    for agent in roster:
        name = str(agent.get("name") or "")
        role = str(agent.get("role") or "").lower()
        model = str(agent.get("model") or models.get(name) or "")
        haystack = f"{name} {role} {model}".lower()
        if any(term in haystack for term in ("media", "audio", "video", "music", "vision", "local", "lmstudio", "ollama")):
            media_candidates.append({
                "agent": name,
                "label": agent.get("label") or name,
                "model": model,
                "role": agent.get("role") or "",
            })
    return {
        "enabled_count": len(models),
        "agents": media_candidates[:12],
        "registry_source": "utils.db.registry",
    }


def _media_advisor_context(payload: dict[str, Any]) -> dict[str, Any]:
    model_agents = {str(item.get("agent") or ""): item for item in payload.get("models", {}).get("agents", [])}
    roles = [
        {
            "agent_id": "10",
            "title": "Composition Advisor",
            "role": "structure / composition",
            "focus": "Helps shape sections, pacing, arrangement, hooks, and transitions for music-driven projects.",
            "how_to_use": "Use 10 when the track needs form, momentum, or a clearer musical arc before routing generation work.",
        },
        {
            "agent_id": "17",
            "title": "Production Workflow Advisor",
            "role": "implementation / production",
            "focus": "Helps turn scenes, references, and prompts into an executable music/video workflow with lanes, jobs, and handoffs.",
            "how_to_use": "Use 17 when you need help structuring clips, synth takes, queue order, or render handoff decisions.",
        },
        {
            "agent_id": "19",
            "title": "Critique and Review Advisor",
            "role": "critique / next-step refinement",
            "focus": "Helps review what is missing, what clashes, and which next edits would most improve the piece.",
            "how_to_use": "Use 19 after a draft pass when you want critique, revision suggestions, or a stronger review loop.",
        },
    ]
    for role in roles:
        match = model_agents.get(role["agent_id"]) or {}
        role["availability"] = "advertised" if match else "seeded"
        role["model"] = match.get("model") or ""
        role["label"] = match.get("label") or role["title"]
        role["surfaces"] = "Media Center, Studio Projects, Knowledge Center"
    return {"roles": roles}


def _media_swarm_context() -> dict[str, Any]:
    try:
        nodes = _nodes.list_nodes()
    except Exception:
        nodes = []
    linked = []
    for node in nodes[:12]:
        try:
            capabilities = json.loads(node.get("capabilities") or "[]")
        except Exception:
            capabilities = []
        try:
            agents = json.loads(node.get("agents_json") or "[]")
        except Exception:
            agents = []
        linked.append({
            "node_id": node.get("node_id"),
            "name": node.get("name"),
            "url": node.get("url"),
            "role": node.get("role"),
            "capabilities": capabilities,
            "agents": agents,
            "last_seen": node.get("last_seen"),
            "media_relevant": any(
                str(item).lower() in {"media", "audio", "video", "music", "render", "ffmpeg", "model"}
                for item in capabilities
            ),
        })
    return {
        "local_node_id": _nodes.get_local_node_id(),
        "nodes": linked,
        "count": len(linked),
    }
