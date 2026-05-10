"""
terminal.py — Fridays / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Slim app factory. All routes live in blueprints/.
Shared state and helpers live in services.py.

python3 terminal.py
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import importlib
import traceback
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

# Multi-environment port logic
ENV = os.environ.get('SWARM_ENV', 'prod').lower()
PORT_MAP = {
    'prod': 5050,
    'dev':  5051,
    'uat':  5053,
}
PORT = int(os.environ.get('PORT') or PORT_MAP.get(ENV, 5050))

print(f"[Swarm Terminal] Starting in {ENV.upper()} mode on port {PORT}")

# Ensure services module is importable (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import (
    Flask, initialise_database, mark_orphaned_chat_jobs,
    sweep_stuck_jobs,
    SWARM_ROOT, time_wizard, orchestrator,
)

# ── Safe blueprint loader ────────────────────────────────────────────────────
# Each entry: (import_path, attribute_name)
# If a blueprint fails to import, the server still starts — just without that
# blueprint's routes. The failure is logged and exposed on GET /_health.
_BLUEPRINT_REGISTRY = [
    ('vs_tools',                  'vs_bp'),
    ('blueprints.agent_api',      'agent_api_bp'),
    ('blueprints.agents',         'agents_bp'),
    ('blueprints.auth',           'auth_bp'),
    ('blueprints.brief',          'brief_bp'),
    ('blueprints.chat',           'chat_bp'),
    ('blueprints.conversations',  'conversations_bp'),
    ('blueprints.debates',        'debates_bp'),
    ('blueprints.decisions',      'decisions_bp'),
    ('blueprints.docs',           'docs_bp'),
    ('blueprints.exec_bp',        'exec_bp'),
    ('blueprints.git',            'git_bp'),
    ('blueprints.kb',             'kb_bp'),
    ('blueprints.killswitch',     'killswitch_bp'),
    ('blueprints.legacy',         'legacy_bp'),
    ('blueprints.memory',         'memory_bp'),
    ('blueprints.nine',           'nine_bp'),
    ('blueprints.ollama',         'ollama_bp'),
    ('blueprints.email_bp',       'email_bp'),
    ('blueprints.proposals',             'proposals_bp'),
    ('blueprints.proposals_git',         'proposals_git_bp'),
    ('blueprints.proposals_attachments', 'proposals_attachments_bp'),
    ('blueprints.shell',          'shell_bp'),
    ('blueprints.system',         'system_bp'),
    ('blueprints.tickets',        'tickets_bp'),
    ('blueprints.time_wizard_bp', 'time_wizard_bp'),
    ('blueprints.workspace',      'workspace_bp'),
    ('blueprints.library',        'library_bp'),
    ('blueprints.localai',        'localai_bp'),
    ('blueprints.media_center',   'media_center_bp'),
    ('blueprints.node',           'node_bp'),
    ('blueprints.research',       'research_bp'),
    ('blueprints.tools',          'tools_bp'),
    ('blueprints.metrics',        'metrics_bp'),
    ('blueprints.sse',            'sse_bp'),
    ('blueprints.onboarding',     'onboarding_bp'),
    ('blueprints.diamond',        'diamond_bp'),
    ('blueprints.weather_bp',     'weather_bp'),
    ('blueprints.vpn_bp',         'vpn_bp'),
    ('blueprints.auto_audit',     'audit_bp'),
    ('blueprints.patterns_bp',    'patterns_bp'),
    ('blueprints.personality_bp', 'personality_bp'),
    ('blueprints.interests_bp',   'interests_bp'),
    ('blueprints.login_bp',       'login_bp'),
    ('blueprints.idle_mgmt_bp',   'idle_bp'),
    ('blueprints.tasker_bp',      'tasker_bp'),
    ('blueprints.testlab_bp',     'testlab_bp'),
    ('blueprints.spine_bp',       'spine_bp'),
    ('blueprints.knowledge_bp',   'knowledge_bp'),
    ('blueprints.coding_bible',   'coding_bible_bp'),
    ('blueprints.curiosity',      'curiosity_bp'),
    ('blueprints.voice',          'voice_bp'),
    ('blueprints.fan',            'fan_bp'),
    ('blueprints.health',         'health_bp'),    ('blueprints.health_bp',       'health_digest_bp'),    ('blueprints.council_bp',     'council_bp'),
    ('blueprints.sysmod',         'sysmod_bp'),
    ('blueprints.studio_evidence','studio_evidence_bp'),
    ('blueprints.email_accounts', 'email_accounts_bp'),
    ('blueprints.enrollment',     'enrollment_bp'),
    ('blueprints.gmail_labels',   'gmail_labels_bp'),
    ('blueprints.feeds_bp',       'feeds_bp'),
    ('blueprints.seven_bp',       'seven_bp'),
    ('blueprints.wishlist_bp',    'wishlist_bp'),
    ('blueprints.cybersecurity_bp', 'cybersecurity_bp'),
    ('blueprints.financial_bp',     'financial_bp'),
    ('blueprints.trading_bp',       'trading_bp'),
    ('blueprints.business_bp',      'business_bp'),
    ('blueprints.media_curriculum', 'media_curriculum_bp'),
    ('blueprints.media_jobs',       'media_jobs_bp'),
    ('blueprints.synth_board',      'synth_board_bp'),
    ('blueprints.video_editor',     'video_editor_bp'),
    ('blueprints.app_center',       'app_center_bp'),
    ('blueprints.kc_overview',      'kc_overview_bp'),
    ('blueprints.orientation',      'orientation_bp'),
    ('blueprints.wishlist_registry','wishlist_registry_bp'),
    ('blueprints.hive',             'hive_bp'),
]

_loaded_blueprints   = []   # (attr_name, blueprint_object)
_failed_blueprints   = []   # (attr_name, error_string)

for _mod_path, _attr in _BLUEPRINT_REGISTRY:
    try:
        _mod = importlib.import_module(_mod_path)
        _bp  = getattr(_mod, _attr)
        _loaded_blueprints.append((_attr, _bp))
    except Exception as _bp_err:
        _short = f"{type(_bp_err).__name__}: {_bp_err}"
        print(f"[Terminal] BLUEPRINT LOAD FAILED — {_attr} ({_mod_path}): {_short}")
        traceback.print_exc()
        _failed_blueprints.append((_attr, _short))

if _failed_blueprints:
    print(f"[Terminal] WARNING: {len(_failed_blueprints)} blueprint(s) failed — "
          f"those routes are unavailable. See GET /_health for details.")
else:
    print(f"[Terminal] All {len(_loaded_blueprints)} blueprints loaded OK.")


def _compute_asset_version() -> str:
    """Asset cache-bust token (S-CAAD1B6D9C).

    Order of preference: SWARM_ASSET_VERSION env var (CI/deploy can pin),
    short git sha if a .git tree is reachable, else the current epoch
    second so devs always see fresh assets after a restart.
    """
    forced = os.environ.get('SWARM_ASSET_VERSION', '').strip()
    if forced:
        return forced
    try:
        import subprocess
        out = subprocess.run(
            ['git', '-C', str(Path(__file__).resolve().parent.parent),
             'rev-parse', '--short=10', 'HEAD'],
            capture_output=True, text=True, timeout=2,
        )
        sha = out.stdout.strip()
        if sha:
            return sha
    except Exception:
        pass
    import time as _t
    return str(int(_t.time()))


def create_app():
    app = Flask(__name__)

    # R.1: Session-based UI authentication
    try:
        from utils.session_auth import init_session_auth
        init_session_auth(app)
    except Exception as _auth_err:
        print(f'[Terminal] session auth warning: {_auth_err}')

    # E.1: Security headers + request size limits
    try:
        from utils.security_headers import init_security
        init_security(app)
    except Exception as _sec_err:
        print(f'[Terminal] security middleware warning: {_sec_err}')

    # Inject ENV_STAGE + ASSET_VERSION into all templates.
    # ASSET_VERSION (S-CAAD1B6D9C) is appended as a query string to every
    # /static/js/views/*.js include in terminal_base.html so a deploy
    # invalidates the browser cache without manual ?v=N bumps.
    _asset_version = _compute_asset_version()

    @app.context_processor
    def inject_env_stage():
        stage = os.environ.get('STAGE', os.environ.get('SWARM_ENV', 'PROD' if PORT == 5050 else 'unknown')).upper()
        return dict(ENV_STAGE=stage, ASSET_VERSION=_asset_version)

    # Y.58c — never let the browser serve a stale HTML shell. The shell
    # routes the entire SPA so a cached copy makes new tile layouts
    # (Y.58 Files-into-KC, Cyber-into-Vortex, Money-Hub merge, etc.)
    # invisible until the user manually hard-refreshes. Static assets keep
    # their per-deploy ?v=ASSET_VERSION cache-bust untouched.
    @app.after_request
    def _no_cache_html(resp):  # noqa: ANN001
        try:
            ctype = (resp.headers.get('Content-Type') or '').lower()
            if 'text/html' in ctype:
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                resp.headers['Pragma'] = 'no-cache'
                resp.headers['Expires'] = '0'
        except Exception:
            pass
        return resp

    # Ensure schema/migrations are present before serving APIs.
    try:
        initialise_database()
    except Exception as exc:
        print(f'[Terminal] database bootstrap warning: {exc}')

    # Mark orphaned chat jobs from previous process.
    try:
        mark_orphaned_chat_jobs()
    except Exception as exc:
        print(f'[Terminal] chat job orphan cleanup warning: {exc}')

    # DEV / UAT are manual test targets — they must NOT run background daemons
    # that fight prod for DB locks, Ollama runners, or scheduled tasks.
    _STAGE = os.environ.get('STAGE', '').upper()
    _IS_PROD = _STAGE == 'PROD' or _STAGE == ''

    if _IS_PROD:
        # Background sweep for stuck jobs (every 10 minutes).
        import threading as _th
        def _stuck_job_sweeper():
            import time as _time
            while True:
                _time.sleep(600)
                try:
                    n = sweep_stuck_jobs(max_age_minutes=120)
                    if n:
                        print(f'[Terminal] swept {n} stuck job(s)')
                except Exception:
                    pass
        _sweep_t = _th.Thread(target=_stuck_job_sweeper, daemon=True, name='stuck-job-sweep')
        _sweep_t.start()

        # Node heartbeat daemon (A.5.1) — pings registered remote nodes
        try:
            from utils.node_discovery import start_heartbeat
            start_heartbeat()
        except Exception as _hb_err:
            print(f'[Terminal] node heartbeat start warning: {_hb_err}')

        # Agent 20 — council scheduler (§4b, Phase 8.1)
        try:
            from agents.twenty.scheduler import start as _a20_start
            _a20_start(app)
        except Exception as _a20_err:
            print(f'[Terminal] Agent 20 scheduler start warning: {_a20_err}')

        # Seven — perception + memory + reasoning + continuous learner (PACKET-09 Phase 2)
        try:
            from core.seven import boot as _seven_boot
            _seven_info = _seven_boot()
            print(f'[Terminal] Seven brain online: {_seven_info}')
        except Exception as _seven_err:
            print(f'[Terminal] Seven brain start warning: {_seven_err}')
    else:
        print(f'[Terminal] STAGE={_STAGE} — background daemons disabled (manual mode)')

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.route("/", methods=["GET"])
    def root_status():
        from flask import jsonify
        return jsonify({"status": "ok", "message": "Fridays/Swarm API is running."})

    @app.route("/_health", methods=["GET"])
    def health_status():
        from flask import jsonify
        components = {}

        # DB writable check
        try:
            from utils.db._connection import get_connection
            c = get_connection()
            c.execute("SELECT 1")
            c.close()
            components['database'] = 'healthy'
        except Exception as e:
            components['database'] = f'unhealthy: {e}'

        # Heartbeat thread check
        try:
            from utils.node_discovery import _heartbeat_thread
            if _heartbeat_thread and _heartbeat_thread.is_alive():
                components['heartbeat'] = 'healthy'
            else:
                components['heartbeat'] = 'not_running'
        except Exception:
            components['heartbeat'] = 'unknown'

        # Agent count
        try:
            from utils.db._connection import get_connection
            c = get_connection()
            cnt = c.execute(
                "SELECT COUNT(*) FROM agents WHERE enabled=1"
            ).fetchone()[0]
            c.close()
            components['agents'] = f'healthy ({cnt} active)'
        except Exception:
            components['agents'] = 'unknown'

        any_unhealthy = any('unhealthy' in v for v in components.values())
        overall = 'unhealthy' if any_unhealthy else (
            'degraded' if _failed_blueprints else 'healthy'
        )

        return jsonify({
            "status": overall,
            "port": PORT,
            "env": ENV.upper(),
            "components": components,
            "blueprints_loaded": [a for a, _ in _loaded_blueprints],
            "blueprints_failed": {a: e for a, e in _failed_blueprints},
        })

    # Fridays UI route (serves main HTML interface)
    @app.route("/ui", methods=["GET"])
    def fridays_ui():
        from flask import send_from_directory, render_template_string, render_template
        import pathlib
        fridays_dir = pathlib.Path(__file__).resolve().parent / 'fridays-os'
        html_path = fridays_dir / 'index.html'
        try:
            html = html_path.read_text(encoding='utf-8')
            html = html.replace('{{ ASSET_VERSION }}', _asset_version)
            return render_template_string(html)
        except Exception:
            # Fallback to old UI if FRIDAYS OS shell is missing
            return render_template("terminal_base.html", theme_css="")

    @app.route("/fridays-os/<path:filename>")
    def fridays_os_static(filename):
        from flask import send_from_directory
        import pathlib
        fridays_dir = pathlib.Path(__file__).resolve().parent / 'fridays-os'
        return send_from_directory(fridays_dir, filename)

    # Hive Nodes standalone popout (B21) — minimal page, 20 most recently
    # touched library sources, rendered with the same library-graph engine.
    @app.route("/hive-nodes", methods=["GET"])
    def hive_nodes_page():
        from flask import render_template
        return render_template("hive_nodes.html")


    # ── Register blueprints (only those that loaded) ──────────────────────────
    for _attr, _bp in _loaded_blueprints:
        try:
            app.register_blueprint(_bp)
        except Exception as _reg_err:
            print(f"[Terminal] Blueprint register failed — {_attr}: {_reg_err}")

    # Studio Projects layer bridge (Grok-Pot-Money-Maker + future sandpit projects)
    try:
        from studio_loader.studio_projects_bp import studio_projects_bp
        app.register_blueprint(studio_projects_bp)
        print("[Terminal] Studio projects blueprint registered (sandpits/studio discovery)")
    except Exception as _studio_err:
        print(f"[Terminal] Studio projects blueprint failed to register: {_studio_err}")

    # Convenience redirects — deep-link tile views into the master shell.
    # /media-center previously rendered a standalone template that drifted
    # to a raw test placeholder; route it through /ui so the real window
    # template (terminal_base.html#view-media-center) is always used.
    @app.route("/media-center", methods=["GET"])
    @app.route("/library", methods=["GET"])
    @app.route("/studio", methods=["GET"])
    @app.route("/chat", methods=["GET"])
    @app.route("/monitor", methods=["GET"])
    def ui_redirect():
        from flask import redirect, request
        # preserve any query string and pass the tile id as a hash so
        # window-manager can auto-open it on load.
        target = request.path.lstrip("/") or "ui"
        qs = ("?" + request.query_string.decode("utf-8")) if request.query_string else ""
        return redirect(f"/ui{qs}#{target}")

    # R.5: Register /api/v1/* versioned aliases
    try:
        from utils.api_versioning import register_versioned_routes
        register_versioned_routes(app, version='v1')
    except Exception as _ver_err:
        print(f'[Terminal] API versioning warning: {_ver_err}')

    # Global input-type guard (Session 30.1 v5): when a request handler
    # raises TypeError or AttributeError while parsing the request body,
    # it's almost always a bad-type input (e.g. int where string expected
    # hitting `.strip()`). Return a proper 400 instead of a generic 500.
    # Real server bugs still surface as 500 — only these two exception
    # types during a JSON-body request are converted.
    from flask import jsonify as _jsonify, request as _request
    import logging as _logging
    _input_guard_log = _logging.getLogger('swarm.input_guard')

    def _bad_input_type(err):
        # Only convert when the request actually had a JSON body; routes
        # without a body that legitimately TypeError should still 500.
        is_api = _request.path.startswith('/api/')
        has_body = _request.content_length and _request.content_length > 0
        if is_api and has_body:
            _input_guard_log.warning(
                "bad-type input on %s %s: %s",
                _request.method, _request.path, err,
            )
            return _jsonify({
                'ok': False,
                'error': 'invalid request body (wrong field types)',
            }), 400
        # Re-raise for Flask's default 500 handling
        raise err

    app.register_error_handler(TypeError, _bad_input_type)
    app.register_error_handler(AttributeError, _bad_input_type)

    # Hive — start the self-sampler so the leader's own telemetry shows
    # up in /api/hive/nodes without an external agent. Disabled by
    # $SWARM_HIVE_DISABLE_SELF_SAMPLER for tests / headless workers.
    # Also disabled on DEV/UAT so they don't fight prod for telemetry.
    if _IS_PROD:
        try:
            from core.hive import self_sampler as _hive_self_sampler
            _hive_self_sampler.start()
        except Exception as _hss_err:
            print(f'[Terminal] hive self-sampler warning: {_hss_err}')

    return app


# ── Server startup ───────────────────────────────────────────────────────────
class _ReuseAddrServer(ThreadingMixIn, WSGIServer):
    """Threaded WSGI server that sets SO_REUSEADDR so restarts don't hit
    'Address already in use' when the old process is in TIME_WAIT."""
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    # Bootstrap Time Wizard session
    try:
        session_id = time_wizard.bootstrap_session()
        if session_id:
            print(f'[Time Wizard] Session started: {session_id}')
    except Exception as e:
        print(f'[Time Wizard] Bootstrap warning: {e}')

    app = create_app()

    # Use our hardened server class instead of Flask's dev runner so that
    # SO_REUSEADDR is set and concurrent requests are handled in threads.
    with make_server('0.0.0.0', PORT, app, server_class=_ReuseAddrServer) as httpd:
        print(f'[Swarm Terminal] Listening on port {PORT}')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('[Swarm Terminal] Shutting down.')
