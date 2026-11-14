#!/usr/bin/env python3
"""hummingbird_nanny.py v2 - deterministic supervisor for local models.

No LLM, no tokens, no network except localhost. Standard library only.

v1: task state machine, liveness (llama-server /health, /slots, GPU busy),
    verification gates, escalation ladder.
v2: DOES sustain sweep (VRAM / latency -> compress context), D.R.E.A.M.
    sub-task generation, per-domain LoRA adapter swap at task start.

States: QUEUED -> RUNNING -> CLAIMED_DONE -> VERIFIED | FAILED | ESCALATED
Escalation: failure 1 retry_apex, 2 escalate_fred, 3 queue_online.

What is real and what is not (read this before trusting it)
  * /health, /slots and sysfs GPU counters are real llama-server / amdgpu
    interfaces.
  * llama-server has NO endpoint that compresses context and NO VRAM
    telemetry endpoint. So:
      - VRAM is read from /sys/class/drm/card*/device/mem_info_vram_used.
      - Latency is only available if you expose GET /telemetry yourself
        (a small shim). Without it, only the VRAM trigger works.
      - system_sweep tries POST /memory/compress. If the server has no such
        route the action comes back with executed=False and the
        orchestrator must summarise the history and start a fresh context.
  * LoRA swap tries POST /lora/load/<name> (shim) first, then falls back to
    llama-server's POST /lora-adapters scale switching. The adapters must
    have been loaded at startup with --lora. The /lora-adapters request body
    is from memory of the llama.cpp docs and is NOT verified on your build.
  * D.R.E.A.M. sub-task generation is a fixed 3-step template unless you pass
    a `decomposer` callable (for example one that asks Apex). The template
    steps 1-2 carry no acceptance checks, so they cannot be verified until
    you add checks with `accept`.

Config is read from the environment at call time:
  HB_NANNY_DB, HB_LLAMA_URL, HB_STALL_SECONDS, HB_MAX_RUNTIME,
  HB_GPU_ACTIVE_PCT, HB_VRAM_LIMIT_MB, HB_LATENCY_LIMIT_MS,
  HB_SWEEP_COOLDOWN, HB_LORA_MAP (JSON {"domain": "adapter-name"}).

Acceptance file (accept.json) is a list of checks, for example:
  [
    {"type": "file_exists", "path": "core/nanny.py"},
    {"type": "modified_since_start", "path": "core/nanny.py"},
    {"type": "min_bytes", "path": "core/nanny.py", "n": 500},
    {"type": "py_compile", "path": "core/nanny.py"},
    {"type": "not_matches", "path": "core/nanny.py", "regex": "TODO|placeholder"},
    {"type": "contains", "path": "core/nanny.py", "text": "def tick"},
    {"type": "cmd", "cmd": "python3 -m pytest tests/test_nanny.py -q", "cwd": ".", "timeout": 300}
  ]
"""
import argparse
import glob
import json
import os
import py_compile
import re
import shlex
import shutil
import sqlite3
import subprocess
import time
import urllib.request

LADDER = ["retry_apex", "escalate_fred", "queue_online"]         # index = failed attempts - 1
_last_ticks = {}


# ----------------------------------------------------------------- config
def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def db_path():
    return os.environ.get("HB_NANNY_DB", "hummingbird_nanny.db")


def llama_url():
    return os.environ.get("HB_LLAMA_URL", "http://127.0.0.1:8080")


