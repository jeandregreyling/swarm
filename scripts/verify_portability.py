"""Pre-push & Potato Farm (Dell OptiPlex) portability and secret-safety gatekeeper."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MUST_STAY_IGNORED = [
    'runtime/.hb_nectar_key',
    'utils/telegram_config.py',
    'config.py',
    '.env',
    'swarm_memory.db',
]


def run_checks() -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Verify sensitive paths are ignored by git
    if shutil.which('git') and (ROOT / '.git').exists():
        for rel in MUST_STAY_IGNORED:
            chk = subprocess.run(['git', 'check-ignore', '-q', rel], cwd=ROOT)
            if chk.returncode != 0:
                errors.append(f'Secret/local path is NOT gitignored: {rel}')
            tr = subprocess.run(['git', 'ls-files', '--error-unmatch', rel], cwd=ROOT, capture_output=True)
            if tr.returncode == 0:
                errors.append(f'Secret/local path is TRACKED in git: {rel}')

    # 2. Dynamic SWARM_ROOT check
    try:
        from utils.swarm_root import SWARM_ROOT
        if not Path(SWARM_ROOT).is_dir():
            errors.append(f'SWARM_ROOT does not exist: {SWARM_ROOT}')
    except Exception as exc:
        errors.append(f'utils.swarm_root import failed: {exc}')

    # 3. Core pillar blueprints import cleanly
    for mod in ('core.media_center.audio_engine', 'core.media_center.dsp_video', 'frontend.blueprints.media_center', 'frontend.blueprints.business_bp', 'frontend.blueprints.trading_bp'):
        try:
            __import__(mod)
        except Exception as exc:
            errors.append(f'Blueprint/module import failed ({mod}): {exc}')

    # 4. Toolchain visibility (non-fatal warnings for potato nodes)
    tools = {name: bool(shutil.which(name)) for name in ('python3', 'git', 'ffmpeg', 'ffprobe', 'node')}
    for name in ('ffmpeg', 'ffprobe'):
        if not tools[name]:
            warnings.append(f'Optional media binary missing on this node: {name}')

    return {
        'ok': len(errors) == 0,
        'root': str(ROOT),
        'tools': tools,
        'errors': errors,
        'warnings': warnings,
    }


def main() -> int:
    report = run_checks()
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
