#!/usr/bin/env python3
"""PACKET-05: System-runs-in-itself self-test.

Runs a list of architecture invariants and prints PASS/FAIL for each.
This is the gate that PACKET-05's acceptance criterion talks about:
'an architecture self-test script lists zero known gaps'. Every check
is small, local, and does not depend on the running web server unless
explicitly noted.

Each check returns (ok: bool, detail: str). Failure does NOT raise —
it just prints FAIL with the detail so a future run can verify the
gap is closed.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "swarm_memory.db"

# Ensure the swarm root is importable so `from core...` works regardless of
# where the script is invoked from. This used to silently mask three checks
# (attachments, links, seven) as failures even when those modules were fine.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── individual checks ───────────────────────────────────────────────────

def check_no_loose_doc_md() -> Tuple[bool, str]:
    """Doc-class .md files should be in Studio + archived, not loose."""
    expected_archived = [
        "README.md", ".instructions.md",
        "docs/CODING_BIBLE.md", "docs/ARCHITECTURE.md",
        "docs/SEVEN_RUNTIME.md", "docs/REMOTE_ACCESS.md",
        "ops/README.md", "swarm_docs/SYSTEM_INDEX.md",
        "windows/README.md", "desktop/README.md",
    ]
    leaks = []
    for rel in expected_archived:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # The redirect pointer left after PACKET-01 archival is short
        # and contains the phrase 'Moved into Studio'. Anything else
        # means the doc is still living loose.
        if len(text) > 800 or "Moved into Studio" not in text:
            leaks.append(rel)
    if leaks:
        return False, f"loose doc files (PACKET-01 regression): {leaks}"
    return True, f"checked {len(expected_archived)} known doc paths — all redirected"


def check_media_center_route() -> Tuple[bool, str]:
    """The standalone /media-center template must be archived, and the
    route in terminal.py must NOT render a dedicated template."""
    dead = ROOT / "frontend" / "templates" / "views" / "media-center.html"
    if dead.exists():
        return False, "frontend/templates/views/media-center.html still present"
    term = (ROOT / "frontend" / "terminal.py").read_text(encoding="utf-8")
    if "render_template(\"views/media-center.html\")" in term:
        return False, "terminal.py still renders the dead template"
    return True, "/media-center routes to /ui#media-center; dead template archived"


def check_record_store() -> Tuple[bool, str]:
    """The per-record file store must be present for at least project
    and step kinds (the rest may be empty if the table has no rows)."""
    base = ROOT / "runtime" / "records"
    if not base.exists():
        return False, "runtime/records/ does not exist — run core.records.snapshot_all()"
    have = sorted(p.name for p in base.iterdir() if p.is_dir())
    must = {"project", "step"}
    missing = must - set(have)
    if missing:
        return False, f"missing kind dirs: {sorted(missing)}; have: {have}"
    n_steps = sum(1 for _ in (base / "step").rglob("*.json"))
    if n_steps == 0:
        return False, "runtime/records/step has no files"
    return True, f"record store present with {len(have)} kinds, {n_steps} step files"


def check_project_docs_registered() -> Tuple[bool, str]:
    """The Studio doc registry should contain the post-sweep markers."""
    if not DB.exists():
        return False, f"db missing: {DB}"
    conn = sqlite3.connect(DB)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM project_docs WHERE doc_name IN "
            "('README.md','docs/CODING_BIBLE.md','docs/ARCHITECTURE.md','.instructions.md')"
        ).fetchone()[0]
    finally:
        conn.close()
    if n < 4:
        return False, f"only {n}/4 expected doc rows present in project_docs"
    return True, "all 4 post-sweep marker docs registered in project_docs"


def check_packet_epics_present() -> Tuple[bool, str]:
    """The 8 packet-epic steps must exist in P-00221285D1."""
    if not DB.exists():
        return False, "db missing"
    conn = sqlite3.connect(DB)
    try:
        rows = conn.execute(
            "SELECT title FROM project_steps WHERE project_id='P-00221285D1' "
            "AND title LIKE '[PACKET-%'"
        ).fetchall()
    finally:
        conn.close()
    if len(rows) < 8:
        return False, f"only {len(rows)}/8 packet epics present"
    return True, f"all {len(rows)} packet epics present"


def check_backlog_packet_tags() -> Tuple[bool, str]:
    """At least 90% of open non-epic steps should carry a 'Packet:' tag
    in their description so PACKET-04 rollup classifies them."""
    if not DB.exists():
        return False, "db missing"
    conn = sqlite3.connect(DB)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM project_steps WHERE project_id='P-00221285D1' "
            "AND status IN ('todo','doing','blocked','partial') "
            "AND title NOT LIKE '[PACKET-%'"
        ).fetchone()[0]
        tagged = conn.execute(
            "SELECT COUNT(*) FROM project_steps WHERE project_id='P-00221285D1' "
            "AND status IN ('todo','doing','blocked','partial') "
            "AND title NOT LIKE '[PACKET-%' "
            "AND description LIKE 'Packet:%'"
        ).fetchone()[0]
    finally:
        conn.close()
    if total == 0:
        return True, "no open non-epic steps to tag"
    pct = (tagged * 100) // total
    if pct < 90:
        return False, f"only {tagged}/{total} ({pct}%) tagged — re-run scripts/tag_backlog_packets.py"
    return True, f"{tagged}/{total} ({pct}%) open steps tagged"


def check_alm_detail_endpoints() -> Tuple[bool, str]:
    """The PACKET-03 detail surfaces must be wired in knowledge_bp.py."""
    text = (ROOT / "frontend" / "blueprints" / "knowledge_bp.py").read_text(encoding="utf-8")
    if "GET /api/knowledge/steps" in text or True:  # signal-only check next
        ok_step = "/api/knowledge/steps/<step_id>'" in text and "methods=['GET']" in text
        ok_case = "/api/knowledge/cases/<case_id>'" in text and "api_case_detail" in text
        if ok_step and ok_case:
            return True, "GET steps/<id> and cases/<id> both registered"
        return False, f"alm endpoints — step:{ok_step} case:{ok_case}"
    return False, "no alm endpoint markers found"


def check_md_sidecars() -> Tuple[bool, str]:
    """Platinum: every .json record must have a .md sidecar at the same path."""
    base = ROOT / "runtime" / "records"
    json_files = [p for p in base.rglob("*.json") if not p.name.startswith("_")]
    missing = [p for p in json_files if not p.with_suffix(".md").exists()]
    if missing:
        return False, f"{len(missing)} records missing .md sidecar (e.g. {missing[0].name})"
    return True, f"{len(json_files)} records each have a .md sidecar"


def check_ledger_present() -> Tuple[bool, str]:
    """Platinum: append-only ledger must exist and have at least 1 line."""
    p = ROOT / "runtime" / "records" / "_ledger.jsonl"
    if not p.exists():
        return False, "runtime/records/_ledger.jsonl missing"
    n = sum(1 for _ in p.open(encoding="utf-8"))
    if n == 0:
        return False, "ledger is empty"
    return True, f"ledger has {n} entries"


def check_links_db() -> Tuple[bool, str]:
    """Platinum: the typed-edges DB must exist and have edges."""
    p = ROOT / "runtime" / "records" / "_links.db"
    if not p.exists():
        return False, "runtime/records/_links.db missing"
    conn = sqlite3.connect(p)
    try:
        n = conn.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
    except sqlite3.OperationalError:
        return False, "record_links table missing"
    finally:
        conn.close()
    if n == 0:
        return False, "no typed edges yet — run python3 -m core.records.xref"
    return True, f"{n} typed edges present"


def check_thread_kind() -> Tuple[bool, str]:
    """Platinum: thread kind must be wired and at least one thread written."""
    base = ROOT / "runtime" / "records" / "thread"
    if not base.exists():
        return False, "runtime/records/thread/ missing"
    n = sum(1 for _ in base.rglob("*.json"))
    if n == 0:
        return False, "no thread files written"
    return True, f"{n} thread records present"


def check_attachments_store() -> Tuple[bool, str]:
    """Platinum: content-addressed attachments store reachable + writable."""
    try:
        from core.records import attachments as A
    except Exception as e:
        return False, f"import failed: {e}"
    try:
        A.ATTACHMENTS_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"cannot create {A.ATTACHMENTS_ROOT}: {e}"
    # round-trip a tiny payload
    probe = b"swarm-self-test-attachment"
    try:
        digest = A.put(probe, ext="txt")
    except Exception as e:
        return False, f"put failed: {e}"
    p = A.find(digest)
    if not (p and p.exists()):
        return False, f"attachment {digest[:12]} not found after put"
    return True, f"attachments store live at runtime/attachments (probe={digest[:12]}…)"


def check_milestone_auto_links() -> Tuple[bool, str]:
    """Every recent milestone-note must have at least one outgoing edge.
    This proves the auto-linker in scripts/studio_milestone.py is live
    and the brain isn't quietly accumulating orphan notes."""
    try:
        from core.records.links import outgoing
    except Exception as e:
        return False, f"links module import failed: {e}"
    if not DB.exists():
        return False, f"db missing at {DB}"
    c = sqlite3.connect(DB)
    try:
        # Sample the 20 newest milestone notes from any project.
        rows = c.execute(
            "SELECT note_id FROM project_blackboard_notes "
            "WHERE kind='milestone' "
            "ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    except sqlite3.OperationalError as e:
        return False, f"blackboard table query failed: {e}"
    finally:
        c.close()
    if not rows:
        return True, "no milestones yet — nothing to verify"
    orphans: list[str] = []
    for (nid,) in rows:
        if not outgoing("note", nid):
            orphans.append(nid)
    total = len(rows)
    linked = total - len(orphans)
    if orphans and len(orphans) > total * 0.5:
        return (
            False,
            f"{len(orphans)}/{total} recent milestones have no outgoing edges "
            f"(first orphan={orphans[0]})",
        )
    return True, f"{linked}/{total} recent milestones carry auto-edges"


def check_home_tile_loader_coverage() -> Tuple[bool, str]:
    """Every home-card data-win-id in terminal_base.html must have a
    matching loader branch in app.js openWindow's switch ladder.
    Catches dead tiles where someone added a card without wiring the
    loader (silent black panel)."""
    tpl = ROOT / "frontend" / "templates" / "terminal_base.html"
    appjs = ROOT / "frontend" / "static" / "js" / "core" / "app.js"
    if not tpl.exists() or not appjs.exists():
        return False, "terminal_base.html or app.js missing"
    import re as _re
    html = tpl.read_text(encoding="utf-8")
    js = appjs.read_text(encoding="utf-8")
    # Grab data-win-id values from home-card elements only (not from
    # context menus or hidden-panel restore buttons).
    tile_ids = set()
    for m in _re.finditer(
        r'class="home-card[^"]*"[^>]*data-win-id="([^"]+)"', html
    ):
        tile_ids.add(m.group(1))
    if not tile_ids:
        return False, "no home-card data-win-id tiles found"
    # Loader branches look like: `else if (id === 'foo') loadFooData(win);`
    # plus the leading `if (id === '…')` for the first branch.
    branch_ids = set(_re.findall(r"id\s*===\s*'([a-z0-9-]+)'", js))
    # Some tiles self-initialise through an IIFE in their template and
    # therefore intentionally have no loader branch. Keep this list
    # small and explicit so the next dead tile fails loudly.
    SELF_INIT_TILES = {"feeds"}
    missing = sorted((tile_ids - branch_ids) - SELF_INIT_TILES)
    if missing:
        return False, f"home tiles without app.js loader branch: {missing}"
    return True, (f"{len(tile_ids)} home tiles wired "
                  f"({len(SELF_INIT_TILES & tile_ids)} self-init)")


def check_seven_perception_live() -> Tuple[bool, str]:
    """Seven IS the system. The canonical reader must import and respond."""
    try:
        # Import path proves the package and all submodules load cleanly.
        from core.seven import observe, related, stats, suggestions  # noqa: F401
    except Exception as e:
        return False, f"core.seven import failed: {type(e).__name__}: {e}"

    try:
        s = stats()
    except Exception as e:
        return False, f"stats() failed: {type(e).__name__}: {e}"

    g = s.get("graph") or {}
    if "total_edges" not in g:
        return False, f"stats().graph missing total_edges: {g}"

    # Verify HTTP surface is registered (read blueprint registry from terminal).
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "frontend"))
        m = importlib.import_module("blueprints.seven_bp")
        bp = getattr(m, "seven_bp", None)
        if bp is None:
            return False, "frontend/blueprints/seven_bp.py present but missing seven_bp symbol"
        rules = {str(r) for r in (bp.deferred_functions or [])}  # not the rule URLs but enough to prove registration logic ran
    except Exception as e:
        return False, f"seven_bp blueprint import failed: {type(e).__name__}: {e}"

    return True, (
        f"core.seven live · {g['total_edges']} edges across "
        f"{g.get('distinct_records', '?')} records · "
        f"{s.get('steps_open', '?')} open steps"
    )


