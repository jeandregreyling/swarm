"""Flask bridge for sandpits/studio project discovery."""

from __future__ import annotations

from flask import Blueprint, jsonify

from .project_discovery import discover_projects


studio_projects_bp = Blueprint('studio_projects_loader', __name__)


@studio_projects_bp.route('/api/studio-loader/projects', methods=['GET'])
def list_studio_loader_projects():
    projects = discover_projects()
    return jsonify({'ok': True, 'projects': projects, 'count': len(projects)})


@studio_projects_bp.route('/api/studio-loader/projects/<project_id>', methods=['GET'])
def get_studio_loader_project(project_id: str):
    for project in discover_projects():
        if project.get('id') == project_id:
            return jsonify({'ok': True, 'project': project})
    return jsonify({'ok': False, 'error': 'project not found'}), 404