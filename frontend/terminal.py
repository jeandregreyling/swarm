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

    class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    try:
        server = make_server('::', 5050, app, server_class=_ThreadingWSGIServer)
        addr_family = 'IPv6+IPv4'
    except OSError:
        server = make_server('0.0.0.0', 5050, app, server_class=_ThreadingWSGIServer)
        addr_family = 'IPv4'

    print(f'[Terminal] Serving on port 5050 ({addr_family})')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[Terminal] Shutting down.')
        server.shutdown()
