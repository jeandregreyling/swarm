# Session 30 — FULL QUALITY TESTING
**Date:** 22 April 2026  
**Phase:** Quality gate, not build.  
**Directive (user, verbatim):**  
> "we are now in FULL quality testing. so lets make it proper"  
> "if ALM test lab was properly up and running this would be a lot easier because I would only be looking at new tests"  
> "that needs to stop and be a LOT more targeted right?"

This plan replaces the long Session 29 thread to stop the *loss-in-the-middle*.
Everything from Sessions 29 / 29.1 / 29.2 is considered **shipped and frozen** —
it is listed here for traceability, not for edits.

---

## 1. Shipped (frozen)

### Session 29 — Seven as Spine
- `core/spine.py` (300 LOC). `TraceEvent`, `EventKind`, `Severity`. Ring
  `deque(maxlen=500)` + SQLite mirror via `utils.db.trace_log`.
- `route()` guardian: wraps `core.routing.route`, intercepts non-Seven picks
  when `confidence < 0.6` or target unroutable. Threshold `0.6`.
- `utils/db/trace_log.py` — `trace_events` table + 4 indexes, persist/list/vacuum/count.
- `frontend/blueprints/spine_bp.py` — `/api/spine/events`, `/api/spine/log`
  (rejects server-only kinds), `/api/spine/stream` (SSE 20s heartbeat).
- Emit points: watchdog, checkpoint, ticket, testlab, relay.
- Frontend: `trace-bus.js` (`window.__trace`), `trace.css`, `#trace-ticker`,
  `view-traced`, `traced.js`, Vortex spine feed IIFE (`MAX=30`).
- Guardian hook in `/api/chat/classify` returns parallel `guardian` block.
- Tests: `tests/test_spine.py` (21 tests).

### Session 29.1 — Bridge + cleanup
- `spine.log` mirrors **warn+** into `activity_log` via `utils.db.audit.log_activity`.
- Trace tile **System Log** tab surfaces guardian/watchdog entries.
- Home chat tile: `#home-chat-thread-select` hidden (duplicate of rail).
- Cache-bust `?v=29` on all Session 29 JS.
- +2 spine tests (activity_log mirror).

### Session 29.2 — UX + Knowledge Center foundation
- Main chat thread rail collapsed by default.
- Email multi-select toolbar + bulk close (`_emailBulkClose`).
- Guardian narrator card (dismissible, amber, renders only on
  `original_target !== final && original_target !== 'seven'`).
- `core/knowledge/` package: `scripts.py` re-exports testlab registry +
  `change_runs` table (record/list).
- `frontend/blueprints/knowledge_bp.py` — 3 endpoints:
  `GET /api/knowledge/testlab/scripts`,
  `GET /api/knowledge/change-runs`,
  `GET /api/knowledge/change-runs/<change_id>`.
- Test Lab resolve persists selections to KC `change_runs`.
- `tests/test_knowledge.py` — 9 tests.

### Session 30 — ALM Test Lab (this session, in-progress below)

### Session 30.0.1 — Visibility patch (after user feedback)
Symptom: user hard-refreshed `/ui` and saw no change because all Session 30
work was buried inside **Studio → Test Lab** sub-tab.

Fixes:
- New top-level home tile **Test Lab** (`data-win-id="studio-testlab"`,
  `data-after-open="studioSetTab:testlab"`) — one click from home.
- `core/app.js` `afterOpen` handler extended to dispatch `studioSetTab:*`
  (previously only `docsSetTab:*`).
- Test Lab panel heading upgraded: "ALM Test Lab" + a **Session 30** pill.
  Summary line explicitly references the new Run History panel.
- Home tile badge: `paintHomeTestlabBadge()` paints PASS/FAIL/ERROR/RUNNING
  pill + "Last: <script_id> · <time>" based on `/api/knowledge/test-runs?limit=1`.
  Wired from `core/init.js` on boot + every 30s.
- Cache-bust: `app.js?v=30`, `init.js?v=30`, `studio-testlab.js?v=30`.

