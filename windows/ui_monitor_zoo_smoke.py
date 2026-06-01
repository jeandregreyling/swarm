"""Windows/browser smoke for the Monitor Zoo Census surface.

Opens the live runtime, launches Monitor, verifies the Sovereign Zoo Census
card renders, triggers the "Ping cages" action, and checks that the card
refreshes with the persisted census summary.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


APP_URL = "http://127.0.0.1:5050/ui"
OUT_DIR = Path(__file__).resolve().parent / "artifacts"
OUT_DIR.mkdir(exist_ok=True)
REPORT_PATH = OUT_DIR / "monitor-zoo-smoke-report.json"


def _record(steps: list[dict], step: str, ok: bool, detail: str = "") -> None:
    steps.append({"step": step, "ok": ok, "detail": detail})


def main() -> int:
    steps: list[dict] = []
    errors: list[str] = []
    bad_responses: list[dict[str, str | int]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1680, "height": 1280})
        page.set_default_timeout(12000)
        page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}"))
        page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))
        page.on(
            "response",
            lambda response: bad_responses.append(
                {"status": response.status, "url": response.url}
            ) if response.status >= 400 else None,
        )

        try:
            page.goto(APP_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_selector("body", timeout=8000)
            page.wait_for_timeout(1500)
            _record(steps, "open-ui", True, APP_URL)

            if page.locator("#friday-auth-overlay").count():
                page.evaluate(
                    """
                    (() => {
                      const overlay = document.getElementById('friday-auth-overlay');
                      if (overlay) overlay.remove();
                    })()
                    """
                )
                page.wait_for_timeout(250)
                _record(steps, "auth-overlay-removed", True, "")

            page.evaluate("openWindow('monitor','Monitor','view-monitor')")
            page.wait_for_selector("#monitor-content", timeout=12000)
            _record(steps, "open-monitor", True, "#monitor-content visible")

            zoo = page.locator("#monitor-zoo-census")
            zoo.wait_for(timeout=12000)
            page.wait_for_timeout(1200)
            card_text = zoo.inner_text()
            if "Sovereign Zoo Census" not in card_text:
                raise AssertionError("zoo census card title missing")
            _record(steps, "zoo-card-visible", True, card_text[:200])

            ping_btn = page.locator("#monitor-zoo-ping-btn").first
            ping_btn.click()
            page.wait_for_timeout(1800)
            _record(steps, "ping-cages-click", True, "")

            refreshed = zoo.inner_text()
            refreshed_upper = refreshed.upper()
            if "ORPHANED" not in refreshed_upper or "ACTIVE" not in refreshed_upper:
                raise AssertionError("zoo census metrics missing after ping")
            _record(steps, "zoo-card-refresh", True, refreshed[:240])

            page.screenshot(path=str(OUT_DIR / "monitor-zoo-smoke.png"), full_page=True)
        finally:
            report = {
                "ok": all(step["ok"] for step in steps) and not bad_responses,
                "steps": steps,
                "errors": errors,
                "bad_responses": bad_responses,
                "url": APP_URL,
                "generated_at": int(time.time()),
            }
            REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
            browser.close()

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
