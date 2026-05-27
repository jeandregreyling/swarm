"""Knowledge Center interactive source-bubble surface."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_knowledge_sources_tab_and_bubble_controls_present():
    js = (ROOT / "frontend/static/js/views/knowledge.js").read_text()
    html = (ROOT / "frontend/templates/terminal_base.html").read_text()

    assert "id: 'sources'" in js
    assert "knowledgeLoadSources" in js
    assert "knowledgeOpenSourceBubble" in js
    assert "kn-source-dot" in js
    assert "Folder: classification" in js
    assert "Folder: preview" in js
    assert "knowledgeSaveSourceBubble" in js
    assert "knowledgeReprocessSource" in js
    assert "knowledgeDeleteSource" in js
    assert 'id="kn-panel-sources"' in html


def test_knowledge_sources_css_supports_folder_dots_and_thought_bubble():
    css = (ROOT / "frontend/static/css/views/knowledge.css").read_text()

    assert ".kn-source-folder" in css
    assert ".kn-source-orbit" in css
    assert ".kn-source-dot" in css
    assert ".kn-source-bubble" in css
    assert ".kn-source-thought" in css