### Session 30.1 — Projects pivot (this session)
User directive (verbatim):
- "shouldn't be a tile on its own it should be grouped with Studio and GIT so lets
  move into the simplificaltion of the entire tile layout and start making it more
  'mission enabled'"
- "you will need to log and tag your test scripps as actual steps and add the test
  cases to each project"
- "we can go with Agile, Waterfall or Prince2 (mixed) approuch"
- "testing is no longer just in proposals, proposals need to be linked to projects
  and projects need to have a test plan and that all feeds into Vortex"
- "update Seven as the owner of each step and each project"
- "put that into a project plan and terst to see how that works"

Pivot: **Projects are first-class.** Proposals, plan steps, test cases and test
runs all hang off a project. Seven is the default owner of every project and
every step. Every project mutation emits a spine `TICKET` event with source
`projects` — that auto-feeds Vortex and the System Log.

Layout cleanup (no tile sprawl):
- Standalone "Test Lab" home tile (30.0.1) **reverted**.
- Studio home tile now shows the combined Studio/Git/Projects/Test Lab
  badge via `#home-studio-badge` + `#home-studio-desc`.
- Studio sub-tabs: Pending · In Progress · History · **Projects (new)** · Git · Test Lab.

Methodology (enum, validated server-side): `agile`, `waterfall`, `prince2`, `mixed`.
Step statuses: `todo`, `doing`, `blocked`, `done`, `skipped`.
Case statuses: `draft`, `ready`, `passed`, `failed`, `blocked`, `obsolete`.
Default owner: `seven`.

New schema (in `core/knowledge/projects.py`, lazy `_ensure_schema`):

| Table                  | Keys / Columns                                                         |
|------------------------|------------------------------------------------------------------------|
| `projects`             | `project_id` (P-XXXXXXXXXX), name, description, methodology, status, owner, created_at, updated_at |
| `project_steps`        | `step_id` (S-XXXXXXXXXX), project_id, order_idx, title, description, status, owner, timestamps |
| `project_test_cases`   | `case_id` (C-XXXXXXXXXX), project_id, step_id (nullable), title, script_id, status, owner |
| `proposal_projects`    | (proposal_id, project_id) PK, created_at                               |
| `test_runs` **extended** | + `project_id`, `step_id`, `case_id` (nullable; idempotent ALTERs)   |

New endpoints (in `frontend/blueprints/knowledge_bp.py`):

| Method + Path                                                  | Purpose                                  |
|----------------------------------------------------------------|------------------------------------------|
| `GET  /api/knowledge/projects`                                 | List with aggregates (step/case counts)  |
| `POST /api/knowledge/projects`                                 | Create (validates methodology)           |
| `GET  /api/knowledge/projects/<pid>`                           | Detail flat: project + steps + cases + proposals |
| `PATCH /api/knowledge/projects/<pid>`                          | Rename / set status / methodology        |
| `GET  /api/knowledge/projects/<pid>/steps`                     | List steps ordered                       |
| `POST /api/knowledge/projects/<pid>/steps`                     | Add step (default owner=seven)           |
| `PATCH /api/knowledge/steps/<sid>`                             | Set step status (enum-validated)         |
| `GET  /api/knowledge/projects/<pid>/test-cases`                | List cases (optional step_id filter)     |
| `POST /api/knowledge/projects/<pid>/test-cases`                | Add case linked to step + script_id      |
| `POST /api/knowledge/projects/<pid>/link-proposal`             | Link proposal by id (dedupes)            |
| `POST /api/knowledge/test-runs` **extended**                   | Accepts `project_id`, `step_id`, `case_id` |
| `GET  /api/knowledge/test-runs?project_id=&step_id=&case_id=`  | Filterable by project spine              |

UI (`frontend/static/js/views/projects.js`, cache-bust `?v=30`):
- Projects sub-tab inside Studio. Two-pane layout (list left, detail right).
- "+ New Project" with methodology dropdown (Agile/Waterfall/Prince2/Mixed).
- Project detail: plan steps with inline status dropdown, test cases with
  script_id binding, linked proposals, recent test runs tagged to the project.
- Test Lab header extended with **Project** + **Step** selectors; any run
  started from Test Lab while a project is selected is recorded against
  that project/step in `test_runs`.

