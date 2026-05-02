"""Lock the legacy config shim and qwen3 alias mapping.

Regression for S-F0D3F4B8DA: the live config moved to ``utils.config`` but
many call sites still ``from config import ...``. The shim must re-export
``OPENAI_API_KEY`` even when the env var is unset, and Twenty must repair
the ``qwen3:latest`` alias to its real model.
"""
import importlib
import os


class TestConfigShim:
    def test_openai_api_key_attribute_exists(self):
        import config
        importlib.reload(config)
        assert hasattr(config, "OPENAI_API_KEY")

    def test_openai_api_key_is_string(self):
        import config
        importlib.reload(config)
        assert isinstance(config.OPENAI_API_KEY, str)

    def test_openai_api_key_in_all(self):
        import config
        importlib.reload(config)
        assert "OPENAI_API_KEY" in config.__all__

    def test_star_import_exposes_openai_api_key(self):
        ns: dict = {}
        exec("from config import *", ns)
        assert "OPENAI_API_KEY" in ns

    def test_env_var_passthrough(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-shim-1234")
        # Force a fresh import so the shim re-reads the env.
        import sys
        for mod in ("config", "utils.config"):
            sys.modules.pop(mod, None)
        import config
        assert config.OPENAI_API_KEY == "sk-test-shim-1234"

    def test_missing_env_returns_empty_string_not_none(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import sys
        for mod in ("config", "utils.config"):
            sys.modules.pop(mod, None)
        import config
        # utils.config may have its own default; either '' or a real value,
        # but never None — the shim guarantees a string.
        assert isinstance(config.OPENAI_API_KEY, str)


class TestTwentyQwen3Alias:
    def test_alias_repairs_to_real_model(self, monkeypatch):
        # Force the registry to return the broken alias.
        from agents.twenty import twenty_agent
        monkeypatch.setattr(
            "utils.db.registry.get_agent_models",
            lambda: {"twenty": "qwen3:latest"},
        )
        chosen = twenty_agent._resolve_model()
        assert chosen == twenty_agent.MODEL
        assert chosen != "qwen3:latest"

    def test_alias_repairs_bare_qwen3(self, monkeypatch):
        from agents.twenty import twenty_agent
        monkeypatch.setattr(
            "utils.db.registry.get_agent_models",
            lambda: {"twenty": "qwen3"},
        )
        assert twenty_agent._resolve_model() == twenty_agent.MODEL

    def test_alias_is_case_insensitive(self, monkeypatch):
        from agents.twenty import twenty_agent
        monkeypatch.setattr(
            "utils.db.registry.get_agent_models",
            lambda: {"twenty": "Qwen3:Latest"},
        )
        assert twenty_agent._resolve_model() == twenty_agent.MODEL

    def test_passthrough_for_real_model(self, monkeypatch):
        from agents.twenty import twenty_agent
        monkeypatch.setattr(
            "utils.db.registry.get_agent_models",
            lambda: {"twenty": "qwen3.6:latest"},
        )
        assert twenty_agent._resolve_model() == "qwen3.6:latest"

    def test_falls_back_to_default_when_registry_empty(self, monkeypatch):
        from agents.twenty import twenty_agent
        monkeypatch.setattr(
            "utils.db.registry.get_agent_models",
            lambda: {},
        )
        assert twenty_agent._resolve_model() == twenty_agent.MODEL

    def test_survives_registry_exception(self, monkeypatch):
        from agents.twenty import twenty_agent

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr("utils.db.registry.get_agent_models", _boom)
        assert twenty_agent._resolve_model() == twenty_agent.MODEL
