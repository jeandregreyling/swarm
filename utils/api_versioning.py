"""
utils/api_versioning.py — API version prefix support (R.5)
═══════════════════════════════════════════════════════════════════════════════
Registers /api/v1/* mirror routes for all /api/* blueprint routes.
Existing unversioned routes continue to work (backward-compatible).

Usage in create_app():
    from utils.api_versioning import register_versioned_routes
    register_versioned_routes(app, version='v1')
"""

from flask import Flask


def register_versioned_routes(app: Flask, version: str = 'v1'):
    """Add /api/v1/* aliases for all /api/* routes.

    Must be called AFTER all blueprints are registered.
    Only mirrors rules starting with /api/ — UI routes are unaffected.
    """
    prefix = f'/api/{version}'
    rules_to_add = []

    for rule in app.url_map.iter_rules():
        if rule.rule.startswith('/api/') and not rule.rule.startswith(prefix):
            new_path = rule.rule.replace('/api/', f'{prefix}/', 1)
            rules_to_add.append((new_path, rule.endpoint, rule.methods - {'OPTIONS', 'HEAD'}))

    for path, endpoint, methods in rules_to_add:
        # Use add_url_rule to alias the new path to the same endpoint
        try:
            app.add_url_rule(path, endpoint=f'v1_{endpoint}',
                             view_func=app.view_functions[endpoint],
                             methods=methods)
        except Exception:
            pass  # Skip if duplicate or conflict
