#!/usr/bin/env python3
"""Live local LLM runtime proof for Linux + Android visibility.

This is intentionally not a unit test. It hits the running Ollama daemon and
the running Fridays Flask service so regressions show up before the UI does.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ollama_model_guard import build_model_store_guard  # noqa: E402
from utils.db._connection import get_connection  # noqa: E402
from utils.local_runtime_policy import preferred_model_for_agent  # noqa: E402


BASE = "http://127.0.0.1:5050"
OLLAMA = "http://127.0.0.1:11434"
TOKEN_PREFIX = "LIVE_CHAT_PROOF"
ANDROID_PROOF_PREFIX = "ANDROIDHIVEPROOF"
PROOF_MODEL = preferred_model_for_agent("qwen", "qwen:latest")
HIVE_PACKAGE = "com.swarm.hive"
HIVE_APK = ROOT / "android" / "hive-agent" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
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


def _adb(cmd: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return _run(["adb", *cmd], timeout=timeout)


def _adb_shell(command: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return _run(["adb", "shell", command], timeout=timeout)


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


def _assert_useful_response(text: str, token: str) -> tuple[bool, str]:
    raw = str(text or "").strip()
    compact_raw = raw.replace(" _", "_").replace("_ ", "_").replace(" ", "")
    compact_token = token.replace(" ", "")
    if token not in raw and compact_token not in compact_raw:
        return False, f"proof token missing; response={raw[:220]!r}"
    for bad in BAD_INTERNAL_TEXT:
        if bad.lower() in raw.lower():
            return False, f"internal handoff text leaked: {bad}"
    return True, raw[:220]


def _probe_android(results: list[dict[str, Any]]) -> None:
    adb = _adb(["devices", "-l"], timeout=8)
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

    _record(results, "android-adb", True, joined, devices=lines)

    pkg = _adb(["shell", "pidof", HIVE_PACKAGE], timeout=8)
    running = pkg.returncode == 0 and bool(pkg.stdout.strip())
    _record(results, "android-hive-process", running, "com.swarm.hive running" if running else "com.swarm.hive not running")


def _bounds_center(bounds: str) -> tuple[int, int] | None:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    x1, y1, x2, y2 = [int(part) for part in match.groups()]
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def _dump_android_ui() -> tuple[str, ET.Element | None]:
    _adb(["shell", "uiautomator", "dump", "/sdcard/swarm-hive-window.xml"], timeout=12)
    cat = _adb(["shell", "cat", "/sdcard/swarm-hive-window.xml"], timeout=12)
    xml_text = cat.stdout or ""
    if not xml_text.strip().startswith("<?xml"):
        return xml_text, None
    try:
        return xml_text, ET.fromstring(xml_text)
    except Exception:
        return xml_text, None


def _node_by_resource(root: ET.Element | None, resource_id: str) -> ET.Element | None:
    if root is None:
        return None
    suffix = f":id/{resource_id}"
    for node in root.iter("node"):
        rid = node.attrib.get("resource-id", "")
        if rid == resource_id or rid.endswith(suffix):
            return node
    return None


def _tap_resource(resource_id: str) -> bool:
    node = _find_android_resource(resource_id)
    if node is None:
        return False
    center = _bounds_center(node.attrib.get("bounds", ""))
    if center is None:
        return False
    tap = _adb(["shell", "input", "tap", str(center[0]), str(center[1])], timeout=8)
    return tap.returncode == 0


def _find_android_resource(resource_id: str, attempts: int = 6) -> ET.Element | None:
    for idx in range(max(1, attempts)):
        _, root = _dump_android_ui()
        node = _node_by_resource(root, resource_id)
        if node is not None:
            return node
        if idx < attempts - 1:
            _adb(["shell", "input", "swipe", "1200", "1250", "1200", "280", "650"], timeout=8)
            time.sleep(0.7)
    return None


def _find_android_text(resource_id: str, attempts: int = 6) -> str:
    node = _find_android_resource(resource_id, attempts=attempts)
    if node is None:
        xml_text, _ = _dump_android_ui()
        return xml_text
    return node.attrib.get("text", "") or ""


def _android_text_for(root: ET.Element | None, resource_id: str) -> str:
    node = _node_by_resource(root, resource_id)
    if node is None:
        return ""
    return node.attrib.get("text", "") or ""


def _android_input_text(text: str) -> bool:
    escaped = (
        text.replace("\\", "\\\\")
        .replace(" ", "%s")
        .replace("&", "\\&")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace('"', '\\"')
    )
    res = _adb(["shell", "input", "text", escaped], timeout=12)
    return res.returncode == 0


def _wait_for_leader_node(base: str, node_id: str, deadline_s: float = 90.0) -> tuple[bool, str]:
    deadline = time.time() + deadline_s
    last = ""
    while time.time() < deadline:
        try:
            nodes = _http_json("GET", f"{base}/api/hive/nodes", timeout=8)
            for item in nodes.get("nodes") or []:
                if str(item.get("node_id") or "") == node_id:
                    offline = bool(item.get("offline"))
                    age = item.get("age_s")
                    last = f"{node_id} offline={offline} age_s={age}"
                    if not offline:
                        return True, last
            last = f"{node_id} not present"
        except Exception as exc:
            last = str(exc)
        time.sleep(5)
    return False, last


def _probe_android_hive_app(results: list[dict[str, Any]], *, base: str, token: str, node_id: str, apk: Path) -> None:
    adb = _adb(["devices", "-l"], timeout=8)
    if adb.returncode != 0:
        _record(results, "android-adb", False, (adb.stderr or adb.stdout or "adb failed").strip())
        return
    lines = [line.strip() for line in adb.stdout.splitlines()[1:] if line.strip()]
    joined = " | ".join(lines)
    if not lines:
        _record(results, "android-adb", False, "no Android device connected")
        return
    if "unauthorized" in joined:
        _record(results, "android-adb", False, "device connected but unauthorized; accept the USB prompt on Android", devices=lines)
        return
    if "\tdevice" not in adb.stdout and " device " not in joined:
        _record(results, "android-adb", False, f"device not ready: {joined}", devices=lines)
        return
    _record(results, "android-adb", True, joined, devices=lines)

    if not apk.exists():
        _record(results, "android-hive-apk", False, f"APK missing: {apk}")
        return
    install = _adb(["install", "-r", str(apk)], timeout=120)
    install_text = (install.stdout + install.stderr).strip()
    _record(results, "android-hive-install", install.returncode == 0, install_text[:320])
    if install.returncode != 0:
        return

    leader = base.replace("127.0.0.1", "100.87.66.45")
    join_url = f"swarmhive://join?leader={quote(leader, safe=':/')}&node_id={quote(node_id)}"
    launch = _adb_shell(
        "am start "
        "-a android.intent.action.VIEW "
        f"-d {shlex.quote(join_url)} "
        f"-n {HIVE_PACKAGE}/.MainActivity",
        timeout=20,
    )
    _record(results, "android-hive-launch", launch.returncode == 0, (launch.stdout + launch.stderr).strip()[:320])
    if launch.returncode != 0:
        return

    pid_ok = False
    pid_detail = ""
    for _ in range(12):
        pid = _adb(["shell", "pidof", HIVE_PACKAGE], timeout=8)
        pid_detail = pid.stdout.strip() or pid.stderr.strip()
        if pid.returncode == 0 and pid.stdout.strip():
            pid_ok = True
            break
        time.sleep(2)
    _record(results, "android-hive-process", pid_ok, pid_detail or "process not running")

    live_ok, live_detail = _wait_for_leader_node(base, node_id)
    _record(results, "android-hive-leader-node-live", live_ok, live_detail)

    _adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], timeout=8)
    _adb(["shell", "input", "keyevent", "KEYCODE_MENU"], timeout=8)
    _tap_resource("btn_models")
    time.sleep(4)
    model_text = _find_android_text("model_summary", attempts=6)
    _record(
        results,
        "android-hive-model-list-ui",
        "Selected for chat" in model_text and "Available on Dell" in model_text,
        model_text[:320],
    )

    proof_ok = _tap_resource("btn_run_chat_proof")
    _record(results, "android-hive-clean-proof-ui-send", proof_ok, f"proof_button={proof_ok}")
    if not proof_ok:
        return

    response_detail = ""
    response_ok = False
    proof_token = ""
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(5)
        xml_text, root = _dump_android_ui()
        response_detail = _android_text_for(root, "chat_response") or xml_text[:600]
        proof_match = re.search(rf"{ANDROID_PROOF_PREFIX}\d+", response_detail)
        if proof_match:
            proof_token = proof_match.group(0)
            answer = response_detail.split("\n\n", 1)[-1].strip()
            clean_answer = answer.strip('"').strip()
            response_ok = clean_answer == proof_token
            break
        if "Chat failed:" in response_detail:
            break
    if "⁶" in response_detail:
        response_ok = False
    _record(results, "android-hive-clean-proof-ui-response", response_ok, response_detail[:600], proof_token=proof_token)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--skip-android", action="store_true")
    parser.add_argument("--android-apk", default=str(HIVE_APK))
    parser.add_argument("--android-node-id", default="potato-2")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    token = f"{TOKEN_PREFIX}_{int(time.time())}"
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

    direct_prompt = f"Return exactly this token and no other words: {token}"
    try:
        direct = _http_json(
            "POST",
            f"{OLLAMA}/api/generate",
            {"model": PROOF_MODEL, "prompt": direct_prompt, "stream": False, "keep_alive": "300s"},
            timeout=120,
        )
        ok, detail = _assert_useful_response(str(direct.get("response") or ""), token)
        _record(results, "ollama-direct-qwen", ok, detail)
    except Exception as exc:
        _record(results, "ollama-direct-qwen", False, str(exc))

    try:
        quick = _http_json(
            "POST",
            f"{base}/api/localai/ollama/chat",
            {"model": PROOF_MODEL, "message": direct_prompt},
            timeout=140,
        )
        ok, detail = _assert_useful_response(str(quick.get("answer") or quick.get("response") or ""), token)
        _record(results, "flask-quick-chat-qwen", ok and bool(quick.get("ok")), detail)
    except Exception as exc:
        _record(results, "flask-quick-chat-qwen", False, str(exc))

    try:
        main_chat = _http_json(
            "POST",
            f"{base}/api/chat",
            {
                "message": f"Return exactly this token and no other characters: {token}",
                "agent": "qwen",
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
                ok, detail = _assert_useful_response(response, token)
                _record(results, "main-chat-qwen", ok and final_job.get("status") == "completed", detail, job_id=final_job.get("job_id"), status=final_job.get("status"))
            else:
                _record(results, "main-chat-qwen", False, f"job did not finish within deadline: {job_ids}")
        else:
            ok, detail = _assert_useful_response(response, token)
            _record(results, "main-chat-qwen", ok and bool(main_chat.get("ok")), detail)
    except Exception as exc:
        _record(results, "main-chat-qwen", False, str(exc))

    try:
        runtime = _http_json("GET", f"{base}/api/ollama/runtime/health", timeout=10)
        _record(results, "ollama-runtime-health", bool(runtime.get("ok")), json.dumps(runtime, sort_keys=True)[:320])
    except Exception as exc:
        _record(results, "ollama-runtime-health", False, str(exc))

    if not args.skip_android:
        _probe_android_hive_app(
            results,
            base=base,
            token=token,
            node_id=args.android_node_id,
            apk=Path(args.android_apk),
        )

    failed = [item for item in results if not item.get("ok")]
    print(json.dumps({"ok": not failed, "failed": failed, "results": results}, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
