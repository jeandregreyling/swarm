"""V8 Phase-5/6/7 BIG items — source-assertion coverage.

Each test verifies the scaffolding landed. Heavy runtime behaviour (LoRA
training, llama.cpp streaming, Cloudflare Tunnel provisioning, real Gmail
label pull) is intentionally not exercised — those paths depend on external
infrastructure the test runner doesn't have. The tests instead assert the
declared surface area so regressions in shape are caught.
"""
from __future__ import annotations

import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read_doc(rel_path: str) -> str:
    """Read a doc preferring Studio (`project_docs.doc_name`) over disk.

    PACKET-01 moved doc-class .md files into Studio; the disk file is now a
    redirect stub starting with 'Moved into Studio'. Tests asserting content
    must read from Studio first.
    """
    try:
        con = sqlite3.connect(str(ROOT / "swarm_memory.db"))
        try:
            row = con.execute(
                "SELECT content FROM project_docs WHERE doc_name = ?",
                (rel_path,),
            ).fetchone()
        finally:
            con.close()
    except Exception:
        row = None
    if row and row[0] and "Moved into Studio" not in row[0][:200]:
        return row[0]
    return (ROOT / rel_path).read_text()


# ── Phase-7 Seven Runtime (S-C84B33F9A8, S-656DCD475C, S-5E73858F90, ────────
#    S-3F610B254A, S-594AEA9884, S-02DD9A82C1) ────────────────────────────────
def test_seven_runtime_package_shape():
    pkg = ROOT / "core" / "seven_llm"
    assert pkg.is_dir()
    for fname in (
        "__init__.py", "registry.py", "pool.py",
        "driver_base.py", "driver_ollama.py",
        "driver_llamacpp.py", "driver_lmstudio.py", "driver_openai.py",
    ):
        assert (pkg / fname).is_file(), fname


def test_seven_runtime_registry_defaults():
    from core.seven_llm import registry
    names = {m.name for m in registry.list_models()}
    assert "llama3.2:3b" in names
    roles = {m.role for m in registry.list_models()}
    assert {"general", "reasoner", "coder"} <= roles


def test_seven_runtime_pool_acquire_release():
    from core.seven_llm import pool
    entry = pool.acquire("test-model", ram_gb=0.1, ttl_seconds=1)
    assert entry.in_flight == 1
    pool.release("test-model")
    assert entry.in_flight == 0
    pool.sweep(now=pool.time.time() + 5)
    assert "test-model" not in [e["name"] for e in pool.snapshot()]


def test_seven_runtime_driver_abc():
    from core.seven_llm.driver_base import Driver
    assert hasattr(Driver, "chat") and hasattr(Driver, "ps") and hasattr(Driver, "list_models")


def test_seven_runtime_theme_doc():
    txt = _read_doc("docs/SEVEN_RUNTIME.md")
    assert "Feature flag" in txt and "SEVEN_RUNTIME=1" in txt


# ── Phase-7 Remote access (S-6B25D0490E, S-E9D6E762E5, S-E553444811, ────────
#    S-04F364419E, S-4012EC1D09, S-0AEDBBC48B) ─────────────────────────────────
def test_totp_enroll_and_verify_unit():
    from core import auth_2fa
    data = auth_2fa.enroll("pytest_user")
    code = auth_2fa.totp_now(data["secret"])
    assert auth_2fa.verify("pytest_user", code) is True
    assert data["otpauth_url"].startswith("otpauth://totp/")


def test_rate_limiter_basic():
    from core import auth_rate_limit
    key = "pytest:rl"
    for _ in range(5):
        assert auth_rate_limit.allow(key, limit=5, window_s=60)
    assert auth_rate_limit.allow(key, limit=5, window_s=60) is False


def test_auth_2fa_routes_registered():
    src = (ROOT / "frontend" / "blueprints" / "auth.py").read_text()
    assert "/api/auth/2fa/enroll" in src
    assert "/api/auth/2fa/verify" in src
    assert "/api/auth/2fa/status" in src


def test_login_rate_limit_hooked():
    src = (ROOT / "frontend" / "blueprints" / "login_bp.py").read_text()
    assert "auth_rate_limit" in src and "rate_limited" in src


def test_caddy_template_exists():
    txt = (ROOT / "ops" / "caddy" / "Caddyfile.template").read_text()
    assert "{{DOMAIN}}" in txt and "reverse_proxy 127.0.0.1:5050" in txt


def test_cloudflared_template_exists():
    txt = (ROOT / "ops" / "cloudflared" / "config.yml.template").read_text()
    assert "{{TUNNEL_UUID}}" in txt and "ingress:" in txt


def test_remote_access_onboarding_pack():
    txt = (ROOT / "ops" / "onboarding" / "remote_access.yaml").read_text()
    assert "enroll_2fa" in txt and "totp_enroll" in txt


def test_remote_access_theme_doc():
    txt = _read_doc("docs/REMOTE_ACCESS.md")
    assert "/api/auth/2fa/enroll" in txt and "Caddy" in txt and "Cloudflare Tunnel" in txt


# ── Phase-7 Trainer (S-664A2D05E7) ──────────────────────────────────────────
def test_seven_trainer_scaffold():
    p = ROOT / "ops" / "seven_trainer.py"
    src = p.read_text()
    assert "def collect_training_set" in src
    assert "PROMOTE_THRESHOLD" in src
    assert "SEVEN_TRAINER" in src


