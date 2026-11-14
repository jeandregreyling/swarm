"""Practice 78 (owner 15 Nov): "still getting ollama.service reset requests that shouldn't be happening"."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_practice_78_chat_watchdog_does_not_restart_ollama(monkeypatch):
    src = (ROOT / 'frontend/blueprints/chat.py').read_text()
    i = src.index('def _watchdog_restart_ollama_service(model_name: str) -> dict:')
    body = src[i:i + 700]
    assert body.index('if not _ollama_restart_allowed():') < body.index("['systemctl', '--no-ask-password', 'restart', 'ollama']")
    ns = {}
    exec(src[src.index('def _ollama_restart_allowed() -> bool:'):i], ns)
    monkeypatch.delenv('HB_ALLOW_OLLAMA_RESTART', raising=False)
    assert ns['_ollama_restart_allowed']() is False
    monkeypatch.setenv('HB_ALLOW_OLLAMA_RESTART', '1')
    assert ns['_ollama_restart_allowed']() is True


def test_practice_78_runtime_gateway_has_no_default_restart(monkeypatch):
    monkeypatch.delenv('HB_ALLOW_OLLAMA_RESTART', raising=False)
    src = (ROOT / 'core/model_runtime_gateway.py').read_text()
    assert "if _os.environ.get('HB_ALLOW_OLLAMA_RESTART', '').strip() == '1' else [])" in src
    assert src.count('"--no-ask-password", "restart", "ollama"') == 2      # only inside the opt-in list
