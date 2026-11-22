from flask import Flask

# Import the agent identity blueprint (the real dispatcher lives here)
from frontend.blueprints.agent_identity import agent_identity_bp


def create_app() -> Flask:
    """Create and configure the Flask application.

    The tests only need a minimal app that exposes the /api/agent/v1/tools
    endpoint.  The real implementation lives in ``frontend/blueprints/agent_identity``.
    We simply register that blueprint so the test client can hit the route.
    """
    app = Flask(__name__)
    # Register the blueprint that contains the /api/agent/v1/tools route.
    app.register_blueprint(agent_identity_bp, url_prefix="")
    return app
