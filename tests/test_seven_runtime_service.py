import json
import threading
import time
import urllib.request


def _read_json(url, *, data=None, timeout=5):
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_health_snapshot_is_standalone_direct_runtime():
    from core.seven_runtime import service

    snap = service.health_snapshot()

    assert snap["service"] == "seven-runtime"
    assert snap["flask_required"] is False
    assert snap["ollama_required"] is False
    assert snap["model"] == "seven-direct:daily"
    assert "direct" in snap


def test_standalone_http_health_and_models():
    from core.seven_runtime import service

    httpd = service.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        health = _read_json(base + "/health")
        models = _read_json(base + "/v1/models")
    finally:
        httpd.shutdown()
        thread.join(timeout=3)

    assert health["service"] == "seven-runtime"
    assert models["object"] == "list"
    assert any(row["id"] == "seven-direct:daily" for row in models["data"])


def test_standalone_http_chat_uses_guarded_seven(monkeypatch):
    from core.seven_runtime import service

    monkeypatch.setattr(
        service,
        "guarded_chat",
        lambda payload: {
            "ok": True,
            "content": f"echo:{payload['message']}",
            "tokens": 1,
            "stages": ["test"],
            "model": "seven-direct:daily",
        },
    )
    httpd = service.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        out = _read_json(base + "/chat", data={"message": "hello"})
    finally:
        httpd.shutdown()
        thread.join(timeout=3)

    assert out["ok"] is True
    assert out["content"] == "echo:hello"
    assert out["model"] == "seven-direct:daily"


def test_guarded_chat_timeout_returns_promptly(monkeypatch):
    from core.seven_runtime import service

    def slow_chat(_payload):
        time.sleep(3)
        return {"ok": True, "content": "late", "tokens": 1}

    monkeypatch.setattr(service, "_chat", slow_chat)
    started = time.monotonic()
    out = service.guarded_chat({"message": "hello", "timeout_seconds": 1})
    elapsed = time.monotonic() - started

    assert out["ok"] is False
    assert "timeout after 1s" in out["error"]
    assert elapsed < 2