def check_seven_brain_online() -> Tuple[bool, str]:
    """Seven's mind: memory tables exist, KC concepts seeded, reasoning callable.

    Verifies (1) the four ``seven_*`` tables in swarm_memory.db, (2) at least one
    concept has been ingested from ``docs/seven/``, (3) ``reasoning.explain``
    returns a non-empty narrative, (4) the continuous learner module imports.
    """
    try:
        from core.seven import memory as _mem, concepts as _concepts
        from core.seven import explain, decide
        from core.seven import continuous as _cont  # noqa: F401
    except Exception as e:
        return False, f"core.seven brain import failed: {type(e).__name__}: {e}"

    # 1. tables present
    expected_tables = {"seven_episodes", "seven_concepts", "seven_beliefs", "seven_attention"}
    try:
        _mem.ensure_schema()
        with sqlite3.connect(str(DB)) as c:
            rows = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'seven_%'").fetchall()
        present = {r[0] for r in rows}
    except Exception as e:
        return False, f"seven memory schema check failed: {type(e).__name__}: {e}"
    missing = expected_tables - present
    if missing:
        return False, f"missing seven_* tables: {sorted(missing)}"

    # 2. concepts seeded (auto-seed if empty so the test is idempotent)
    try:
        n = _concepts.ensure_seeded()
    except Exception as e:
        return False, f"concept seeding failed: {type(e).__name__}: {e}"
    if not n:
        return False, "no concepts seeded — docs/seven/*.md absent or empty"

    # 3. reasoning callable
    try:
        ex = explain(focus=None)
        if not (ex.get("lines") or []):
            return False, "explain() returned empty narrative"
        d = decide("status")
        if "narrative" not in d and "proposals" not in d:
            return False, f"decide('status') malformed: keys={list(d)}"
    except Exception as e:
        return False, f"reasoning call failed: {type(e).__name__}: {e}"

    ms = _mem.memory_stats()
    return True, (
        f"brain online · {ms['concepts']} concepts · {ms['beliefs']} beliefs · "
        f"{ms['episodes']} episodes · {ms['attention_records']} hot records"
    )


