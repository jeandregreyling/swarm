"""Load ignored, project-local environment files for Swarm processes."""

import os
from pathlib import Path


def load_local_env(root: Path | None = None) -> None:
    """Load `.env` then `.env.agents`, without overriding process settings."""
    project_root = root or Path(__file__).resolve().parents[1]
    for env_file in (project_root / ".env", project_root / ".env.agents"):
        try:
            lines = env_file.read_text().splitlines()
        except FileNotFoundError:
            continue

        for line in lines:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            if entry.startswith("export "):
                entry = entry[7:].lstrip()
            if "=" not in entry:
                continue

            name, value = entry.split("=", 1)
            name = name.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if name:
                os.environ.setdefault(name, value)
