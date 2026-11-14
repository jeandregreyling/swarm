import json
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_hummingbird_fixerupper.py"
SPEC = importlib.util.spec_from_file_location("seed_hummingbird_fixerupper", SCRIPT)
assert SPEC and SPEC.loader
seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed)


def test_plan_teaches_safe_rename_and_gpu_routing():
    payload = seed.plan()
    text = json.dumps(payload).lower()

    assert payload["owner"] == "apex"
    assert len(payload["steps"]) == 12
    assert "never bulk search/replace" in text
    assert "llama.cpp server" in text
    assert "ollama" in text and "fallback" in text
    assert "16 gb" in text
    assert "compatibility" in text
    assert "local playwright mcp" in text
    assert "github mcp" in text
    assert "local hummingbird tool server" in text
    assert "ggml_vulkan" in text
    assert "amd gpu" in text
    assert "microsoft service or account" in text
    assert payload["mcp_explanation"]["name"] == "Model Context Protocol"
    assert "not a microsoft server" in payload["mcp_explanation"]["ownership"].lower()


def test_preview_does_not_apply(monkeypatch, capsys):
    monkeypatch.setattr(seed, "apply", lambda: (_ for _ in ()).throw(AssertionError("must not write")))

    assert seed.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"].startswith("preview-only")
    assert "project_id" not in payload


def test_apply_requires_explicit_scope_confirmation(capsys):
    try:
        seed.main(["--apply"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("unconfirmed scope must not be applied")
    assert "--apply requires --confirm-scope" in capsys.readouterr().err


def test_tool_audit_reports_missing_and_present_commands(monkeypatch):
    monkeypatch.setattr(seed.shutil, "which", lambda command: f"/bin/{command}" if command == "git" else None)

    audit = seed.tool_audit()

    assert audit["binaries"]["core"]["git"] == "/bin/git"
    assert audit["binaries"]["recommended_additions"]["shellcheck"] is None
    assert audit["binaries"]["amd_vulkan_host"]["vulkaninfo"] is None
    assert "nvidia-smi" not in json.dumps(audit)
    assert audit["scope"].startswith("current execution environment")