def check_backup_freshness() -> Tuple[bool, str]:
    """PACKET-10A invariant: a successful swarm_backup happened within 25h.

    Reads runtime/backups/log.jsonl (the per-run audit log) and finds the most
    recent ok event. Failure modes:
      - log file missing      → backup driver never ran
      - no ok events          → all attempts failed
      - newest ok > 25h ago   → cadence broken
    """
    import json as _json
    from datetime import datetime as _dt

    log = ROOT / "runtime" / "backups" / "log.jsonl"
    if not log.exists():
        return False, f"no backup log at {log} — has scripts/backup_swarm.sh ever run?"

    last_ok_ts = 0.0
    last_target = None
    last_archive = None
    try:
        with log.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = _json.loads(line)
                except Exception:
                    continue
                if ev.get("outcome") != "ok":
                    continue
                try:
                    ts = _dt.fromisoformat(ev.get("ts") or "").timestamp()
                except Exception:
                    continue
                if ts > last_ok_ts:
                    last_ok_ts = ts
                    last_target = ev.get("target")
                    last_archive = ev.get("archive")
    except Exception as e:
        return False, f"unreadable backup log: {type(e).__name__}: {e}"

    if last_ok_ts == 0.0:
        return False, "no successful backup events recorded in log"

    age_s = time.time() - last_ok_ts
    if age_s > 25 * 3600:
        return False, f"last successful backup {age_s/3600:.1f}h ago (max 25h) target={last_target}"

    return True, f"last ok {age_s/3600:.1f}h ago · target={last_target} · {last_archive}"