# ── Phase-6 KC seeds (S-EFF8AD6DFC, S-564D885C69, S-0D3FEA1574) ─────────────
def test_kc_seeds_framework():
    from ops.kc_seeds import _loader as L  # type: ignore
    topics = L.load_all()
    ids = {t.topic_id for t in topics}
    assert {"huggingface", "github", "music_creation", "visual_art_image_generation"} <= ids
    for t in topics:
        assert t.errors == [], f"{t.topic_id}: {t.errors}"


def test_kc_seed_prompts_flow_into_library_seed_docs():
    from lib.knowledge import seed

    docs = seed._all_kc_seed_prompt_docs()
    titles = {d["title"] for d in docs}
    assert any("Music creation" in title for title in titles)
    assert any("Visual art" in title for title in titles)
    assert any(d.get("category") == "creative_media" for d in docs)


def test_kc_seeds_readme():
    txt = _read_doc("ops/kc_seeds/README.md")
    assert "topic_id" in txt and "cadence" in txt


# ── Phase-6 Fan / sysmod / onboarding (S-C194440A7C, S-514BB9FBD3, ──────────
#    S-B4B7DC89E2) ─────────────────────────────────────────────────────────────
def test_fan_cross_platform():
    from core import fan_controller as fc
    s = fc.summary_cross_platform()
    assert "platform" in s and "self_install" in s
    assert fc.self_install_hint()["platform"] in {"linux", "darwin", "windows", "unknown"}


def test_sysmod_pack_yaml():
    txt = (ROOT / "ops" / "onboarding" / "system_modifications.yaml").read_text()
    assert "fan_controller" in txt and "audit/sysmod.log" in txt


def test_sysmod_settings_surface():
    src = (ROOT / "frontend" / "templates" / "terminal_base.html").read_text()
    assert 'id="sysmod-enable-input"' in src
    assert "setSysmodEnabled" in src
    theme = (ROOT / "frontend" / "static" / "js" / "core" / "theme.js").read_text()
    assert "SYSMOD_KEY" in theme and "setSysmodEnabled" in theme


def test_sysmod_blueprint():
    from frontend.blueprints import sysmod as _m  # type: ignore
    assert _m.sysmod_bp is not None


# ── Phase-5 BIG (S-EAA7C440CC, S-DD6BBCDFD7, S-5695672E4C, S-5E5BD3C268, ────
#    S-90F968769C) ─────────────────────────────────────────────────────────────
def test_orbs_overhaul_styles():
    css = (ROOT / "frontend" / "static" / "css" / "taskbar.css").read_text()
    assert '.taskbar-launcher-btn[data-active="1"]' in css
    assert ".taskbar-badge" in css


def test_orbs_overhaul_active_state():
    js = (ROOT / "frontend" / "static" / "js" / "core" / "app.js").read_text()
    assert "openWinIds" in js and "data-active" in js.lower() or "dataset.active" in js


def test_seven_memory_backfill_module():
    from agents.seven import memory_backfill as mb  # type: ignore
    assert hasattr(mb, "run") and hasattr(mb, "repair_thread")
    src = (ROOT / "agents" / "seven" / "memory_backfill.py").read_text()
    assert "thread_2112" in src or "thread 2112" in src or "thread continuity" in src.lower()


def test_gmail_labels_blueprint():
    from frontend.blueprints import gmail_labels as g  # type: ignore
    assert g.gmail_labels_bp is not None
    assert "INBOX" in g.GMAIL_SYSTEM_LABEL_MAP


def test_enrollment_blueprint():
    from frontend.blueprints import enrollment as e  # type: ignore
    assert e.enrollment_bp is not None
    src = (ROOT / "frontend" / "blueprints" / "enrollment.py").read_text()
    assert "/api/enrollment/create" in src and "/api/enrollment/invite" in src


def test_onboarding_launch_toggle_is_visible_and_persists_immediately():
    html = (ROOT / "frontend" / "templates" / "views" / "onboarding.html").read_text()
    js = (ROOT / "frontend" / "static" / "js" / "views" / "onboarding.js").read_text()
    assert 'id="ob-reopen-every-launch"' in html
    assert "_persistLaunchPreference" in js
    assert "addEventListener('change'" in js
    assert "if (!reopen) return;" in js


def test_governance_tab_wired():
    # S-90F968769C: Studio's Governance button opens the modal, state+toggle
    # endpoints exist in the Diamond blueprint, and init.js renders pause
    # state + toggles for governance and vortex separately.
    html = (ROOT / "frontend" / "templates" / "terminal_base.html").read_text()
    assert "studio-btn-governance" in html and "openGovernancePanel()" in html
    init = (ROOT / "frontend" / "static" / "js" / "core" / "init.js").read_text()
    assert "/api/governance/state" in init and "/api/governance/toggle" in init
    assert "Pause Governance" in init and "Pause Vortex" in init
    diamond = (ROOT / "frontend" / "blueprints" / "diamond.py").read_text()
    assert "/api/governance/state" in diamond and "/api/governance/toggle" in diamond


# ── Tauri v2 desktop bundles (S-E7775EAA48) ─────────────────────────────────
def test_tauri_v2_config_and_ui_route():
    conf = (ROOT / "desktop" / "tauri.conf.json").read_text()
    assert "schema.tauri.app/config/2" in conf
    assert "localhost:5050" in conf
    term = (ROOT / "frontend" / "terminal.py").read_text()
    assert '@app.route("/ui"' in term
    build = ROOT / "desktop" / "build.sh"
    assert build.is_file() and "cargo tauri" in build.read_text()
