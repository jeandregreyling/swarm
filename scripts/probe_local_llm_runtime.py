#!/usr/bin/env python3
"""Live local LLM runtime proof for Linux + Android visibility.

This is intentionally not a unit test. It hits the running Ollama daemon and
the running Fridays Flask service so regressions show up before the UI does.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ollama_model_guard import build_model_store_guard  # noqa: E402
from utils.db._connection import get_connection  # noqa: E402


BASE = "http://127.0.0.1:5050"
OLLAMA = "http://127.0.0.1:11434"
TOKEN = "LIVE_CHAT_PROOF_602"
BAD_INTERNAL_TEXT = (
    "FRIDAYS STUDIO HANDOFF TIMER",
    "SELF-HANDOFF",
    "visible deadline",
    "Do not wait silently",
)


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _run(cmd: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _ollama_models() -> set[str]:
    payload = _http_json("GET", f"{OLLAMA}/api/tags", timeout=8)
    return {
        str(item.get("model") or item.get("name") or "").strip().lower()
        for item in payload.get("models") or []
        if str(item.get("model") or item.get("name") or "").strip()
    }


def _agent_rows() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, model, tier, enabled FROM agents WHERE number >= 0 ORDER BY number ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _record(results: list[dict[str, Any]], name: str, ok: bool, detail: str, **extra: Any) -> None:
    row = {"name": name, "ok": bool(ok), "detail": str(detail)}
    row.update(extra)
    results.append(row)
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}: {detail}", flush=True)


def _assert_useful_response(text: str) -> tuple[bool, str]:
    raw = str(text or "").strip()
    if TOKEN not in raw:
        return False, f"proof token missing; response={raw[:220]!r}"
    for bad in BAD_INTERNAL_TEXT:
        if bad.lower() in raw.lower():
            return False, f"internal handoff text leaked: {bad}"
    return True, raw[:220]


def _probe_android(results: list[dict[str, Any]]) -> None:
    adb = _run(["adb", "devices", "-l"], timeout=8)
    if adb.returncode != 0:
        _record(results, "android-adb", False, (adb.stderr or adb.stdout or "adb failed").strip())
        return
    lines = [line.strip() for line in adb.stdout.splitlines()[1:] if line.strip()]
    if not lines:
        _record(results, "android-adb", False, "no Android device connected")
        return
    joined = " | ".join(lines)
    if "unauthorized" in joined:
        _record(results, "android-adb", False, "device connected but unauthorized; accept the USB prompt on Android", devices=lines)
        return
    if "\tdevice" not in adb.stdout and " device " not in joined:
        _record(results, "android-adb", False, f"device not ready: {joined}", devices=lines)
        return

    pkg = _run(["adb", "shell", "pidof", "com.swarm.hive"], timeout=8)
    running = pkg.returncode == 0 and bool(pkg.stdout.strip())
    _record(results, "android-hive-process", running, "com.swarm.hive running" if running else "com.swarm.hive not running")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--skip-android", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    results: list[dict[str, Any]] = []

    try:
        health = _http_json("GET", f"{base}/_health", timeout=8)
        _record(results, "flask-health", bool(health.get("ok") or health.get("status") == "healthy"), str(health)[:220])
    except Exception as exc:
        _record(results, "flask-health", False, str(exc))

    try:
        models = _ollama_models()
        _record(results, "ollama-tags", bool(models), ", ".join(sorted(models))[:260])
        guard = build_model_store_guard(_agent_rows(), models)
        guard_ok = bool(guard.get("ok")) and not guard.get("absent_from_expected")
        _record(results, "shared-model-store", guard_ok, json.dumps({
            "store": guard.get("expected_store"),
            "issues": guard.get("issues"),
            "absent_from_expected": guard.get("absent_from_expected"),
        }, sort_keys=True)[:420])
    except Exception as exc:
        _record(results, "shared-model-store", False, str(exc))

    direct_prompt = f"Return exactly this token and no other words: {TOKEN}"
    try:
        direct = _http_json(
            "POST",
            f"{OLLAMA}/api/generate",
            {"model": "qwen:latest", "prompt": direct_prompt, "stream": False, "keep_alive": "300s"},
            timeout=120,
        )
        ok, detail = _assert_useful_response(str(direct.get("response") or ""))
        _record(results, "ollama-direct-qwen", ok, detail)
    except Exception as exc:
        _record(results, "ollama-direct-qwen", False, str(exc))

    try:
        quick = _http_json(
            "POST",
            f"{base}/api/localai/ollama/chat",
            {"model": "qwen:latest", "message": direct_prompt},
            timeout=140,
        )
        ok, detail = _assert_useful_response(str(quick.get("answer") or quick.get("response") or ""))
        _record(results, "flask-quick-chat-qwen", ok and bool(quick.get("ok")), detail)
    except Exception as exc:
        _record(results, "flask-quick-chat-qwen", False, str(exc))

    try:
        main_chat = _http_json(
            "POST",
            f"{base}/api/chat",
            {
                "message": f"In one short sentence, include the exact token {TOKEN}.",
                "agent": "librarian",
                "history_mode": "none",
                "new_thread": True,
                "parallel": False,
            },
            timeout=20,
        )
        job_ids = [str(x) for x in (main_chat.get("pending_jobs") or []) if str(x).strip()]
        response = str(main_chat.get("response") or "")
        if job_ids:
            deadline = time.time() + 180
            final_job = None
            while time.time() < deadline:
                status = _http_json("GET", f"{base}/api/chat/jobs/status?job_ids={','.join(job_ids)}", timeout=10)
                jobs = status.get("jobs") or []
                if jobs and str(jobs[0].get("status") or "").lower() in {"completed", "failed", "cancelled"}:
                    final_job = jobs[0]
                    break
                time.sleep(4)
            if final_job:
                response = str(final_job.get("response") or final_job.get("error") or response)
                ok, detail = _assert_useful_response(response)
                _record(results, "main-chat-librarian", ok and final_job.get("status") == "completed", detail, job_id=final_job.get("job_id"), status=final_job.get("status"))
            else:
                _record(results, "main-chat-librarian", False, f"job did not finish within deadline: {job_ids}")
        else:
            ok, detail = _assert_useful_response(response)
            _record(results, "main-chat-librarian", ok and bool(main_chat.get("ok")), detail)
    except Exception as exc:
        _record(results, "main-chat-librarian", False, str(exc))

    try:
        runtime = _http_json("GET", f"{base}/api/ollama/runtime/health", timeout=10)
        _record(results, "ollama-runtime-health", bool(runtime.get("ok")), json.dumps(runtime, sort_keys=True)[:320])
    except Exception as exc:
        _record(results, "ollama-runtime-health", False, str(exc))

    if not args.skip_android:
        _probe_android(results)

    failed = [item for item in results if not item.get("ok")]
    print(json.dumps({"ok": not failed, "failed": failed, "results": results}, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
