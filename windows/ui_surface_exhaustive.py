"""Broad non-destructive UI sweep for Fridays tiles and controls.

Opens each visible home tile on the live runtime, then clicks every visible
safe control it can find inside the tile window. The intent is not to mutate
state aggressively; destructive or workflow-committing controls are skipped.
Results are written to windows/artifacts/ui-surface-exhaustive-report.json.
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
REPORT_PATH = OUT_DIR / "ui-surface-exhaustive-report.json"
MAX_CLICKS_PER_TILE = 24
PER_TILE_BUDGET_S = 18.0

SAFE_BUTTON_SELECTORS = [
    "[data-kn-tab]",
    ".agents-tab",
    ".money-hub-tab",
    ".email-tab",
    "[data-email-tab]",
    ".media-dock-tab",
    "[data-studio-tab]",
    "[id^='studio-tab-']",
    "#trace-tab-bar button",
    "#agents-tab-bar .agents-tab",
    "#media-center-bottom-tabs .media-dock-tab",
    "#media-center-research-tabs .media-dock-tab",
    ".tasker-action-btn",
    ".tasker-toggle",
    "button[title='Previous week']",
    "button[title='Today']",
    "button[title='Next week']",
    "#tasker-evidence-status",
    "#tasker-filter-type",
    "#tasker-filter-status",
    "button",
]

WINDOW_CHROME_RE = re.compile(
    r"^(help|\?|new window|maximize|minimize|pin\b|close\b|dictionary:)$",
    re.IGNORECASE,
)

GLOBAL_SKIP_SELECTOR = (
    ".window-btn, "
    ".home-card-help-btn, "
    "#chat-dictionary-inline, "
    "[data-kn-tab], "
    "#friday-auth-overlay *"
)

SKIP_LABEL_RE = re.compile(
    r"(delete|remove|destroy|shutdown|kill|reset|wipe|purge|drop\b|"
    r"restart|reboot|logout|sign out|disable|revoke|promote|merge|"
    r"commit|push|pull|checkout|apply|save|update|create|submit|"
    r"run now|execute|close\b|cancel\b|archive|open spotlight|open digest)",
    re.IGNORECASE,
)
IGNORE_CONSOLE_RE = re.compile(
    r"(favicon|401|unauthorized|not implemented)",
    re.IGNORECASE,
)
TEXT_ISSUE_RE = re.compile(
    r"(traceback|exception|failed|error|unavailable|could not|unable to)",
    re.IGNORECASE,
)
TEXT_IGNORE_RE = re.compile(
    r"(no tasks|no jobs|no feeds|no topics|no entries|loading|welcome|manual)",
    re.IGNORECASE,
)
TRANSIENT_OVERLAY_IDS = [
    "spotlight-overlay",
    "window-help-modal",
    "studio-tab-help-modal",
    "kn-info-modal",
    "tw-section-help-modal",
    "tw-info-modal",
    "terminal-shortcut-modal",
    "governance-panel-modal",
    "troubleshoot-modal",
    "shortcuts-help-modal",
    "memory-detail-modal",
    "email-account-prefs-modal",
    "agents-add-modal",
    "agent-init-modal",
    "agent-delete-modal",
    "alm-detail-modal",
    "testlab-run-modal",
    "ticket-detail-modal",
]


def _window_selector(tile_id: str) -> str:
    return f"#win-{tile_id}"


def _tile_safe_selector(tile_id: str) -> str:
    root = _window_selector(tile_id)
    return ", ".join(f"{root} {selector}" for selector in SAFE_BUTTON_SELECTORS)


def _label(locator) -> str:
    try:
        text = (locator.inner_text(timeout=500) or "").strip()
    except Exception:
        text = ""
    if not text:
        try:
            text = (locator.get_attribute("title") or "").strip()
        except Exception:
            text = ""
    if not text:
        try:
            text = (locator.get_attribute("aria-label") or "").strip()
        except Exception:
            text = ""
    if not text:
        try:
            text = (locator.get_attribute("id") or "").strip()
        except Exception:
            text = ""
    return " ".join(text.split())[:120]


def _visible_text_issues(text: str) -> list[str]:
    issues: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        if not TEXT_ISSUE_RE.search(line):
            continue
        if TEXT_IGNORE_RE.search(line):
            continue
        if line not in issues:
            issues.append(line[:220])
    return issues[:16]


def _dismiss_transient_overlays(page, keep_tile_id: str | None = None) -> None:
    page.evaluate(
        """(args) => {
          const { ids, keepTileId } = args;
          for (const id of ids) {
            const el = document.getElementById(id);
            if (!el) continue;
            if (typeof el.remove === 'function') {
              el.remove();
              continue;
            }
            el.style.display = 'none';
            el.style.opacity = '0';
            el.style.pointerEvents = 'none';
          }
          if (window.winManager && window.winManager.windows) {
            for (const [id] of window.winManager.windows.entries()) {
              if (keepTileId && id === keepTileId) continue;
              try { window.winManager.close(id); } catch (_) {}
            }
          }
        }""",
        {"ids": TRANSIENT_OVERLAY_IDS, "keepTileId": keep_tile_id},
    )
    page.wait_for_timeout(120)


def _click_visible_controls(page, tile_id: str) -> tuple[list[dict], list[dict], bool]:
    locator = page.locator(_tile_safe_selector(tile_id))
    handles = locator.element_handles()
    clicked: list[dict] = []
    skipped: list[dict] = []
    seen_keys: set[str] = set()
    deadline = time.monotonic() + PER_TILE_BUDGET_S
    budget_hit = False

    for idx, item in enumerate(handles):
        if len(clicked) >= MAX_CLICKS_PER_TILE or time.monotonic() >= deadline:
            budget_hit = True
            break
        try:
            if not item.is_visible():
                continue
            if not item.is_enabled():
                continue
        except Exception:
            continue

        label = _label(item) or f"item-{idx + 1}"
        try:
            if item.evaluate(
                """(node, selector) => !!node.closest(selector)""",
                GLOBAL_SKIP_SELECTOR,
            ):
                skipped.append({"label": label, "reason": "global-skip-selector"})
                continue
        except Exception:
            pass
        key = f"{label}|{item.get_attribute('id') or ''}|{item.get_attribute('class') or ''}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        if WINDOW_CHROME_RE.search(label):
            skipped.append({"label": label, "reason": "window-chrome"})
            continue
        if SKIP_LABEL_RE.search(label):
            skipped.append({"label": label, "reason": "dangerous-label"})
            continue

        try:
            page.evaluate(
                """(args) => {
                  try { openWindow(args.id, args.title, args.template); } catch (_) {}
                }""",
                {"id": tile_id, "title": tile_id, "template": f"view-{tile_id}"},
            )
        except Exception:
            pass

        try:
            item.scroll_into_view_if_needed(timeout=2000)
            item.click(timeout=4000)
            page.wait_for_timeout(350)
            _dismiss_transient_overlays(page, tile_id)
            clicked.append({"label": label, "ok": True})
            continue
        except Exception as exc:
            message = str(exc)
            if "intercepts pointer events" in message or "not attached to the DOM" in message:
                try:
                    _dismiss_transient_overlays(page, tile_id)
                    item.scroll_into_view_if_needed(timeout=2000)
                    item.click(timeout=4000, force=True)
                    page.wait_for_timeout(250)
                    _dismiss_transient_overlays(page, tile_id)
                    clicked.append({"label": label, "ok": True, "forced": True})
                    continue
                except Exception as forced_exc:
                    _dismiss_transient_overlays(page, tile_id)
                    clicked.append({"label": label, "ok": False, "error": str(forced_exc)[:500]})
                    continue
            _dismiss_transient_overlays(page, tile_id)
            clicked.append({"label": label, "ok": False, "error": message[:500]})
    return clicked, skipped, budget_hit


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

        global_errors: list[str] = []
        current_tile: dict | None = None

        def _on_console(msg) -> None:
            line = f"{msg.type}:{msg.text}"
            if IGNORE_CONSOLE_RE.search(line):
                return
            global_errors.append(line)
            if current_tile is not None and msg.type == "error":
                current_tile.setdefault("console_errors", []).append(line)

        def _on_pageerror(exc) -> None:
            line = f"pageerror:{exc}"
            global_errors.append(line)
            if current_tile is not None:
                current_tile.setdefault("console_errors", []).append(line)

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
                () => {
                  const overlay = document.getElementById('friday-auth-overlay');
                  if (overlay) overlay.remove();
                }
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
            tile_report = {
                "id": tile_id,
                "title": tile["title"],
                "opened": False,
                "clicked": [],
                "skipped": [],
                "budget_hit": False,
                "bad_responses": [],
                "console_errors": [],
                "text_issues": [],
            }
            current_tile = tile_report
            print(f"[tile] {tile_id}", flush=True)

            try:
                _dismiss_transient_overlays(page)
                page.evaluate(
                    "(args) => openWindow(args.id, args.title, args.template)",
                    tile,
                )
                page.wait_for_selector(_window_selector(tile_id), timeout=12000)
                page.wait_for_timeout(1400)
                tile_report["opened"] = True

                clicked, skipped, budget_hit = _click_visible_controls(page, tile_id)
                tile_report["clicked"] = clicked
                tile_report["skipped"] = skipped
                tile_report["budget_hit"] = budget_hit
                page.wait_for_timeout(800)

                win_text = page.locator(_window_selector(tile_id)).inner_text(timeout=5000)
                tile_report["text_issues"] = _visible_text_issues(win_text)
            except Exception as exc:
                tile_report["text_issues"] = [f"open-failed: {exc}"]
            finally:
                try:
                    _dismiss_transient_overlays(page)
                    page.evaluate("(id) => window.winManager && winManager.close(id)", tile_id)
                    page.wait_for_timeout(350)
                except Exception:
                    pass

            if (
                tile_report["bad_responses"]
                or tile_report["console_errors"]
                or any(not row.get("ok", False) for row in tile_report["clicked"])
                or tile_report["text_issues"]
            ):
                report["ok"] = False

            report["tiles"].append(tile_report)
            current_tile = None

        report["global_errors"] = global_errors
        if global_errors:
            report["ok"] = False

        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        browser.close()

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
