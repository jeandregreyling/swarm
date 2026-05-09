# Rollback plan for app_center.py

- Remove the import: `from studio_loader.project_discovery import discover_projects`
- Remove all code in list_projects and get_project that references `discover_projects` or sandpit projects.
- Restore both endpoints to their original state (only DB-backed projects).
- After rollback, restart DEV and confirm /api/app-center/projects returns the normal list (no 404, no import error).
- Once confirmed, re-add discovery logic in a safer way.
