"""Browser smoke for live Sync Story rendering in the Traced surface.

Injects a synthetic sync_story event through the spine API, opens the running
UI, launches Traced, filters to Sync Story rows, and verifies the detail card
renders the causality sections without a manual refresh.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:5050"
APP_URL = BASE_URL + "/ui"
OUT_DIR = Path(__file__).resolve().parent / "artifacts"
OUT_DIR.mkdir(exist_ok=True)
REPORT_PATH = OUT_DIR / "sync-story-smoke-report.json"


def _inject_sync_story() -> dict:
    stamp = int(time.time())
    payload = {
        "kind": "sync_story",
        "version": 1,
        "summary": f"sync-smoke-node main aaa111bbb222 -> ccc333ddd444 | synced | 2 paths | risk=runtime-impacting | smoke={stamp}",
        "risk": "runtime-impacting",
        "origin": {
            "source_node": "sync-smoke-node",
            "target_node": "origin",
            "transport": "github",
            "actor": "smoke",
            "trigger": "ui_sync_story_smoke",
            "repo_root": "/tmp/swarm-smoke",
        },
        "intent": {
            "branch": "main",
            "from_sha": "aaa111bbb222",
            "to_sha": "ccc333ddd444",
            "reason": "ui_sync_story_smoke",
            "threshold": 2,
            "change_count": 2,
        },
        "transition": {
            "files_changed_count": 2,
            "paths": [
                "frontend/blueprints/chat.py",
                "frontend/static/js/views/traced.js",
            ],
            "paths_truncated": False,
            "categories": ["runtime", "ui"],
        },
        "consequence": {
            "result": "synced",
            "reason": "threshold-met",
            "current_state": {
                "git_status": "synced",
                "clean_after_sync": True,
                "restart_recommended": True,
                "local_overrides_remain": False,
            },
            "next": "upstream aligned for this batch",
            "commit": "ccc333ddd444",
            "pushed": True,
            "push_output": "",
            "scan": "",
        },
        "intervention": {
            "recommended": [
                "open diff",
                "inspect changed paths",
                "review runtime impact",
                "proceed",
            ]
        },
    }
    body = {
        "kind": "system",
        "source": "sync-story-smoke",
        "message": payload["summary"],
        "payload": payload,
    }
    r = requests.post(BASE_URL + "/api/spine/log", json=body, timeout=5)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"spine log failed: {data}")
    return data["event"]


def main() -> int:
    report: dict = {
        "ok": False,
        "url": APP_URL,
        "generated_at": int(time.time()),
        "steps": [],
        "errors": [],
        "event": {},
    }

    def _step(name: str, ok: bool, detail: str = "") -> None:
        report["steps"].append({"step": name, "ok": ok, "detail": detail})

    try:
        event = _inject_sync_story()
        report["event"] = {
            "id": event.get("id"),
            "message": event.get("message"),
            "payload_kind": (event.get("payload") or {}).get("kind"),
        }
        _step("inject-sync-story", True, event.get("id", ""))
    except Exception as exc:
        report["errors"].append(f"inject:{exc}")
        _step("inject-sync-story", False, str(exc))
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1680, "height": 1200})
        page.set_default_timeout(12000)
        page.on("console", lambda msg: report["errors"].append(f"console:{msg.type}:{msg.text}"))
        page.on("pageerror", lambda exc: report["errors"].append(f"pageerror:{exc}"))

        try:
            page.goto(APP_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_selector("body", timeout=8000)
            page.wait_for_timeout(1200)
            _step("open-ui", True, APP_URL)

            if page.locator("#friday-auth-overlay").count():
                page.evaluate(
                    """
                    () => {
                      const overlay = document.getElementById('friday-auth-overlay');
                      if (overlay) overlay.remove();
                    }
                    """
                )
                page.wait_for_timeout(250)
                _step("remove-auth-overlay", True, "")

            page.evaluate(
                """
                () => {
                  openWindow('traced','Traced','view-traced');
                  if (typeof window.loadTracedPanel === 'function') {
                    window.loadTracedPanel({ kinds: ['sync_story'] });
                  }
                }
                """
            )
            page.wait_for_selector("#traced-panel", timeout=12000)
            _step("open-traced", True, "")

            page.wait_for_selector("#traced-kind", timeout=12000)
            page.select_option("#traced-kind", "sync_story")
            page.wait_for_timeout(600)
            _step("filter-sync-story", True, "")

            row = page.locator(".traced-sync-row").filter(has_text="sync-smoke-node").first
            row.wait_for(timeout=12000)
            _step("sync-row-visible", True, "sync-smoke-node")

            row.click()
            detail = page.locator("#traced-detail")
            detail.wait_for(timeout=5000)
            sync_detail = page.locator("#traced-detail .traced-sync-detail").first
            sync_detail.wait_for(timeout=5000)
            required = ["Origin", "Intent", "Consequence", "Impact Summary", "Intervention"]
            missing: list[str] = []
            for name in required:
                label = sync_detail.locator(f".traced-sync-label:text-is('{name}')").first
                if label.count() == 0:
                    missing.append(name)
            if missing:
                detail_html = sync_detail.inner_html(timeout=1000)
                raise AssertionError(f"missing detail sections: {missing} | html={detail_html[:800]}")
            _step("sync-detail-visible", True, ", ".join(required))

            risk_badge = page.locator(".traced-sync-risk-runtime-impacting").first
            risk_badge.wait_for(timeout=3000)
            _step("risk-badge-visible", True, risk_badge.inner_text(timeout=1000))

            page.screenshot(path=str(OUT_DIR / "sync-story-smoke.png"), full_page=True)
            _step("screenshot", True, str(OUT_DIR / "sync-story-smoke.png"))
            report["ok"] = True
        except Exception as exc:
            report["errors"].append(str(exc))
            _step("browser-check", False, str(exc))
        finally:
            browser.close()

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
