from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "frontend"))

from terminal import create_app


TEMPLATE = ROOT / "frontend" / "templates" / "terminal_base.html"
STUDIO_JS = ROOT / "frontend" / "static" / "js" / "views" / "studio.js"


def test_studio_template_contains_media_tab_and_panel():
    html = TEMPLATE.read_text()
    assert "studio-tab-media" in html
    assert "studio-media-panel" in html
    assert "Open Media Center" in html
    assert "media-center-resizer" in html
    assert "media-center-transport" in html
    assert "media-editor-shell" in html
    assert "media-center-editor-stage" in html
    assert "media-center-research-body" in html
    assert "media-center-bottom-body" in html


def test_studio_js_knows_media_tab():
    src = STUDIO_JS.read_text()
    assert "const isMedia = (tab === 'media');" in src
    assert "loadStudioMediaPanel" in src


def test_studio_media_panel_links_tracking_project():
    src = (ROOT / "frontend/static/js/views/studio-media.js").read_text()
    assert "Internal Tracking Project" in src
    assert "Remix Lab" in src
    assert "studioMediaCreateRemix" in src
    assert "/api/media/mix-songs" in src
    assert "studioMediaOpenProject" in src
    assert "tracking_project_id" in src


def test_media_center_has_resizable_layout_contract():
    css = (ROOT / "frontend/static/css/views/media-center.css").read_text()
    js = (ROOT / "frontend/static/js/views/media-center.js").read_text()
    assert "--media-center-sidebar-width" in css
    assert ".media-center-resizer" in css
    assert "_mediaCenterWireResizer" in js
    assert "fridays.mediaCenter.sidebarWidth" in js
    assert "mediaCenterTogglePanel" in js
    assert "mediaCenterExpandAll" in js
    assert "mediaCenterCollapseToFocus" in js
    assert "mediaCenterOpenReviewPlan" in js
    assert ".media-panel.is-collapsed .media-panel-body" in css
    assert "position: sticky;" in css
    assert ".media-editor-shell" in css
    assert ".media-composer-surface" in css
    assert ".media-right-dock" in css
    assert "media-bottom-dock" in html_or_css(css)


def html_or_css(css: str) -> str:
    return css + TEMPLATE.read_text()


def test_media_center_context_surfaces_models_swarms_and_chat():
    js = (ROOT / "frontend/static/js/views/media-center.js").read_text()
    html = TEMPLATE.read_text()
    assert "Make playable preview" in html
    assert "Add song or clip" in html
    assert "Play outputs" in html
    assert "Expand all" in html
    assert "Studio trail" in html
    assert "Queue audio only" in html
    assert "Queue video only" in html
    assert "Research Center" in html
    assert "Start here" in js
    assert "mediaCenterMakePreview" in js
    assert "Model / Swarm Routing" in js
    assert "Assistive Advisors" in js
    assert "Linked Swarms" in js
    assert "Studio Review Plan" in js
    assert "mediaCenterAddClip" in js
    assert "mediaCenterCreateSynthTake" in js
    assert "Linked Accounts" in js
    assert "Knowledge Docs" in js
    assert "Project References" in js
    assert "auto-detect" in js
    assert "mediaCenterReferenceCard" in js
    assert "mediaCenterAddReference" in js
    assert "mediaCenterUpdateRouting" in js
    assert "mediaCenterLinkAccount" in js
    assert "mediaCenterRunJob" in js
    assert "Run local" in js
    assert "<audio controls" in js
    assert "Handoff Manifest" in js
    assert "mediaCenterCopyHandoff" in js
    assert "mediaCenterMarkScene" in js


def test_feeds_template_is_server_synced_and_conflict_free():
    src = (ROOT / "frontend/templates/views/feeds.html").read_text()
    assert "<<<<<<<" not in src
    assert ">>>>>>>" not in src
    assert "/api/feeds/subscriptions" in src
    assert "Custom RSS subscriptions persist to the server-side feed store today" in src


