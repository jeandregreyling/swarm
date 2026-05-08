"""
core/testlab_registry.py — Session 28 Studio Test Lab
═══════════════════════════════════════════════════════════════════════════════
Declarative registry of runnable test scripts available in the Studio Test Lab.

Each entry is a pure data dict — the backend never imports or executes Python
from here. The Test Lab endpoint turns the selected entries into shell commands
that run via the existing `/api/terminal/run` stream path, so output rendering,
hard-kill, and ANSI/semantic formatting are all reused.

Entries are grouped so the Test Lab UI can show logical sections. Users can
extend by appending to ``REGISTRY`` — no new Python imports are needed as long
as the command is a plain shell string.

Fields
------
id          stable identifier (used in API payloads + localStorage)
group       UI section ("Smoke", "Pytest", "JS", "Relay", "Custom")
label       short human label
description one-line explanation shown in the UI tooltip
command     shell command (run via bash -lc from repo root)
change_aware True if the script benefits from a change_id / diff context
default_on  True if this script should be pre-checked in the UI
"""

from __future__ import annotations

from typing import List, Dict


REGISTRY: List[Dict[str, object]] = [
    # ── Smoke ─────────────────────────────────────────────────────────────
    {
        'id': 'smoke-endpoints',
        'group': 'Smoke',
        'label': 'HTTP smoke (7 endpoints)',
        'description': 'GETs 7 core read-only endpoints and asserts every response is 200.',
        'command': (
            "for ep in /api/health /api/pulse /api/chat/jobs/status "
            "/api/auth/me /api/chat/agents/health "
            "/api/knowledge/runs/feed /api/knowledge/testlab/scripts; do "
            "code=$(curl -s -o /dev/null -w '%{http_code}' "
            "http://127.0.0.1:5050$ep); echo \"$code $ep\"; "
            "[[ \"$code\" == \"200\" ]] || exit 1; done"
        ),
        'change_aware': False,
        'default_on': True,
    },
    {
        'id': 'smoke-change-run-lifecycle',
        'group': 'Smoke',
        'label': 'Change-run lifecycle (start → finish → fetch)',
        'description': 'Starts a test run for change SMOKE, finishes it ok, then asserts the run shows up in the change timeline. Validates the full POST/PATCH/GET path.',
        'command': (
            "set -e; BASE=http://127.0.0.1:5050; "
            "RID=$(curl -s -XPOST $BASE/api/knowledge/test-runs "
            "-H 'Content-Type: application/json' "
            "-d '{\"script_id\":\"smoke-endpoints\",\"change_id\":\"SMOKE\"}' "
            "| python -c 'import sys,json; print(json.load(sys.stdin)[\"run_id\"])'); "
            "echo \"started run $RID\"; "
            "curl -s -XPATCH $BASE/api/knowledge/test-runs/$RID "
            "-H 'Content-Type: application/json' "
            "-d '{\"status\":\"pass\",\"exit_code\":0}' >/dev/null; "
            "curl -s $BASE/api/knowledge/changes/SMOKE/timeline "
            "| python -c 'import sys,json; data=json.load(sys.stdin); "
            "assert data[\"ok\"], data; assert any(i[\"kind\"]==\"test_run\" for i in data[\"items\"]), data'; "
            "echo OK"
        ),
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'smoke-agents-health',
        'group': 'Smoke',
        'label': 'Agent watchdog snapshot',
        'description': 'Pretty-prints /api/chat/agents/health so you can eyeball p50/p95 and stall counts before shipping.',
        'command': "curl -s http://127.0.0.1:5050/api/chat/agents/health | python -m json.tool",
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'smoke-architecture-self-test',
        'group': 'Smoke',
        'label': 'Architecture self-test (PACKET-05)',
        'description': 'Runs the system invariant gate: doc redirects, /media-center route, per-record file store, ALM detail endpoints, packet tagging, epic rows present. Exit 0 = all green.',
        'command': 'python3 scripts/architecture_self_test.py',
        'change_aware': False,
        'default_on': True,
    },

    # ── Pytest groups ────────────────────────────────────────────────────
    {
        'id': 'pytest-full',
        'group': 'Pytest',
        'label': 'Full pytest (excl. chat_quality)',
        'description': 'Runs the full test suite excluding the long-running chat_quality slice. ~70s on this box.',
        'command': 'python -m pytest --ignore=tests/test_chat_quality.py -q',
        'change_aware': False,
        'default_on': True,
    },
    {
        'id': 'pytest-targeted-knowledge-spine-testlab',
        'group': 'Pytest',
        'label': 'Targeted: knowledge + spine + testlab',
        'description': 'Fast targeted run for the Session 30 surface — Knowledge Center, spine event ring, and Test Lab. Use during KC/testlab work to skip the full suite.',
        'command': (
            'python -m pytest -q '
            'tests/test_knowledge.py '
            'tests/test_knowledge_batch_t.py '
            'tests/test_testlab.py '
            'tests/test_testlab_suites.py '
            'tests/test_spine.py '
            'tests/test_chat_smoke_probe_spine.py '
            '-k "not chat_quality"'
        ),
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'pytest-chat-core',
        'group': 'Pytest',
        'label': 'Chat core (actions + watchdog + routing)',
        'description': 'Focused run for the chat stack — action-intent detector, watchdog, reply routing, classifier bridge.',
        'command': (
            'python -m pytest -q '
            'tests/test_chat_actions.py '
            'tests/test_chat_watchdog.py '
            'tests/test_chat_reply_routing.py '
            'tests/test_chat_classify_router_bridge.py'
        ),
        'change_aware': True,
        'default_on': False,
    },
    {
        'id': 'pytest-email-guard',
        'group': 'Pytest',
        'label': 'Email bounce guard',
        'description': 'Runs the 8 bounce/auto-reply detector tests added in Session 28.',
        'command': 'python -m pytest -q tests/test_email_bounce_guard.py',
        'change_aware': True,
        'default_on': False,
    },
    {
        'id': 'pytest-governance',
        'group': 'Pytest',
        'label': 'Governance + ALM gate',
        'description': 'Runs governance and ALM gate endpoint tests.',
        'command': 'python -m pytest -q tests/test_governance.py tests/test_alm_gate_endpoints.py',
        'change_aware': True,
        'default_on': False,
    },
    {
        'id': 'pytest-media-center-review',
        'group': 'Pytest',
        'label': 'Media Center review suite',
        'description': 'Covers Media Center layout, Studio Projects tracking integration, routing, references, and accordion/resizer contracts.',
        'command': 'python -m pytest -q tests/test_media_center_integration.py',
        'change_aware': True,
        'default_on': False,
    },
    {
        'id': 'pytest-media-center-projects-chat',
        'group': 'Pytest',
        'label': 'Media Center + Projects + chat intents',
        'description': 'Checks Studio Projects defaults, Media Center window routing, and chat actions that open Media Center or Studio Projects.',
        'command': (
            'python -m pytest -q '
            'tests/test_projects.py '
            'tests/test_chat_actions.py '
            'tests/test_v7c_a01_studio_default.py '
            'tests/test_v7c_r13_studio.py'
        ),
        'change_aware': True,
        'default_on': False,
    },
    {
        'id': 'pytest-media-center-daw-workspace',
        'group': 'Pytest',
        'label': 'Media Center DAW workspace',
        'description': 'Covers the DAW-first layout contract, research/right dock behavior, review/bottom dock behavior, and advisor/Knowledge surfacing.',
        'command': (
            'python -m pytest -q '
            'tests/test_media_center_integration.py '
            'tests/test_chat_actions.py '
            '-k "media_center or open_media_center or open_music_editor or projects_section"'
        ),
        'change_aware': True,
        'default_on': False,
    },
    {
        'id': 'pytest-local-agent-runtime-fixes',
        'group': 'Pytest',
        'label': 'Local agent runtime fixes',
        'description': 'Guards the Twenty model alias repair, Eight local-runtime path, and Fridays music/video knowledge seeding.',
        'command': (
            'python -m pytest -q '
            'tests/test_local_agent_runtime_fixes.py '
            'tests/test_media_center_integration.py '
            '-k "local_agent_runtime_fixes or knowledge_docs"'
        ),
        'change_aware': True,
        'default_on': False,
    },

    # ── JS / static checks ───────────────────────────────────────────────
    {
        'id': 'js-syntax-core',
        'group': 'JS',
        'label': 'node --check (core chat JS)',
        'description': 'Syntax-checks the three JS files most commonly touched by chat refactors.',
        'command': (
            'node --check frontend/static/js/core/swarm-chat.js && '
            'node --check frontend/static/js/views/chat.js && '
            'node --check frontend/static/js/views/home-chat.js && '
            'echo OK'
        ),
        'change_aware': True,
        'default_on': True,
    },
    {
        'id': 'js-syntax-media-center',
        'group': 'JS',
        'label': 'node --check (Media Center views)',
        'description': 'Syntax-checks the Media Center and Studio media bridge files after layout or workflow edits.',
        'command': (
            'node --check frontend/static/js/views/media-center.js && '
            'node --check frontend/static/js/views/studio-media.js && '
            'echo OK'
        ),
        'change_aware': True,
        'default_on': False,
    },
    {
        'id': 'js-syntax-all-views',
        'group': 'JS',
        'label': 'node --check (all views/*.js)',
        'description': 'Syntax-checks every JS file under frontend/static/js/views. Catches typos across the full frontend surface.',
        'command': (
            "for f in frontend/static/js/views/*.js; do "
            "node --check \"$f\" || { echo \"FAIL: $f\"; exit 1; }; "
            "done; echo 'All views OK'"
        ),
        'change_aware': False,
        'default_on': False,
    },

    # ── Relay / integration ──────────────────────────────────────────────
    {
        'id': 'relay-chain-dry',
        'group': 'Relay',
        'label': 'Relay chain dry run',
        'description': 'Exercises the relay chain test harness without any live agent calls.',
        'command': 'python -m pytest -q tests/relay_chain_test.py',
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'triage-queue-dry',
        'group': 'Relay',
        'label': 'Triage queue dry run',
        'description': 'Runs the Librarian triage + queue intake dry-run suite.',
        'command': 'python -m pytest -q tests/test_triage_queue_dryrun.py',
        'change_aware': False,
        'default_on': False,
    },

    # ── Audits / system sweeps (Session 30.1 Projects pivot) ─────────────
    {
        'id': 'api-wide-probe',
        'group': 'Audit',
        'label': 'API wide probe (every GET /api/*)',
        'description': 'Iterates every registered GET /api/* route and classifies HEALTHY / EXPECTED / STREAMING / MISSING / BROKEN / STUCK. Exits 0 only when MISSING+BROKEN+STUCK == 0.',
        'command': '.venv/bin/python tests/api_wide_probe.py',
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'api-mutation-probe',
        'group': 'Audit',
        'label': 'API mutation safety probe (POST/PATCH/PUT empty body)',
        'description': 'Sends an empty JSON body to every non-destructive mutation endpoint. Classifies VALIDATED (schema said no) / ACCEPTED (idempotent) / AUTH / DEPENDENCY (503) / BROKEN (5xx) / STUCK. Exits 0 only when BROKEN+STUCK == 0. DELETE endpoints and known-destructive POSTs are skipped.',
        'command': '.venv/bin/python tests/api_mutation_probe.py',
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'api-bogus-probe',
        'group': 'Audit',
        'label': 'API bogus-body probe (type-confusion / wrong field types)',
        'description': 'Sends structurally wrong payloads (list, dict, int, null, 4KB string) to every non-destructive mutation endpoint. Classifies VALIDATED (schema said no) / ACCEPTED (tolerated) / AUTH / DEPENDENCY (503) / BROKEN (5xx from type confusion) / STUCK. Exits 0 only when BROKEN+STUCK == 0.',
        'command': '.venv/bin/python tests/api_bogus_probe.py',
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'api-concurrency-probe',
        'group': 'Audit',
        'label': 'API concurrency / idempotency probe (parallel fanout)',
        'description': 'Fires N=5 parallel empty-body requests at every non-destructive mutation endpoint. Classifies worst-outcome across the batch as VALIDATED / ACCEPTED / AUTH / DEPENDENCY / FLAKY / BROKEN / STUCK. Catches UNIQUE-constraint races, lock contention, TOCTOU bugs. Exits 0 only when BROKEN+STUCK == 0; FLAKY is report-only.',
        'command': '.venv/bin/python tests/api_concurrency_probe.py',
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'api-ctype-probe',
        'group': 'Audit',
        'label': 'API content-type confusion probe (wrong / missing Content-Type)',
        'description': 'Sends each non-destructive mutation endpoint 5 content-type variants: no Content-Type, text/plain, lying application/json with non-JSON body, application/xml, and XML-as-JSON. Catches handlers that crash on malformed bodies or misroute werkzeug BadRequest as 500. Exits 0 only when BROKEN+STUCK == 0.',
        'command': '.venv/bin/python tests/api_ctype_probe.py',
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'alm-self-test',
        'group': 'Audit',
        'label': 'ALM self-test (status / case / run validation)',
        'description': 'Audits the Test Center endpoints themselves: project status enum, test case status transition, bogus project_id on test runs.',
        'command': '.venv/bin/python tests/alm_self_test.py',
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'audit-icons-emoji',
        'group': 'Audit',
        'label': 'No emoji icons in templates',
        'description': 'Asserts no UI emoji-as-icon glyphs (⚙️ 🔧 📁 📂 🗂 🔍 ✏️ 📝 🗑 ➕ ➖ ✅ ❌ 📊 📈 🎛 🎚) remain in rendered template content. All UI iconography should be inline SVG. Ignores console.log strings and *_test.html fixtures.',
        'command': (
            "hits=$(grep -nP '[\\x{2699}\\x{1F527}\\x{1F4C1}\\x{1F4C2}\\x{1F5C2}\\x{1F50D}\\x{270F}\\x{1F4DD}\\x{1F5D1}\\x{2795}\\x{2796}\\x{2705}\\x{274C}\\x{1F4CA}\\x{1F4C8}\\x{1F39B}\\x{1F39A}]' "
            "frontend/templates/terminal_base.html frontend/templates/*.html 2>/dev/null "
            "| grep -v 'console\\.' "
            "| grep -v '_test\\.html:' "
            "| grep -v '/test_'); "
            "if [ -n \"$hits\" ]; then echo \"FAIL: emoji-as-icon found:\"; echo \"$hits\"; exit 1; fi; "
            "echo 'OK: no emoji icons in templates'"
        ),
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'audit-icons-fontawesome',
        'group': 'Audit',
        'label': 'No font-icon classes (fa/fas/far/glyphicon/bi)',
        'description': 'Asserts no Font Awesome / Bootstrap Icons / Glyphicon class attributes remain in templates — all icons should be inline SVG.',
        'command': (
            "if grep -rEn 'class=\"[^\"]*\\b(fa|fas|far|fab|glyphicon|bi-[a-z])\\b' "
            "frontend/templates/ ; then "
            "echo 'FAIL: font-icon classes found'; exit 1; "
            "fi; echo 'OK: no font-icon classes'"
        ),
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'audit-icons-stroke-width',
        'group': 'Audit',
        'label': 'Window-chrome SVGs use stroke-width 1.3',
        'description': 'Project standard: window chrome / header icons use stroke-width=\"1.3\". Scans terminal_base.html for any window-chrome SVG using a different stroke-width.',
        'command': (
            "bad=$(grep -nE 'class=\"window-(control|chrome|action)[^\"]*\"' frontend/templates/terminal_base.html | "
            "grep -oE 'stroke-width=\"[^\"]+\"' | grep -v 'stroke-width=\"1.3\"' | wc -l); "
            "if [ \"$bad\" -gt 0 ]; then echo \"FAIL: $bad non-1.3 window-chrome strokes\"; exit 1; fi; "
            "echo 'OK: window-chrome strokes standardised'"
        ),
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'audit-icons-img-tags',
        'group': 'Audit',
        'label': 'No <img> tags used as UI icons',
        'description': 'Asserts no raster <img> tags are used for UI icons inside buttons / nav / tiles (avatar/logo uses are allowed and excluded).',
        'command': (
            "bad=$(grep -rEn '<img\\b[^>]+(icon|glyph)' frontend/templates/ | "
            "grep -v 'avatar\\|logo\\|agent-portrait' | wc -l); "
            "if [ \"$bad\" -gt 0 ]; then "
            "echo \"FAIL: $bad raster <img> icons found\"; "
            "grep -rEn '<img\\b[^>]+(icon|glyph)' frontend/templates/ | grep -v 'avatar\\|logo\\|agent-portrait'; "
            "exit 1; fi; "
            "echo 'OK: no raster <img> icons'"
        ),
        'change_aware': False,
        'default_on': False,
    },

    # ── Test Lab suites (P-00221285D1) ───────────────────────────────────
    {
        'id': 'suite-tasker',
        'group': 'Suites',
        'label': 'Tasker suite (S-53B7D03A12)',
        'description': 'Runs the Tasker dry-run, calendar-static, and research integration tests as one suite.',
        'command': (
            'python -m pytest -q --tb=line '
            'tests/test_tasker_dry_run.py '
            'tests/test_tasker_calendar_static.py '
            'tests/test_tasker_research_integration_fixes.py'
        ),
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'suite-research-watcher',
        'group': 'Suites',
        'label': 'Research watcher suite (S-2E9343FB8F)',
        'description': 'Runs the Research watcher tests plus the Tasker↔Research integration fixes as one suite.',
        'command': (
            'python -m pytest -q --tb=line '
            'tests/test_research.py '
            'tests/test_tasker_research_integration_fixes.py'
        ),
        'change_aware': False,
        'default_on': False,
    },
    {
        'id': 'suite-studio-projects',
        'group': 'Suites',
        'label': 'Studio projects suite (S-F7FB61FF05)',
        'description': 'Runs the Studio Projects API contract suite plus tags, step-deps, case-rollup, and closeout tests.',
        'command': (
            'python -m pytest -q --tb=line '
            'tests/test_knowledge_projects_api.py '
            'tests/test_project_tags.py '
            'tests/test_step_deps_and_case_rollup.py '
            'tests/test_frontend_smokes_and_routes.py'
        ),
        'change_aware': False,
        'default_on': False,
    },
]


def get_registry() -> List[Dict[str, object]]:
    """Return a shallow copy so callers can't mutate the canonical list."""
    return [dict(entry) for entry in REGISTRY]


def get_entry(script_id: str) -> Dict[str, object] | None:
    for entry in REGISTRY:
        if entry.get('id') == script_id:
            return dict(entry)
    return None
