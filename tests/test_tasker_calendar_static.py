from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tasker_calendar_ui_is_wired_to_scheduled_jobs():
    html = (ROOT / "frontend/templates/terminal_base.html").read_text()
    js = (ROOT / "frontend/static/js/views/tasker.js").read_text()
    css = (ROOT / "frontend/static/css/views/tasker.css").read_text()

    assert "tasker-calendar-grid" in html
    assert "shiftTaskerCalendar" in html
    assert "_taskerRenderCalendar" in js
    assert "_taskerTaskHasEmail" in js
    assert "interest_research_update" in js
    assert ".tasker-calendar-item.email-linked" in css