# ----------------------------------------------------------------- storage
def db():
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY, title TEXT, state TEXT DEFAULT 'QUEUED',
            accept TEXT DEFAULT '[]', attempts INTEGER DEFAULT 0,
            created REAL, started REAL, last_activity REAL, updated REAL,
            note TEXT DEFAULT '', parent_id INTEGER, domain TEXT, active_adapter TEXT);
        CREATE TABLE IF NOT EXISTS events(
            ts REAL, task_id INTEGER, kind TEXT, detail TEXT);
        """
    )
    cols = {r[1] for r in con.execute("PRAGMA table_info(tasks)")}
    for name, ddl in (("parent_id", "INTEGER"), ("domain", "TEXT"), ("active_adapter", "TEXT")):
        if name not in cols:                       # upgrade a v1 database in place
            con.execute(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}")
    con.commit()
    return con


def log(con, tid, kind, detail=""):
    con.execute("INSERT INTO events VALUES(?,?,?,?)", (time.time(), tid, kind, str(detail)))


def get_task(con, tid):
    row = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if row is None:
        raise SystemExit(f"no such task: {tid}")
    return row


def add_task(con, title, accept, parent_id=None, domain=None):
    now = time.time()
    cur = con.execute(
        "INSERT INTO tasks(title, accept, created, updated, parent_id, domain) VALUES(?,?,?,?,?,?)",
        (title, json.dumps(accept), now, now, parent_id, domain),
    )
    log(con, cur.lastrowid, "added", title)
    con.commit()
    return cur.lastrowid


def set_accept(con, tid, accept):
    con.execute("UPDATE tasks SET accept=?, updated=? WHERE id=?", (json.dumps(accept), time.time(), tid))
    log(con, tid, "accept_set", f"{len(accept)} checks")
    con.commit()


def set_task_domain(con, tid, domain):
    con.execute("UPDATE tasks SET domain=?, updated=? WHERE id=?", (domain, time.time(), tid))
    log(con, tid, "domain", domain)
    con.commit()


def set_state(con, tid, state, note=""):
    con.execute(
        "UPDATE tasks SET state=?, note=?, updated=? WHERE id=?",
        (state, note, time.time(), tid),
    )
    log(con, tid, state.lower(), note)
    con.commit()


def start_task(con, tid, execute_adapter_check=False, base=None):
    """Mark RUNNING. With execute_adapter_check, swap to the task domain's LoRA first."""
    t = get_task(con, tid)
    if execute_adapter_check and t["domain"]:
        base = base or llama_url()
        adapter = lora_map().get(t["domain"], t["domain"])
        _, busy = server_state(base)
        if busy:
            log(con, tid, "adapter", f"swap to {adapter!r} deferred: server is mid-generation")
        else:
            ok, how = swap_adapter(base, adapter)
            if ok:
                con.execute("UPDATE tasks SET active_adapter=? WHERE id=?", (adapter, tid))
                log(con, tid, "adapter", f"loaded {adapter!r} via {how}")
            else:
                log(con, tid, "adapter", f"swap to {adapter!r} failed ({how}); running on current weights")
    now = time.time()
    con.execute(
        "UPDATE tasks SET state='RUNNING', started=?, last_activity=?, updated=? WHERE id=?",
        (now, now, now, tid),
    )
    log(con, tid, "started")
    con.commit()


# ----------------------------------------------------------------- http helpers
def http_json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode() or "null")
    except Exception:
        return None


def http_post(url, payload=None, timeout=10):
    """Returns (ok, parsed_json_or_None). ok is False on any HTTP or network error."""
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            try:
                return True, json.loads(body or "null")
            except ValueError:
                return True, None
    except Exception:
        return False, None


# ----------------------------------------------------------------- liveness
def server_state(base):
    """(healthy, busy). busy is None if /slots is unavailable (e.g. --no-slots)."""
    health = http_json(base + "/health")
    healthy = isinstance(health, dict) and health.get("status") == "ok"
    slots = http_json(base + "/slots")
    busy = None
    if isinstance(slots, list):
        busy = any(
            isinstance(s, dict) and (s.get("is_processing") or s.get("state") == 1)
            for s in slots
        )
    return healthy, busy


def gpu_busy():
    """Highest amdgpu busy % across cards, or None if not readable."""
    vals = []
    for p in glob.glob("/sys/class/drm/card*/device/gpu_busy_percent"):
        try:
            with open(p) as f:
                vals.append(int(f.read().strip()))
        except Exception:
            pass
    return max(vals) if vals else None


