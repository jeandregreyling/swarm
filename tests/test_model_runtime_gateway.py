import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import model_runtime_gateway as gateway


def test_normalize_model_json_accepts_fenced_object():
    result = gateway.normalize_model_json('```json\n{"image_prompt":"a","video_prompt":"b"}\n```')

    assert result["ok"] is True
    assert result["shape"] == "object"
    assert result["value"]["image_prompt"] == "a"
    assert result["truncated"] is False


def test_normalize_model_json_accepts_first_object_from_list():
    result = gateway.normalize_model_json('[{"image_prompt":"a"},{"image_prompt":"b"}]')

    assert result["ok"] is True
    assert result["shape"] == "list"
    assert result["value"]["image_prompt"] == "a"


def test_normalize_model_json_flags_truncated_output():
    result = gateway.normalize_model_json('```json\n{"image_prompt":"a", "video_prompt":"')

    assert result["ok"] is False
    assert result["truncated"] is True


def test_ollama_health_flags_stopping_models():
    payload = {
        "models": [
            {"model": "Llama3.2:latest", "until": "Stopping...", "size": 123},
            {"model": "gemma3:latest", "expires_at": "2026-04-30T01:00:00Z"},
        ]
    }

    result = gateway.ollama_health(ps_payload=payload)

    assert result["ok"] is True
    assert result["status"] == "degraded"
    assert result["models"][0]["state"] == "stopping"
    assert result["models"][1]["state"] == "loaded"


def test_chat_generate_fallback_has_short_timeout(monkeypatch):
    calls = []

    class _GenerateResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "OK", "eval_count": 1}

    def _post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/api/chat"):
            raise gateway.requests.ReadTimeout("no tokens")
        return _GenerateResponse()

    monkeypatch.setattr(gateway.requests, "post", _post)

    result = gateway.chat(
        "llama3.2:latest",
        [{"role": "user", "content": "health"}],
        idle_timeout_s=900,
    )

    assert result.ok is True
    assert result.content == "OK"
    assert calls[1][1]["timeout"] == (10, gateway.FALLBACK_GENERATE_TIMEOUT_S)
