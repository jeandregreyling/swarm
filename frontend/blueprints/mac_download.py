"""Serve macOS install instructions and source tarball for Seven Desktop."""
from __future__ import annotations

import io
import tarfile
from pathlib import Path

from flask import Blueprint, Response, jsonify

mac_bp = Blueprint('mac', __name__, url_prefix='/api/download/mac')

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DESKTOP_DIR = _REPO_ROOT / 'desktop'
_README = _DESKTOP_DIR / 'README_INSTALL_MAC.md'


@mac_bp.get('/')
def mac_download_page():
    """HTML page with macOS install instructions."""
    leader = 'http://100.87.66.45:5050'
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seven — Install on macOS</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 2rem; background: #0b0f19; color: #e0e6f1; }}
  .card {{ max-width: 560px; margin: auto; background: #151b2b; border-radius: 16px; padding: 2rem; box-shadow: 0 8px 32px rgba(0,0,0,.4); }}
  h1 {{ margin: 0 0 .5rem; font-size: 1.6rem; }}
  p {{ line-height: 1.5; color: #a0aec0; }}
  .btn {{ display: block; width: 100%; padding: 1rem; margin: 1rem 0 0; font-size: 1.05rem; font-weight: 600; text-align: center; text-decoration: none; color: #0b0f19; background: #4fd1c5; border-radius: 10px; border: none; cursor: pointer; }}
  .btn:hover {{ background: #38b2ac; }}
  .btn-secondary {{ background: #1e293b; color: #e0e6f1; }}
  .btn-secondary:hover {{ background: #2d3748; }}
  code {{ background: #0b0f19; padding: .2rem .4rem; border-radius: 6px; font-size: .9rem; color: #4fd1c5; }}
  .steps {{ margin-top: 1rem; padding-left: 1.2rem; }}
  .steps li {{ margin-bottom: .6rem; color: #a0aec0; }}
  .warn {{ color: #f6ad55; font-size: .9rem; margin-top: 1rem; }}
  .note {{ color: #a0aec0; font-size: .85rem; margin-top: .5rem; }}
  .option {{ border-top: 1px solid #1e293b; margin-top: 1.5rem; padding-top: 1rem; }}
  .option h3 {{ margin: 0 0 .5rem; font-size: 1.1rem; color: #e0e6f1; }}
</style>
</head>
<body>
<div class="card">
  <h1>🖥 Seven for macOS</h1>
  <p>One app. Chat, monitor nodes, and enrol your Mac — all in Seven.</p>

  <div class="option">
    <h3>Option 1 — One-Command Build (Fastest)</h3>
    <p>Copy this script to your Mac and run it. It downloads source, builds the DMG, and installs Seven automatically.</p>
    <a class="btn" href="{leader}/api/download/mac/build-script">⬇ Download build_mac.sh</a>
    <div class="note">Then run: <code>chmod +x build_mac.sh && ./build_mac.sh</code></div>
  </div>

  <div class="option">
    <h3>Option 2 — GitHub Actions (Zero Build)</h3>
    <p>Trigger a CI build on GitHub's macOS runners. The DMG is produced automatically and attached to a release.</p>
    <a class="btn btn-secondary" href="https://github.com/jeandregreyling/swarm/actions/workflows/build-seven-dmg.yml" target="_blank">Open GitHub Actions</a>
    <div class="note">Or push a tag: <code>git tag v1.0.0 && git push origin v1.0.0</code></div>
  </div>

  <div class="option">
    <h3>Option 3 — Manual Build</h3>
    <a class="btn btn-secondary" href="{leader}/api/download/mac/source">⬇ Download Source (desktop.tar.gz)</a>
    <ol class="steps">
      <li>Extract the source above.</li>
      <li>Install Rust: <code>curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh</code></li>
      <li>Install Tauri: <code>cargo install tauri-cli --version '^2'</code></li>
      <li>Build: <code>cd desktop/src-tauri && cargo tauri build</code></li>
      <li>Open the DMG and drag <strong>Seven.app</strong> → <strong>Applications</strong></li>
      <li>Right-click Seven → <strong>Open</strong> (Gatekeeper workaround).</li>
    </ol>
  </div>

  <p class="warn">⚠ First launch: right-click → Open. Do not double-click.</p>
</div>
</body>
</html>'''
    return Response(html, mimetype='text/html')


@mac_bp.get('/build-script')
def mac_build_script():
    """Serve the one-command Mac build script."""
    p = _DESKTOP_DIR / 'build_mac.sh'
    if not p.exists():
        return jsonify({'ok': False, 'error': 'build_mac.sh not found'}), 503
    return Response(
        p.read_text(),
        mimetype='text/x-shellscript',
        headers={
            'Content-Disposition': 'attachment; filename="build_mac.sh"',
            'Content-Length': str(p.stat().st_size),
        },
    )


@mac_bp.get('/source')
def mac_source_tarball():
    """Build and serve desktop/ source as a tar.gz for building on macOS."""
    if not _DESKTOP_DIR.is_dir():
        return jsonify({'ok': False, 'error': 'desktop/ not found'}), 503

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for path in sorted(_DESKTOP_DIR.rglob('*')):
            if '__pycache__' in path.parts:
                continue
            if path.suffix in {'.pyc', '.pyo'}:
                continue
            if path.name.startswith('.'):
                continue
            arcname = 'desktop/' + str(path.relative_to(_DESKTOP_DIR)).replace('\\', '/')
            tar.add(str(path), arcname=arcname, recursive=False)
    data = buf.getvalue()
    return Response(
        data,
        mimetype='application/gzip',
        headers={
            'Content-Disposition': 'attachment; filename="seven-desktop.tar.gz"',
            'Content-Length': str(len(data)),
        },
    )