def vram_used_mb():
    """Highest amdgpu VRAM in use (MB) across cards, or None if not readable."""
    vals = []
    for p in glob.glob("/sys/class/drm/card*/device/mem_info_vram_used"):
        try:
            with open(p) as f:
                vals.append(int(f.read().strip()) // (1024 * 1024))
        except Exception:
            pass
    return max(vals) if vals else None


def cpu_ticks(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return int(fields[11]) + int(fields[12])      # utime + stime
    except Exception:
        return None


def activity(base=None, pid=None):
    info = {"healthy": None, "slot_busy": None, "gpu": None, "cpu_ticks": None, "working": False}
    gpu_pct = env_int("HB_GPU_ACTIVE_PCT", 15)
    if base:
        info["healthy"], info["slot_busy"] = server_state(base)
        info["gpu"] = gpu_busy()
        if info["slot_busy"]:
            info["working"] = True
        elif info["slot_busy"] is None and info["gpu"] is not None and info["gpu"] >= gpu_pct:
            info["working"] = True           # no /slots available: fall back to GPU load
    if pid:
        t = cpu_ticks(pid)
        info["cpu_ticks"] = t
        prev = _last_ticks.get(pid)
        _last_ticks[pid] = t
        if t is not None and prev is not None and t > prev + 2:
            info["working"] = True
    return info


# ----------------------------------------------------------------- DOES sustain
def telemetry(base):
    """VRAM / latency / context size. Prefers a GET /telemetry shim, else sysfs VRAM only."""
    t = http_json(base + "/telemetry")
    if isinstance(t, dict):
        return {"vram_usage_mb": t.get("vram_usage_mb"), "latency_ms": t.get("latency_ms"),
                "context_size": t.get("context_size"), "source": "telemetry endpoint"}
    return {"vram_usage_mb": vram_used_mb(), "latency_ms": None,
            "context_size": None, "source": "sysfs"}


def system_sweep(con, base=None):
    """DOES Sustain: if VRAM or latency is past its limit, request context compression.

    Returns a list of actions. executed=False means the server has no compress
    endpoint and the orchestrator must summarise history and reset the context.
    """
    base = base or llama_url()
    t = telemetry(base)
    vram_limit = env_int("HB_VRAM_LIMIT_MB", 14000)
    lat_limit = env_int("HB_LATENCY_LIMIT_MS", 3000)
    reasons = []
    if t["vram_usage_mb"] is not None and t["vram_usage_mb"] > vram_limit:
        reasons.append("VRAM saturation")
    if t["latency_ms"] is not None and t["latency_ms"] > lat_limit:
        reasons.append("latency degradation")
    if not reasons:
        return []
    last = con.execute("SELECT MAX(ts) FROM events WHERE task_id=0 AND kind='sustain'").fetchone()[0]
    if last and time.time() - last < env_int("HB_SWEEP_COOLDOWN", 60):
        return []                                    # already acted recently
    ok, _ = http_post(base + "/memory/compress")
    reason = reasons[0]
    if ok:
        msg = f"DOES_SUSTAIN: Context compressed due to {reason}."
    else:
        msg = (f"DOES_SUSTAIN: {reason} detected; server has no compress endpoint, "
               "orchestrator must summarise history and start a fresh context.")
    log(con, 0, "sustain", msg)
    con.commit()
    return [{"action": "compress_context", "reason": reason, "executed": ok,
             "vram_mb": t["vram_usage_mb"], "latency_ms": t["latency_ms"], "source": t["source"]}]


def get_system_log(con, limit=50):
    rows = con.execute(
        "SELECT detail FROM events WHERE task_id=0 AND kind='sustain' ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return "\n".join(r["detail"] for r in reversed(rows))


# ----------------------------------------------------------------- D.R.E.A.M.
def default_decompose(title, accept):
    return [
        {"description": f"Analyze requirements: {title}", "accept": []},
        {"description": f"Implement: {title}", "accept": []},
        {"description": f"Verify against acceptance checks: {title}", "accept": accept},
    ]


def trigger_dream_vector(con, parent_id, base=None, decomposer=None):
    """Create sub-tasks for a parent task. Idempotent: returns existing ids if already done.

    decomposer(title, accept) -> [{"description": str, "accept": [checks]}, ...]
    lets you plug a model in. `base` is reserved for that and unused by the template.
    """
    existing = con.execute("SELECT id FROM tasks WHERE parent_id=? ORDER BY id", (parent_id,)).fetchall()
    if existing:
        return [r["id"] for r in existing]
    parent = get_task(con, parent_id)
    accept = json.loads(parent["accept"] or "[]")
    steps = decomposer(parent["title"], accept) if decomposer else default_decompose(parent["title"], accept)
    ids = [add_task(con, s["description"], s.get("accept", []), parent_id=parent_id,
                    domain=parent["domain"]) for s in steps]
    log(con, parent_id, "dream", f"{len(ids)} subtasks generated")
    con.commit()
    return ids


def get_subtasks(con, parent_id):
    out = []
    for r in con.execute("SELECT * FROM tasks WHERE parent_id=? ORDER BY id", (parent_id,)).fetchall():
        d = dict(r)
        d["status"] = d["state"]
        d["description"] = d["title"]
        out.append(d)
    return out


# ----------------------------------------------------------------- LoRA
def lora_map():
    try:
        m = json.loads(os.environ.get("HB_LORA_MAP", "{}"))
        return m if isinstance(m, dict) else {}
    except ValueError:
        return {}


def swap_adapter(base, adapter):
    """Switch the active LoRA. Returns (ok, how). Only call when the server is idle."""
    ok, _ = http_post(f"{base}/lora/load/{adapter}")
    if ok:
        return True, "POST /lora/load"
    lst = http_json(base + "/lora-adapters")
    if isinstance(lst, list) and lst:
        match = {a["id"] for a in lst
                 if adapter.lower() in os.path.basename(str(a.get("path", ""))).lower()}
        if not match:
            return False, f"no loaded adapter matches {adapter!r}"
        payload = [{"id": a["id"], "scale": 1.0 if a["id"] in match else 0.0} for a in lst]
        ok, _ = http_post(base + "/lora-adapters", payload)
        return ok, "POST /lora-adapters"
    return False, "no adapter endpoint available (was the server started with --lora?)"


# ----------------------------------------------------------------- verification
def run_gate(g, started):
    t = g.get("type")
    p = g.get("path")
    try:
        if t == "file_exists":
            return os.path.exists(p), f"missing: {p}"
        if t == "min_bytes":
            n = g.get("n", 1)
            return os.path.getsize(p) >= n, f"{p} smaller than {n} bytes"
        if t == "modified_since_start":
            return os.path.getmtime(p) >= started, f"{p} not modified since the task started"
        if t == "py_compile":
            py_compile.compile(p, doraise=True)
            return True, ""
        if t == "contains":
            with open(p, errors="replace") as f:
                return g["text"] in f.read(), f"{p} does not contain {g['text']!r}"
        if t == "not_matches":
            with open(p, errors="replace") as f:
                m = re.search(g["regex"], f.read())
            return m is None, (f"{p} matches forbidden pattern {m.group(0)!r}" if m else "")
        if t == "cmd":
            r = subprocess.run(
                shlex.split(g["cmd"]), capture_output=True, text=True,
                timeout=g.get("timeout", 300), cwd=g.get("cwd"),
            )
            tail = (r.stdout + r.stderr).strip()[-300:]
            return r.returncode == g.get("rc", 0), f"`{g['cmd']}` exited {r.returncode}: {tail}"
        return False, f"unknown check type {t!r}"
    except Exception as e:
        return False, f"{t} on {p or g.get('cmd')}: {e}"


def escalate(con, tid, reason):
    """Count a failed attempt and return the next action for the orchestrator."""
    t = get_task(con, tid)
    attempts = t["attempts"] + 1
    action = LADDER[min(attempts, len(LADDER)) - 1]
    state = "ESCALATED" if action == "queue_online" else "FAILED"
    con.execute("UPDATE tasks SET attempts=? WHERE id=?", (attempts, tid))
    set_state(con, tid, state, reason)
    return {"task": tid, "action": action, "attempts": attempts, "reason": reason}


def claim_done(con, tid):
    """Apex says it is done. Record the claim, then check it. Never trust it."""
    set_state(con, tid, "CLAIMED_DONE", "model claimed completion")
    t = get_task(con, tid)
    gates = json.loads(t["accept"] or "[]")
    started = t["started"] or t["created"]
    failures = []
    if not gates:
        failures.append("no acceptance checks defined, so completion cannot be verified")
    for g in gates:
        ok, msg = run_gate(g, started)
        if not ok:
            failures.append(msg)
    if failures:
        res = escalate(con, tid, "; ".join(failures))
        res.update({"verified": False, "failures": failures})
        return res
    set_state(con, tid, "VERIFIED", f"{len(gates)} checks passed")
    return {"task": tid, "verified": True, "checks": len(gates)}


# ----------------------------------------------------------------- supervision
def tick(con, base=None, pid=None):
    """One supervision pass. Returns a list of actions for the orchestrator."""
    actions = []
    now = time.time()
    stall = env_int("HB_STALL_SECONDS", 300)
    max_runtime = env_int("HB_MAX_RUNTIME", 5400)
    a = activity(base, pid)
    for t in con.execute("SELECT * FROM tasks WHERE state='RUNNING'").fetchall():
        tid = t["id"]
        started = t["started"] or now
        if now - started > max_runtime:
            actions.append(escalate(con, tid, f"exceeded max runtime of {max_runtime}s"))
            continue
        if a["working"]:
            con.execute("UPDATE tasks SET last_activity=?, updated=? WHERE id=?", (now, now, tid))
            con.commit()
            continue
        idle = now - (t["last_activity"] or started)
        if idle > stall:
            actions.append(escalate(con, tid, f"stalled: no model activity for {int(idle)}s"))
    return actions


def notify(msg):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "Hummingbird nanny", msg], check=False)


def status(con):
    rows = con.execute(
        "SELECT id, state, attempts, title, note, parent_id, active_adapter FROM tasks ORDER BY id"
    ).fetchall()
    for r in rows:
        sub = f" (sub of #{r['parent_id']})" if r["parent_id"] else ""
        lora = f" [lora={r['active_adapter']}]" if r["active_adapter"] else ""
        print(f"#{r['id']:<4} {r['state']:<13} attempts={r['attempts']} {r['title']}{sub}{lora}")
        if r["note"] and r["state"] in ("FAILED", "ESCALATED"):
            print(f"      {r['note'][:200]}")


# ----------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Hummingbird nanny (deterministic supervisor)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--title", required=True)
    p.add_argument("--accept", required=True)
    p.add_argument("--domain")
    p = sub.add_parser("start")
    p.add_argument("id", type=int)
    p.add_argument("--swap", action="store_true", help="load the task domain's LoRA first")
    p.add_argument("--url")
    p = sub.add_parser("claim")
    p.add_argument("id", type=int)
    p = sub.add_parser("domain")
    p.add_argument("id", type=int)
    p.add_argument("name")
    p = sub.add_parser("accept")
    p.add_argument("id", type=int)
    p.add_argument("file")
    p = sub.add_parser("dream")
    p.add_argument("id", type=int)
    sub.add_parser("status")
    sub.add_parser("log")
    p = sub.add_parser("sweep")
    p.add_argument("--url")
    p = sub.add_parser("watch")
    p.add_argument("--url")
    p.add_argument("--pid", type=int)
    p.add_argument("--interval", type=int, default=30)
    args = ap.parse_args()
    con = db()

    if args.cmd == "add":
        with open(args.accept) as f:
            print(add_task(con, args.title, json.load(f), domain=args.domain))
    elif args.cmd == "start":
        start_task(con, args.id, execute_adapter_check=args.swap, base=args.url)
    elif args.cmd == "claim":
        print(json.dumps(claim_done(con, args.id), indent=2))
    elif args.cmd == "domain":
        set_task_domain(con, args.id, args.name)
    elif args.cmd == "accept":
        with open(args.file) as f:
            set_accept(con, args.id, json.load(f))
    elif args.cmd == "dream":
        print(trigger_dream_vector(con, args.id))
    elif args.cmd == "status":
        status(con)
    elif args.cmd == "log":
        print(get_system_log(con))
    elif args.cmd == "sweep":
        print(json.dumps(system_sweep(con, args.url), indent=2))
    elif args.cmd == "watch":
        base = args.url or llama_url()
        print(f"watching {base} every {args.interval}s (Ctrl+C to stop)")
        while True:
            for act in tick(con, base, args.pid) + system_sweep(con, base):
                print(json.dumps(act))
                notify(f"{act['action']}: {str(act.get('reason', ''))[:80]}")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
