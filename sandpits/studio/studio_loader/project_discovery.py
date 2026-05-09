"""
studio_loader/project_discovery.py
Minimal dynamic project discovery for sandpits/studio/

Any folder containing PROJECT_PLAN.md becomes a discoverable Studio project.
"""

import os
from pathlib import Path
from typing import List, Dict, Any

STUDIO_ROOT = Path(__file__).resolve().parents[2] / "sandpits" / "studio"

def discover_projects() -> List[Dict[str, Any]]:
    projects = []
    if not STUDIO_ROOT.exists():
        return projects

    for entry in STUDIO_ROOT.iterdir():
        if not entry.is_dir():
            continue
        plan_file = entry / "PROJECT_PLAN.md"
        if not plan_file.exists():
            continue
        project = _parse_project(entry.name, plan_file)
        projects.append(project)
    return projects

def _parse_project(name: str, plan_file: Path) -> Dict[str, Any]:
    content = plan_file.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    title = name
    status = "active"
    packets = []
    blackboard_notes = []
    current_section = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and title == name:
            title = stripped[2:].strip()
        elif stripped.lower().startswith("**status:**"):
            status = stripped.split(":", 1)[1].strip().lower()
        elif stripped.lower().startswith("## packet") or stripped.lower().startswith("## step"):
            current_section = "packets"
        elif stripped.lower().startswith("## blackboard"):
            current_section = "blackboard"
        elif stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:].strip()
            if current_section == "packets":
                packets.append({"title": item, "status": "todo"})
            elif current_section == "blackboard":
                blackboard_notes.append(item)

    if not packets:
        packets.append({
            "title": "Project initialized (PROJECT_PLAN.md present)",
            "status": "done"
        })

    return {
        "id": name,
        "name": title,
        "status": status,
        "packets": packets,
        "blackboard": blackboard_notes,
        "path": str(plan_file.parent),
        "source": "sandpits/studio"
    }