Tests: `tests/test_projects.py` (16 tests) — covers methodology validation,
aggregates, step ordering + status validation, case filtering by step,
proposal dedupe, test_runs project-tag filtering, and full detail-tree shape.

Vortex integration: `_emit_spine()` is called on every mutation
(create/update project, add/update step, add case, link proposal) → spine
`TICKET` kind, source `projects`. Existing Vortex feed picks them up
unchanged.

Smoke (live, restart on port 5050):
- Create → P-xxxxxxxxxx; bad methodology → 400.
- Step added, patched to `doing` (emits spine warn/info).
- Case + proposal linked; `GET /projects/<id>` returns 1/1/1/owner=seven/methodology=agile.
- Run tagged with project_id is returned by `GET /test-runs?project_id=`.
- `GET /api/spine/events?source=projects` returns 20 events (Vortex-ready).

---

## 2. Session 30 delivery — ALM Test Lab

### 2.1 Why
Running `python -m pytest` (700+) every turn is a **regression net**, not a
test lab. The user wants HP/ALM-style behaviour:

1. Only run scripts relevant to the current change.
2. Record each run with pass/fail + duration + exit code.
3. Attach notes, log snippets, screenshots to each run.
4. Browse history per script and per change_id.

### 2.2 Persistence — `core/knowledge/test_runs.py`
New tables (lazy schema):

```sql
CREATE TABLE test_runs (
  run_id       TEXT PRIMARY KEY,
  script_id    TEXT NOT NULL,
  change_id    TEXT,
  status       TEXT NOT NULL,   -- running | pass | fail | error | aborted
  started_at   REAL NOT NULL,
  ended_at     REAL,
  duration_ms  INTEGER,
  exit_code    INTEGER,
  stdout_tail  TEXT,            -- last 8 KB only
  command      TEXT,
  triggered_by TEXT             -- manual | change:<id> | auto | scheduled
);
CREATE INDEX idx_test_runs_script  ON test_runs(script_id);
CREATE INDEX idx_test_runs_change  ON test_runs(change_id);
CREATE INDEX idx_test_runs_started ON test_runs(started_at);

CREATE TABLE test_run_artifacts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id     TEXT NOT NULL,
  kind       TEXT NOT NULL,     -- note | screenshot | log | link
  body       TEXT NOT NULL,     -- up to 64 KB; screenshots are data-URLs
  created_at REAL NOT NULL
);
CREATE INDEX idx_artifacts_run ON test_run_artifacts(run_id);
```

Public API:  `start_run`, `finish_run`, `abort_run`, `add_artifact`,
`get_run`, `list_runs`.

### 2.3 Endpoints — `knowledge_bp`
| Verb    | Path                                         | Purpose                           |
| ------- | -------------------------------------------- | --------------------------------- |
| `POST`  | `/api/knowledge/test-runs`                   | Start a run → returns `run_id`.   |
| `PATCH` | `/api/knowledge/test-runs/<run_id>`          | Finish a run (status/exit/tail).  |
| `POST`  | `/api/knowledge/test-runs/<run_id>/artifacts`| Attach note/log/screenshot/link.  |
| `GET`   | `/api/knowledge/test-runs`                   | List recent runs (filter scriptid, change_id, status, limit). |
| `GET`   | `/api/knowledge/test-runs/<run_id>`          | Single run + artifacts.           |

### 2.4 UI — `studio-testlab.js` (`?v=30`)
- `testLabRunSelected` now wraps each script with
  `_tlStartRunRecord → _tlRunOneCommand → _tlFinishRunRecord`.
- `_tlRunOneCommand` returns `{ok, exitCode, stdoutTail}` instead of bool.
- New **Run History** pane below the output console: rows of
  `STATUS · time · script_id · change_id · duration · Details`.
- **Details** modal (`#testlab-run-modal`) shows full metadata, stdout tail,
  artifacts, and a textarea to add notes on the fly.
- History auto-refreshes when runs finish and when the panel mounts.

