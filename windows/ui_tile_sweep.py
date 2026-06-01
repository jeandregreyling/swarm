"""Broad Windows browser sweep for visible Fridays home tiles.

Opens each visible home tile/window in the live browser runtime, triggers cheap
sub-tab interactions where available, and records obvious browser/runtime
failures per surface.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


APP_URL = "http://127.0.0.1:5050/ui"
OUT_DIR = Path(__file__).resolve().parent / "artifacts"
OUT_DIR.mkdir(exist_ok=True)
REPORT_PATH = OUT_DIR / "tile-sweep-report.json"

ERROR_RE = re.compile(
    r"(failed|error|unable|could not|unavailable|traceback|exception|not loaded|not available)",
    re.IGNORECASE,
)
IGNORE_TEXT_RE = re.compile(
    r"(no jobs|no tasks|no tickers yet|no research entries yet|no topics yet|loading|welcome|manual)",
    re.IGNORECASE,
)


def _visible_text_issues(text: str) -> list[str]:
    issues: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        if not ERROR_RE.search(line):
            continue
        if IGNORE_TEXT_RE.search(line):
            continue
        issues.append(line[:220])
    deduped: list[str] = []
    for item in issues:
        if item not in deduped:
            deduped.append(item)
    return deduped[:12]


def _window_selector(tile_id: str) -> str:
    return f"#win-{tile_id}"


def _safe_click_all(page, selector: str, per_click_wait_ms: int = 350) -> list[str]:
    clicked: list[str] = []
    locator = page.locator(selector)
    count = locator.count()
    for idx in range(count):
        item = locator.nth(idx)
        label = (item.text_content() or "").strip()
        try:
            item.click(timeout=5000)
            page.wait_for_timeout(per_click_wait_ms)
            clicked.append(label[:80] or f"item-{idx + 1}")
        except Exception as exc:
            clicked.append(f"click-failed:{label[:40] or idx + 1}:{exc}")
    return clicked


def _interact_tile(page, tile_id: str) -> dict:
    actions: dict[str, list[str] | str] = {}
    root = _window_selector(tile_id)

    if tile_id == "knowledge":
        actions["knowledge_tabs"] = _safe_click_all(page, f"{root} [data-kn-tab]")
    elif tile_id == "studio":
        actions["studio_tabs"] = _safe_click_all(page, f"{root} [id^='studio-tab-']", 500)
    elif tile_id == "agents-config":
        actions["agents_tabs"] = _safe_click_all(page, f"{root} #agents-tab-bar .agents-tab", 500)
    elif tile_id == "money-hub":
        actions["money_tabs"] = _safe_click_all(page, f"{root} .money-hub-tab", 700)
    elif tile_id == "trace":
        actions["trace_tabs"] = _safe_click_all(page, f"{root} #trace-tab-bar button", 500)
    elif tile_id == "media-center":
        actions["media_bottom_tabs"] = _safe_click_all(page, f"{root} #media-center-bottom-tabs .media-dock-tab", 400)
        actions["media_research_tabs"] = _safe_click_all(page, f"{root} #media-center-research-tabs .media-dock-tab", 400)
    elif tile_id == "email":
        actions["email_tabs"] = _safe_click_all(page, f"{root} [data-email-tab], {root} .email-tab", 400)
    return actions


def main() -> int:
    report: dict = {
        "ok": True,
        "url": APP_URL,
        "generated_at": int(time.time()),
        "overlay_present": False,
        "tiles": [],
        "global_errors": [],
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1720, "height": 1280})
        page.set_default_timeout(10000)

        page_errors: list[str] = []
        current_tile: dict | None = None

        def _on_console(msg) -> None:
            nonlocal current_tile
            line = f"{msg.type}:{msg.text}"
            page_errors.append(f"console:{msg.type}:{msg.text}")
            if current_tile is not None and msg.type == "error":
                current_tile.setdefault("console_errors", []).append(line)

        def _on_pageerror(exc) -> None:
            page_errors.append(f"pageerror:{exc}")
            if current_tile is not None:
                current_tile.setdefault("console_errors", []).append(f"pageerror:{exc}")

        def _on_response(response) -> None:
            if response.status < 400 or current_tile is None:
                return
            current_tile.setdefault("bad_responses", []).append(
                {"status": response.status, "url": response.url}
            )

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)
        page.on("response", _on_response)

        page.goto(APP_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector("body", timeout=8000)
        page.wait_for_timeout(1800)

        if page.locator("#friday-auth-overlay").count():
            report["overlay_present"] = True
            page.evaluate(
                """
                (() => {
                  const overlay = document.getElementById('friday-auth-overlay');
                  if (overlay) overlay.remove();
                })()
                """
            )
            page.wait_for_timeout(250)

        tiles = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('.home-card[data-win-id]'))
              .filter((node) => {
                const style = window.getComputedStyle(node);
                return style.display !== 'none' && style.visibility !== 'hidden' && !node.hidden;
              })
              .map((node) => ({
                id: node.dataset.winId,
                title: node.dataset.winTitle || node.dataset.winId,
                template: node.dataset.winTemplate || ('view-' + node.dataset.winId),
              }))
            """
        )

        for tile in tiles:
            tile_id = tile["id"]
            tile_title = tile["title"]
            tile_template = tile["template"]

            tile_report = {
                "id": tile_id,
                "title": tile_title,
                "opened": False,
                "interactions": {},
                "bad_responses": [],
                "console_errors": [],
                "text_issues": [],
            }
            current_tile = tile_report
            print(f"[tile] {tile_id}", flush=True)

            try:
                page.evaluate(
                    "(args) => openWindow(args.id, args.title, args.template)",
                    {"id": tile_id, "title": tile_title, "template": tile_template},
                )
                page.wait_for_selector(_window_selector(tile_id), timeout=12000)
                page.wait_for_timeout(1400)
                tile_report["opened"] = True

                interactions = _interact_tile(page, tile_id)
                tile_report["interactions"] = interactions
                page.wait_for_timeout(1200)

                win_text = page.locator(_window_selector(tile_id)).inner_text(timeout=4000)
                tile_report["text_issues"] = _visible_text_issues(win_text)
            except Exception as exc:
                tile_report["text_issues"] = [f"open-failed: {exc}"]
                report["ok"] = False
            finally:
                try:
                    page.evaluate(
                        """
                        () => {
                          document.getElementById('window-help-modal')?.remove();
                          document.getElementById('studio-tab-help-modal')?.remove();
                        }
                        """
                    )
                    page.evaluate("(id) => window.winManager && winManager.close(id)", tile_id)
                    page.wait_for_timeout(350)
                except Exception:
                    pass

            if tile_report["bad_responses"] or tile_report["console_errors"] or tile_report["text_issues"]:
                report["ok"] = False

            report["tiles"].append(tile_report)
            current_tile = None

        report["global_errors"] = page_errors
        if page_errors:
            report["ok"] = False

        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        browser.close()

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
