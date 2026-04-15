"""A.4.1 – Enforce that blueprints never cross-import each other.

Scans every .py in frontend/blueprints/ and verifies that no module
inside that package imports from another sibling blueprint.
"""
import ast, pathlib, pytest

BP_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "blueprints"

# Collect all blueprint module names (minus __init__)
_bp_modules = {
    p.stem for p in BP_DIR.glob("*.py")
    if p.stem != "__init__" and not p.name.endswith((".bak", ".backup"))
}

# Build the set of forbidden import sources
_forbidden = {f"frontend.blueprints.{m}" for m in _bp_modules} | _bp_modules


def _find_cross_imports(filepath: pathlib.Path):
    """Return list of (lineno, imported_module) for cross-blueprint imports."""
    source = filepath.read_text()
    tree = ast.parse(source, filename=str(filepath))
    violations = []
    own_name = filepath.stem
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                # Only flag "frontend.blueprints.<sibling>"
                if (len(parts) >= 3
                        and parts[0] == "frontend" and parts[1] == "blueprints"
                        and parts[2] in _bp_modules and parts[2] != own_name):
                    violations.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                parts = node.module.split(".")
                # "from frontend.blueprints.sibling import …"
                if (len(parts) >= 3
                        and parts[0] == "frontend" and parts[1] == "blueprints"
                        and parts[2] in _bp_modules and parts[2] != own_name):
                    violations.append((node.lineno, node.module))
                # relative "from .sibling import …" (level=1 within blueprints)
                elif (node.level == 1
                      and len(parts) == 1
                      and parts[0] in _bp_modules and parts[0] != own_name):
                    violations.append((node.lineno, f".{node.module}"))
    return violations


@pytest.mark.parametrize(
    "bp_file",
    sorted(BP_DIR.glob("*.py")),
    ids=lambda p: p.stem,
)
def test_no_cross_blueprint_imports(bp_file):
    if bp_file.stem == "__init__" or bp_file.name.endswith((".bak", ".backup")):
        pytest.skip("not a blueprint")
    violations = _find_cross_imports(bp_file)
    assert violations == [], (
        f"{bp_file.name} cross-imports blueprints: "
        + ", ".join(f"L{ln}: {mod}" for ln, mod in violations)
    )
