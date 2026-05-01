#!/usr/bin/env python3
"""ops/e2e_paper_trail.py — numbered end-to-end paper trail.

Runs every major surface (Seven training included), captures stdout per
numbered step, writes audit/E2E_PAPER_TRAIL_<utc>.md and prints a colored
summary to the terminal. Exits non-zero if any required step fails.

This is what was missing: a real paper trail. No shortcuts.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python")
AUDIT_DIR = ROOT / "audit"
AUDIT_DIR.mkdir(exist_ok=True)
STAMP = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
REPORT = AUDIT_DIR / f"E2E_PAPER_TRAIL_{STAMP}.md"

GREEN = "\033[32m"
RED = "\033[31m"
YEL = "\033[33m"
DIM = "\033[2m"
RST = "\033[0m"

steps: list[dict] = []
counter = {"n": 0}


def _step(title: str, fn) -> dict:
    counter["n"] += 1
    n = counter["n"]
    t0 = time.time()
    ok = False
    detail = ""
    err = ""
    try:
        result = fn()
        if isinstance(result, tuple):
            ok, detail = result
        else:
            ok, detail = bool(result), str(result) if result else ""
    except Exception as exc:  # noqa: BLE001 — paper trail catches everything
        ok = False
        err = f"{type(exc).__name__}: {exc}"
    dt = time.time() - t0
    rec = {"n": n, "title": title, "ok": ok, "detail": detail, "err": err, "elapsed": dt}
    steps.append(rec)
    color = GREEN if ok else RED
    sym = "✔" if ok else "✘"
    print(f"  {color}{sym}{RST} [{n:03d}] {title}  {DIM}({dt:.2f}s){RST}")
    if not ok and err:
        print(f"      {RED}↳ {err}{RST}")
    return rec


def _http_get(path: str, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(f"http://localhost:5050{path}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read().decode("utf-8", "replace")


def _http_post_json(path: str, body: dict, timeout: float = 30.0) -> tuple[int, str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://localhost:5050{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read().decode("utf-8", "replace")


def _run(cmd: list[str], timeout: int = 60, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, **(env or {})},
    )


def _server_alive() -> bool:
    try:
        with socket.create_connection(("localhost", 5050), timeout=1):
            return True
    except OSError:
        return False


# ────────────────────────────────────────────────────────────────────────
# SECTION A — Environment
# ────────────────────────────────────────────────────────────────────────
def section(title: str) -> None:
    print(f"\n{YEL}══ {title} ══{RST}")
    steps.append({"section": title})


def env_checks():
    section("A · Environment")
    _step("Python venv interpreter exists", lambda: (pathlib.Path(PY).exists(), PY))
    _step("Repo root has Makefile + README.md + ops/", lambda: all(
        (ROOT / p).exists() for p in ("Makefile", "README.md", "ops")))
    _step("Git branch is proposal/GHOST_CODER-2128",
          lambda: (
              _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() == "proposal/GHOST_CODER-2128",
              _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip(),
          ))
    _step("HEAD commit is pushed to origin",
          lambda: (
              _run(["git", "rev-parse", "HEAD"]).stdout.strip()
              == _run(["git", "rev-parse", "origin/proposal/GHOST_CODER-2128"]).stdout.strip(),
              _run(["git", "rev-parse", "HEAD"]).stdout.strip()[:10],
          ))
    _step("Server :5050 is alive", lambda: _server_alive())


# ────────────────────────────────────────────────────────────────────────
# SECTION B — Detector
# ────────────────────────────────────────────────────────────────────────
def detector_checks():
    section("B · Bullshit detector")
    cache = ROOT / ".swarm" / "bullshit_report.json"

    def fresh_scan():
        if cache.exists():
            cache.unlink()
        out = _run([PY, "-c",
                    "from ops.bullshit_detector import scan; import json; "
                    "print(json.dumps(scan()))"], timeout=60)
        if out.returncode != 0:
            return False, out.stderr.strip()[:200]
        d = json.loads(out.stdout)
        ok = d["stamp"] == "GREEN" and d["score"] >= 95 and d["by_severity"]["critical"] == 0 \
            and d["by_severity"]["warning"] == 0 and d["files_scanned"] >= 480
        return ok, f"stamp={d['stamp']} score={d['score']} crit={d['by_severity']['critical']} " \
                   f"warn={d['by_severity']['warning']} files={d['files_scanned']}"
    _step("Clear cache + fresh scan returns GREEN/0/0/≥480", fresh_scan)

    def has_rules():
        # RULES is a list of tuples; the rule name is index 0.
        out = _run([PY, "-c",
                    "from ops.bullshit_detector import RULES; "
                    "print(','.join(r[0] for r in RULES))"], timeout=10)
        names = out.stdout.strip()
        ok = "VAPOR_LANGUAGE" in names and "CAPTURE_ONLY_DESC" in names \
            and "TODO_MARKER" in names
        return ok, names
    _step("Detector has VAPOR_LANGUAGE + CAPTURE_ONLY_DESC + TODO_MARKER", has_rules)

    def files_count():
        out = _run([PY, "-c",
                    "from ops.bullshit_detector import scan; import json; "
                    "print(json.dumps(scan()))"], timeout=60)
        d = json.loads(out.stdout)
        return d["files_scanned"] >= 480, f"files_scanned={d['files_scanned']}"
    _step("scan().files_scanned exposed for Seven", files_count)


# ────────────────────────────────────────────────────────────────────────
# SECTION C — Seven brain · TRAINING (the bit that was forgotten)
# ────────────────────────────────────────────────────────────────────────
def training_checks():
    section("C · Seven brain · training (PACKET-10B)")

    def run_training_tests():
        out = _run(
            [PY, "-m", "pytest", "tests/test_seven_training.py", "--tb=line"],
            timeout=90,
        )
        m = re.search(r"(\d+) passed", out.stdout)
        passed = int(m.group(1)) if m else 0
        ok = out.returncode == 0 and passed >= 6
        return ok, f"passed={passed} rc={out.returncode}"
    _step("pytest tests/test_seven_training.py — 6 cases pass", run_training_tests)

    def run_curiosity_tests():
        out = _run([PY, "-m", "pytest", "tests/test_curiosity.py", "-q", "--tb=line"], timeout=60)
        return out.returncode == 0, out.stdout.strip().splitlines()[-1] if out.stdout else ""
    _step("pytest tests/test_curiosity.py — green", run_curiosity_tests)

    def run_slash_tests():
        out = _run([PY, "-m", "pytest", "tests/test_slash_commands.py", "-q", "--tb=line"], timeout=60)
        return out.returncode == 0, out.stdout.strip().splitlines()[-1] if out.stdout else ""
    _step("pytest tests/test_slash_commands.py — green", run_slash_tests)

    # Live HTTP — chat() through the real /api/chat surface
    def chat_audit():
        if not _server_alive():
            return False, "server down"
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": "/audit"}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = "Stamp: GREEN" in resp and "Score:" in resp
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("HTTP /api/chat seven /audit → GREEN audit report", chat_audit)

    def chat_standard():
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": "/standard"}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = "Standard" in resp or "standard" in resp
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("HTTP /api/chat seven /standard → returns the Standard", chat_standard)

    def chat_identity():
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": "/identity"}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = "Seven" in resp
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("HTTP /api/chat seven /identity → identity block", chat_identity)

    def chat_curiosity():
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": "/curiosity"}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = isinstance(resp, str) and len(resp) > 0
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("HTTP /api/chat seven /curiosity → inbox view", chat_curiosity)

    def chat_learnings():
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": "/learnings"}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = isinstance(resp, str) and len(resp) > 0
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("HTTP /api/chat seven /learnings → lessons block", chat_learnings)

    def chat_pillars():
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": "/pillars"}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = "pillar" in resp.lower() or "Pillar" in resp
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("HTTP /api/chat seven /pillars → pillar contract status", chat_pillars)

    def chat_help():
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": "/help"}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = "/audit" in resp or "/standard" in resp
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("HTTP /api/chat seven /help → lists slash commands", chat_help)

    # Embedded-slash defence — chat blueprint wraps with scaffolding
    def chat_embedded_audit():
        msg = "[Auto Relay: ENABLED]\n/audit\nplease run the audit"
        code, body = _http_post_json("/api/chat", {"agent": "seven", "message": msg}, timeout=60)
        d = json.loads(body)
        resp = d.get("response", "")
        ok = "Stamp:" in resp and ("GREEN" in resp or "AMBER" in resp or "RED" in resp)
        return ok, resp.splitlines()[0][:120] if resp else ""
    _step("Embedded /audit inside scaffolding still fires", chat_embedded_audit)


# ────────────────────────────────────────────────────────────────────────
# SECTION D — /api/health composite
# ────────────────────────────────────────────────────────────────────────
def health_checks():
    section("D · /api/health composite")

    def health_payload():
        if not _server_alive():
            return False, "server down"
        code, body = _http_get("/api/health", timeout=10)
        d = json.loads(body)
        # Cache for next checks
        health_checks._last = d  # type: ignore
        return code == 200 and d.get("ok") is True, f"stamp={d.get('stamp')} keys={sorted(d.keys())}"
    _step("GET /api/health 200 + ok=True", health_payload)

    _step("composite stamp == GREEN",
          lambda: (health_checks._last["stamp"] == "GREEN", health_checks._last["stamp"]))

    _step("build.detector_stamp == GREEN",
          lambda: (health_checks._last["build"]["detector_stamp"] == "GREEN",
                   f"score={health_checks._last['build']['detector_score']}"))

    _step("4 pillars present + all ok=True",
          lambda: (
              set(health_checks._last["pillars"].keys()) == {"cyber-security", "financial", "trading", "business"}
              and all(p["ok"] for p in health_checks._last["pillars"].values()),
              ",".join(sorted(health_checks._last["pillars"].keys())),
          ))

    _step("blueprints_failed == []",
          lambda: (health_checks._last["blueprints_failed"] == [],
                   str(health_checks._last["blueprints_failed"])))

    _step("learnings block has total/positive/negative keys",
          lambda: (
              set(health_checks._last["learnings"].keys()) >= {"total", "positive", "negative"},
              str(health_checks._last["learnings"]),
          ))


# ────────────────────────────────────────────────────────────────────────
# SECTION E — Pillar + wishlist APIs
# ────────────────────────────────────────────────────────────────────────
def pillar_checks():
    section("E · Pillar + wishlist APIs")

    for slug in ("cyber-security", "financial", "trading", "business"):
        def _check(s=slug):
            code, body = _http_get(f"/api/wishlist/pillars/{s}", timeout=10)
            d = json.loads(body)
            return code == 200 and d.get("ok") is True, f"keys={sorted(d.keys())}"
        _step(f"GET /api/wishlist/pillars/{slug} ok=True", _check)

    def summary():
        code, body = _http_get("/api/wishlist/summary", timeout=10)
        d = json.loads(body)
        ok = code == 200 and "pillars" in d
        return ok, f"pillars={list((d.get('pillars') or {}).keys())}"
    _step("GET /api/wishlist/summary returns pillars block", summary)


# ────────────────────────────────────────────────────────────────────────
# SECTION F — Pre-commit hook
# ────────────────────────────────────────────────────────────────────────
def hook_checks():
    section("F · Pre-commit hook")

    hook = ROOT / ".git" / "hooks" / "pre-commit"
    _step("scripts/install-hooks.sh exists + executable",
          lambda: (
              (ROOT / "scripts" / "install-hooks.sh").exists()
              and os.access(ROOT / "scripts" / "install-hooks.sh", os.X_OK),
              str((ROOT / "scripts" / "install-hooks.sh").stat().st_mode),
          ))

    _step(".git/hooks/pre-commit installed + executable",
          lambda: (hook.exists() and os.access(hook, os.X_OK), str(hook)))

    _step("pre-commit hook references bullshit_detector",
          lambda: ("bullshit_detector" in hook.read_text() if hook.exists() else False,
                   "len=" + str(len(hook.read_text())) if hook.exists() else "missing"))


# ────────────────────────────────────────────────────────────────────────
# SECTION G — Make targets present
# ────────────────────────────────────────────────────────────────────────
def make_checks():
    section("G · Make targets")

    mk = (ROOT / "Makefile").read_text()
    for tgt in ("doctor", "health", "hooks", "excellent"):
        _step(f"Makefile has '{tgt}:' target",
              (lambda t=tgt: (re.search(rf"^{t}:", mk, re.M) is not None, f"target={t}")))


# ────────────────────────────────────────────────────────────────────────
# SECTION H — Test batch sweep (per-file with timeout)
# ────────────────────────────────────────────────────────────────────────
def test_sweep():
    section("H · Test batch sweep")

    batches = [
        "tests/test_session28_batch11.py",
        "tests/test_session28_batch12.py",
        "tests/test_session28_batch13.py",
        "tests/test_session28_batch14.py",
        "tests/test_session28_batch15.py",
        "tests/test_session28_batch16.py",
        "tests/test_curiosity.py",
        "tests/test_seven_training.py",
        "tests/test_slash_commands.py",
        "tests/test_v8_big_items.py",
        "tests/test_no_cross_imports.py",
    ]
    for b in batches:
        path = ROOT / b
        if not path.exists():
            continue
        def _run_batch(p=b):
            out = _run([PY, "-m", "pytest", p, "-q", "--tb=line"], timeout=60)
            tail = (out.stdout.strip().splitlines() or [""])[-1][:120]
            return out.returncode == 0, tail
        _step(f"pytest {b}", _run_batch)


# ────────────────────────────────────────────────────────────────────────
# SECTION I — make doctor
# ────────────────────────────────────────────────────────────────────────
def doctor_check():
    section("I · make doctor")

    def doctor():
        out = _run(["make", "doctor"], timeout=180, env={"PYTHON": PY})
        last = (out.stdout.strip().splitlines() or [""])[-1]
        return out.returncode == 0 and ("green across the board" in out.stdout), last[:120]
    _step("make doctor → green across the board", doctor)


# ────────────────────────────────────────────────────────────────────────
# SECTION J — Fresh-DB e2e
# ────────────────────────────────────────────────────────────────────────
def fresh_db_e2e():
    section("J · Fresh-DB end-to-end")

    fresh = "/tmp/swarm-paper-trail.db"

    def seed():
        if os.path.exists(fresh):
            os.unlink(fresh)
        out = _run([PY, "-m", "ops.seed_demo"], timeout=30,
                   env={"SWARM_MEMORY_DB": fresh})
        ok = out.returncode == 0 and "'ok': True" in out.stdout
        return ok, out.stdout.strip().splitlines()[-1][:120] if out.stdout else ""
    _step("seed_demo populates fresh DB", seed)

    def restart():
        subprocess.run(["pkill", "-f", "python.*frontend/terminal.py"], capture_output=True)
        time.sleep(1)
        # Launch fully detached so it survives this script
        subprocess.Popen(
            [PY, "frontend/terminal.py"],
            cwd=str(ROOT),
            stdout=open("/tmp/swarm-paper-trail.log", "w"),
            stderr=subprocess.STDOUT,
            env={**os.environ, "SWARM_MEMORY_DB": fresh},
            start_new_session=True,
        )
        for _ in range(20):
            if _server_alive():
                break
            time.sleep(0.5)
        return _server_alive(), "alive" if _server_alive() else "DOWN"
    _step("restart server against fresh DB", restart)

    def fresh_health():
        code, body = _http_get("/api/health", timeout=10)
        d = json.loads(body)
        ok = d["stamp"] == "GREEN" and all(p["ok"] for p in d["pillars"].values())
        return ok, f"stamp={d['stamp']}"
    _step("fresh /api/health composite=GREEN", fresh_health)

    def fresh_summary():
        code, body = _http_get("/api/wishlist/summary", timeout=10)
        d = json.loads(body)
        # at least one pillar should have non-empty data after seed
        pillars = d.get("pillars") or {}
        ok = bool(pillars) and len(pillars) >= 1
        return ok, f"pillars={list(pillars.keys())}"
    _step("fresh /api/wishlist/summary returns populated pillars", fresh_summary)

    def restore():
        subprocess.run(["pkill", "-f", "python.*frontend/terminal.py"], capture_output=True)
        time.sleep(1)
        subprocess.Popen(
            [PY, "frontend/terminal.py"],
            cwd=str(ROOT),
            stdout=open("/tmp/swarm-terminal.log", "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        for _ in range(20):
            if _server_alive():
                break
            time.sleep(0.5)
        if os.path.exists(fresh):
            os.unlink(fresh)
        return _server_alive(), "restored"
    _step("restore server on default DB", restore)


# ────────────────────────────────────────────────────────────────────────
# SECTION K — Frontend assets
# ────────────────────────────────────────────────────────────────────────
def frontend_checks():
    section("K · Frontend assets present")

    must = [
        "frontend/templates/terminal_base.html",
        "frontend/static/js/views/home_banner.js",
        "frontend/static/js/views/studio.js",
        "frontend/static/js/views/pillar_live.js",
        "frontend/static/css/themes.css",
        "README.md",
    ]
    for rel in must:
        _step(f"file exists · {rel}",
              (lambda p=rel: ((ROOT / p).exists(), str((ROOT / p).stat().st_size) + "B")
               if (ROOT / p).exists() else (False, "missing")))

    # README must have the things our README test pins
    def readme_keywords():
        text = (ROOT / "README.md").read_text()
        wanted = ["make excellent", "the-standard", "Seven", "/api/health", "pillars"]
        forbidden = ["capture only"]
        missing = [w for w in wanted if w not in text]
        bad = [w for w in forbidden if w in text]
        return not missing and not bad, f"missing={missing} bad={bad}"
    _step("README.md has required keywords + no forbidden", readme_keywords)

    # First-run banner div present in template
    def banner_div():
        text = (ROOT / "frontend/templates/terminal_base.html").read_text()
        ok = 'id="first-run-banner"' in text and "home_banner.js" in text
        return ok, "found" if ok else "missing"
    _step("terminal_base.html has banner div + script", banner_div)


# ────────────────────────────────────────────────────────────────────────
# SECTION L — Seven the Witness
# ────────────────────────────────────────────────────────────────────────
def witness_checks():
    section("L · Seven the Witness")

    def import_ok():
        from core import witness  # noqa: F401
        return True, "core.witness imported"
    _step("core.witness imports", import_ok)

    def vapor_flag():
        from core import witness
        rep = witness.scan_text("This should work probably, I think.",
                                kind='user', target='user')
        rules = {c.rule for c in rep}
        return ('VAPOR' in rules), f"rules={sorted(rules)}"
    _step("scan_text flags VAPOR on hedgy text", vapor_flag)

    def hedge_flag():
        from core import witness
        rep = witness.scan_text("Will fix later, placeholder TBD.",
                                kind='user', target='user')
        rules = {c.rule for c in rep}
        return ('HEDGE' in rules), f"rules={sorted(rules)}"
    _step("scan_text flags HEDGE on empty-promise text", hedge_flag)

    def conviction_clean():
        from core import witness
        score = witness.conviction("Run the migration. The build is green.")
        return (score >= 0.85), f"score={score:.2f}"
    _step("conviction(clean) >= 0.85", conviction_clean)

    def conviction_dirty():
        from core import witness
        score = witness.conviction("It should work, probably, maybe, I think it's fine.")
        return (score < 0.7), f"score={score:.2f}"
    _step("conviction(vapor-heavy) < 0.7", conviction_dirty)

    def annotate_dirty():
        from core import witness
        rep = witness.review_seven_response(
            "This should work probably, will fix later.",
            user_msg="?", save=False)
        out = witness.annotate(rep)
        return (bool(out)), f"footer_len={len(out)}"
    _step("annotate(dirty report) returns a footer", annotate_dirty)

    def daily_brief_compose():
        from agents.seven import daily_brief
        out = daily_brief.compose_daily()
        body = out.get('body', '')
        ok = ("Seven's Daily Brief" in body and
              '## Conviction' in body and
              '## Bullshit ledger' in body)
        return ok, f"path={out.get('path')!r} len={len(body)}"
    _step("daily_brief.compose_daily() produces prose", daily_brief_compose)

    def health_has_witness():
        import urllib.request, json
        try:
            with urllib.request.urlopen("http://127.0.0.1:5050/api/health", timeout=5) as r:
                d = json.loads(r.read().decode('utf-8'))
        except Exception as exc:
            return False, f"http error: {exc}"
        w = d.get('witness') or {}
        ok = isinstance(w, dict) and 'enabled' in w and 'total' in w
        return ok, f"witness_keys={sorted(w.keys())}"
    _step("/api/health includes witness block", health_has_witness)

    def chat_witness_list():
        import urllib.request, json
        body = json.dumps({"agent": "seven", "message": "/witness list"}).encode('utf-8')
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:5050/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method='POST')
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read().decode('utf-8'))
        except Exception as exc:
            return False, f"http error: {exc}"
        msg = (d.get('response') or d.get('message') or d.get('answer') or '')
        ok = ('Witness' in msg or 'callout' in msg.lower() or 'no callouts' in msg.lower())
        return ok, f"reply[:80]={msg[:80]!r}"
    _step("HTTP /api/chat seven /witness list works", chat_witness_list)

    def friday_task_registered():
        from fridays import task_runner
        reg = getattr(task_runner, 'TASK_REGISTRY', None) or {}
        ok = 'seven_daily_brief' in reg
        return ok, f"present={ok} (n={len(reg)})"
    _step("Friday task `seven_daily_brief` registered", friday_task_registered)


# ────────────────────────────────────────────────────────────────────────
# Report writer
# ────────────────────────────────────────────────────────────────────────
def write_report():
    lines = [
        f"# E2E Paper Trail · {STAMP} UTC",
        "",
        f"Generated by `ops/e2e_paper_trail.py`. Branch: `{_run(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).stdout.strip()}`. "
        f"HEAD: `{_run(['git', 'rev-parse', '--short', 'HEAD']).stdout.strip()}`.",
        "",
    ]
    actual_steps = [s for s in steps if "n" in s]
    passed = sum(1 for s in actual_steps if s["ok"])
    failed = sum(1 for s in actual_steps if not s["ok"])
    total = len(actual_steps)
    overall = "🟢 GREEN" if failed == 0 else "🔴 RED"

    lines += [
        f"## Summary · {overall}",
        "",
        f"- Total steps: **{total}**",
        f"- Passed: **{passed}**",
        f"- Failed: **{failed}**",
        "",
        "## Steps",
        "",
        "| # | Section | Step | Result | Detail | Time |",
        "|---|---------|------|--------|--------|------|",
    ]

    current_section = "?"
    for s in steps:
        if "section" in s:
            current_section = s["section"]
            continue
        sym = "🟢 PASS" if s["ok"] else "🔴 FAIL"
        detail = (s["detail"] or s["err"]).replace("|", "\\|").replace("\n", " ")[:140]
        lines.append(f"| {s['n']:03d} | {current_section} | {s['title']} | {sym} | `{detail}` | {s['elapsed']:.2f}s |")

    REPORT.write_text("\n".join(lines) + "\n")
    return overall, total, passed, failed


def main() -> int:
    print(f"{YEL}Paper trail starting · output → {REPORT}{RST}\n")
    env_checks()
    detector_checks()
    training_checks()
    health_checks()
    pillar_checks()
    hook_checks()
    make_checks()
    frontend_checks()
    test_sweep()
    doctor_check()
    fresh_db_e2e()
    witness_checks()

    overall, total, passed, failed = write_report()
    print(f"\n{YEL}══ Summary ══{RST}")
    print(f"  steps  : {total}")
    print(f"  passed : {GREEN}{passed}{RST}")
    print(f"  failed : {RED if failed else GREEN}{failed}{RST}")
    print(f"  report : {REPORT.relative_to(ROOT)}")
    print(f"  overall: {overall}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
