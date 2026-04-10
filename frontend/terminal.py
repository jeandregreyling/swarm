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
    SWARM_ROOT, time_wizard, orchestrator,
)

# ── Blueprint imports ────────────────────────────────────────────────────────
from vs_tools import vs_bp
from blueprints.agent_api import agent_api_bp
from blueprints.agents import agents_bp
from blueprints.auth import auth_bp
from blueprints.brief import brief_bp
from blueprints.chat import chat_bp
from blueprints.conversations import conversations_bp
from blueprints.debates import debates_bp
from blueprints.decisions import decisions_bp
from blueprints.docs import docs_bp
from blueprints.exec_bp import exec_bp
from blueprints.git import git_bp
from blueprints.kb import kb_bp
from blueprints.killswitch import killswitch_bp
from blueprints.legacy import legacy_bp
from blueprints.memory import memory_bp
from blueprints.nine import nine_bp
from blueprints.ollama import ollama_bp
from blueprints.proposals import proposals_bp
from blueprints.shell import shell_bp
from blueprints.system import system_bp
from blueprints.tickets import tickets_bp
from blueprints.time_wizard_bp import time_wizard_bp
from blueprints.workspace import workspace_bp
from blueprints.library import library_bp



def create_app():
    app = Flask(__name__)

    # Inject ENV_STAGE into all templates for environment banner
    @app.context_processor
    def inject_env_stage():
        return {'ENV_STAGE': os.environ.get('STAGE', 'unknown')}

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

    # Register blueprints


    # Add root health/status route
    @app.route("/", methods=["GET"])
    def root_status():
        from flask import jsonify
        return jsonify({"status": "ok", "message": "Fridays/Swarm API is running. See /api/proposals for proposals."})


    # Fridays UI route (serves main HTML interface)
    @app.route("/ui", methods=["GET"])
    def fridays_ui():
        from flask import render_template
        # theme_css is injected as empty for now; can be extended for dynamic theming
        return render_template("terminal_base.html", theme_css="")
    app.register_blueprint(vs_bp)
    app.register_blueprint(agent_api_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(brief_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(conversations_bp)
    app.register_blueprint(debates_bp)
    app.register_blueprint(decisions_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(exec_bp)
    app.register_blueprint(git_bp)
    app.register_blueprint(kb_bp)
    app.register_blueprint(killswitch_bp)
    app.register_blueprint(legacy_bp)
    app.register_blueprint(memory_bp)
    app.register_blueprint(nine_bp)
    app.register_blueprint(ollama_bp)
    app.register_blueprint(proposals_bp)
    app.register_blueprint(shell_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(time_wizard_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(library_bp)

    return app


# ── Server startup ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Bootstrap Time Wizard session
    try:
        session_id = time_wizard.bootstrap_session()
        if session_id:
            print(f'[Time Wizard] Session started: {session_id}')
    except Exception as e:
        print(f'[Time Wizard] Bootstrap warning: {e}')

    app = create_app()
    app.run(host='0.0.0.0', port=PORT, debug=False)