def test_media_center_state_exposes_studio_interests_feeds_and_spine():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/api/media-center/state")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "studio" in payload
    assert "interests" in payload
    assert "feeds" in payload
    assert "spine" in payload
    assert "chat" in payload
    assert "models" in payload
    assert "linked_swarms" in payload
    assert "tracking" in payload
    assert "synths" in payload
    assert "accounts" in payload
    assert "knowledge" in payload
    assert "routing" in payload
    assert "advisors" in payload
    assert "linked_projects" in payload["studio"]
    assert "tracking_project_id" in payload["studio"]
    assert "progress" in payload["tracking"]
    assert "recent_runs" in payload["tracking"]
    assert "subscriptions" in payload["feeds"]
    assert "actions" in payload["chat"]
    assert "local_node_id" in payload["linked_swarms"]
    assert payload["projects"][0]["timeline"]["lanes"]
    assert isinstance(payload["projects"][0]["timeline"]["clips"], list)
    assert isinstance(payload["projects"][0]["media_refs"], list)
    assert payload["synths"]["registry"]
    assert payload["accounts"]["registry"]
    assert "references" in payload["knowledge"]
    assert payload["knowledge"]["project_docs"]
    assert payload["advisors"]["roles"]
    assert payload["routing"]["default_mode"] == "local-first"


def test_media_center_state_seeds_fridays_music_and_video_knowledge_docs():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/api/media-center/state")
        assert response.status_code == 200

    from utils.db._connection import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT doc_name, tags, content FROM project_docs "
            "WHERE doc_name IN ("
            "'FRIDAYS_COMPOSITION_HEURISTICS.md', "
            "'FRIDAYS_MUSIC_WORKFLOW.md', "
            "'FRIDAYS_RENDER_HANDOFF.md', "
            "'FRIDAYS_VIDEO_WORKFLOW.md'"
            ") "
            "ORDER BY doc_name ASC"
        ).fetchall()
    finally:
        conn.close()

    assert [row["doc_name"] for row in rows] == [
        "FRIDAYS_COMPOSITION_HEURISTICS.md",
        "FRIDAYS_MUSIC_WORKFLOW.md",
        "FRIDAYS_RENDER_HANDOFF.md",
        "FRIDAYS_VIDEO_WORKFLOW.md",
    ]
    assert "composition" in rows[0]["tags"]
    assert "Start with sections before sound design" in rows[0]["content"]
    assert "music" in rows[1]["tags"]
    assert "Media Center" in rows[1]["content"]
    assert "render" in rows[2]["tags"]
    assert "Save routing before delegating" in rows[2]["content"]
    assert "video" in rows[3]["tags"]
    assert "Studio Projects" in rows[3]["content"]


