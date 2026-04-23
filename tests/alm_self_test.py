#!/usr/bin/env python3
"""ALM self-test v2 — exhaustive audit of the Test Center API surface.

Every scenario is a thin probe against the live service at 127.0.0.1:5050.
Exits 0 only if all scenarios pass.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:5050"
FAILS: list[str] = []
PASSES: list[str] = []


def _req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})

    def _decode(raw):
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {"_raw": raw[:200]}

    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.getcode(), _decode(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, _decode(e.read().decode())
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def check(label: str, cond: bool, note: str = "") -> None:
    if cond:
        PASSES.append(label)
        print(f"  [PASS] {label}")
    else:
        FAILS.append(f"{label} — {note}" if note else label)
        print(f"  [FAIL] {label}{(' — ' + note) if note else ''}")


def new_project():
    code, data = _req("POST", "/api/knowledge/projects",
                      {"name": "self-test probe", "methodology": "mixed"})
    if code != 200 or not data.get("project_id"):
        raise SystemExit(f"setup failed: {code} {data}")
    return data["project_id"]


def main() -> int:
    pid = new_project()
    print(f"setup pid={pid}")

    # G1 project status enum
    print("G1 project status enum")
    code, _ = _req("PATCH", f"/api/knowledge/projects/{pid}", {"status": "HACKED"})
    check("G1.1 unknown status rejected (400)", code == 400)
    _, got = _req("GET", f"/api/knowledge/projects/{pid}")
    check("G1.2 stored status stays valid",
          (got.get("project") or {}).get("status") in ("active", "archived", "on_hold"))
    code, _ = _req("PATCH", f"/api/knowledge/projects/{pid}", {"status": "on_hold"})
    check("G1.3 valid status accepted (200)", code == 200)

    # G2 methodology enum on PATCH
    print("G2 project methodology enum")
    code, _ = _req("PATCH", f"/api/knowledge/projects/{pid}", {"methodology": "bogus"})
    check("G2.1 bad methodology rejected (400)", code == 400)
    code, _ = _req("PATCH", f"/api/knowledge/projects/{pid}", {"methodology": "prince2"})
    check("G2.2 valid methodology accepted (200)", code == 200)

    # G3 create-project validation
    print("G3 create project validation")
    code, _ = _req("POST", "/api/knowledge/projects", {"name": ""})
    check("G3.1 empty name rejected (400)", code == 400)
    code, _ = _req("POST", "/api/knowledge/projects",
                   {"name": "x", "methodology": "bogus"})
    check("G3.2 bad methodology on create rejected (400)", code == 400)

    # G4 GET unknown project
    print("G4 GET unknown project")
    code, data = _req("GET", "/api/knowledge/projects/P-DOESNOTEXIST")
    check("G4.1 unknown project returns 404", code == 404,
          f"got {code}")

    # G5 steps
    print("G5 steps")
    code, data = _req("POST", f"/api/knowledge/projects/{pid}/steps",
                      {"title": "step one"})
    step_id = data.get("step_id")
    check("G5.1 add step succeeds", code == 200 and bool(step_id))
    code, _ = _req("POST", f"/api/knowledge/projects/{pid}/steps", {"title": ""})
    check("G5.2 empty step title rejected (400)", code == 400)
    code, _ = _req("PATCH", f"/api/knowledge/steps/{step_id}", {"status": "bogus"})
    check("G5.3 bad step status rejected (400)", code == 400)
    code, _ = _req("PATCH", f"/api/knowledge/steps/{step_id}", {"status": "doing"})
    check("G5.4 valid step status accepted (200)", code == 200)
    code, _ = _req("PATCH", "/api/knowledge/steps/S-DOESNOTEXIST",
                   {"status": "doing"})
    check("G5.5 unknown step returns 404", code == 404)
    code, data = _req("POST", "/api/knowledge/projects/P-MISSING/steps",
                      {"title": "orphan"})
    check("G5.6 add step to missing project fails",
          code >= 400 or not data.get("step_id"),
          f"got {code}")

    # G6 cases
    print("G6 cases")
    code, data = _req("POST", f"/api/knowledge/projects/{pid}/test-cases",
                      {"title": "case one"})
    case_id = data.get("case_id")
    check("G6.1 add case succeeds", code == 200 and bool(case_id))
    code, _ = _req("POST", f"/api/knowledge/projects/{pid}/test-cases",
                   {"title": ""})
    check("G6.2 empty case title rejected (400)", code == 400)
    code, _ = _req("PATCH", f"/api/knowledge/cases/{case_id}", {"status": "bogus"})
    check("G6.3 bad case status rejected (400)", code == 400)
    code, _ = _req("PATCH", f"/api/knowledge/cases/{case_id}", {"status": "passed"})
    check("G6.4 valid case status accepted (200)", code == 200)
    code, _ = _req("PATCH", "/api/knowledge/cases/C-DOESNOTEXIST",
                   {"status": "passed"})
    check("G6.5 unknown case returns 404", code == 404)
    code, data = _req("POST", "/api/knowledge/projects/P-MISSING/test-cases",
                      {"title": "orphan case"})
    check("G6.6 add case to missing project fails",
          code >= 400 or not data.get("case_id"),
          f"got {code}")

    # G7 proposal linkage
    print("G7 proposal link")
    code, _ = _req("POST", f"/api/knowledge/projects/{pid}/link-proposal",
                   {"proposal_id": ""})
    check("G7.1 empty proposal_id rejected (400)", code == 400)

    # G8 test-run validation
    print("G8 test-run validation")
    code, _ = _req("POST", "/api/knowledge/test-runs",
                   {"script_id": "probe", "project_id": "P-NOTREAL"})
    check("G8.1 bogus project_id rejected (400)", code == 400)
    code, data = _req("POST", "/api/knowledge/test-runs",
                      {"script_id": "probe", "project_id": pid})
    check("G8.2 real project_id accepted", code == 200 and bool(data.get("run_id")))
    run_id = data.get("run_id")
    if run_id:
        code, _ = _req("PATCH", f"/api/knowledge/test-runs/{run_id}",
                       {"status": "pass", "exit_code": 0})
        check("G8.3 finish_run accepted", code == 200)
    code, _ = _req("POST", "/api/knowledge/test-runs", {"script_id": ""})
    check("G8.4 empty script_id rejected (400)", code == 400)
    code, _ = _req("POST", "/api/knowledge/test-runs",
                   {"script_id": "probe", "project_id": pid,
                    "step_id": "S-NOTOURSTEP"})
    check("G8.5 step_id foreign to project rejected (400)", code == 400)
    code, _ = _req("POST", "/api/knowledge/test-runs",
                   {"script_id": "probe", "project_id": pid,
                    "case_id": "C-NOTOURS"})
    check("G8.6 case_id foreign to project rejected (400)", code == 400)

    # G9 mass-assignment on PATCH /projects
    print("G9 mass-assignment on PATCH /projects")
    code, _ = _req("PATCH", f"/api/knowledge/projects/{pid}",
                   {"project_id": "P-OVERWRITE", "created_at": 0,
                    "description": "legit change"})
    _, got = _req("GET", f"/api/knowledge/projects/{pid}")
    p = got.get("project") or {}
    check("G9.1 project_id not overwritable", p.get("project_id") == pid)
    check("G9.2 created_at not overwritable", p.get("created_at", 0) > 1)
    check("G9.3 allowed fields still land", p.get("description") == "legit change")

    # cleanup
    _req("PATCH", f"/api/knowledge/projects/{pid}", {"status": "archived"})

    print()
    print(f"Result: {len(PASSES)} pass, {len(FAILS)} fail")
    if FAILS:
        print("Fails:")
        for f in FAILS:
            print(f"  - {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
