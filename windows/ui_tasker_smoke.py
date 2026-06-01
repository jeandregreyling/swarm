"""Windows browser smoke for the live Fridays Tasker view.

Opens the running UI on localhost:5050, launches Tasker, scrolls the view,
clicks through the visible Tasker controls, creates a temporary task, exercises
its actions, and deletes it again.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


APP_URL = "http://127.0.0.1:5050/ui"
TMP_TASK_NAME = f"ui_smoke_tasker_{int(time.time())}"
TMP_TASK_DATA = (
    "cmd /c echo ui_smoke_tasker"
    if os.name == "nt"
    else "sh -lc 'echo ui_smoke_tasker'"
)
OUT_DIR = Path(__file__).resolve().parent / "artifacts"
OUT_DIR.mkdir(exist_ok=True)


def _record(step_log: list[dict], step: str, ok: bool, detail: str = "") -> None:
    step_log.append({"step": step, "ok": ok, "detail": detail})


def _click(page, selector: str, step_log: list[dict], name: str, timeout: int = 10000) -> None:
    try:
        page.locator(selector).first.click(timeout=timeout)
        _record(step_log, name, True, selector)
    except Exception as exc:
        _record(step_log, name, False, f"{selector}: {exc}")
        raise


def main() -> int:
    step_log: list[dict] = []
    errors: list[str] = []
    bad_responses: list[dict[str, str | int]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_default_timeout(10000)
        page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}"))
        page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))
        page.on(
            "response",
            lambda response: bad_responses.append(
                {"status": response.status, "url": response.url}
            )
            if response.status >= 400
            else None,
        )

        try:
            page.goto(APP_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_selector("body", timeout=8000)
            page.wait_for_timeout(1500)
            _record(step_log, "open-ui", True, APP_URL)

            page.evaluate("openWindow('tasker','Tasker','view-tasker')")
            page.wait_for_selector("#tasker-list", timeout=12000)
            _record(step_log, "open-tasker", True, "#tasker-list visible")

            if page.locator("#friday-auth-overlay").count():
                _record(step_log, "auth-overlay-present", True, "overlay blocked pointer events")
                page.evaluate(
                    """
                    (() => {
                      const overlay = document.getElementById('friday-auth-overlay');
                      if (overlay) overlay.remove();
                    })()
                    """
                )
                page.wait_for_timeout(300)
                _record(step_log, "auth-overlay-removed-for-smoke", True, "")

            page.locator("#tasker-calendar-grid").scroll_into_view_if_needed()
            _record(step_log, "scroll-calendar", True, "")
            _click(page, "button[title='Previous week']", step_log, "calendar-prev")
            _click(page, "button[title='Today']", step_log, "calendar-today")
            _click(page, "button[title='Next week']", step_log, "calendar-next")
            calendar_items = page.locator(".tasker-calendar-item")
            if calendar_items.count():
                calendar_items.first.click()
                page.wait_for_selector("#tasker-form.open", timeout=8000)
                _record(step_log, "calendar-open-first-task", True, "")
                _click(page, "button:has-text('Cancel')", step_log, "close-calendar-task-form")
            else:
                _record(step_log, "calendar-open-first-task", True, "no calendar items visible")

            page.locator("#tasker-search").scroll_into_view_if_needed()
            cards = page.locator(".tasker-card")
            safe_card_clicks = min(cards.count(), 5)
            for idx in range(safe_card_clicks):
                task_card = cards.nth(idx)
                task_card.scroll_into_view_if_needed()
                task_card.locator("button[title='Edit']").first.click()
                page.wait_for_selector("#tasker-form.open", timeout=8000)
                _record(step_log, f"inspect-task-card-{idx + 1}", True, "edit opened")
                _click(page, "button:has-text('Cancel')", step_log, f"close-task-card-{idx + 1}")

            _click(page, "button:has-text('+ New Task')", step_log, "open-new-task")
            page.fill("#tasker-field-name", TMP_TASK_NAME)
            page.select_option("#tasker-field-type", "SHELL")
            page.fill("#tasker-field-schedule", "daily 23:59")
            page.fill("#tasker-field-data", TMP_TASK_DATA)
            page.fill("#tasker-field-creator", "ghost")
            _click(page, "button:has-text('Create Task')", step_log, "create-task")

            page.wait_for_selector(f".tasker-card[data-task-id]", timeout=12000)
            page.wait_for_timeout(800)
            card = page.locator(".tasker-card").filter(has_text=TMP_TASK_NAME).first
            card.wait_for(timeout=12000)
            _record(step_log, "task-created", True, TMP_TASK_NAME)

            card.scroll_into_view_if_needed()
            page.fill("#tasker-search", TMP_TASK_NAME)
            page.wait_for_timeout(300)
            _record(step_log, "search-task", True, TMP_TASK_NAME)

            page.select_option("#tasker-filter-type", "SHELL")
            page.wait_for_timeout(200)
            _record(step_log, "filter-type-shell", True, "")
            page.select_option("#tasker-filter-status", "active")
            page.wait_for_timeout(200)
            _record(step_log, "filter-status-active", True, "")
            page.select_option("#tasker-filter-type", "")
            page.select_option("#tasker-filter-status", "")
            page.fill("#tasker-search", "")
            page.wait_for_timeout(200)
            _record(step_log, "clear-filters", True, "")

            run_btn = card.locator("button[title='Run now']").first
            run_btn.click()
            page.wait_for_timeout(800)
            _record(step_log, "run-task", True, "")

            edit_btn = card.locator("button[title='Edit']").first
            edit_btn.click()
            page.wait_for_selector("#tasker-form.open", timeout=8000)
            _record(step_log, "edit-task", True, "")
            _click(page, "button:has-text('Hourly')", step_log, "preset-hourly")
            _click(page, "button:has-text('Update Task')", step_log, "update-task")
            page.wait_for_timeout(800)

            card = page.locator(".tasker-card").filter(has_text=TMP_TASK_NAME).first
            toggle = card.locator(".tasker-toggle").first
            toggle.click()
            page.wait_for_timeout(600)
            _record(step_log, "disable-task", True, "")
            toggle = card.locator(".tasker-toggle").first
            toggle.click()
            page.wait_for_timeout(600)
            _record(step_log, "enable-task", True, "")

            page.locator("#tasker-evidence-summary").scroll_into_view_if_needed()
            page.select_option("#tasker-evidence-status", "qualified")
            page.wait_for_timeout(600)
            _record(step_log, "filter-evidence-qualified", True, "")
            page.select_option("#tasker-evidence-status", "all")
            page.wait_for_timeout(600)
            _record(step_log, "filter-evidence-all", True, "")
            _click(page, "button:has-text('Refresh Evidence')", step_log, "refresh-evidence")
            page.wait_for_timeout(800)

            page.once("dialog", lambda dialog: dialog.accept())
            delete_btn = card.locator("button[title='Delete']").first
            delete_btn.click()
            page.wait_for_timeout(300)
            delete_btn = card.locator("button[title='Delete']").first
            delete_btn.click()
            page.wait_for_timeout(1000)
            _record(step_log, "delete-task", True, "")

            try:
                page.locator(".tasker-card").filter(has_text=TMP_TASK_NAME).wait_for(
                    state="detached", timeout=12000
                )
                _record(step_log, "task-deleted", True, TMP_TASK_NAME)
            except PlaywrightTimeoutError as exc:
                _record(step_log, "task-deleted", False, str(exc))
                raise

            page.screenshot(path=str(OUT_DIR / "tasker-smoke.png"), full_page=True)

        finally:
            report = {
                "ok": all(item["ok"] for item in step_log) and not errors and not bad_responses,
                "steps": step_log,
                "errors": errors,
                "bad_responses": bad_responses,
                "task_name": TMP_TASK_NAME,
                "url": APP_URL,
            }
            (OUT_DIR / "tasker-smoke-report.json").write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            browser.close()

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
