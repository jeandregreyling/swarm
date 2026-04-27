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


def test_studio_js_knows_media_tab():
    src = STUDIO_JS.read_text()
    assert "const isMedia = (tab === 'media');" in src
    assert "loadStudioMediaPanel" in src


def test_studio_media_panel_links_tracking_project():
    src = (ROOT / "frontend/static/js/views/studio-media.js").read_text()
    assert "Internal Tracking Project" in src
    assert "studioMediaOpenProject" in src
    assert "tracking_project_id" in src


def test_media_center_has_resizable_layout_contract():
    css = (ROOT / "frontend/static/css/views/media-center.css").read_text()
    js = (ROOT / "frontend/static/js/views/media-center.js").read_text()
    assert "--media-center-sidebar-width" in css
    assert ".media-center-resizer" in css
    assert "_mediaCenterWireResizer" in js
    assert "fridays.mediaCenter.sidebarWidth" in js


def test_media_center_context_surfaces_models_swarms_and_chat():
    js = (ROOT / "frontend/static/js/views/media-center.js").read_text()
    assert "Projects Tracker" in js
    assert "Chat Actions" in js
    assert "Model Candidates" in js
    assert "Linked Swarms" in js
    assert "recent passes" in js
    assert "Editor Timeline" in js
    assert "mediaCenterAddClip" in js
    assert "Synth Registry" in js
    assert "mediaCenterCreateSynthTake" in js
    assert "Media Accounts" in js
    assert "Knowledge Index" in js
    assert "Media References" in js
    assert "mediaCenterAddReference" in js
    assert "Model / Swarm Routing" in js
    assert "mediaCenterUpdateRouting" in js
    assert "mediaCenterLinkAccount" in js
    assert "Handoff Manifest" in js
    assert "mediaCenterCopyHandoff" in js


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
    assert payload["routing"]["default_mode"] == "local-first"


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
    assert "Project tracking + test harness" in step_titles
    assert "Chat integration" in step_titles
    assert "Swarm and model federation" in step_titles
    assert "Chat action intents can open Media Center and Studio Projects" in case_titles
    assert "Remote swarms and enabled models are visible to the media pipeline" in case_titles