### 2.5 "Only new tests" workflow
1. Set a **Change ID** in the Test Lab header (persisted to `localStorage`).
2. Tick only the scripts relevant to the current edit.
3. Press **Run selected** — each run is tagged with `change_id`.
4. The History pane filters to `change_id` when present → only new tests.

---

## 3. Backend ↔ Frontend wiring audit

The user reported: *"there is definitely an issue with what you're doing in
the 'backend' and it's not being wired to what I'm able to see."*

Audit checklist — every backend endpoint must have a visible UI consumer.

| Endpoint                                        | UI consumer                                                 | Status |
| ----------------------------------------------- | ----------------------------------------------------------- | ------ |
| `/api/spine/events`                             | `traced.js` populating `view-traced`                        | ✅ wired |
| `/api/spine/stream`                             | `trace-bus.js` EventSource → ticker + Vortex feed           | ✅ wired |
| `/api/spine/log`                                | (server-only kinds rejected; client uses for CHAT/SYSTEM)   | ✅ intentional |
| `/api/knowledge/testlab/scripts`                | studio-testlab panel (mirror of studio endpoint)            | ⚠️ unused by UI — studio-testlab hits `/api/studio/testlab/scripts` directly. Keep as API for external tooling; **not a bug**. |
| `/api/knowledge/change-runs`                    | None yet                                                    | ❌ needs tile |
| `/api/knowledge/change-runs/<change_id>`        | None yet                                                    | ❌ needs tile |
| `/api/knowledge/test-runs` (POST/GET)           | `studio-testlab.js` history pane + auto-record              | ✅ wired (Session 30) |
| `/api/knowledge/test-runs/<id>` (PATCH/GET)     | `studio-testlab.js` finish + details modal                  | ✅ wired (Session 30) |
| `/api/knowledge/test-runs/<id>/artifacts` POST  | Details modal **Add Note** button                           | ✅ wired (Session 30) |
| Guardian block on `/api/chat/classify`          | `_renderGuardianNarrator` amber card in chat.js             | ✅ wired |

**Next audit targets (Session 30.1):**
- Create a **Knowledge Center** tile that consumes `change-runs` endpoints
  and links into the Test Lab run history. Without this, two endpoints are
  invisible to the user.
- Verify `#trace-ticker` renders on a hard refresh (confirm z-index above
  chat rail).

---

## 4. Prioritised backlog

### P0 — this session
- [x] test_runs persistence
- [x] test-runs endpoints
- [x] auto-record in studio-testlab.js
- [x] History pane + details modal + add-note
- [x] This plan doc
- [ ] Targeted test execution (knowledge + spine + testlab only)
- [ ] Smoke: 7 endpoints + new run lifecycle

### P1 — Session 30.1
- [ ] Knowledge Center tile — surface `change_runs` and `test_runs`.
- [ ] Screenshot artifact: drag-and-drop into details modal (uses existing
      `kind=screenshot` + data-URL).
- [ ] Step-through flow: stitch a change's runs into a timeline view
      (`/knowledge/change/<id>` page consuming `change-runs/<id>` +
      `test-runs?change_id=<id>`).
- [ ] Auto-tag `triggered_by` as `change:<id>` on resolve-with-change-id.
      (Already implemented in JS: uses `change:{id}` when change set.)

### P2 — Session 30.2
- [ ] Promote `core/testlab_registry` into a DB-backed registry (currently
      in-memory Python). Re-exports already live behind `core.knowledge`.
- [ ] Periodic chat+AI round-trip smoke probe (easy with spine events now).
- [ ] Email additional configuration (SMTP-from, signature, auto-file rules).
- [ ] Hard-refresh login/new-thread clarification for users.

---

## 5. QA-phase gates (rules for every future turn)

1. **No full pytest.** Use targeted scripts from the Test Lab. Only run the
   regression net when the user explicitly says "regression".
2. **Every new endpoint ships with a UI consumer or is explicitly marked
   API-only** in the wiring-audit table above.
3. **Every new change_id gets a test run.** Tag the change in the Test Lab
   header before running. History will filter to that change.
4. **Cache-bust every JS that changes this session.** Bump `?v=N`.
5. **One plan doc per session** — append here or supersede with `SESSION_31.md`.
