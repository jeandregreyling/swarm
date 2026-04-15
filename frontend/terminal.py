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
    ('blueprints.proposals',      'proposals_bp'),
    ('blueprints.shell',          'shell_bp'),
    ('blueprints.system',         'system_bp'),
    ('blueprints.tickets',        'tickets_bp'),
    ('blueprints.time_wizard_bp', 'time_wizard_bp'),
    ('blueprints.workspace',      'workspace_bp'),
    ('blueprints.library',        'library_bp'),
    ('blueprints.localai',        'localai_bp'),
    ('blueprints.node',           'node_bp'),
    ('blueprints.research',       'research_bp'),
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


def create_app():
    app = Flask(__name__)

    # Inject ENV_STAGE into all templates for environment banner
    @app.context_processor
    def inject_env_stage():
        stage = os.environ.get('STAGE', os.environ.get('SWARM_ENV', 'PROD' if PORT == 5050 else 'unknown')).upper()
        return dict(ENV_STAGE=stage)

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

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.route("/", methods=["GET"])
    def root_status():
        from flask import jsonify
        return jsonify({"status": "ok", "message": "Fridays/Swarm API is running."})

    @app.route("/_health", methods=["GET"])
    def health_status():
        from flask import jsonify
        return jsonify({
            "status": "ok" if not _failed_blueprints else "degraded",
            "port": PORT,
            "env": ENV.upper(),
            "blueprints_loaded": [a for a, _ in _loaded_blueprints],
            "blueprints_failed": {a: e for a, e in _failed_blueprints},
        })

    # Fridays UI route (serves main HTML interface)
    @app.route("/ui", methods=["GET"])
    def fridays_ui():
        from flask import render_template
        return render_template("terminal_base.html", theme_css="")

    # Convenience redirects — deep-link views directly
    @app.route("/library", methods=["GET"])
    @app.route("/studio", methods=["GET"])
    @app.route("/chat", methods=["GET"])
    @app.route("/monitor", methods=["GET"])
    def ui_redirect():
        from flask import redirect
        return redirect("/ui")

    # ── Register blueprints (only those that loaded) ──────────────────────────
    for _attr, _bp in _loaded_blueprints:
        try:
            app.register_blueprint(_bp)
        except Exception as _reg_err:
            print(f"[Terminal] Blueprint register failed — {_attr}: {_reg_err}")

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
