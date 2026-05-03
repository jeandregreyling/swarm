"""ops/install/hive_installer_core.py — headless install logic.

This module is deliberately UI-free so the GUI wizard can sit on top
of it AND so we can test every branch without rendering a window.

Public surface:

    probe_leader(url, timeout=5)         -> ProbeResult
    fetch_install_manifest(url, timeout) -> dict
    download_agent(url, dest, timeout)   -> Path
    detect_platform()                    -> "linux"|"macos"|"windows"|"unknown"
    plan_install(leader, node_id=None)   -> InstallPlan
    run_platform_installer(plan, ...)    -> InstallResult

All network operations use std-lib only (urllib + ssl). No third-party
deps. Errors raise InstallerError with a human-readable message.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

USER_AGENT = "swarm-hive-installer/1.0"
DEFAULT_TIMEOUT = 8.0


class InstallerError(RuntimeError):
    """Anything the installer wants the UI to surface verbatim."""


@dataclass
class ProbeResult:
    ok: bool
    leader: str
    reason: str = ""
    leader_version: Optional[str] = None
    node_count: Optional[int] = None
    requires_token: bool = False


@dataclass
class InstallPlan:
    leader: str
    platform: str
    node_id: Optional[str]
    stage_dir: Path
    agent_url: str
    installer_url: str
    installer_filename: str
    python_executable: str = field(default_factory=lambda: sys.executable or "python3")


@dataclass
class InstallResult:
    ok: bool
    detail: str
    log: list[str] = field(default_factory=list)


# ---- platform -------------------------------------------------------------

def detect_platform() -> str:
    sysname = platform.system().lower()
    if sysname == "linux":
        return "linux"
    if sysname == "darwin":
        return "macos"
    if sysname == "windows":
        return "windows"
    return "unknown"


def default_stage_dir(plat: str) -> Path:
    if plat == "windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "swarm-hive"
    if plat == "macos":
        return Path.home() / "Library" / "Application Support" / "swarm-hive"
    # linux + unknown → XDG fallback
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "swarm-hive"


# ---- network --------------------------------------------------------------

def _open(url: str, timeout: float = DEFAULT_TIMEOUT, *, accept_self_signed: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = None
    if url.startswith("https://") and accept_self_signed:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)  # noqa: S310 — explicit url
    except urllib.error.HTTPError as e:
        raise InstallerError(f"HTTP {e.code} from {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise InstallerError(f"could not reach {url}: {e.reason}") from e
    except (TimeoutError, socket.timeout) as e:
        raise InstallerError(f"timed out reaching {url}") from e


def probe_leader(url: str, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    """Hit the leader's /api/hive/install/ manifest and a node count.

    Returns a populated ProbeResult; never raises (errors land in .reason).
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return ProbeResult(ok=False, leader="", reason="leader URL is empty")
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url
    try:
        with _open(f"{url}/api/hive/install/", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except InstallerError as e:
        return ProbeResult(ok=False, leader=url, reason=str(e))
    if not isinstance(data, dict) or not data.get("ok"):
        return ProbeResult(ok=False, leader=url, reason="leader did not return a Hive manifest")
    node_count = None
    try:
        with _open(f"{url}/api/hive/nodes", timeout=timeout) as r:
            nb = json.loads(r.read().decode("utf-8"))
            if isinstance(nb, dict):
                node_count = nb.get("count")
    except InstallerError:
        pass  # nodes endpoint is informational
    return ProbeResult(
        ok=True,
        leader=url,
        leader_version=data.get("version"),
        node_count=node_count,
        requires_token=bool(data.get("requires_token", False)),
    )


def fetch_install_manifest(leader: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    leader = leader.rstrip("/")
    with _open(f"{leader}/api/hive/install/", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download_to(url: str, dest: Path, timeout: float = 30.0,
                progress: Optional[Callable[[int, Optional[int]], None]] = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url, timeout=timeout) as r:
        total_hdr = r.headers.get("Content-Length")
        total = int(total_hdr) if total_hdr and total_hdr.isdigit() else None
        read = 0
        chunk = 64 * 1024
        with open(tmp, "wb") as f:
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                f.write(buf)
                read += len(buf)
                if progress:
                    try:
                        progress(read, total)
                    except Exception:
                        pass
    os.replace(tmp, dest)
    return dest


# ---- install plan ---------------------------------------------------------

_INSTALLER_FILENAMES = {
    "linux":   "install_linux.sh",
    "macos":   "install_macos.sh",
    "windows": "install_windows.ps1",
}


def plan_install(leader: str, *, node_id: Optional[str] = None,
                 plat: Optional[str] = None,
                 stage_dir: Optional[Path] = None) -> InstallPlan:
    leader = leader.rstrip("/")
    if not leader:
        raise InstallerError("leader URL is required")
    p = (plat or detect_platform()).lower()
    if p not in _INSTALLER_FILENAMES:
        raise InstallerError(f"unsupported platform: {p!r}")
    fname = _INSTALLER_FILENAMES[p]
    stage = (stage_dir or default_stage_dir(p)).resolve()
    return InstallPlan(
        leader=leader,
        platform=p,
        node_id=node_id,
        stage_dir=stage,
        agent_url=f"{leader}/api/hive/install/agent.py",
        installer_url=f"{leader}/api/hive/install/{fname}",
        installer_filename=fname,
    )


def stage_artefacts(plan: InstallPlan, *,
                    progress: Optional[Callable[[str, int, Optional[int]], None]] = None) -> tuple[Path, Path]:
    """Download agent + installer into the plan's stage_dir. Returns (agent_path, installer_path)."""
    plan.stage_dir.mkdir(parents=True, exist_ok=True)
    ops_dir = plan.stage_dir / "ops"
    install_dir = ops_dir / "install"
    install_dir.mkdir(parents=True, exist_ok=True)

    agent_dest = ops_dir / "hive_agent.py"
    inst_dest  = install_dir / plan.installer_filename

    def _agent_progress(read: int, total: Optional[int]) -> None:
        if progress: progress("agent", read, total)
    def _inst_progress(read: int, total: Optional[int]) -> None:
        if progress: progress("installer", read, total)

    download_to(plan.agent_url, agent_dest, progress=_agent_progress)
    download_to(plan.installer_url, inst_dest, progress=_inst_progress)
    if plan.platform != "windows":
        try:
            agent_dest.chmod(0o755)
            inst_dest.chmod(0o755)
        except OSError:
            pass
    return agent_dest, inst_dest


# ---- execution ------------------------------------------------------------

def run_platform_installer(plan: InstallPlan, installer_path: Path, *,
                           env: Optional[dict] = None,
                           on_log: Optional[Callable[[str], None]] = None) -> InstallResult:
    """Run the platform installer in a subprocess. Streams stdout to on_log."""
    log: list[str] = []

    def _emit(line: str) -> None:
        log.append(line)
        if on_log:
            try: on_log(line)
            except Exception: pass

    if not installer_path.exists():
        return InstallResult(ok=False, detail=f"installer not staged: {installer_path}", log=log)

    full_env = dict(os.environ)
    full_env["SWARM_HIVE_LEADER"] = plan.leader
    if plan.node_id:
        full_env["SWARM_NODE_ID"] = plan.node_id
    if plan.python_executable:
        full_env["SWARM_HIVE_PYTHON"] = plan.python_executable
    if env:
        full_env.update(env)

    if plan.platform == "windows":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if not powershell:
            return InstallResult(ok=False, detail="powershell not found on PATH", log=log)
        cmd = [powershell, "-ExecutionPolicy", "Bypass", "-File", str(installer_path)]
    else:
        bash = shutil.which("bash")
        if not bash:
            return InstallResult(ok=False, detail="bash not found on PATH", log=log)
        cmd = [bash, str(installer_path)]

    _emit(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(installer_path.parent),
            env=full_env,
            text=True,
            bufsize=1,
        )
    except OSError as e:
        return InstallResult(ok=False, detail=f"could not launch installer: {e}", log=log)

    assert proc.stdout is not None
    for raw in proc.stdout:
        _emit(raw.rstrip("\n"))
    rc = proc.wait()
    if rc == 0:
        return InstallResult(ok=True, detail="installer completed", log=log)
    return InstallResult(ok=False, detail=f"installer exited with code {rc}", log=log)
