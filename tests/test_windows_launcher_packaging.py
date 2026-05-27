from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BUILD_BAT = ROOT / "windows" / "build.bat"
REQ = ROOT / "windows" / "requirements-windows.txt"


def test_windows_build_add_data_sources_exist():
    """Windows PyInstaller data paths must track the live repo layout."""
    src = BUILD_BAT.read_text(encoding="utf-8")
    add_data_args = re.findall(r'--add-data "%ROOT%\\([^;"]+);([^"]+)"', src)
    assert add_data_args, "windows/build.bat must declare PyInstaller data inputs"

    missing = []
    for rel, _dest in add_data_args:
        path = ROOT / Path(rel.replace("\\", "/"))
        if not path.exists():
            missing.append(rel)

    assert not missing, f"missing Windows bundle inputs: {missing}"


def test_windows_build_packages_frontend_services_package():
    src = BUILD_BAT.read_text(encoding="utf-8")
    assert r"%ROOT%\frontend\services;frontend\services" in src
    assert "frontend\\services.py" not in src


def test_windows_requirements_inherit_base_app_requirements():
    req = REQ.read_text(encoding="utf-8")
    assert "-r ../requirements.txt" in req

    build = BUILD_BAT.read_text(encoding="utf-8")
    assert 'pip install -r "%SCRIPT%requirements-windows.txt"' in build