def test_media_center_adds_timeline_clip_through_api():
    app = create_app()
    with app.test_client() as client:
        state = client.get("/api/media-center/state").get_json()
        project_id = state["projects"][0]["id"]
        lane_id = state["projects"][0]["timeline"]["lanes"][0]["id"]
        response = client.post(
            f"/api/media-center/projects/{project_id}/clips",
            json={
                "name": "pytest editor clip",
                "lane_id": lane_id,
                "start_sec": 1.5,
                "duration_sec": 3.25,
                "prompt": "clip created by integration test",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["clip"]["name"] == "pytest editor clip"
        refreshed = client.get("/api/media-center/state").get_json()

    project = next(item for item in refreshed["projects"] if item["id"] == project_id)
    assert any(clip["id"] == data["clip"]["id"] for clip in project["timeline"]["clips"])


def test_media_center_real_local_run_creates_playable_artifact_and_evidence():
    app = create_app()
    with app.test_client() as client:
        created = client.post(
            "/api/media-center/projects",
            json={
                "name": "pytest real local render",
                "prompt": "render a short usable audio preview",
                "medium": "audio",
                "duration_sec": 12,
            },
        )
        assert created.status_code == 200
        project = created.get_json()["project"]
        queued = client.post(
            f"/api/media-center/projects/{project['id']}/jobs",
            json={"job_type": "generate-audio", "mode": "real-local"},
        )
        assert queued.status_code == 200
        job = queued.get_json()["job"]
        run = client.post(f"/api/media-center/jobs/{job['id']}/run")
        assert run.status_code == 200
        data = run.get_json()
        assert data["ok"] is True
        assert data["job"]["status"] == "completed"
        audio = next(a for a in data["job"]["artifacts"] if a["mime_type"] == "audio/wav")
        assert audio["url"].startswith("/api/media-center/artifacts/artifacts/media_center/")
        artifact_response = client.get(audio["url"])
        assert artifact_response.status_code == 200
        assert artifact_response.data[:4] == b"RIFF"

    from utils.db._connection import get_connection

    conn = get_connection()
    try:
        evidence = conn.execute(
            "SELECT COUNT(*) AS n FROM project_step_evidence "
            "WHERE project_id=? AND source_type='media_center_artifact' AND source_ref=?",
            (project["studio_project_id"], job["id"]),
        ).fetchone()["n"]
    finally:
        conn.close()
    assert evidence >= 1


def test_media_center_creates_synth_take_on_timeline():
    app = create_app()
    with app.test_client() as client:
        state = client.get("/api/media-center/state").get_json()
        project_id = state["projects"][0]["id"]
        synth_id = state["synths"]["registry"][0]["id"]
        lane_id = state["projects"][0]["timeline"]["lanes"][1]["id"]
        response = client.post(
            f"/api/media-center/projects/{project_id}/synth-takes",
            json={
                "synth_id": synth_id,
                "lane_id": lane_id,
                "start_sec": 2,
                "duration_sec": 5,
                "prompt": "pytest synth take",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["take"]["synth_id"] == synth_id
        assert data["take"]["clip"]["take_id"] == data["take"]["id"]
        refreshed = client.get("/api/media-center/state").get_json()

    project = next(item for item in refreshed["projects"] if item["id"] == project_id)
    assert any(take["id"] == data["take"]["id"] for take in project["synth_runs"])
    assert any(clip.get("take_id") == data["take"]["id"] for clip in project["timeline"]["clips"])


def test_media_center_indexes_media_reference_into_knowledge():
    app = create_app()
    with app.test_client() as client:
        state = client.get("/api/media-center/state").get_json()
        project_id = state["projects"][0]["id"]
        account_id = state["accounts"]["registry"][0]["id"]
        response = client.post(
            f"/api/media-center/projects/{project_id}/references",
            json={
                "title": "pytest indexed reference",
                "account_id": account_id,
                "media_type": "video",
                "url": "https://example.invalid/media-ref",
                "notes": "reference created by integration test",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["reference"]["account_id"] == account_id
        assert data["reference"]["knowledge_status"] == "indexed"
        refreshed = client.get("/api/media-center/state").get_json()

    project = next(item for item in refreshed["projects"] if item["id"] == project_id)
    assert any(ref["id"] == data["reference"]["id"] for ref in project["media_refs"])
    assert any(ref["id"] == data["reference"]["id"] for ref in refreshed["knowledge"]["references"])

    from utils.db.knowledge import search_knowledge

    matches = search_knowledge("pytest indexed reference", category="fact", limit=5)
    assert any(item["key"].startswith(f"media-ref-{project_id}-") for item in matches)


def test_media_center_auto_detects_embeddable_media_reference():
    app = create_app()
    with app.test_client() as client:
        state = client.get("/api/media-center/state").get_json()
        project_id = state["projects"][0]["id"]
        response = client.post(
            f"/api/media-center/projects/{project_id}/references",
            json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "notes": "auto-detected reference test",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        ref = data["reference"]
        assert ref["account_id"] == "youtube"
        assert ref["media_type"] == "video"
        assert ref["preview_kind"] == "embed"
        assert ref["source_id"] == "dQw4w9WgXcQ"
        assert ref["embed_url"] == "https://www.youtube.com/embed/dQw4w9WgXcQ"
        refreshed = client.get("/api/media-center/state").get_json()

    project = next(item for item in refreshed["projects"] if item["id"] == project_id)
    saved = next(item for item in project["media_refs"] if item["id"] == ref["id"])
    assert saved["canonical_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert "youtube" in saved["tags"]


def test_media_center_saves_project_model_swarm_route():
    app = create_app()
    with app.test_client() as client:
        state = client.get("/api/media-center/state").get_json()
        project_id = state["projects"][0]["id"]
        response = client.patch(
            f"/api/media-center/projects/{project_id}/routing",
            json={"handoff_mode": "swarm-assisted", "music_agent": "", "video_agent": "", "swarm_node_id": ""},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["routing"]["handoff_mode"] == "swarm-assisted"
        refreshed = client.get("/api/media-center/state").get_json()

    project = next(item for item in refreshed["projects"] if item["id"] == project_id)
    assert project["routing"]["handoff_mode"] == "swarm-assisted"


def test_media_center_links_account_into_feed_store():
    app = create_app()
    with app.test_client() as client:
        response = client.post(
            "/api/media-center/accounts/youtube/link",
            json={"url": "https://www.youtube.com/@pytest", "title": "pytest YouTube"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["account"]["status"] == "linked"
        assert data["account"]["subscription_id"]
        feeds = client.get("/api/feeds/subscriptions").get_json()

    assert any(item["sub_id"] == data["account"]["subscription_id"] for item in feeds["items"])


def test_media_center_exposes_project_handoff_manifest():
    app = create_app()
    with app.test_client() as client:
        state = client.get("/api/media-center/state").get_json()
        project_id = state["projects"][0]["id"]
        response = client.get(f"/api/media-center/projects/{project_id}/handoff")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    manifest = data["manifest"]
    assert manifest["schema"] == "fridays.media_center.handoff.v1"
    assert manifest["project"]["id"] == project_id
    assert "routing" in manifest
    assert "timeline" in manifest
    assert "inputs" in manifest
    assert "generation" in manifest
    assert "federation" in manifest
    assert manifest["instructions"]


def test_media_center_internal_project_is_logged_in_projects_section():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/api/media-center/state")
    assert response.status_code == 200
    payload = response.get_json()
    tracking_project_id = payload["studio"]["tracking_project_id"]
    assert tracking_project_id

    from core.knowledge import projects as kc_projects

    tree = kc_projects.get_project(tracking_project_id)
    assert tree
    assert tree["project"]["name"] == "Media Center + Studio Integration"
    step_titles = {step["title"] for step in tree["steps"]}
    case_titles = {case["title"] for case in tree["test_cases"]}
    assert "DAW-first workspace review" in step_titles
    assert "Research dock usefulness review" in step_titles
    assert "Bottom review dock review" in step_titles
    assert "Knowledge Center composition seeding" in step_titles
    assert "Advisor workflow review" in step_titles
    assert "Chat and local-agent flow checks" in step_titles
    assert "Media Center opens as a DAW-first editor with a dominant composer surface" in case_titles
    assert "Research Center renders references, accounts, feeds, knowledge docs, routing, and advisor roles as dock tabs" in case_titles
    assert "Advisor roles 10, 17, and 19 are exposed for composition, production, and critique guidance" in case_titles
    assert "Media Center review plan is visible inside Studio Projects tracking" in case_titles
    assert "Chat action intents can open Media Center and Studio Projects" in case_titles
    assert "Remote swarms and enabled models are visible to the media pipeline" in case_titles


def test_media_center_advisors_are_seeded_for_10_17_and_19():
    app = create_app()
    with app.test_client() as client:
        payload = client.get("/api/media-center/state").get_json()
    roles = {item["agent_id"]: item for item in payload["advisors"]["roles"]}
    assert {"10", "17", "19"} <= set(roles)
    assert "composition" in roles["10"]["role"]
    assert "production" in roles["17"]["role"]
    assert "critique" in roles["19"]["role"]
