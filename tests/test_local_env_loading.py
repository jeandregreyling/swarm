import os

from utils.env import load_local_env


def test_local_env_files_load_in_precedence_order(tmp_path):
    test_keys = ("SWARM_ENV_TEST_KEY", "SWARM_ENV_AGENTS_ONLY")
    previous = {key: os.environ.get(key) for key in test_keys}
    for key in test_keys:
        os.environ.pop(key, None)
    (tmp_path / ".env").write_text(
        "SWARM_ENV_TEST_KEY=from-root\n"
        "SWARM_ENV_AGENTS_ONLY=\n"
    )
    (tmp_path / ".env.agents").write_text(
        "SWARM_ENV_TEST_KEY=from-agents\n"
        "SWARM_ENV_AGENTS_ONLY=from-agents\n"
    )

    try:
        load_local_env(tmp_path)
        assert os.environ["SWARM_ENV_TEST_KEY"] == "from-root"
        assert os.environ["SWARM_ENV_AGENTS_ONLY"] == ""
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_process_environment_overrides_local_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ENV_TEST_KEY", "from-process")
    (tmp_path / ".env").write_text("SWARM_ENV_TEST_KEY=from-root\n")

    load_local_env(tmp_path)

    assert os.environ["SWARM_ENV_TEST_KEY"] == "from-process"