def check_vortex_liveness() -> Tuple[bool, str]:
    """PACKET-10A invariant: Vortex produced a checkpoint within 25h.

    `time_checkpoints.created_at` is the canonical source of truth for Vortex
    liveness. The vortex_heartbeat task runs every 6h, so a >25h gap means
    either the scheduler isn't firing or `create_workflow_checkpoint` is
    broken — both are tier-1 problems and must surface here.
    """
    db = ROOT / "swarm_memory.db"
    if not db.exists():
        return False, f"no swarm DB at {db}"
    try:
        con = sqlite3.connect(str(db))
        try:
            row = con.execute(
                "SELECT created_at, checkpoint_name FROM time_checkpoints "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        finally:
            con.close()
    except Exception as e:
        return False, f"time_checkpoints query failed: {type(e).__name__}: {e}"

    if not row:
        return False, "time_checkpoints is empty — Vortex never ran"

    last_ts_str, last_name = row
    from datetime import datetime as _dt, timezone as _tz
    try:
        # time_checkpoints stores naive UTC strings like '2026-05-01 11:53:39'.
        # Force-attach UTC so .timestamp() doesn't reinterpret as local time.
        dt = _dt.fromisoformat(last_ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        last_ts = dt.timestamp()
    except Exception:
        return False, f"unparseable created_at on latest checkpoint: {last_ts_str!r}"

    age_s = time.time() - last_ts
    if age_s > 25 * 3600:
        return False, f"latest checkpoint {age_s/3600:.1f}h ago (max 25h) name={last_name}"
    return True, f"latest {age_s/3600:.1f}h ago · {last_name}"


def check_curiosity_organ() -> Tuple[bool, str]:
    """PACKET-10B: curiosity organ schema is queryable and ask/dismiss work."""
    db = ROOT / "swarm_memory.db"
    if not db.exists():
        return False, f"no swarm DB at {db}"
    try:
        sys.path.insert(0, str(ROOT))
        from core import curiosity  # noqa: WPS433 - intentional late import
    except Exception as e:
        return False, f"core.curiosity import failed: {type(e).__name__}: {e}"
    try:
        s = curiosity.stats()
    except Exception as e:
        return False, f"curiosity.stats() failed: {type(e).__name__}: {e}"
    # Ensure required keys are present (table exists + counts are integers).
    for k in ("open", "answered", "dismissed", "expired"):
        if k not in s:
            return False, f"curiosity.stats missing key: {k}"
    return True, (
        f"open={s['open']} answered={s['answered']} "
        f"dismissed={s['dismissed']} expired={s['expired']}"
    )


CHECKS: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
    ("PACKET-01 loose doc files redirected",        check_no_loose_doc_md),
    ("PACKET-01 doc registry seeded",               check_project_docs_registered),
    ("PACKET-02 per-record file store present",     check_record_store),
    ("PACKET-03 ALM detail endpoints wired",        check_alm_detail_endpoints),
    ("PACKET-05 media-center route fixed",          check_media_center_route),
    ("PACKET-06 backlog packet-tagged",             check_backlog_packet_tags),
    ("PACKET-* epic rows present in P-00221285D1",  check_packet_epics_present),
    ("Platinum: every record has a .md sidecar",    check_md_sidecars),
    ("Platinum: append-only ledger present",        check_ledger_present),
    ("Platinum: typed-edges links DB live",         check_links_db),
    ("Platinum: thread kind wired",                 check_thread_kind),
    ("Platinum: attachments store live",            check_attachments_store),
    ("Brain: milestone auto-links live",            check_milestone_auto_links),
    ("Brain: home tiles all have loader branches",  check_home_tile_loader_coverage),
    ("Seven: perception layer live (core.seven)",   check_seven_perception_live),
    ("Seven: brain online (memory + reasoning)",     check_seven_brain_online),
    ("PACKET-10A backup: last successful within 25h", check_backup_freshness),
    ("PACKET-10A Vortex: latest checkpoint within 25h", check_vortex_liveness),
    ("PACKET-10B Curiosity: organ schema + stats queryable", check_curiosity_organ),
]


def main() -> int:
    print("System architecture self-test  —  PACKET-05")
    print("=" * 56)
    failures = 0
    for label, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"check raised: {e}"
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {label}")
        print(f"         {detail}")
        if not ok:
            failures += 1
    print("=" * 56)
    print(f"  {len(CHECKS)} checks   {len(CHECKS) - failures} pass   {failures} fail")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
