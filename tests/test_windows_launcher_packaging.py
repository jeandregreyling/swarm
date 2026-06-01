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


def test_windows_msi_installer_files_exist():
    """MSI build pipeline (Slice C) must ship its three companion files."""
    wxs = ROOT / "windows" / "installer" / "Fridays.wxs"
    bat = ROOT / "windows" / "build_msi.bat"
    assert wxs.exists(), "windows/installer/Fridays.wxs missing"
    assert bat.exists(), "windows/build_msi.bat missing"

    wxs_text = wxs.read_text(encoding="utf-8")
    bat_text = bat.read_text(encoding="utf-8")

    # Component group name must match between harvest invocation and .wxs ref
    assert 'Id="HarvestedFiles"' in wxs_text
    assert "-cg HarvestedFiles" in bat_text

    # Per-user scope (no admin)
    assert 'Scope="perUser"' in wxs_text

    # Install root referenced by both shortcuts and harvest must match
    assert 'Id="INSTALLFOLDER"' in wxs_text
    assert "-dr INSTALLFOLDER" in bat_text


def test_windows_requirements_inherit_base_app_requirements():
    req = REQ.read_text(encoding="utf-8")
    assert "-r ../requirements.txt" in req

    build = BUILD_BAT.read_text(encoding="utf-8")
    assert 'pip install -r "%SCRIPT%requirements-windows.txt"' in build


def test_windows_install_and_start_verify_core_imports():
    install = (ROOT / "windows" / "install-fridays.bat").read_text(encoding="utf-8")
    start = (ROOT / "windows" / "start-fridays.bat").read_text(encoding="utf-8")

    assert '"%VENV%\\Scripts\\python.exe" -c "import flask, requests, psutil"' in install
    assert '"%PY%" -c "import flask, requests, psutil"' in start
    assert 'Windows venv exists but core app deps are missing' in start
    assert 'Windows venv still missing core app deps after repair.' in start
